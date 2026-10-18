#!/usr/bin/env python3
"""Collect the complete V5 B0 ±60 mm hardware block on XC330 ID5."""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import collect_m0 as base
import collect_g1 as documented_support
from dynamixel_io import DynamixelBus
from experiment_media import (
    ExperimentMediaCapture,
    MediaCaptureError,
    camera_only_status,
    episode_media_identity,
    validated_experiment_number,
    write_start_here,
)
from profiles import authoritative_active_profiles, executed_profiles, pilot_profile, profile_statistics


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "experiment_config_b0.json"
base.CONFIG_PATH = CONFIG_PATH


def cfg() -> dict[str, Any]:
    overlay = base.read_json(CONFIG_PATH)
    parent_name = overlay.get("extends")
    if parent_name is None:
        values = overlay
    else:
        values = copy.deepcopy(base.read_json(HERE / str(parent_name)))
        for key, value in overlay.items():
            if key != "extends":
                values[key] = copy.deepcopy(value)
    return values


# Shared hardware helpers must see the fully expanded configuration, including
# when this balanced-fixture runner is reused by collect_b2.py.
base.config = cfg


DOCUMENTED_CAMPAIGN_TOTAL_EPISODES = 60
MOTION_ROLES = {"pilot", "calibration", "model_selection", "held_out"}
CALIBRATION_PROFILE_ORDER = (
    "P01_slow_triangle",
    "P02_multisine",
    "P03_smooth_levels",
)
MODEL_SELECTION_PROFILE_ORDER = ("P04_chirp", "P05_wide_sine")
HELD_OUT_PROFILE_ORDER = ("P06_heldout_composite",)
H1_H2_THREE_REPEAT_ORDER = (
    ("R01", ("H1", "H2")),
    ("R02", ("H2", "H1")),
    ("R03", ("H1", "H2")),
)
H1_H2_FIVE_REPEAT_ORDER = (
    *H1_H2_THREE_REPEAT_ORDER,
    ("R04", ("H2", "H1")),
    ("R05", ("H1", "H2")),
)
FULL_BALANCED_THREE_REPEAT_ORDER = (
    ("R01", ("H1", "H2", "H3", "H4", "H5")),
    ("R02", ("H5", "H4", "H3", "H2", "H1")),
    ("R03", ("H3", "H1", "H5", "H2", "H4")),
)
EPISODE_FRAME_MAP_COLUMNS = [
    "video_frame_index",
    "video_time_s",
    "timeline_source",
    "target_source_timestamp_s",
    "source_frame_index",
    "iphone_timestamp_unix_s",
    "host_receive_timestamp_unix_s",
    "host_receive_monotonic_ns",
    "source_time_error_ms",
    "repeated_source_frame",
    "resized_for_video",
    "episode_display_code",
    "campaign_ordinal",
    "phase_event_index",
    "phase_label",
    "burned_in_label",
    "color_file",
]
KEYFRAME_COLUMNS = [
    "event_index",
    "label",
    "event_host_monotonic_ns",
    "source_frame_index",
    "source_host_monotonic_ns",
    "selection_delta_ms",
    "keyframe_file",
    "source_color_file",
]
CAMPAIGN_FRAME_MAP_COLUMNS = [
    "campaign_frame_index",
    "campaign_time_s",
    "campaign_session_order",
    "campaign_session_frame_index",
    "session_id",
    "session_title",
    "episode_display_code",
    "campaign_ordinal",
    "session_relative_directory",
    "episode_video",
    "episode_frame_map",
    "episode_video_frame_index",
    "episode_video_time_s",
    "timeline_source",
    "target_source_timestamp_s",
    "source_frame_index",
    "iphone_timestamp_unix_s",
    "host_receive_timestamp_unix_s",
    "host_receive_monotonic_ns",
    "source_time_error_ms",
    "repeated_source_frame",
    "resized_for_video",
    "resized_for_campaign",
    "campaign_letterbox_left_px",
    "campaign_letterbox_top_px",
    "phase_event_index",
    "phase_label",
    "burned_in_label",
    "source_color_file",
]
CHAPTER_COLUMNS = [
    "chapter_index",
    "campaign_start_frame",
    "campaign_end_frame_inclusive",
    "campaign_start_time_s",
    "campaign_end_time_s_exclusive",
    "session_id",
    "session_title",
    "episode_display_code",
    "campaign_ordinal",
    "episode_video_frame_count",
    "raw_capture_status",
]


def configuration_identity(values: dict[str, Any]) -> tuple[str, int, list[int], str]:
    label = str(values["mechanical_configuration"])
    stem = label.lower()
    if label == "M0":
        return label, 0, [], stem
    center_mm = int(values["fixture"]["absolute_payload_center_distance_mm"])
    centers = [-center_mm, center_mm]
    return label, center_mm, centers, stem


def m0_fixture_identity_is_exact(fixture: dict[str, Any]) -> bool:
    """Require a truthful motor-only M0 boundary with no invented centers."""

    return bool(
        fixture.get("type") == "motor-only, no external moving hardware"
        and fixture.get("fixture_revision")
        == "M0-motor-only-no-external-load"
        and fixture.get("external_horn_installed") is False
        and fixture.get("external_link_installed") is False
        and fixture.get("external_pin_installed") is False
        and fixture.get("external_payload_installed") is False
        and fixture.get("payload_center_positions_mm") == []
        and int(fixture.get("absolute_payload_center_distance_mm", -1)) == 0
        and int(fixture.get("complete_payload_mass_each_g", -1)) == 0
        and fixture.get("complete_payload_includes_pin") is False
        and int(fixture.get("payload_count", -1)) == 0
        and int(fixture.get("link_mass_g", -1)) == 0
        and int(fixture.get("total_external_moving_mass_g", -1)) == 0
        and float(fixture.get("external_gravity_moment_Nm", -1.0)) == 0.0
        and "no external moving hardware"
        in str(fixture.get("mass_property_status", "")).lower()
    )


def documented_fixture_identity_is_exact(
    label: str,
    fixture: dict[str, Any],
    expected_centers: list[int],
) -> bool:
    """Check the exact configuration-specific external hardware boundary."""

    if label == "M0":
        return m0_fixture_identity_is_exact(fixture)
    return bool(
        fixture.get("payload_center_positions_mm") == expected_centers
        and fixture.get("total_external_moving_mass_g") == 110
        and fixture.get("payload_print_infill_percent") == 50
        and fixture.get("fixture_revision")
        == "2026-08-26-recollection-110g"
        and fixture.get("complete_payload_mass_each_g") == 44
        and fixture.get("complete_payload_includes_pin") is True
        and fixture.get("payload_count") == 2
        and fixture.get("link_mass_g") == 22
    )


def documented_campaign_total(values: dict[str, Any] | None = None) -> int:
    """Return the configured retained media-session count."""

    active = cfg() if values is None else values
    total = int(
        active.get("iphone_media_capture", {}).get(
            "campaign_total_episodes", -1
        )
    )
    if total < 1:
        raise ValueError(
            "iphone_media_capture.campaign_total_episodes must be positive"
        )
    return total


def documented_campaign_role_counts(
    values: dict[str, Any],
) -> dict[str, int]:
    """Derive the exact role matrix without trusting declared totals."""

    profile_roles = {
        role: [
            profile_id
            for profile_id, spec in values["profiles"].items()
            if spec.get("split") == role
        ]
        for role in ("calibration", "model_selection", "held_out")
    }
    return {
        "pilot": len(values["pilot"]["controllers"]),
        "calibration": sum(
            len(order) * len(profile_roles["calibration"])
            for order in values.get("condition_order_by_repeat", {}).values()
        ),
        "model_selection": sum(
            len(order) * len(profile_roles["model_selection"])
            for order in values.get(
                "model_selection_condition_order_by_repeat", {}
            ).values()
        ),
        "held_out": sum(
            len(order) * len(profile_roles["held_out"])
            for order in values.get(
                "held_out_condition_order_by_repeat", {}
            ).values()
        ),
    }


def documented_campaign_enabled(values: dict[str, Any]) -> bool:
    """Select schema-2 capture without changing legacy M0/B0 entry points."""

    label = str(values.get("mechanical_configuration", ""))
    return label in {"B1", "B2"} or (
        label in {"M0", "B0"}
        and values.get("runner_mode") == "documented_media"
    )


def campaign_controller_ids(values: dict[str, Any]) -> list[str]:
    """Return the explicitly executable controller set for a campaign."""

    configured = values.get("campaign_controller_ids")
    if configured is None:
        configured = (
            ["H1", "H2"]
            if str(values.get("mechanical_configuration")) == "B1"
            else sorted(values["controllers"])
        )
    condition_ids = [str(item) for item in configured]
    if (
        not condition_ids
        or len(condition_ids) != len(set(condition_ids))
        or not set(condition_ids).issubset(values["controllers"])
    ):
        raise ValueError(
            "campaign_controller_ids must be unique configured controllers"
        )
    return condition_ids


def expected_campaign_role_counts(values: dict[str, Any]) -> dict[str, int]:
    """Return the independently declared role totals for validation."""

    declared = values.get("campaign_role_counts")
    if declared is None:
        declared = (
            {
                "pilot": 2,
                "calibration": 18,
                "model_selection": 0,
                "held_out": 10,
            }
            if str(values.get("mechanical_configuration")) == "B1"
            else {
                "pilot": 3,
                "calibration": 45,
                "model_selection": 12,
                "held_out": 0,
            }
        )
    return {role: int(declared.get(role, -1)) for role in MOTION_ROLES}


def write_report(name: str, value: Any) -> None:
    base.write_json(base.REPORT_ROOT / name, value)


def validate() -> dict[str, Any]:
    values = cfg()
    label, center_mm, expected_centers, stem = configuration_identity(values)
    dt_s = 1.0 / float(values["command_rate_hz"])
    active = authoritative_active_profiles(values)
    executed = executed_profiles(values)
    zero = int(values["servo_zero_raw"])
    minimum = int(values["software_goal_min_raw"])
    maximum = int(values["software_goal_max_raw"])
    documented_mode = documented_campaign_enabled(values)
    executable_conditions = campaign_controller_ids(values)
    expected_role_counts = expected_campaign_role_counts(values)
    observed_role_counts = documented_campaign_role_counts(values)
    uses_h1_h2_primary = label == "B1" or (
        label in {"M0", "B0"} and documented_mode
    )
    expected_primary_order = (
        H1_H2_THREE_REPEAT_ORDER
        if uses_h1_h2_primary
        else FULL_BALANCED_THREE_REPEAT_ORDER
    )
    expected_secondary_order = (
        H1_H2_FIVE_REPEAT_ORDER
        if label == "B1"
        else () if label == "M0"
        else H1_H2_THREE_REPEAT_ORDER
    )
    observed_primary_order = tuple(
        (str(repeat_id), tuple(str(item) for item in order))
        for repeat_id, order in values["condition_order_by_repeat"].items()
    )
    secondary_key = (
        "held_out_condition_order_by_repeat"
        if label == "B1"
        else "model_selection_condition_order_by_repeat"
    )
    observed_secondary_order = tuple(
        (str(repeat_id), tuple(str(item) for item in order))
        for repeat_id, order in values.get(secondary_key, {}).items()
    )
    observed_calibration_profile_order = tuple(
        name
        for name, item in values["profiles"].items()
        if item["split"] == "calibration"
    )
    observed_model_selection_profile_order = tuple(
        name
        for name, item in values["profiles"].items()
        if item["split"] == "model_selection"
    )
    observed_held_out_profile_order = tuple(
        name
        for name, item in values["profiles"].items()
        if item["split"] == "held_out"
    )
    vectors = {
        name: (
            int(item["position_p_gain_raw"]),
            int(item["position_i_gain_raw"]),
            int(item["position_d_gain_raw"]),
        )
        for name, item in values["controllers"].items()
    }
    goals = {
        name: zero
        + np.rint(profile.command_rad / base.POSITION_RAD_PER_TICK).astype(int)
        for name, profile in executed.items()
    }
    calibration_profiles = {
        name for name, item in values["profiles"].items() if item["split"] == "calibration"
    }
    model_selection_profiles = {
        name
        for name, item in values["profiles"].items()
        if item["split"] == "model_selection"
    }
    held_out_profiles = {
        name
        for name, item in values["profiles"].items()
        if item["split"] == "held_out"
    }
    fixture = values["fixture"]
    media = values.get("iphone_media_capture", {})
    media_python = Path(str(media.get("python_executable", "")))
    media_script = Path(str(media.get("service_script", "")))
    if media_script and not media_script.is_absolute():
        media_script = HERE / media_script
    checks = {
        f"scope_is_{label}": label in {"M0", "B0", "B1", "B2"},
        (
            "motor_only_M0_has_no_payload_centers"
            if label == "M0"
            else f"centers_are_minus_plus_{center_mm}mm"
        ): fixture["payload_center_positions_mm"] == expected_centers,
        "preliminary_inertia_not_claimed_measured": (
            label == "M0"
            or any(
                token in fixture["mass_property_status"].lower()
                for token in ("preliminary", "recompute", "measured masses")
            )
        ),
        (
            "motor_only_M0_has_no_payload_material_claim"
            if label == "M0"
            else "common_weight_50pct_infill_recorded"
        ): (
            (
                int(fixture.get("payload_count", -1)) == 0
                and int(fixture.get("complete_payload_mass_each_g", -1)) == 0
                and "payload_print_infill_percent" not in fixture
                and "payload_commonality" not in fixture
            )
            if label == "M0"
            else (
                fixture.get("payload_print_infill_percent") == 50
                and "same"
                in fixture.get("payload_commonality", "").lower()
            )
        ),
        "target_is_ID5": int(values["dynamixel_id"]) == 5,
        "software_gate_is_exactly_plus_minus_90deg": (minimum, maximum)
        == (1024, 3072),
        "condition_vectors_match_M0": vectors
        == {
            "H1": (600, 0, 150),
            "H2": (800, 0, 150),
            "H3": (600, 0, 220),
            "H4": (300, 0, 60),
            "H5": (1200, 0, 320),
        },
        "calibration_profiles_exact": calibration_profiles
        == {"P01_slow_triangle", "P02_multisine", "P03_smooth_levels"},
        "model_selection_profiles_exact": model_selection_profiles
        == (
            set()
            if label in {"M0", "B1"}
            else {"P04_chirp", "P05_wide_sine"}
        ),
        "held_out_profiles_exact": held_out_profiles
        == ({"P06_heldout_composite"} if label == "B1" else set()),
        "calibration_profile_sequence_is_exact": (
            observed_calibration_profile_order == CALIBRATION_PROFILE_ORDER
        ),
        "model_selection_profile_sequence_is_exact": (
            observed_model_selection_profile_order
            == (() if label in {"M0", "B1"} else MODEL_SELECTION_PROFILE_ORDER)
        ),
        "held_out_profile_sequence_is_exact": (
            observed_held_out_profile_order
            == (HELD_OUT_PROFILE_ORDER if label == "B1" else ())
        ),
        "active_sample_counts_exact": {
            name: int(command.size) for name, command in active.items()
        }
        == (
            {
                "P01_slow_triangle": 1201,
                "P02_multisine": 1201,
                "P03_smooth_levels": 755,
                "P06_heldout_composite": 1101,
            }
            if label == "B1"
            else {
                "P01_slow_triangle": 1201,
                "P02_multisine": 1201,
                "P03_smooth_levels": 755,
            }
            if label == "M0"
            else {
                "P01_slow_triangle": 1201,
                "P02_multisine": 1201,
                "P03_smooth_levels": 755,
                "P04_chirp": 1201,
                "P05_wide_sine": 1001,
            }
        ),
        "all_executed_profiles_start_and_end_at_zero": all(
            abs(float(profile.command_rad[0])) < 1e-12
            and abs(float(profile.command_rad[-1])) < 1e-12
            for profile in executed.values()
        ),
        "all_active_samples_unchanged": all(
            np.array_equal(
                profile.command_rad[
                    profile.active_start_index : profile.active_start_index
                    + profile.active_sample_count
                ],
                active[name],
            )
            for name, profile in executed.items()
        ),
        "all_goals_inside_software_gate": all(
            int(goal.min()) >= minimum and int(goal.max()) <= maximum
            for goal in goals.values()
        ),
        "calibration_repeats_complete_design": set(
            values["condition_order_by_repeat"]
        )
        == {"R01", "R02", "R03"}
        and all(
            sorted(order) == sorted(executable_conditions)
            for order in values["condition_order_by_repeat"].values()
        ),
        "secondary_design_is_exact": (
            set(values.get("held_out_condition_order_by_repeat", {}))
            == {"R01", "R02", "R03", "R04", "R05"}
            and all(
                sorted(order) == ["H1", "H2"]
                for order in values.get(
                    "held_out_condition_order_by_repeat", {}
                ).values()
            )
            if label == "B1"
            else (
                not values.get("model_selection_condition_order_by_repeat", {})
                and not values.get("held_out_condition_order_by_repeat", {})
            )
            if label == "M0"
            else set(
                values.get(
                    "model_selection_condition_order_by_repeat", {}
                )
            )
            == {"R01", "R02", "R03"}
            and all(
                sorted(order) == ["H1", "H2"]
                for order in values.get(
                    "model_selection_condition_order_by_repeat", {}
                ).values()
            )
        ),
        "calibration_repeat_condition_sequence_is_exact": (
            observed_primary_order == expected_primary_order
        ),
        "secondary_repeat_condition_sequence_is_exact": (
            observed_secondary_order == expected_secondary_order
        ),
        "pilot_design_is_exact": values["pilot"]["controllers"]
        == (
            executable_conditions
            if uses_h1_h2_primary
            else ["H1", "H4", "H5"]
        ),
        "no_torque_channel_claimed": values["measurement_boundary"][
            "torque_channel_available"
        ]
        is False,
        "prior_observations_excluded": values["data_policy"][
            "prior_zip_or_V4_observations_used"
        ]
        is False,
        "documented_campaign_role_counts_match_total": (
            sum(observed_role_counts.values())
            == documented_campaign_total(values)
            and observed_role_counts == expected_role_counts
        ),
    }
    if label == "M0":
        checks.update(
            {
                "motor_only_M0_fixture_identity_is_exact": m0_fixture_identity_is_exact(fixture),
                "documented_M0_runner_mode_is_explicit": (
                    values.get("runner_mode") == "documented_media"
                ),
                "documented_M0_collector_entrypoint_is_exact": (
                    values.get("collector_entrypoint")
                    == "collect_m0_h1_h2.py"
                ),
                "documented_M0_uses_only_H1_H2": executable_conditions
                == ["H1", "H2"],
                "documented_M0_has_no_secondary_orders": (
                    not values.get("model_selection_condition_order_by_repeat", {})
                    and not values.get("held_out_condition_order_by_repeat", {})
                ),
                "documented_M0_model_selection_exclusion_is_explicit": (
                    "excluded from the design-contract model-selection block"
                    in values["data_policy"].get("model_selection_policy", "")
                    and "P04 and P05 must not be collected"
                    in values["data_policy"].get("model_selection_policy", "")
                    and "P06 is not an M0 profile"
                    in values["data_policy"].get("model_selection_policy", "")
                ),
                "M0_uses_standard_tick_2048_zero_not_gravity_start": (
                    zero == 2048
                    and values.get("gravity_loaded_active_zero_start") is not True
                ),
                "experiment_number_policy_is_Dubai_YYMMDD_HHMMSS": (
                    media.get("experiment_number_format") == "YYMMDD-HHMMSS"
                    and media.get("experiment_number_timezone") == "Asia/Dubai"
                ),
                "read_only_U2D2_latency_gate_is_configured_at_1ms": int(
                    values.get(
                        "operator_declared_u2d2_usb_latency_timer_ms",
                        -1,
                    )
                )
                == 1,
                "iPhone_camera_is_required_before_motion": (
                    media.get("enabled_for_run") is True
                    and media.get("required_before_motion") is True
                    and media.get("required_asmagic_sdk_version") == "0.1.4"
                    and media.get("save_depth") is True
                ),
                "camera_runtime_dependencies_exist": (
                    media_python.is_file()
                    and os.access(media_python, os.X_OK)
                    and media_script.is_file()
                ),
                "native_paired_640x480_videos_are_required": (
                    int(media.get("native_video_width_px", 0)) == 640
                    and int(media.get("native_video_height_px", 0)) == 480
                    and media.get("paired_labeled_unlabeled_video_required")
                    is True
                    and media.get("audio_available") is False
                    and documented_campaign_total(values) == 20
                ),
            }
        )
    elif label == "B0":
        checks.update(
            {
                "PDF_50mm_value_explicitly_superseded": fixture[
                    "pdf_preliminary_center_positions_mm_superseded"
                ]
                == [-50, 50],
                "old_preliminary_inertia_not_reused": "recompute"
                in fixture["mass_property_status"],
                "recollection_fixture_mass_declaration_exact": fixture.get(
                    "fixture_revision"
                )
                == "2026-08-26-recollection-110g"
                and int(fixture.get("complete_payload_mass_each_g", -1)) == 44
                and fixture.get("complete_payload_includes_pin") is True
                and int(fixture.get("payload_count", -1)) == 2
                and int(fixture.get("link_mass_g", -1)) == 22
                and int(fixture.get("total_external_moving_mass_g", -1)) == 110,
                "documented_B0_runner_mode_is_explicit": (
                    not documented_mode
                    or values.get("runner_mode") == "documented_media"
                ),
                "documented_B0_collector_entrypoint_is_exact": (
                    not documented_mode
                    or values.get("collector_entrypoint")
                    == "collect_b0_h1_h2.py"
                ),
                "documented_B0_uses_only_H1_H2": (
                    not documented_mode
                    or executable_conditions == ["H1", "H2"]
                ),
                "documented_B0_model_selection_policy_is_explicit": (
                    not documented_mode
                    or "must not influence calibration fitting"
                    in values["data_policy"].get("model_selection_policy", "")
                ),
                "experiment_number_policy_is_Dubai_YYMMDD_HHMMSS": (
                    media.get("experiment_number_format") == "YYMMDD-HHMMSS"
                    and media.get("experiment_number_timezone")
                    == "Asia/Dubai"
                ),
                "read_only_U2D2_latency_gate_is_configured_at_1ms": int(
                    values.get(
                        "operator_declared_u2d2_usb_latency_timer_ms", -1
                    )
                )
                == 1,
                "iPhone_camera_is_required_before_motion": (
                    media.get("enabled_for_run") is True
                    and media.get("required_before_motion") is True
                    and media.get("required_asmagic_sdk_version") == "0.1.4"
                    and media.get("save_depth") is True
                ),
                "camera_runtime_dependencies_exist": (
                    media_python.is_file()
                    and os.access(media_python, os.X_OK)
                    and media_script.is_file()
                ),
                "native_paired_640x480_videos_are_required": (
                    int(media.get("native_video_width_px", 0)) == 640
                    and int(media.get("native_video_height_px", 0)) == 480
                    and media.get(
                        "paired_labeled_unlabeled_video_required"
                    )
                    is True
                    and media.get("audio_available") is False
                    and documented_campaign_total(values)
                    == (32 if documented_mode else 60)
                ),
            }
        )
    elif label == "B1":
        checks.update(
            {
                "PDF_preliminary_B1_inertia_recorded": abs(
                    float(fixture["pdf_preliminary_inertia_kg_m2"])
                    - 0.00075
                )
                < 1e-12,
                "recollection_fixture_mass_declaration_exact": fixture.get(
                    "fixture_revision"
                )
                == "2026-08-26-recollection-110g"
                and int(fixture.get("complete_payload_mass_each_g", -1)) == 44
                and fixture.get("complete_payload_includes_pin") is True
                and int(fixture.get("payload_count", -1)) == 2
                and int(fixture.get("link_mass_g", -1)) == 22
                and int(fixture.get("total_external_moving_mass_g", -1)) == 110,
                "held_out_policy_is_explicit": "must not influence"
                in values["data_policy"]["held_out_policy"],
                "experiment_number_policy_is_Dubai_YYMMDD_HHMMSS": (
                    media.get("experiment_number_format") == "YYMMDD-HHMMSS"
                    and media.get("experiment_number_timezone")
                    == "Asia/Dubai"
                ),
                "read_only_U2D2_latency_gate_is_configured_at_1ms": int(
                    values.get(
                        "operator_declared_u2d2_usb_latency_timer_ms", -1
                    )
                )
                == 1,
                "iPhone_camera_is_required_before_motion": (
                    media.get("enabled_for_run") is True
                    and media.get("required_before_motion") is True
                    and media.get("required_asmagic_sdk_version") == "0.1.4"
                    and media.get("save_depth") is True
                ),
                "camera_runtime_dependencies_exist": (
                    media_python.is_file()
                    and os.access(media_python, os.X_OK)
                    and media_script.is_file()
                ),
                "native_paired_640x480_videos_are_required": (
                    int(media.get("native_video_width_px", 0)) == 640
                    and int(media.get("native_video_height_px", 0)) == 480
                    and media.get(
                        "paired_labeled_unlabeled_video_required"
                    )
                    is True
                    and media.get("audio_available") is False
                    and documented_campaign_total(values) == 30
                ),
            }
        )
    elif label == "B2":
        checks.update(
            {
                "PDF_preliminary_B2_inertia_recorded": abs(
                    float(fixture["pdf_preliminary_inertia_kg_m2"]) - 0.00150
                )
                < 1e-12,
                "recollection_fixture_mass_declaration_exact": fixture.get(
                    "fixture_revision"
                )
                == "2026-08-26-recollection-110g"
                and int(fixture.get("complete_payload_mass_each_g", -1)) == 44
                and fixture.get("complete_payload_includes_pin") is True
                and int(fixture.get("payload_count", -1)) == 2
                and int(fixture.get("link_mass_g", -1)) == 22
                and int(fixture.get("total_external_moving_mass_g", -1)) == 110,
                "experiment_number_policy_is_Dubai_YYMMDD_HHMMSS": (
                    media.get("experiment_number_format") == "YYMMDD-HHMMSS"
                    and media.get("experiment_number_timezone") == "Asia/Dubai"
                ),
                "read_only_U2D2_latency_gate_is_configured_at_1ms": int(
                    values.get(
                        "operator_declared_u2d2_usb_latency_timer_ms", -1
                    )
                )
                == 1,
                "iPhone_camera_is_required_before_motion": (
                    media.get("enabled_for_run") is True
                    and media.get("required_before_motion") is True
                    and media.get("required_asmagic_sdk_version") == "0.1.4"
                    and media.get("save_depth") is True
                ),
                "camera_runtime_dependencies_exist": (
                    media_python.is_file()
                    and os.access(media_python, os.X_OK)
                    and media_script.is_file()
                ),
                "native_paired_640x480_videos_are_required": (
                    int(media.get("native_video_width_px", 0)) == 640
                    and int(media.get("native_video_height_px", 0)) == 480
                    and media.get(
                        "paired_labeled_unlabeled_video_required"
                    )
                    is True
                    and media.get("audio_available") is False
                ),
            }
        )
    report = {
        "experiment_id": values["experiment_id"],
        "fixture": fixture,
        "checks": checks,
        "profile_statistics": {
            name: profile_statistics(profile, dt_s)
            for name, profile in executed.items()
        },
        "passed": all(checks.values()),
    }
    write_report(f"{stem}_validation.json", report)
    return report


def status() -> dict[str, Any]:
    offline = validate()
    available = base.availability()
    if not offline["passed"] or not available["available"]:
        result = {
            "offline_validation": offline,
            "availability": available,
            "passed": False,
            "motion_executed": False,
        }
    else:
        with base.hardware_lock():
            values = cfg()
            bus = DynamixelBus(
                str(values["serial_port"]), int(values["baud_rate_bps"])
            )
            try:
                result = base.read_only_status_on_open_bus(bus)
            finally:
                bus.close()
        result["fixture_declaration"] = values["fixture"]
        result["offline_validation_passed"] = True
        result["availability_before_open"] = available
    stem = str(cfg()["mechanical_configuration"]).lower()
    write_report(f"{stem}_live_status.json", result)
    return result


def write_method_results(run_root: Path, summary: pd.DataFrame) -> None:
    values = cfg()
    label, center_mm, _, _ = configuration_identity(values)
    fixture = values["fixture"]
    summary = summary.copy()

    def role_rows(role: str) -> pd.DataFrame:
        if "role" not in summary.columns:
            return summary.iloc[0:0].copy()
        return summary[summary["role"] == role].copy()

    def complete_count(role: str) -> int:
        rows = role_rows(role)
        if "completion_status" not in rows.columns:
            return 0
        return int(rows["completion_status"].eq("complete").sum())

    def formatted_extreme(
        column: str,
        *,
        reduction: str,
        digits: int,
        suffix: str,
    ) -> str:
        if column not in summary.columns:
            return "not available"
        numeric = pd.to_numeric(summary[column], errors="coerce").dropna()
        if numeric.empty:
            return "not available"
        value = (
            float(numeric.max())
            if reduction == "max"
            else float(numeric.min())
        )
        return f"{value:.{digits}f}{suffix}"

    def append_tracking_rows(
        lines: list[str], rows: pd.DataFrame
    ) -> None:
        required = {
            "controller_id",
            "tracking_rmse_rad_active",
            "tracking_peak_abs_rad_active",
        }
        if rows.empty or not required.issubset(rows.columns):
            lines.append("| — | 0 | not available | not available | not available |")
            return
        for condition, group in rows.groupby(
            "controller_id", sort=True
        ):
            rmse = pd.to_numeric(
                group["tracking_rmse_rad_active"], errors="coerce"
            ).dropna()
            peak = pd.to_numeric(
                group["tracking_peak_abs_rad_active"], errors="coerce"
            ).dropna()

            def show(value: float | None) -> str:
                return (
                    "not available"
                    if value is None or not np.isfinite(value)
                    else f"{value:.9f}"
                )

            lines.append(
                f"| {condition} | {len(group)} | "
                f"{show(float(rmse.mean()) if len(rmse) else None)} | "
                f"{show(float(rmse.std(ddof=1)) if len(rmse) > 1 else None)} | "
                f"{show(float(peak.max()) if len(peak) else None)} |"
            )

    calibration = role_rows("calibration")
    selection = role_rows("model_selection")
    held_out = role_rows("held_out")
    role_counts = documented_campaign_role_counts(values)
    lines = [
        (
            "# V5 M0 motor-only hardware collection: method and results"
            if label == "M0"
            else f"# V5 {label} ±{center_mm} mm hardware collection: method and results"
        ),
        "",
        f"Run: `{run_root.name}`",
        "",
        "## Physical fixture",
        "",
        (
            "M0 was physically configured as **motor-only** with no external horn, link, pin, "
            "or payload: **0 g external moving mass**, no payload centers, and exactly zero "
            "external-load gravity moment. No external payload inertia is applicable."
            if label == "M0"
            else "B0 was physically configured with equal payload centers at **−60 mm and +60 mm**. "
            "This user-confirmed value supersedes the PDF's preliminary ±50 mm declaration. "
            "For this recollection, each complete payload is **44 g including its pin**, and the "
            "link is **22 g**, giving **110 g total external moving mass**. The PDF's preliminary "
            "`0.00025 kg·m²` inertia is not reused. Payload point inertia is calculated from "
            "the measured payload masses; link rotational inertia still requires link geometry."
            if label == "B0"
            else f"{label} was physically configured with equal payload centers at **−{center_mm} mm "
            f"and +{center_mm} mm**. For this recollection, each complete payload is **44 g "
            "including its pin**, and the link is **22 g**, giving **110 g total external "
            "moving mass**. The PDF's "
            f"`{float(fixture['pdf_preliminary_inertia_kg_m2']):.5f} kg·m²` value remains a "
            "preliminary design value and is not reused; link rotational inertia still "
            "requires link geometry."
        ),
        "",
        "## Episode design",
        "",
        *(
            [
                "- Total retained M0 motion-and-media sessions: 20.",
                "- Calibration: P01–P03 × H1/H2 × three repeats = 18 episodes.",
                "- Safety pilots: H1 and H2 = 2 episodes.",
                "- Model-selection and held-out profiles are excluded from M0 by design.",
            ]
            if label == "M0"
            else
            [
                "- Calibration: P01–P03 × H1/H2 × three repeats = 18 episodes.",
                "- Untouched held out: P06 × H1/H2 × five repeats = 10 episodes.",
                "- Safety pilots: H1 and H2 = 2 episodes.",
                "- P06 remains frozen and must not influence fitting, bounds, timing/filter choices, or model selection.",
            ]
            if label == "B1"
            else [
                "- Calibration: P01–P03 × H1/H2 × three repeats = 18 episodes.",
                "- Model selection: P04–P05 × H1/H2 × three repeats = 12 episodes.",
                "- Safety pilots: H1 and H2 = 2 episodes.",
                "- P04/P05 remain model-selection data and must not influence calibration fitting.",
            ]
            if label == "B0" and documented_campaign_enabled(values)
            else [
                "- Calibration: P01–P03 × H1–H5 × three repeats = 45 episodes.",
                "- Model selection: P04–P05 × H1/H2 × three repeats = 12 episodes.",
                "- Safety pilots: H1, H4, and H5 = 3 episodes.",
            ]
        ),
        "- Every episode began at raw tick 2048 within ±5 ticks and used the 1024–3072 software goal gate.",
        "",
        "## Collection outcome",
        "",
        f"- Retained episode rows: {len(summary)}.",
        f"- Complete calibration episodes: {complete_count('calibration')} / {role_counts['calibration']}.",
        f"- Complete model-selection episodes: {complete_count('model_selection')} / {role_counts['model_selection']}.",
        f"- Complete held-out episodes: {complete_count('held_out')} / {role_counts['held_out']}.",
        f"- Complete pilot episodes: {complete_count('pilot')} / {role_counts['pilot']}.",
        "- Maximum input-supply current: "
        + formatted_extreme(
            "maximum_abs_current_A",
            reduction="max",
            digits=6,
            suffix=" A",
        )
        + ".",
        "- Maximum PWM fraction: "
        + formatted_extreme(
            "maximum_abs_pwm_fraction",
            reduction="max",
            digits=6,
            suffix="",
        )
        + ".",
        "- Maximum temperature: "
        + formatted_extreme(
            "maximum_temperature_C",
            reduction="max",
            digits=1,
            suffix=" °C",
        )
        + ".",
        "- Minimum voltage: "
        + formatted_extreme(
            "minimum_voltage_V",
            reduction="min",
            digits=1,
            suffix=" V",
        )
        + ".",
        "",
        "### Calibration tracking",
        "",
        "| H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |",
        "|---|---:|---:|---:|---:|",
    ]
    append_tracking_rows(lines, calibration)
    if label == "M0":
        lines.extend(
            [
                "",
                "### Excluded secondary profiles",
                "",
                "M0 contains no P04/P05 model-selection or P06 held-out episodes by design.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                (
                    "### Frozen held-out tracking"
                    if label == "B1"
                    else "### Model-selection tracking"
                ),
                "",
                "| H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        append_tracking_rows(lines, held_out if label == "B1" else selection)
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            (
                "Present Current remains XC330 input-supply-current telemetry, not output torque. No MuJoCo joint parameters or equivalent gains are identified during this collection step. No P04/P05 model-selection or P06 held-out episodes are collected for M0."
                if label == "M0"
                else "Present Current remains XC330 input-supply-current telemetry, not output torque. No MuJoCo joint parameters or equivalent gains are identified during this collection step. Held-out P06 episodes must not be used as calibration or model-selection data."
                if label == "B1"
                else "Present Current remains XC330 input-supply-current telemetry, not output torque. No MuJoCo joint parameters or equivalent gains are identified during this collection step. Model-selection episodes must not be used as calibration data."
            ),
            "",
            (
                "The campaign stops after B0. Do not change the B0 record to ±50 mm when the documentation is revised."
                if label == "B0"
                else f"The campaign stops after {label}."
            ),
        ]
    )
    (run_root / f"{label}_METHOD_AND_RESULTS.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def verify_legacy_run(run_root: Path) -> dict[str, Any]:
    values = cfg()
    label, center_mm, expected_centers, _ = configuration_identity(values)
    run_manifest = base.read_json(run_root / "run.json")
    inventory_lines = [
        line.split("  ", 1)
        for line in (run_root / "inventory.sha256")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    hash_failures = [
        relative
        for expected, relative in inventory_lines
        if not (run_root / relative).is_file()
        or base.sha256_file(run_root / relative) != expected
    ]
    manifests = [
        base.read_json(path)
        for path in sorted((run_root / "episodes").glob("*/episode.json"))
    ]
    calibration = [item for item in manifests if item["role"] == "calibration"]
    selection = [item for item in manifests if item["role"] == "model_selection"]
    pilots = [item for item in manifests if item["role"] == "pilot"]
    expected_calibration = {
        f"{label}__{condition}__{profile}__{repeat}"
        for repeat in ("R01", "R02", "R03")
        for profile in ("P01_slow_triangle", "P02_multisine", "P03_smooth_levels")
        for condition in values["controllers"]
    }
    expected_selection = {
        f"{label}__{condition}__{profile}__{repeat}"
        for repeat in ("R01", "R02", "R03")
        for profile in ("P04_chirp", "P05_wide_sine")
        for condition in ("H1", "H2")
    }
    episode_data_checks: list[bool] = []
    torque_measurement_columns: list[str] = []
    for manifest in manifests:
        episode_root = run_root / "episodes" / manifest["episode_id"]
        command = pd.read_parquet(episode_root / "command_events.parquet")
        telemetry = pd.read_parquet(episode_root / "telemetry_events.parquet")
        torque_measurement_columns.extend(
            column
            for column in [*command.columns, *telemetry.columns]
            if "torque" in column.lower() and "torque_enable" not in column.lower()
        )
        first_goal = int(command.iloc[0]["goal_position_raw_requested"])
        episode_data_checks.append(
            bool(
                len(command)
                and len(telemetry)
                and command["goal_position_raw_requested"].between(1024, 3072).all()
                and telemetry["present_position_raw"].between(1024, 3072).all()
                and (manifest["role"] == "preparation" or first_goal == 2048)
                and telemetry["hardware_error_status_raw"].eq(0).all()
                and manifest["mechanical_configuration"] == label
                and manifest["fixture"]["payload_center_positions_mm"] == expected_centers
            )
        )
    checks = {
        "run_complete": run_manifest["terminal_status"] == "complete",
        "exact_45_calibration": len(calibration) == 45,
        "calibration_matrix_exact": {item["episode_id"] for item in calibration}
        == expected_calibration,
        "exact_12_model_selection": len(selection) == 12,
        "model_selection_matrix_exact": {item["episode_id"] for item in selection}
        == expected_selection,
        "exact_3_pilots": len(pilots) == 3,
        "all_manifests_complete": all(
            item["completion_status"] == "complete" for item in manifests
        ),
        "all_terminal_torque_disabled": all(
            item["terminal_torque_disabled"] for item in manifests
        ),
        "all_registers_stable": all(
            item["critical_registers_match_before_after"] for item in manifests
        ),
        "all_episode_data_checks": all(episode_data_checks),
        f"all_episode_manifests_record_{center_mm}mm": all(
            item.get("fixture", {}).get("payload_center_positions_mm") == expected_centers
            and (
                label != "B2"
                or item.get("fixture", {}).get("payload_print_infill_percent") == 50
            )
            for item in manifests
        ),
        "run_and_episode_manifests_record_exact_recollection_mass": (
            run_manifest.get("fixture", {}).get("fixture_revision")
            != "2026-08-26-recollection-110g"
        )
        or (
            run_manifest.get("fixture", {}).get("fixture_revision")
            == "2026-08-26-recollection-110g"
            and int(
                run_manifest.get("fixture", {}).get(
                    "complete_payload_mass_each_g", -1
                )
            )
            == 44
            and run_manifest.get("fixture", {}).get(
                "complete_payload_includes_pin"
            )
            is True
            and int(run_manifest.get("fixture", {}).get("link_mass_g", -1)) == 22
            and int(
                run_manifest.get("fixture", {}).get(
                    "total_external_moving_mass_g", -1
                )
            )
            == 110
            and all(
                item.get("fixture", {}).get("fixture_revision")
                == "2026-08-26-recollection-110g"
                and int(
                    item.get("fixture", {}).get(
                        "complete_payload_mass_each_g", -1
                    )
                )
                == 44
                and item.get("fixture", {}).get("complete_payload_includes_pin")
                is True
                and int(item.get("fixture", {}).get("link_mass_g", -1)) == 22
                and int(
                    item.get("fixture", {}).get(
                        "total_external_moving_mass_g", -1
                    )
                )
                == 110
                for item in manifests
            )
        ),
        "no_manufactured_torque_column": not torque_measurement_columns,
        "inventory_hashes_match": not hash_failures,
        "summary_exists": (run_root / "episode-summary.csv").is_file(),
        "method_results_exists": (run_root / f"{label}_METHOD_AND_RESULTS.md").is_file(),
    }
    return {
        "run_root": str(run_root),
        "checks": checks,
        "episode_manifest_count": len(manifests),
        "calibration_episode_count": len(calibration),
        "model_selection_episode_count": len(selection),
        "pilot_episode_count": len(pilots),
        "inventory_entry_count": len(inventory_lines),
        "inventory_hash_failures": hash_failures,
        "torque_measurement_columns": sorted(set(torque_measurement_columns)),
        "passed": all(checks.values()),
    }


def run_legacy() -> dict[str, Any]:
    offline = validate()
    if not offline["passed"]:
        return {"status": "blocked_by_offline_validation", "passed": False, "motion_executed": False}
    available = base.availability()
    if not available["available"]:
        return {"status": "blocked_device_absent_or_owned", "availability": available, "passed": False, "motion_executed": False}
    values = cfg()
    label, center_mm, _, stem = configuration_identity(values)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = base.RAW_ROOT / f"v5-{stem}-{center_mm}mm-{timestamp}-{uuid.uuid4().hex[:8]}"
    run_root.mkdir(parents=True, exist_ok=False)
    manifests: list[dict[str, Any]] = []
    campaign_error: str | None = None
    terminal_torque_disabled = False
    with base.hardware_lock():
        if not base.availability()["available"]:
            raise RuntimeError("serial device became owned before campaign open")
        bus = DynamixelBus(str(values["serial_port"]), int(values["baud_rate_bps"]))
        try:
            discovered = bus.discover()
            base.disable_discovered(bus, discovered)
            if set(discovered) != {5} or discovered[5]["model_number"] != int(values["expected_model_number"]):
                raise RuntimeError(f"exact ID5/model identity gate failed: {discovered}")
            canonicalization = base.canonicalize_torque_off_position_counter(bus)
            base.write_json(run_root / "position-counter-canonicalization.json", canonicalization)
            live = base.read_only_status_on_open_bus(bus)
            live["fixture_declaration"] = values["fixture"]
            base.write_json(run_root / "live-preflight.json", live)
            if not live["passed"]:
                raise RuntimeError(f"live preflight failed: {live['checks']}")
            recenter_index = base.ensure_zero(bus, run_root, 1, manifests)

            pilot = pilot_profile(values)
            for condition in values["pilot"]["controllers"]:
                recenter_index = base.ensure_zero(bus, run_root, recenter_index, manifests)
                episode_id = f"{label}__{condition}__PILOT_LOW_AMPLITUDE"
                print(f"PILOT {episode_id}", flush=True)
                manifest = base.run_episode(bus, run_root, episode_id, condition, pilot, "pilot", None, True)
                manifests.append(manifest)
                print(f"RESULT {episode_id}: {manifest['completion_status']}", flush=True)
                if manifest["completion_status"] != "complete":
                    raise RuntimeError(f"pilot failed: {manifest['failures']}")

            generated = executed_profiles(values)
            calibration_profiles = {
                name: profile for name, profile in generated.items() if values["profiles"][name]["split"] == "calibration"
            }
            selection_profiles = {
                name: profile for name, profile in generated.items() if values["profiles"][name]["split"] == "model_selection"
            }
            completed = 0
            for repeat, order in values["condition_order_by_repeat"].items():
                for profile_id, profile in calibration_profiles.items():
                    for condition in order:
                        recenter_index = base.ensure_zero(bus, run_root, recenter_index, manifests)
                        completed += 1
                        episode_id = f"{label}__{condition}__{profile_id}__{repeat}"
                        print(f"CALIBRATION {completed:02d}/45: {episode_id}", flush=True)
                        manifest = base.run_episode(bus, run_root, episode_id, condition, profile, "calibration", repeat, True)
                        manifests.append(manifest)
                        print(f"RESULT {episode_id}: {manifest['completion_status']}", flush=True)
                        if manifest["completion_status"] != "complete":
                            raise RuntimeError(f"calibration failed: {manifest['failures']}")

            completed = 0
            for repeat, order in values["model_selection_condition_order_by_repeat"].items():
                for profile_id, profile in selection_profiles.items():
                    for condition in order:
                        recenter_index = base.ensure_zero(bus, run_root, recenter_index, manifests)
                        completed += 1
                        episode_id = f"{label}__{condition}__{profile_id}__{repeat}"
                        print(f"MODEL_SELECTION {completed:02d}/12: {episode_id}", flush=True)
                        manifest = base.run_episode(bus, run_root, episode_id, condition, profile, "model_selection", repeat, True)
                        manifests.append(manifest)
                        print(f"RESULT {episode_id}: {manifest['completion_status']}", flush=True)
                        if manifest["completion_status"] != "complete":
                            raise RuntimeError(f"model-selection failed: {manifest['failures']}")
        except (KeyboardInterrupt, RuntimeError, OSError) as exc:
            campaign_error = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                bus.torque_disable(5)
                terminal_torque_disabled = True
            except RuntimeError as exc:
                campaign_error = f"{campaign_error}; terminal cleanup: {exc}" if campaign_error else f"terminal cleanup: {exc}"
            bus.close()

    calibration = [item for item in manifests if item["role"] == "calibration"]
    selection = [item for item in manifests if item["role"] == "model_selection"]
    pilots = [item for item in manifests if item["role"] == "pilot"]
    terminal_status = "complete" if (
        campaign_error is None
        and len(calibration) == 45
        and len(selection) == 12
        and len(pilots) == 3
        and all(item["completion_status"] == "complete" for item in manifests)
        and terminal_torque_disabled
    ) else "incomplete"
    run_manifest = {
        "schema_version": 1,
        "experiment_id": values["experiment_id"],
        "run_id": run_root.name,
        "mechanical_configuration": label,
        "fixture": values["fixture"],
        "dynamixel_id": 5,
        "source_type": "new_V5_physical_hardware_measurement",
        "start_utc": timestamp,
        "end_utc": datetime.now(UTC).isoformat(),
        "host_platform": platform.platform(),
        "episode_ids": [item["episode_id"] for item in manifests],
        "calibration_episode_count": len(calibration),
        "model_selection_episode_count": len(selection),
        "pilot_episode_count": len(pilots),
        "preparation_episode_count": sum(item["role"] == "preparation" for item in manifests),
        "campaign_error": campaign_error,
        "terminal_torque_disabled": terminal_torque_disabled,
        "terminal_status": terminal_status,
        f"stopped_after_{label}": True,
    }
    base.write_json(run_root / "run.json", run_manifest)
    summary = base.summarize_run(run_root, manifests)
    write_method_results(run_root, summary)
    (run_root / "COMMAND_LOG.md").write_text(
        "# Command log\n\n"
        f"- `{datetime.now(UTC).isoformat()}`: `collect_{stem}.py --run`\n"
        f"- Fixture: {label} with payload centers at `-{center_mm} mm` and `+{center_mm} mm`.\n"
        "- Payload declaration: common V5 3D-printed weight design at `50%` infill.\n"
        + (
            "- Recollection fixture revision: two complete `44 g` payloads including pins, "
            "one `22 g` link, `110 g` total external moving mass.\n"
            if label in {"B0", "B2"}
            else ""
        )
        + f"- Result: `{terminal_status}`.\n"
        f"- Campaign error: `{campaign_error}`.\n"
        f"- Calibration: `{len(calibration)}/45`; model selection: `{len(selection)}/12`; pilots: `{len(pilots)}/3`.\n"
        f"- Terminal torque disabled: `{terminal_torque_disabled}`.\n",
        encoding="utf-8",
    )
    inventory_digest = base.write_inventory(run_root)
    verification = verify_run(run_root)
    write_report(f"{stem}_last_verification.json", verification)
    result = {
        "run_root": str(run_root),
        "terminal_status": terminal_status,
        "calibration_episode_count": len(calibration),
        "model_selection_episode_count": len(selection),
        "pilot_episode_count": len(pilots),
        "preparation_episode_count": sum(item["role"] == "preparation" for item in manifests),
        "campaign_error": campaign_error,
        "terminal_torque_disabled": terminal_torque_disabled,
        "inventory_sha256": inventory_digest,
        "verification": verification,
        "motion_executed": bool(manifests),
        "passed": terminal_status == "complete" and verification["passed"],
    }
    write_report(f"{stem}_last_run.json", result)
    return result


def finalize_existing(run_root: Path) -> dict[str, Any]:
    """Finish summaries and hashes after motion completed but post-processing stopped."""

    run_root = run_root.resolve()
    run_manifest = base.read_json(run_root / "run.json")
    values = cfg()
    label, _, _, stem = configuration_identity(values)
    if run_manifest.get("terminal_status") != "complete":
        raise RuntimeError("refusing to finalize an incomplete physical run")
    manifests = [
        base.read_json(path)
        for path in sorted((run_root / "episodes").glob("*/episode.json"))
    ]
    calibration = [item for item in manifests if item["role"] == "calibration"]
    selection = [item for item in manifests if item["role"] == "model_selection"]
    pilots = [item for item in manifests if item["role"] == "pilot"]
    if (len(calibration), len(selection), len(pilots)) != (45, 12, 3):
        raise RuntimeError(
            "raw physical matrix is not complete: "
            f"calibration={len(calibration)}, model_selection={len(selection)}, "
            f"pilots={len(pilots)}"
        )
    if not all(
        item["completion_status"] == "complete"
        and item["terminal_torque_disabled"]
        for item in manifests
    ):
        raise RuntimeError("an episode is incomplete or lacks torque-off confirmation")
    summary = base.summarize_run(run_root, manifests)
    write_method_results(run_root, summary)
    (run_root / "COMMAND_LOG.md").write_text(
        "# Command log\n\n"
        f"- `collect_{stem}.py --run`: all physical motion completed: 45/45 "
        "calibration, 12/12 model selection, and 3/3 pilots.\n"
        "- Hardware cleanup had already torque-disabled ID5 before post-processing.\n"
        f"- `collect_{stem}.py --finalize`: regenerated "
        "the summary, method/results document, inventory, and verification without "
        "executing motion.\n",
        encoding="utf-8",
    )
    inventory_digest = base.write_inventory(run_root)
    verification = verify_run(run_root)
    write_report(f"{stem}_last_verification.json", verification)
    result = {
        "run_root": str(run_root),
        "terminal_status": run_manifest["terminal_status"],
        "calibration_episode_count": len(calibration),
        "model_selection_episode_count": len(selection),
        "pilot_episode_count": len(pilots),
        "preparation_episode_count": sum(
            item["role"] == "preparation" for item in manifests
        ),
        "terminal_torque_disabled": run_manifest["terminal_torque_disabled"],
        "inventory_sha256": inventory_digest,
        "verification": verification,
        "motion_executed_during_finalize": False,
        "passed": verification["passed"],
    }
    write_report(f"{stem}_last_run.json", result)
    return result


def host_timing_preflight(
    values: dict[str, Any],
    *,
    sys_class_tty_root: Path = Path("/sys/class/tty"),
) -> dict[str, Any]:
    """Read and enforce the FTDI latency timer before camera or motor access."""

    return documented_support.host_timing_preflight(
        values, sys_class_tty_root=sys_class_tty_root
    )


def iphone_camera_status() -> dict[str, Any]:
    """Require a fresh asMagic 0.1.4 AR frame without opening the motor."""

    offline = validate()
    _, _, _, stem = configuration_identity(cfg())
    if not offline["passed"]:
        result = {
            "operation": "iphone_camera_status_only",
            "offline_validation_passed": False,
            "motor_device_opened": False,
            "recording_started": False,
            "motion_executed": False,
            "passed": False,
        }
    else:
        try:
            result = camera_only_status(cfg())
            result["offline_validation_passed"] = True
            result["motion_executed"] = False
        except (MediaCaptureError, OSError, ValueError) as exc:
            result = {
                "operation": "iphone_camera_status_only",
                "iphone_ip": cfg()["iphone_media_capture"]["iphone_ip"],
                "error": f"{type(exc).__name__}: {exc}",
                "offline_validation_passed": True,
                "motor_device_opened": False,
                "recording_started": False,
                "motion_executed": False,
                "passed": False,
            }
    write_report(f"{stem}_camera_status.json", result)
    return result


def expected_documented_media_campaign(
    values: dict[str, Any], experiment_number: str
) -> list[dict[str, Any]]:
    """Return the exact configuration-specific documented capture order."""

    label, _, fixture_centers_mm, _ = configuration_identity(values)
    fixture_total_external_moving_mass_g = int(
        values["fixture"]["total_external_moving_mass_g"]
    )
    campaign_total = documented_campaign_total(values)
    experiment_number = validated_experiment_number(experiment_number)
    expected: list[dict[str, Any]] = []

    def append(
        episode_id: str,
        role: str,
        condition_id: str,
        profile_id: str,
        repeat_id: str | None,
    ) -> None:
        identity = episode_media_identity(
            len(expected) + 1,
            episode_id,
            role,
            condition_id,
            profile_id,
            repeat_id,
            experiment_number=experiment_number,
            mechanical_configuration=label,
            campaign_total_episodes=campaign_total,
        )
        relative_directory = f"episodes/{identity['directory_name']}"
        prefix = str(identity["artifact_prefix"])
        expected.append(
            {
                **identity,
                "session_id": episode_id,
                "session_title": identity["title"],
                "role": role,
                "condition_id": condition_id,
                "profile_id": profile_id,
                "repeat_id": repeat_id,
                "fixture_centers_mm": list(fixture_centers_mm),
                "fixture_total_external_moving_mass_g": (
                    fixture_total_external_moving_mass_g
                ),
                "episode_display_code": identity["display_code"],
                "session_relative_directory": relative_directory,
                "episode_video": (
                    f"{relative_directory}/video/"
                    f"{prefix}_experiment-labeled.mp4"
                ),
                "episode_unlabeled_video": (
                    f"{relative_directory}/video/"
                    f"{prefix}_experiment-unlabeled.mp4"
                ),
                "episode_frame_map": (
                    f"{relative_directory}/video/{prefix}_frame-map.csv"
                ),
                "keyframe_index": (
                    f"{relative_directory}/keyframes/{prefix}_keyframes.csv"
                ),
            }
        )

    uses_h1_h2_primary = label == "B1" or (
        label in {"M0", "B0"} and documented_campaign_enabled(values)
    )
    pilot_conditions = (
        ("H1", "H2") if uses_h1_h2_primary else ("H1", "H4", "H5")
    )
    primary_order = (
        H1_H2_THREE_REPEAT_ORDER
        if uses_h1_h2_primary
        else FULL_BALANCED_THREE_REPEAT_ORDER
    )
    for condition_id in pilot_conditions:
        append(
            f"{label}__{condition_id}__PILOT_LOW_AMPLITUDE",
            "pilot",
            condition_id,
            "PILOT_LOW_AMPLITUDE",
            None,
        )

    for repeat_id, order in primary_order:
        for profile_id in CALIBRATION_PROFILE_ORDER:
            for condition_id in order:
                append(
                    f"{label}__{condition_id}__{profile_id}__{repeat_id}",
                    "calibration",
                    condition_id,
                    profile_id,
                    repeat_id,
                )
    if label in {"B0", "B2"}:
        for repeat_id, order in H1_H2_THREE_REPEAT_ORDER:
            for profile_id in MODEL_SELECTION_PROFILE_ORDER:
                for condition_id in order:
                    append(
                        f"{label}__{condition_id}__{profile_id}__{repeat_id}",
                        "model_selection",
                        condition_id,
                        profile_id,
                        repeat_id,
                    )
    if label == "B1":
        for repeat_id, order in H1_H2_FIVE_REPEAT_ORDER:
            for profile_id in HELD_OUT_PROFILE_ORDER:
                for condition_id in order:
                    append(
                        f"{label}__{condition_id}__{profile_id}__{repeat_id}",
                        "held_out",
                        condition_id,
                        profile_id,
                        repeat_id,
                    )
    if len(expected) != campaign_total:
        raise RuntimeError(
            "canonical media campaign has "
            f"{len(expected)} episodes, not {campaign_total}"
        )
    return expected


def create_motor_data_hardlink_aliases(
    run_root: Path,
    manifest: dict[str, Any],
    identity: dict[str, Any],
) -> dict[str, Any]:
    """Publish prefixed no-copy names through the proven G1 helper."""

    return documented_support.create_motor_data_hardlink_aliases(
        run_root, manifest, identity
    )


def verify_motor_data_hardlink_aliases(
    run_root: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    return documented_support.verify_motor_data_hardlink_aliases(
        run_root, manifest
    )


def ensure_zero_documented(
    bus: DynamixelBus,
    run_root: Path,
    recenter_index: int,
    manifests: list[dict[str, Any]],
    *,
    experiment_number: str,
) -> int:
    """Prefix any unrecorded recenter data without consuming media ordinals."""

    campaign_total = documented_campaign_total()
    before_count = len(manifests)
    next_index: int | None = None
    operation_error: BaseException | None = None
    try:
        next_index = base.ensure_zero(
            bus, run_root, recenter_index, manifests
        )
    except BaseException as exc:
        operation_error = exc

    label, _, _, _ = configuration_identity(cfg())
    for manifest in manifests[before_count:]:
        profile_id = str(manifest.get("profile_id", ""))
        if (
            manifest.get("role") != "preparation"
            or not profile_id.startswith("RECENTER_")
        ):
            annotation_error = RuntimeError(
                "ensure_zero appended a non-recenter preparation manifest"
            )
            if operation_error is None:
                operation_error = annotation_error
            continue
        scene_label = (
            f"H1-{label}-" + profile_id.replace("_", "-")
        )
        identity = {
            "experiment_number": experiment_number,
            "scene_label": scene_label,
            "artifact_prefix": (
                f"{experiment_number}_{scene_label}"
            ),
        }
        manifest.update(
            {
                **identity,
                "campaign_ordinal": None,
                "campaign_total_episodes": campaign_total,
                "excluded_from_recorded_media_campaign": True,
                "media": {
                    "status": "not_recorded_preparation",
                    "reason": (
                        "recenter preparation is motor data outside the "
                        f"{campaign_total} retained motion sessions"
                    ),
                    "experiment_number": experiment_number,
                    "scene_label": scene_label,
                    "artifact_prefix": identity["artifact_prefix"],
                },
            }
        )
        try:
            create_motor_data_hardlink_aliases(
                run_root, manifest, identity
            )
        except (OSError, RuntimeError, ValueError) as exc:
            manifest.setdefault("failures", []).append(
                "preparation artifact alias: "
                f"{type(exc).__name__}: {exc}"
            )
            if operation_error is None:
                operation_error = exc
        finally:
            base.write_json(
                run_root
                / "episodes"
                / str(manifest["episode_id"])
                / "episode.json",
                manifest,
            )
    if operation_error is not None:
        raise operation_error
    assert next_index is not None
    return next_index


def run_documented_episode(
    *,
    bus: DynamixelBus,
    run_root: Path,
    capture: ExperimentMediaCapture,
    media_ordinal: int,
    episode_id: str,
    condition_id: str,
    profile: Any,
    role: str,
    repeat_id: str | None,
    manifests: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run one balanced-fixture motion inside one persisted camera session."""

    values = cfg()
    label, _, _, _ = configuration_identity(values)
    campaign_total = documented_campaign_total(values)
    identity = episode_media_identity(
        media_ordinal,
        episode_id,
        role,
        condition_id,
        str(profile.profile_id),
        repeat_id,
        experiment_number=str(capture.experiment_number),
        mechanical_configuration=label,
        campaign_total_episodes=campaign_total,
    )
    capture.start_episode(
        identity=identity,
        role=role,
        condition_id=condition_id,
        profile_id=str(profile.profile_id),
        repeat_id=repeat_id,
    )
    before_motion_ns = time.monotonic_ns()
    manifest: dict[str, Any] | None = None
    operation_error: BaseException | None = None
    media_error: str | None = None
    combined_media: dict[str, Any] | None = None
    try:
        capture.snapshot(
            "fixture overview before motion"
            if media_ordinal == 1
            else "before motion"
        )
        before_motion_ns = time.monotonic_ns()
        manifest = base.run_episode(
            bus,
            run_root,
            episode_id,
            condition_id,
            profile,
            role,
            repeat_id,
            True,
        )
        manifest["experiment_number"] = identity["experiment_number"]
        manifest["scene_label"] = identity["scene_label"]
        manifest["artifact_prefix"] = identity["artifact_prefix"]
        manifest["campaign_ordinal"] = identity["campaign_ordinal"]
        manifest["campaign_total_episodes"] = identity[
            "campaign_total_episodes"
        ]
        manifests.append(manifest)
        if manifest["completion_status"] != "complete":
            raise RuntimeError(
                f"{role} episode failed: {manifest['failures']}"
            )
        create_motor_data_hardlink_aliases(run_root, manifest, identity)
    except BaseException as exc:
        operation_error = exc
    finally:
        torque_confirmed = bool(
            manifest is not None
            and manifest.get("terminal_torque_disabled") is True
        )
        if not torque_confirmed:
            errors: list[str] = []
            for attempt in range(1, 4):
                try:
                    bus.torque_disable(int(values["dynamixel_id"]))
                except (RuntimeError, OSError) as exc:
                    errors.append(
                        f"attempt {attempt}/3: {type(exc).__name__}: {exc}"
                    )
                else:
                    torque_confirmed = True
                    disabled_ns = time.monotonic_ns()
                    if manifest is not None:
                        manifest["terminal_torque_disabled"] = True
                        manifest[
                            "torque_disabled_host_monotonic_ns"
                        ] = disabled_ns
                        manifest["torque_disable_retry_before_media"] = {
                            "required": True,
                            "attempt_count": attempt,
                            "succeeded": True,
                            "errors": errors,
                            "host_monotonic_ns": disabled_ns,
                        }
                    break
            if not torque_confirmed:
                media_error = (
                    "camera STOP deferred until outer cleanup because "
                    "three torque-disable attempts failed: "
                    + "; ".join(errors)
                )
                if manifest is not None:
                    manifest["torque_disable_retry_before_media"] = {
                        "required": True,
                        "attempt_count": 3,
                        "succeeded": False,
                        "errors": errors,
                    }
                    manifest.setdefault("failures", []).append(media_error)
                if operation_error is None:
                    operation_error = RuntimeError(media_error)

        events = [
            {
                "label": "01 before motion",
                "host_monotonic_ns": before_motion_ns,
            }
        ]
        if manifest is not None:
            for event_label, timestamp in (
                (
                    "02 experiment zero and profile start",
                    manifest.get("start_host_monotonic_ns"),
                ),
                (
                    "03 motion finished or aborted",
                    manifest.get("episode_control_exit_host_monotonic_ns"),
                ),
                (
                    "04 torque disabled",
                    manifest.get("torque_disabled_host_monotonic_ns"),
                ),
            ):
                if timestamp is not None:
                    events.append(
                        {
                            "label": event_label,
                            "host_monotonic_ns": int(timestamp),
                        }
                    )

        if torque_confirmed:
            try:
                combined_media = capture.stop_episode(
                    outcome=(
                        "complete"
                        if operation_error is None
                        and manifest is not None
                        else "aborted"
                    ),
                    events=events,
                )
            except MediaCaptureError as exc:
                media_error = f"{type(exc).__name__}: {exc}"
                if operation_error is None:
                    operation_error = exc

        if manifest is not None:
            if combined_media is not None:
                manifest["media"] = capture.relative_session_media(
                    combined_media
                )
            else:
                manifest["media"] = {
                    "status": "failed",
                    "experiment_number": identity["experiment_number"],
                    "scene_label": identity["scene_label"],
                    "artifact_prefix": identity["artifact_prefix"],
                    "campaign_ordinal": identity["campaign_ordinal"],
                    "campaign_total_episodes": campaign_total,
                    "title": identity["title"],
                    "directory": (
                        "media/episodes/" + identity["directory_name"]
                    ),
                    "video": None,
                    "unlabeled_video": None,
                    "frame_map": None,
                    "key_frame_count": 0,
                    "source_frame_count": 0,
                    "capture_service": "persistent asMagic AR receiver",
                    "raw_jpegs_are_primary_evidence": True,
                    "derived_video_has_audio": False,
                    "error": media_error,
                }
            base.write_json(
                run_root
                / "episodes"
                / manifest["episode_id"]
                / "episode.json",
                manifest,
            )

    if operation_error is not None:
        raise operation_error
    assert manifest is not None
    return manifest
def _csv_values_are_true(values: pd.Series) -> bool:
    return bool(len(values)) and all(
        str(value).strip().lower() == "true" for value in values.tolist()
    )


def _has_exact_four_plus_one_still_artifacts(
    episode_root: Path,
) -> bool:
    """Require four phase keyframes plus one distinct snapshot JPEG."""

    keyframe_jpegs = list(
        (episode_root / "keyframes").glob("*.jpg")
    )
    snapshot_jpegs = list(
        (episode_root / "snapshots").glob("*.jpg")
    )
    return (
        len(keyframe_jpegs) == 4
        and len(snapshot_jpegs) == 1
        and len(keyframe_jpegs) + len(snapshot_jpegs) == 5
    )


def _verify_episode_media(
    run_root: Path,
    manifest: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    """Cross-reference one paired video set to its exact raw AR evidence."""

    episode_id = str(manifest.get("episode_id", ""))
    media = manifest.get("media", {})
    if not isinstance(media, dict):
        media = {}
    errors: list[str] = []
    checks: dict[str, bool] = {}
    prefix = str(expected["artifact_prefix"])
    expected_directory = "media/" + str(
        expected["session_relative_directory"]
    )
    checks.update(
        {
            "motor_and_media_identity_is_exact": (
                manifest.get("experiment_number")
                == expected["experiment_number"]
                and manifest.get("scene_label") == expected["display_code"]
                and manifest.get("artifact_prefix") == prefix
                and manifest.get("campaign_ordinal")
                == expected["campaign_ordinal"]
                and manifest.get("campaign_total_episodes")
                == expected["campaign_total_episodes"]
                and media.get("experiment_number")
                == expected["experiment_number"]
                and media.get("scene_label") == expected["display_code"]
                and media.get("artifact_prefix") == prefix
                and media.get("campaign_ordinal")
                == expected["campaign_ordinal"]
                and media.get("campaign_total_episodes")
                == expected["campaign_total_episodes"]
            ),
            "media_status_complete": media.get("status") == "complete",
            "media_directory_is_exact": (
                media.get("directory") == expected_directory
            ),
            "manifest_artifact_paths_are_prefixed_and_exact": (
                media.get("video")
                == "media/" + str(expected["episode_video"])
                and media.get("unlabeled_video")
                == "media/" + str(expected["episode_unlabeled_video"])
                and media.get("frame_map")
                == "media/" + str(expected["episode_frame_map"])
            ),
            "raw_evidence_policy_is_explicit": (
                media.get("raw_jpegs_are_primary_evidence") is True
                and media.get("raw_jpegs_modified") is False
                and media.get("derived_video_has_audio") is False
            ),
        }
    )
    episode_root = (run_root / expected_directory).resolve()
    try:
        episode_root.relative_to(run_root.resolve())
    except ValueError:
        errors.append("media directory escapes the run root")
        return {
            "episode_id": episode_id,
            "checks": checks,
            "errors": errors,
            "passed": False,
        }

    paths = {
        "capture": episode_root / "capture.json",
        "index": episode_root / "media-index.json",
        "prefixed_ar": episode_root / "raw" / f"{prefix}_ar.csv",
        "ar_compatibility": episode_root / "raw" / "ar.csv",
        "color": episode_root / "raw" / "color_frames",
        "depth": episode_root / "raw" / "depth_frames",
        "labeled": (
            episode_root
            / "video"
            / f"{prefix}_experiment-labeled.mp4"
        ),
        "unlabeled": (
            episode_root
            / "video"
            / f"{prefix}_experiment-unlabeled.mp4"
        ),
        "frame_map": episode_root / "video" / f"{prefix}_frame-map.csv",
        "keyframes": (
            episode_root / "keyframes" / f"{prefix}_keyframes.csv"
        ),
        "snapshots": episode_root / "snapshots",
    }
    for name, path in paths.items():
        try:
            checks[f"{name}_exists"] = (
                path.is_dir()
                if name in {"color", "depth", "snapshots"}
                else path.is_file() and path.stat().st_size > 0
            )
        except OSError as exc:
            checks[f"{name}_exists"] = False
            errors.append(f"{name}: {exc}")
    if not all(
        checks.get(f"{name}_exists", False) for name in paths
    ):
        errors.append("required media artifact missing")
        return {
            "episode_id": episode_id,
            "checks": checks,
            "errors": errors,
            "passed": False,
        }

    def referenced_files_exist(values: list[str]) -> bool:
        if not values:
            return False
        for value in values:
            candidate = (episode_root / value).resolve()
            try:
                candidate.relative_to(episode_root)
                if not candidate.is_file() or candidate.stat().st_size == 0:
                    return False
            except (OSError, ValueError):
                return False
        return True

    try:
        ar = pd.read_csv(paths["prefixed_ar"])
        frame_map = pd.read_csv(paths["frame_map"])
        keyframes = pd.read_csv(paths["keyframes"])
        capture_manifest = base.read_json(paths["capture"])
        index = base.read_json(paths["index"])
        session = capture_manifest.get("session", {})
        capture_metadata = (
            session.get("metadata", {})
            if isinstance(session, dict)
            else {}
        )
        human_viewable = index.get("human_viewable", {})
        video = human_viewable.get("video", {})
        primary = index.get("primary_evidence", {})
        snapshot_records = human_viewable.get("snapshots", [])
        indexed_keyframes = human_viewable.get("keyframes", [])
        color_files = [
            str(value)
            for value in ar.get("color_file", pd.Series(dtype=str))
            .dropna()
            .tolist()
            if str(value).strip()
        ]
        depth_files = [
            str(value)
            for value in ar.get("depth_file", pd.Series(dtype=str))
            .dropna()
            .tolist()
            if str(value).strip()
        ]
        keyframe_files = [
            str(value)
            for value in keyframes.get(
                "keyframe_file", pd.Series(dtype=str)
            )
            .dropna()
            .tolist()
            if str(value).strip()
        ]
        source_keyframe_files = [
            str(value)
            for value in keyframes.get(
                "source_color_file", pd.Series(dtype=str)
            )
            .dropna()
            .tolist()
            if str(value).strip()
        ]
        ar_source_by_index = {
            int(row.frame_index): str(row.color_file)
            for row in ar.itertuples(index=False)
            if pd.notna(row.frame_index) and pd.notna(row.color_file)
        }
        keyframe_cross_references_are_exact = all(
            ar_source_by_index.get(int(row.source_frame_index))
            == str(row.source_color_file)
            and str(row.keyframe_file).startswith(
                f"keyframes/{prefix}_event_{int(row.event_index):02d}_"
            )
            and str(row.keyframe_file).endswith(
                f"frame_{int(row.source_frame_index):08d}.jpg"
            )
            for row in keyframes.itertuples(index=False)
        )
        snapshot_cross_reference_is_exact = (
            isinstance(snapshot_records, list)
            and len(snapshot_records) == 1
            and isinstance(snapshot_records[0], dict)
            and int(snapshot_records[0].get("snapshot_index", -1)) == 1
            and snapshot_records[0].get("label")
            == (
                "fixture overview before motion"
                if expected["campaign_ordinal"] == 1
                else "before motion"
            )
            and ar_source_by_index.get(
                int(snapshot_records[0].get("source_frame_index", -1))
            )
            == snapshot_records[0].get("source_color_file")
            and str(snapshot_records[0].get("snapshot_file", "")).startswith(
                f"snapshots/{prefix}_snapshot_01_"
            )
            and str(snapshot_records[0].get("snapshot_file", "")).endswith(
                "frame_"
                + f"{int(snapshot_records[0].get('source_frame_index', -1)):08d}"
                + ".jpg"
            )
            and referenced_files_exist(
                [
                    str(snapshot_records[0].get("snapshot_file", "")),
                    str(snapshot_records[0].get("source_color_file", "")),
                ]
            )
        )
        expected_labels = [
            "01 before motion",
            "02 experiment zero and profile start",
            "03 motion finished or aborted",
            "04 torque disabled",
        ]
        video_count = int(video.get("video_frame_count", -1))
        unlabeled_count = int(
            video.get("unlabeled_video_frame_count", -1)
        )
        fps = float(video.get("constant_frame_rate_fps", 0.0))
        unlabeled_fps = float(
            video.get("unlabeled_constant_frame_rate_fps", -1.0)
        )
        checks.update(
            {
                "compatibility_ar_csv_is_only_alias_to_prefixed_primary": (
                    paths["ar_compatibility"].samefile(
                        paths["prefixed_ar"]
                    )
                ),
                "capture_metadata_identity_is_exact": (
                    capture_metadata.get("canonical_episode_id")
                    == episode_id
                    and capture_metadata.get("experiment_number")
                    == expected["experiment_number"]
                    and capture_metadata.get("mechanical_configuration")
                    == expected["mechanical_configuration"]
                    and capture_metadata.get("campaign_ordinal")
                    == expected["campaign_ordinal"]
                    and capture_metadata.get("campaign_total_episodes")
                    == expected["campaign_total_episodes"]
                    and capture_metadata.get("display_code")
                    == expected["display_code"]
                    and capture_metadata.get("artifact_prefix") == prefix
                    and capture_metadata.get("fixture_centers_mm")
                    == expected["fixture_centers_mm"]
                    and capture_metadata.get(
                        "fixture_total_external_moving_mass_g"
                    )
                    == expected["fixture_total_external_moving_mass_g"]
                ),
                "AR_table_has_source_and_host_timestamps": (
                    {
                        "frame_index",
                        "iphone_timestamp_unix_s",
                        "host_receive_timestamp_unix_s",
                        "host_receive_monotonic_ns",
                        "color_file",
                        "depth_file",
                    }.issubset(ar.columns)
                    and len(ar) > 0
                ),
                "raw_JPEGs_are_nonempty_prefixed_and_referenced": (
                    referenced_files_exist(color_files)
                    and all(
                        Path(value).name.startswith(prefix + "_")
                        for value in color_files
                    )
                    and int(primary.get("jpeg_count", -1))
                    == len(color_files)
                    and int(video.get("source_jpeg_count", -1))
                    == len(color_files)
                    and int(media.get("source_frame_count", -1))
                    == len(color_files)
                ),
                "raw_frame_filenames_match_AR_frame_indices": all(
                    Path(str(row.color_file)).name.startswith(
                        f"{prefix}_frame_{int(row.frame_index):08d}_"
                    )
                    and (
                        pd.isna(row.depth_file)
                        or Path(str(row.depth_file)).name.startswith(
                            f"{prefix}_depth_{int(row.frame_index):08d}_"
                        )
                    )
                    for row in ar.itertuples(index=False)
                ),
                "depth_arrays_are_nonempty_prefixed_and_referenced": (
                    referenced_files_exist(depth_files)
                    and all(
                        Path(value).name.startswith(prefix + "_")
                        for value in depth_files
                    )
                    and int(primary.get("depth_count", -1))
                    == len(depth_files)
                ),
                "episode_frame_map_schema_and_identity_are_exact": (
                    list(frame_map.columns) == EPISODE_FRAME_MAP_COLUMNS
                    and len(frame_map) > 0
                    and frame_map["video_frame_index"].tolist()
                    == list(range(len(frame_map)))
                    and np.isfinite(
                        frame_map["video_time_s"].to_numpy(dtype=float)
                    ).all()
                    and frame_map["video_time_s"].is_monotonic_increasing
                    and np.allclose(
                        frame_map["video_time_s"].to_numpy(dtype=float),
                        np.arange(len(frame_map), dtype=float) / fps,
                        rtol=0.0,
                        atol=1e-9,
                    )
                    and frame_map["episode_display_code"]
                    .fillna("")
                    .astype(str)
                    .eq(expected["display_code"])
                    .all()
                    and pd.to_numeric(
                        frame_map["campaign_ordinal"], errors="coerce"
                    )
                    .eq(expected["campaign_ordinal"])
                    .all()
                    and frame_map["phase_label"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .ne("")
                    .all()
                    and _csv_values_are_true(
                        frame_map["burned_in_label"]
                    )
                ),
                "exact_four_useful_keyframes_are_retained": (
                    list(keyframes.columns) == KEYFRAME_COLUMNS
                    and len(keyframes) == 4
                    and keyframes["event_index"].tolist() == [1, 2, 3, 4]
                    and keyframes["label"].tolist() == expected_labels
                    and referenced_files_exist(keyframe_files)
                    and referenced_files_exist(source_keyframe_files)
                    and keyframe_cross_references_are_exact
                    and isinstance(indexed_keyframes, list)
                    and len(indexed_keyframes) == 4
                    and [
                        (
                            int(item.get("event_index", -1)),
                            item.get("label"),
                            item.get("keyframe_file"),
                            item.get("source_color_file"),
                            int(item.get("source_frame_index", -1)),
                        )
                        for item in indexed_keyframes
                    ]
                    == [
                        (
                            int(row.event_index),
                            str(row.label),
                            str(row.keyframe_file),
                            str(row.source_color_file),
                            int(row.source_frame_index),
                        )
                        for row in keyframes.itertuples(index=False)
                    ]
                    and int(media.get("key_frame_count", -1)) == 4
                ),
                "one_separate_prefixed_snapshot_makes_five_still_artifacts": (
                    snapshot_cross_reference_is_exact
                    and len(keyframe_files) == 4
                    and _has_exact_four_plus_one_still_artifacts(
                        episode_root
                    )
                ),
                "paired_video_metadata_identity_is_exact": (
                    video.get("experiment_number")
                    == expected["experiment_number"]
                    and video.get("scene_label") == expected["display_code"]
                    and video.get("artifact_prefix") == prefix
                    and video.get("episode_display_code")
                    == expected["display_code"]
                    and video.get("campaign_ordinal")
                    == expected["campaign_ordinal"]
                    and int(
                        video.get("campaign_total_episodes", -1)
                    )
                    == expected["campaign_total_episodes"]
                    and video.get("path")
                    == f"video/{prefix}_experiment-labeled.mp4"
                    and video.get("unlabeled_path")
                    == f"video/{prefix}_experiment-unlabeled.mp4"
                    and video.get("frame_map")
                    == f"video/{prefix}_frame-map.csv"
                ),
                "paired_videos_are_native_640x480_same_timeline": (
                    int(video.get("width_px", 0)) == 640
                    and int(video.get("height_px", 0)) == 480
                    and int(video.get("unlabeled_width_px", 0)) == 640
                    and int(video.get("unlabeled_height_px", 0)) == 480
                    and video_count == len(frame_map)
                    and unlabeled_count == len(frame_map)
                    and int(
                        video.get("decoded_frame_count_verified", -1)
                    )
                    == len(frame_map)
                    and int(
                        video.get(
                            "unlabeled_decoded_frame_count_verified", -1
                        )
                    )
                    == len(frame_map)
                    and fps > 0.0
                    and fps == unlabeled_fps
                    and video.get("codec")
                    == video.get("unlabeled_codec")
                    and video.get("burned_in_labels") is True
                    and video.get("unlabeled_burned_in_labels") is False
                    and video.get("paired_frame_timing_identical") is True
                    and video.get("shared_frame_map") is True
                    and video.get("source_resolution_consistent") is True
                    and video.get("raw_jpegs_modified") is False
                    and video.get("audio_track") is False
                    and video.get("unlabeled_audio_track") is False
                ),
                "frame_map_only_references_retained_source_frames": (
                    set(
                        pd.to_numeric(
                            frame_map["source_frame_index"],
                            errors="coerce",
                        )
                        .dropna()
                        .astype(int)
                        .tolist()
                    ).issubset(
                        set(
                            pd.to_numeric(
                                ar["frame_index"], errors="coerce"
                            )
                            .dropna()
                            .astype(int)
                            .tolist()
                        )
                    )
                    and all(
                        ar_source_by_index.get(int(row.source_frame_index))
                        == str(row.color_file)
                        and Path(str(row.color_file)).name.startswith(
                            prefix + "_"
                        )
                        for row in frame_map.itertuples(index=False)
                    )
                    and referenced_files_exist(
                        [
                            str(value)
                            for value in frame_map["color_file"]
                            .dropna()
                            .tolist()
                            if str(value).strip()
                        ]
                    )
                ),
            }
        )
    except (
        KeyError,
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        pd.errors.EmptyDataError,
    ) as exc:
        errors.append(f"media tables did not cross-reference: {exc}")
        checks["media_tables_parse_and_cross_reference"] = False
    return {
        "episode_id": episode_id,
        "checks": checks,
        "errors": errors,
        "passed": not errors and all(checks.values()),
    }


def _verify_full_experiment_media(
    run_root: Path,
    run_manifest: dict[str, Any],
    expected: list[dict[str, Any]],
) -> dict[str, Any]:
    experiment_number = str(run_manifest.get("experiment_number", ""))
    label = str(run_manifest.get("mechanical_configuration", ""))
    prefix = f"{experiment_number}_{label}"
    campaign_total = len(expected)
    media_root = run_root / "media"
    paths = {
        "index_json": media_root / "index.json",
        "index_html": media_root / "index.html",
        "setup": media_root / "setup" / f"{prefix}_fixture-overview.jpg",
        "labeled": (
            media_root
            / "video"
            / f"{prefix}_full-experiment-labeled.mp4"
        ),
        "unlabeled": (
            media_root
            / "video"
            / f"{prefix}_full-experiment-unlabeled.mp4"
        ),
        "frame_map": (
            media_root
            / "video"
            / f"{prefix}_full-experiment-frame-map.csv"
        ),
        "chapters": media_root / "video" / f"{prefix}_chapters.csv",
    }
    checks: dict[str, bool] = {}
    errors: list[str] = []
    for name, path in paths.items():
        try:
            checks[f"{name}_exists"] = (
                path.is_file() and path.stat().st_size > 0
            )
        except OSError as exc:
            checks[f"{name}_exists"] = False
            errors.append(f"{name}: {exc}")
    if not all(checks.values()):
        return {
            "paths": {key: str(value) for key, value in paths.items()},
            "checks": checks,
            "errors": errors + ["required full-campaign artifact missing"],
            "passed": False,
        }

    expected_ids = [str(item["session_id"]) for item in expected]
    expected_codes = [str(item["display_code"]) for item in expected]
    try:
        index = base.read_json(paths["index_json"])
        full = index.get("full_experiment_video", {})
        run_summary = run_manifest.get(
            "iphone_media_capture", {}
        ).get("full_experiment_video", {})
        frame_map = pd.read_csv(paths["frame_map"])
        chapters = pd.read_csv(paths["chapters"])
        frame_count = len(frame_map)
        labeled_fps = float(
            full.get("constant_frame_rate_fps", 0.0)
        )
        unlabeled_fps = float(
            full.get("unlabeled_constant_frame_rate_fps", -1.0)
        )
        campaign_indices = pd.to_numeric(
            frame_map["campaign_frame_index"], errors="coerce"
        )
        campaign_times = pd.to_numeric(
            frame_map["campaign_time_s"], errors="coerce"
        )
        campaign_timeline_is_exact = (
            campaign_indices.notna().all()
            and campaign_indices.astype(int).tolist()
            == list(range(frame_count))
            and campaign_times.notna().all()
            and np.isfinite(campaign_times.to_numpy(dtype=float)).all()
            and campaign_times.is_monotonic_increasing
            and np.allclose(
                campaign_times.to_numpy(dtype=float),
                np.arange(frame_count, dtype=float) / labeled_fps,
                rtol=0.0,
                atol=1e-9,
            )
        )
        per_session_maps_are_exact = True
        chapter_timeline_is_exact = True
        for expected_item in expected:
            ordinal = int(expected_item["campaign_ordinal"])
            session_id = str(expected_item["session_id"])
            group = frame_map[frame_map["session_id"] == session_id]
            local_count = len(group)
            expected_local_indices = list(range(local_count))
            per_session_maps_are_exact = (
                per_session_maps_are_exact
                and local_count > 0
                and group["campaign_session_order"].eq(ordinal).all()
                and group["campaign_ordinal"].eq(ordinal).all()
                and group["campaign_session_frame_index"].tolist()
                == expected_local_indices
                and group["episode_video_frame_index"].tolist()
                == expected_local_indices
                and np.allclose(
                    group["episode_video_time_s"].to_numpy(dtype=float),
                    np.arange(local_count, dtype=float) / labeled_fps,
                    rtol=0.0,
                    atol=1e-9,
                )
                and group["session_title"].eq(
                    expected_item["session_title"]
                ).all()
                and group["episode_display_code"].eq(
                    expected_item["display_code"]
                ).all()
                and group["session_relative_directory"].eq(
                    expected_item["session_relative_directory"]
                ).all()
                and group["episode_video"].eq(
                    expected_item["episode_video"]
                ).all()
                and group["episode_frame_map"].eq(
                    expected_item["episode_frame_map"]
                ).all()
                and group["source_color_file"]
                .fillna("")
                .astype(str)
                .str.startswith(
                    "raw/color_frames/"
                    + str(expected_item["artifact_prefix"])
                    + "_"
                )
                .all()
            )
            chapter = chapters.iloc[ordinal - 1]
            chapter_timeline_is_exact = (
                chapter_timeline_is_exact
                and int(chapter["campaign_start_frame"])
                == int(group.iloc[0]["campaign_frame_index"])
                and int(chapter["campaign_end_frame_inclusive"])
                == int(group.iloc[-1]["campaign_frame_index"])
                and int(chapter["episode_video_frame_count"])
                == local_count
                and np.isclose(
                    float(chapter["campaign_start_time_s"]),
                    int(chapter["campaign_start_frame"]) / labeled_fps,
                    rtol=0.0,
                    atol=1e-9,
                )
                and np.isclose(
                    float(chapter["campaign_end_time_s_exclusive"]),
                    (
                        int(chapter["campaign_end_frame_inclusive"]) + 1
                    )
                    / labeled_fps,
                    rtol=0.0,
                    atol=1e-9,
                )
            )
        checks.update(
            {
                "root_index_identity_and_session_count_are_exact": (
                    index.get("status") == "complete"
                    and int(index.get("session_count", -1))
                    == campaign_total
                    and int(index.get("finalized_session_count", -1))
                    == campaign_total
                    and index.get("run_metadata", {}).get(
                        "experiment_number"
                    )
                    == experiment_number
                    and index.get("run_metadata", {}).get(
                        "mechanical_configuration"
                    )
                    == label
                    and index.get("run_metadata", {}).get("episode_ids")
                    == expected_ids
                    and index.get("run_metadata", {}).get(
                        "campaign_artifact_prefix"
                    )
                    == prefix
                ),
                "full_video_paths_and_identity_are_exact": (
                    full.get("status") == "complete"
                    and full.get("experiment_number") == experiment_number
                    and full.get("scene_label") == label
                    and full.get("campaign_artifact_prefix") == prefix
                    and full.get("path")
                    == f"video/{prefix}_full-experiment-labeled.mp4"
                    and full.get("unlabeled_path")
                    == f"video/{prefix}_full-experiment-unlabeled.mp4"
                    and full.get("frame_map")
                    == f"video/{prefix}_full-experiment-frame-map.csv"
                    and full.get("chapters")
                    == f"video/{prefix}_chapters.csv"
                ),
                "full_videos_are_native_paired_and_fully_decoded": (
                    frame_count > 0
                    and int(full.get("video_frame_count", -1))
                    == frame_count
                    and int(
                        full.get("unlabeled_video_frame_count", -1)
                    )
                    == frame_count
                    and int(
                        full.get("decoded_frame_count_verified", -1)
                    )
                    == frame_count
                    and int(
                        full.get(
                            "unlabeled_decoded_frame_count_verified", -1
                        )
                    )
                    == frame_count
                    and int(full.get("width_px", 0)) == 640
                    and int(full.get("height_px", 0)) == 480
                    and int(full.get("unlabeled_width_px", 0)) == 640
                    and int(full.get("unlabeled_height_px", 0)) == 480
                    and labeled_fps > 0.0
                    and labeled_fps == unlabeled_fps
                    and np.isclose(
                        float(full.get("campaign_duration_s", -1.0)),
                        frame_count / labeled_fps,
                        rtol=0.0,
                        atol=1e-9,
                    )
                    and full.get("codec") == full.get("unlabeled_codec")
                    and full.get("burned_in_labels") is True
                    and full.get("unlabeled_burned_in_labels") is False
                    and full.get("paired_frame_timing_identical") is True
                    and full.get("shared_frame_map") is True
                    and full.get("source_resolution_consistent") is True
                    and full.get("raw_jpegs_modified") is False
                    and full.get("audio_track") is False
                    and full.get("unlabeled_audio_track") is False
                ),
                "full_campaign_includes_all_sessions_in_exact_order": (
                    int(full.get("declared_campaign_total_episodes", -1))
                    == campaign_total
                    and int(full.get("included_session_count", -1))
                    == campaign_total
                    and int(full.get("total_session_count", -1))
                    == campaign_total
                    and full.get("included_session_ids") == expected_ids
                    and full.get("captured_campaign_ordinals")
                    == list(
                        range(
                            1,
                            campaign_total + 1,
                        )
                    )
                    and full.get("omitted_sessions") == []
                    and full.get("partial_source_sessions") == []
                    and full.get("session_order") == "capture_order"
                    and full.get("inter_episode_gaps_included") is False
                    and full.get(
                        "campaign_structure_checks", {}
                    ).get("all_declared_sessions_have_episode_videos")
                    is True
                    and full.get(
                        "campaign_structure_checks", {}
                    ).get("declared_total_matches_session_count")
                    is True
                    and full.get(
                        "campaign_structure_checks", {}
                    ).get("exact_ordinal_sequence_in_capture_order")
                    is True
                ),
                "campaign_frame_map_schema_identity_and_labels_are_exact": (
                    list(frame_map.columns)
                    == CAMPAIGN_FRAME_MAP_COLUMNS
                    and campaign_timeline_is_exact
                    and per_session_maps_are_exact
                    and frame_map["session_id"]
                    .drop_duplicates()
                    .tolist()
                    == expected_ids
                    and frame_map["episode_display_code"]
                    .drop_duplicates()
                    .tolist()
                    == expected_codes
                    and pd.to_numeric(
                        frame_map["campaign_ordinal"], errors="coerce"
                    )
                    .drop_duplicates()
                    .astype(int)
                    .tolist()
                    == list(
                        range(
                            1,
                            campaign_total + 1,
                        )
                    )
                    and frame_map["phase_label"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .ne("")
                    .all()
                    and _csv_values_are_true(
                        frame_map["burned_in_label"]
                    )
                ),
                "chapter_map_is_exact_and_contiguous": (
                    list(chapters.columns) == CHAPTER_COLUMNS
                    and chapter_timeline_is_exact
                    and len(chapters)
                    == campaign_total
                    and chapters["chapter_index"].tolist()
                    == list(
                        range(
                            1,
                            campaign_total + 1,
                        )
                    )
                    and chapters["session_id"].tolist() == expected_ids
                    and chapters["episode_display_code"].tolist()
                    == expected_codes
                    and chapters["campaign_ordinal"].tolist()
                    == list(
                        range(
                            1,
                            campaign_total + 1,
                        )
                    )
                    and chapters["raw_capture_status"]
                    .astype(str)
                    .eq("complete")
                    .all()
                    and chapters.iloc[0]["campaign_start_frame"] == 0
                    and chapters.iloc[-1][
                        "campaign_end_frame_inclusive"
                    ]
                    == frame_count - 1
                    and all(
                        int(chapters.iloc[index][
                            "campaign_start_frame"
                        ])
                        == int(chapters.iloc[index - 1][
                            "campaign_end_frame_inclusive"
                        ])
                        + 1
                        for index in range(1, len(chapters))
                    )
                ),
                "run_manifest_full_video_summary_is_root_relative": (
                    run_summary.get("status") == "complete"
                    and run_summary.get("path")
                    == f"media/video/{prefix}_full-experiment-labeled.mp4"
                    and run_summary.get("unlabeled_path")
                    == f"media/video/{prefix}_full-experiment-unlabeled.mp4"
                    and run_summary.get("frame_map")
                    == f"media/video/{prefix}_full-experiment-frame-map.csv"
                    and run_summary.get("chapters")
                    == f"media/video/{prefix}_chapters.csv"
                ),
            }
        )
    except (
        KeyError,
        IndexError,
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        pd.errors.EmptyDataError,
    ) as exc:
        errors.append(f"full media tables did not cross-reference: {exc}")
        checks["full_media_tables_parse_and_cross_reference"] = False
    return {
        "paths": {key: str(value) for key, value in paths.items()},
        "checks": checks,
        "errors": errors,
        "frame_count": len(frame_map) if "frame_map" in locals() else 0,
        "chapter_count": len(chapters) if "chapters" in locals() else 0,
        "passed": not errors and all(checks.values()),
    }


def _verify_media_lifecycle(
    run_root: Path,
    run_manifest: dict[str, Any],
    expected: list[dict[str, Any]],
    manifests_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    campaign_total = len(expected)
    result = documented_support.verify_media_lifecycle(
        run_root,
        run_manifest,
        campaign_total,
    )
    path = run_root / "media" / "capture-lifecycle.jsonl"
    rows: list[dict[str, Any]] = []
    commands: list[str] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            rows.append(row)
            command = str(row.get("command", ""))
            if command != "STATUS":
                commands.append(command)
    expected_commands = (
        ["START", "SNAPSHOT", "STOP"]
        * campaign_total
        + ["FINALIZE", "SHUTDOWN"]
    )
    result["checks"]["non_status_command_order_is_exact"] = (
        commands == expected_commands
    )

    episode_rows = [
        row
        for row in rows
        if row.get("command") in {"START", "SNAPSHOT", "STOP"}
    ]
    planned_ids = [str(item["session_id"]) for item in expected]
    triples_are_exact = len(episode_rows) == 3 * campaign_total
    start_identities_are_exact = triples_are_exact
    snapshot_identities_are_exact = triples_are_exact
    stop_identities_are_exact = triples_are_exact
    request_ack_timing_is_valid = triples_are_exact
    snapshot_precedes_motor_start = triples_are_exact
    stop_follows_torque_disable = triples_are_exact
    completed_response_details_are_exact = triples_are_exact
    lifecycle_bindings: list[dict[str, Any]] = []

    for index, expected_item in enumerate(expected):
        session_id = str(expected_item["session_id"])
        if len(episode_rows) < 3 * (index + 1):
            lifecycle_bindings.append(
                {
                    "campaign_ordinal": index + 1,
                    "expected_session_id": session_id,
                    "passed": False,
                    "reason": "lifecycle triplet is missing",
                }
            )
            continue
        start, snapshot, stop = episode_rows[index * 3 : index * 3 + 3]
        if [start.get("command"), snapshot.get("command"), stop.get("command")] != [
            "START",
            "SNAPSHOT",
            "STOP",
        ]:
            triples_are_exact = False

        def response_for(row: dict[str, Any]) -> dict[str, Any]:
            response = row.get("response")
            return response if isinstance(response, dict) else {}

        start_response = response_for(start)
        snapshot_response = response_for(snapshot)
        stop_response = response_for(stop)
        start_matches = start_response.get("session_id") == session_id
        snapshot_matches = snapshot_response.get("session_id") == session_id
        stop_matches = stop_response.get("session_id") == session_id
        start_identities_are_exact &= start_matches
        snapshot_identities_are_exact &= snapshot_matches
        stop_identities_are_exact &= stop_matches

        manifest = manifests_by_id.get(session_id, {})
        try:
            start_request = int(start["request_host_monotonic_ns"])
            start_ack = int(start["ack_host_monotonic_ns"])
            snapshot_request = int(snapshot["request_host_monotonic_ns"])
            snapshot_ack = int(snapshot["ack_host_monotonic_ns"])
            motor_start = int(manifest["start_host_monotonic_ns"])
            torque_disabled = int(
                manifest["torque_disabled_host_monotonic_ns"]
            )
            stop_request = int(stop["request_host_monotonic_ns"])
            stop_ack = int(stop["ack_host_monotonic_ns"])
            request_ack_ok = (
                start_request <= start_ack
                and snapshot_request <= snapshot_ack
                and stop_request <= stop_ack
            )
            snapshot_before_motor = (
                start_ack <= snapshot_request
                and snapshot_ack <= motor_start
            )
            stop_after_torque = (
                stop_request >= torque_disabled
                and stop_ack >= torque_disabled
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            request_ack_ok = False
            snapshot_before_motor = False
            stop_after_torque = False
            torque_disabled = None
            stop_request = None
            stop_ack = None
        request_ack_timing_is_valid &= request_ack_ok
        snapshot_precedes_motor_start &= snapshot_before_motor
        stop_follows_torque_disable &= stop_after_torque

        snapshot_value = snapshot_response.get("snapshot")
        snapshot_value = (
            snapshot_value if isinstance(snapshot_value, dict) else {}
        )
        expected_snapshot_label = (
            "fixture overview before motion" if index == 0 else "before motion"
        )
        details_ok = bool(
            isinstance(start_response.get("first_persisted_frame"), dict)
            and snapshot_value.get("label") == expected_snapshot_label
            and stop_response.get("outcome") == "complete"
            and stop_response.get("raw_capture_status") == "complete"
            and stop_response.get("event_count") == 4
        )
        completed_response_details_are_exact &= details_ok
        binding_passed = bool(
            triples_are_exact
            and start_matches
            and snapshot_matches
            and stop_matches
            and request_ack_ok
            and snapshot_before_motor
            and stop_after_torque
            and details_ok
        )
        lifecycle_bindings.append(
            {
                "campaign_ordinal": index + 1,
                "expected_session_id": session_id,
                "start_response_session_id": start_response.get(
                    "session_id"
                ),
                "snapshot_response_session_id": snapshot_response.get(
                    "session_id"
                ),
                "stop_response_session_id": stop_response.get("session_id"),
                "torque_disabled_host_monotonic_ns": torque_disabled,
                "stop_request_host_monotonic_ns": stop_request,
                "stop_ack_host_monotonic_ns": stop_ack,
                "passed": binding_passed,
            }
        )

    result["checks"].update(
        {
            "episode_lifecycle_triplets_are_exact": triples_are_exact,
            "start_response_session_identities_match_exact_plan": (
                start_identities_are_exact
            ),
            "snapshot_response_session_identities_match_exact_plan": (
                snapshot_identities_are_exact
            ),
            "stop_response_session_identities_match_exact_plan": (
                stop_identities_are_exact
            ),
            "episode_lifecycle_request_ack_timing_is_monotonic": (
                request_ack_timing_is_valid
            ),
            "snapshot_ack_precedes_motor_episode_start": (
                snapshot_precedes_motor_start
            ),
            "every_stop_request_and_ack_follows_episode_torque_disable": (
                stop_follows_torque_disable
            ),
            "episode_lifecycle_completion_details_are_exact": (
                completed_response_details_are_exact
            ),
            "planned_session_id_order_is_unique": (
                len(planned_ids) == len(set(planned_ids)) == campaign_total
            ),
        }
    )
    result["non_status_commands"] = commands
    result["episode_bindings"] = lifecycle_bindings
    result["passed"] = bool(
        not result.get("errors")
        and all(result["checks"].values())
    )
    return result


_INVENTORY_LINE_RE = re.compile(r"^([0-9a-f]{64})  (.+)$")


def _verify_exact_inventory(
    run_root: Path,
    *,
    require_archived_verification: bool,
) -> dict[str, Any]:
    """Verify the writer's exact all-files-except-self inventory contract."""

    run_root = run_root.resolve()
    inventory_path = run_root / "inventory.sha256"
    malformed_lines: list[dict[str, Any]] = []
    unsafe_paths: list[str] = []
    duplicate_paths: list[str] = []
    entries: dict[str, str] = {}
    hash_failures: list[str] = []

    if inventory_path.is_file():
        for line_number, line in enumerate(
            inventory_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            match = _INVENTORY_LINE_RE.fullmatch(line)
            if match is None:
                malformed_lines.append(
                    {"line_number": line_number, "line": line}
                )
                continue
            digest, relative = match.groups()
            relative_path = Path(relative)
            try:
                resolved = (run_root / relative_path).resolve()
                resolved.relative_to(run_root)
                stays_within_root = True
            except (OSError, RuntimeError, ValueError):
                stays_within_root = False
            path_is_safe = bool(
                relative
                and "\\" not in relative
                and not relative_path.is_absolute()
                and relative_path.as_posix() == relative
                and "." not in relative_path.parts
                and ".." not in relative_path.parts
                and relative != "inventory.sha256"
                and stays_within_root
            )
            if not path_is_safe:
                unsafe_paths.append(relative)
                continue
            if relative in entries:
                duplicate_paths.append(relative)
                continue
            entries[relative] = digest

    actual_files = sorted(
        path.relative_to(run_root).as_posix()
        for path in run_root.rglob("*")
        if path.is_file() and path != inventory_path
    )
    actual_file_set = set(actual_files)
    listed_file_set = set(entries)
    missing_paths = sorted(actual_file_set - listed_file_set)
    extra_paths = sorted(listed_file_set - actual_file_set)
    for relative, digest in entries.items():
        candidate = run_root / relative
        if (
            relative not in actual_file_set
            or base.sha256_file(candidate) != digest
        ):
            hash_failures.append(relative)

    verification_path = run_root / "VERIFICATION.json"
    retained_verification_digest = entries.get("VERIFICATION.json")
    archived_verification_retained = bool(
        verification_path.is_file()
        and retained_verification_digest is not None
        and retained_verification_digest
        == base.sha256_file(verification_path)
    )
    archived_verification_report_passed = False
    archived_verification_parse_error: str | None = None
    if verification_path.is_file():
        try:
            archived_verification = base.read_json(verification_path)
            archived_verification_report_passed = bool(
                isinstance(archived_verification, dict)
                and archived_verification.get("passed") is True
            )
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            archived_verification_parse_error = (
                f"{type(exc).__name__}: {exc}"
            )
    checks = {
        "inventory_exists_and_has_entries": (
            inventory_path.is_file() and bool(entries)
        ),
        "inventory_lines_have_exact_sha256_format": not malformed_lines,
        "inventory_paths_are_unique": not duplicate_paths,
        "inventory_paths_are_safe_canonical_run_relative_paths": (
            not unsafe_paths
        ),
        "inventory_covers_every_retained_file_except_itself_exactly": (
            not missing_paths and not extra_paths
        ),
        "inventory_all_listed_hashes_match": not hash_failures,
        "archived_verification_is_retained_when_required": (
            archived_verification_retained
            and archived_verification_report_passed
            if require_archived_verification
            else True
        ),
    }
    return {
        "path": str(inventory_path),
        "require_archived_verification": require_archived_verification,
        "entry_count": len(entries),
        "malformed_lines": malformed_lines,
        "unsafe_paths": unsafe_paths,
        "duplicate_paths": sorted(set(duplicate_paths)),
        "missing_paths": missing_paths,
        "extra_paths": extra_paths,
        "hash_failures": sorted(hash_failures),
        "retained_verification_sha256": retained_verification_digest,
        "archived_verification_report_passed": (
            archived_verification_report_passed
        ),
        "archived_verification_parse_error": (
            archived_verification_parse_error
        ),
        "checks": checks,
        "passed": all(checks.values()),
    }


def unified_number_provenance_is_exact(
    run_manifest: dict[str, Any],
    run_root: Path,
    expected_number: str,
) -> bool:
    """Tie the Dubai number and second-precision UTC name to one instant."""

    try:
        experiment_number = validated_experiment_number(
            str(run_manifest.get("experiment_number", ""))
        )
        start_local = datetime.fromisoformat(
            str(run_manifest.get("start_local", ""))
        )
        start_utc = datetime.strptime(
            str(run_manifest.get("start_utc", "")),
            "%Y%m%dT%H%M%SZ",
        ).replace(tzinfo=UTC)
        offset = start_local.utcoffset()
        if offset is None:
            return False
        fractional_second = (
            start_local.astimezone(UTC) - start_utc
        ).total_seconds()
    except (TypeError, ValueError):
        return False
    return bool(
        experiment_number == expected_number
        and run_manifest.get("experiment_number_format")
        == "YYMMDD-HHMMSS"
        and run_manifest.get("experiment_number_timezone")
        == "Asia/Dubai"
        and offset.total_seconds() == 4 * 3600
        and start_local.astimezone(
            ZoneInfo("Asia/Dubai")
        ).strftime("%y%m%d-%H%M%S")
        == experiment_number
        and start_local.astimezone(UTC).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        == run_manifest.get("start_utc")
        and 0.0 <= fractional_second < 1.0
        and experiment_number in str(run_manifest.get("run_id", ""))
        and run_manifest.get("run_id") == run_root.name
        and experiment_number in run_root.name
    )


def verify_documented_run(
    run_root: Path,
    *,
    require_archived_verification: bool = True,
) -> dict[str, Any]:
    values = cfg()
    label, center_mm, expected_centers, _ = configuration_identity(values)
    run_manifest = base.read_json(run_root / "run.json")
    experiment_number = validated_experiment_number(
        str(run_manifest.get("experiment_number", ""))
    )
    expected = expected_documented_media_campaign(
        values, experiment_number
    )
    campaign_total = len(expected)
    expected_role_ids = {
        role: {
            str(item["session_id"])
            for item in expected
            if item["role"] == role
        }
        for role in MOTION_ROLES
    }
    expected_ids = [str(item["session_id"]) for item in expected]

    inventory = _verify_exact_inventory(
        run_root,
        require_archived_verification=require_archived_verification,
    )

    manifest_paths = sorted(
        (run_root / "episodes").glob("*/episode.json")
    )
    manifests = [base.read_json(path) for path in manifest_paths]
    episode_directory_names_match = all(
        path.parent.name == str(manifest.get("episode_id", ""))
        for path, manifest in zip(manifest_paths, manifests)
    )
    by_id = {
        str(manifest.get("episode_id")): manifest
        for manifest in manifests
    }
    expected_by_id = {
        str(item["session_id"]): item for item in expected
    }
    motion_manifests = [
        by_id[episode_id]
        for episode_id in expected_ids
        if episode_id in by_id
    ]
    preparations = [
        manifest
        for manifest in manifests
        if manifest.get("role") == "preparation"
    ]
    unexpected_manifests = [
        manifest
        for manifest in manifests
        if manifest.get("role") != "preparation"
        and str(manifest.get("episode_id")) not in expected_by_id
    ]
    motion_roles_and_factors_are_exact = all(
        manifest.get("role") == expected_by_id[episode_id]["role"]
        and manifest.get("controller_id")
        == expected_by_id[episode_id]["condition_id"]
        and manifest.get("profile_id")
        == expected_by_id[episode_id]["profile_id"]
        and manifest.get("repeat_id")
        == expected_by_id[episode_id]["repeat_id"]
        for episode_id, manifest in (
            (episode_id, by_id[episode_id])
            for episode_id in expected_ids
            if episode_id in by_id
        )
    )
    media_results = [
        _verify_episode_media(
            run_root, by_id[episode_id], expected_by_id[episode_id]
        )
        for episode_id in expected_ids
        if episode_id in by_id
    ]
    alias_results = [
        verify_motor_data_hardlink_aliases(run_root, manifest)
        for manifest in motion_manifests
    ]
    preparation_alias_results = [
        verify_motor_data_hardlink_aliases(run_root, manifest)
        for manifest in preparations
    ]
    full_media = _verify_full_experiment_media(
        run_root, run_manifest, expected
    )
    lifecycle = _verify_media_lifecycle(
        run_root,
        run_manifest,
        expected,
        by_id,
    )
    host_path = run_root / "HOST_PREFLIGHT.json"
    host = (
        base.read_json(host_path)
        if host_path.is_file()
        else {}
    )

    data_results: list[dict[str, Any]] = []
    torque_columns: list[str] = []
    for manifest in manifests:
        episode_id = str(manifest.get("episode_id", ""))
        episode_root = run_root / "episodes" / episode_id
        episode_checks: dict[str, bool] = {}
        episode_errors: list[str] = []
        try:
            command = pd.read_parquet(
                episode_root / "command_events.parquet"
            )
            telemetry = pd.read_parquet(
                episode_root / "telemetry_events.parquet"
            )
            torque_columns.extend(
                column
                for column in [*command.columns, *telemetry.columns]
                if "torque" in column.lower()
                and "torque_enable" not in column.lower()
            )
            is_motion = manifest.get("role") in MOTION_ROLES
            episode_checks = {
                "tables_nonempty": len(command) > 0 and len(telemetry) > 0,
                "command_goal_gate_exact": bool(
                    command["goal_position_raw_requested"]
                    .between(1024, 3072)
                    .all()
                ),
                "measured_position_gate_exact": bool(
                    telemetry["present_position_raw"]
                    .between(1024, 3072)
                    .all()
                ),
                "motion_starts_with_raw_2048": (
                    not is_motion
                    or int(
                        command.iloc[0][
                            "goal_position_raw_requested"
                        ]
                    )
                    == 2048
                ),
                "motion_zero_contract_is_exact": (
                    not is_motion
                    or (
                        manifest.get("start_required_at_zero") is True
                        and manifest.get(
                            "zero_start_tolerance_ticks"
                        )
                        == 5
                        and manifest.get(
                            "experiment_start_goal_position_raw"
                        )
                        == 2048
                        and int(
                            manifest.get(
                                "experiment_start_position_error_ticks",
                                999,
                            )
                        )
                        <= 5
                        and abs(
                            int(
                                manifest.get(
                                    "experiment_start_position_raw_signed",
                                    0,
                                )
                            )
                            - 2048
                        )
                        <= 5
                    )
                ),
                "telemetry_values_are_finite_and_timing_passed": (
                    np.isfinite(
                        telemetry[
                            [
                                "position_meas_rad",
                                "velocity_meas_rad_s",
                                "current_meas_A",
                                "pwm_meas_fraction",
                                "input_voltage_V",
                                "temperature_C",
                            ]
                        ].to_numpy(dtype=float)
                    ).all()
                    and manifest.get(
                        "telemetry_timing_quality", {}
                    ).get("passed")
                    is True
                    and int(manifest.get("command_count", -1))
                    == len(command)
                    and int(manifest.get("telemetry_count", -1))
                    == len(telemetry)
                ),
                "hardware_status_remains_zero": bool(
                    telemetry["hardware_error_status_raw"].eq(0).all()
                ),
                "configuration_and_fixture_are_exact": (
                    manifest.get("mechanical_configuration") == label
                    and documented_fixture_identity_is_exact(
                        label,
                        manifest.get("fixture", {}),
                        expected_centers,
                    )
                ),
            }
        except (
            KeyError,
            OSError,
            ValueError,
            TypeError,
            IndexError,
        ) as exc:
            episode_errors.append(f"{type(exc).__name__}: {exc}")
        data_results.append(
            {
                "episode_id": episode_id,
                "checks": episode_checks,
                "errors": episode_errors,
                "passed": (
                    not episode_errors
                    and bool(episode_checks)
                    and all(episode_checks.values())
                ),
            }
        )

    calibration = [
        manifest
        for manifest in motion_manifests
        if manifest.get("role") == "calibration"
    ]
    selection = [
        manifest
        for manifest in motion_manifests
        if manifest.get("role") == "model_selection"
    ]
    pilots = [
        manifest
        for manifest in motion_manifests
        if manifest.get("role") == "pilot"
    ]
    held_out = [
        manifest
        for manifest in motion_manifests
        if manifest.get("role") == "held_out"
    ]
    observed_role_ids = {
        role: {
            str(item["episode_id"])
            for item in motion_manifests
            if item.get("role") == role
        }
        for role in MOTION_ROLES
    }
    expected_calibration_ids = {
        str(item["session_id"])
        for item in expected
        if "__P01_" in str(item["session_id"])
        or "__P02_" in str(item["session_id"])
        or "__P03_" in str(item["session_id"])
    }
    expected_selection_ids = {
        str(item["session_id"])
        for item in expected
        if "__P04_" in str(item["session_id"])
        or "__P05_" in str(item["session_id"])
    }
    camera_started = run_manifest.get(
        "camera_preflight_started_host_monotonic_ns"
    )
    motor_opened = run_manifest.get(
        "motor_device_opened_host_monotonic_ns"
    )
    host_completed = host.get("completed_host_monotonic_ns")
    camera_ready = run_manifest.get("camera_ready_status", {})
    media_summary = run_manifest.get("iphone_media_capture", {})
    checks = {
        "run_complete": run_manifest.get("terminal_status") == "complete",
        "run_identity_and_unified_number_are_exact": (
            int(run_manifest.get("schema_version", -1)) == 2
            and run_manifest.get("experiment_id") == values["experiment_id"]
            and run_manifest.get("mechanical_configuration") == label
            and unified_number_provenance_is_exact(
                run_manifest, run_root, experiment_number
            )
            and documented_fixture_identity_is_exact(
                label, run_manifest.get("fixture", {}), expected_centers
            )
            and (
                label not in {"M0", "B0"}
                or (
                    values.get("runner_mode") == "documented_media"
                    and run_manifest.get("collector_entrypoint")
                    == values.get("collector_entrypoint")
                )
            )
            and (label, center_mm)
            in {("M0", 0), ("B0", 60), ("B1", 80), ("B2", 100)}
        ),
        "read_only_latency_preflight_passed_at_exactly_1ms": (
            host_path.is_file()
            and host.get("passed") is True
            and host.get("observed_latency_timer_ms") == 1
            and host.get("configured_latency_timer_ms") == 1
            and host.get("motor_device_opened") is False
            and host.get("camera_service_started") is False
        ),
        "latency_then_fresh_camera_then_motor_order_is_exact": (
            host_completed is not None
            and camera_started is not None
            and motor_opened is not None
            and int(host_completed) <= int(camera_started)
            and int(camera_started) < int(motor_opened)
            and run_manifest.get(
                "camera_ready_before_motor_device_open"
            )
            is True
            and camera_ready.get("ready") is True
            and camera_ready.get("stream_ready") is True
            and camera_ready.get("asmagic_sdk_version") == "0.1.4"
            and float(
                camera_ready.get("last_color_frame_age_s", 999.0)
            )
            <= float(
                values["iphone_media_capture"]["snapshot_max_age_s"]
            )
        ),
        "manifest_set_contains_only_canonical_motion_or_preparation": (
            episode_directory_names_match
            and len(by_id) == len(manifests)
            and not unexpected_manifests
            and motion_roles_and_factors_are_exact
            and all(
                item.get("role") in MOTION_ROLES
                or item.get("role") == "preparation"
                for item in manifests
            )
            and len(run_manifest.get("episode_ids", []))
            == len(manifests)
            and set(run_manifest.get("episode_ids", [])) == set(by_id)
            and [
                episode_id
                for episode_id in run_manifest.get("episode_ids", [])
                if episode_id in expected_by_id
            ]
            == expected_ids
        ),
        "all_recenter_preparation_data_has_unified_no_copy_names": (
            len(preparation_alias_results) == len(preparations)
            and all(item["passed"] for item in preparation_alias_results)
            and all(
                item.get("experiment_number") == experiment_number
                and str(item.get("scene_label", "")).startswith(
                    f"H1-{label}-RECENTER-"
                )
                and item.get("artifact_prefix")
                == (
                    f"{experiment_number}_"
                    + str(item.get("scene_label", ""))
                )
                and item.get(
                    "excluded_from_recorded_media_campaign"
                )
                is True
                and item.get("campaign_ordinal") is None
                and item.get("campaign_total_episodes") == campaign_total
                and item.get("media", {}).get("status")
                == "not_recorded_preparation"
                and item.get("media", {}).get("experiment_number")
                == experiment_number
                for item in preparations
            )
        ),
        "exact_configured_motion_manifest_set": (
            len(motion_manifests) == campaign_total
            and set(by_id).issuperset(expected_ids)
        ),
        "recorded_motion_order_is_exact": (
            run_manifest.get("recorded_motion_episode_ids")
            == expected_ids
            and [
                manifest.get("campaign_ordinal")
                for manifest in motion_manifests
            ]
            == list(
                range(
                    1,
                    campaign_total + 1,
                )
            )
        ),
        "role_counts_and_factor_matrix_are_exact": (
            observed_role_ids == expected_role_ids
            and len(pilots) == len(expected_role_ids["pilot"])
            and len(calibration) == len(expected_role_ids["calibration"])
            and len(selection) == len(expected_role_ids["model_selection"])
            and len(held_out) == len(expected_role_ids["held_out"])
            and {item["episode_id"] for item in calibration}
            == expected_calibration_ids
            and {item["episode_id"] for item in selection}
            == expected_selection_ids
        ),
        "run_manifest_role_counts_are_exact": (
            int(run_manifest.get("pilot_episode_count", -1))
            == len(expected_role_ids["pilot"])
            and int(run_manifest.get("calibration_episode_count", -1))
            == len(expected_role_ids["calibration"])
            and int(
                run_manifest.get("model_selection_episode_count", -1)
            )
            == len(expected_role_ids["model_selection"])
            and int(
                run_manifest.get(
                    "held_out_episode_count",
                    0 if label == "B2" else -1,
                )
            )
            == len(expected_role_ids["held_out"])
        ),
        "all_motion_and_preparation_manifests_complete_and_safe": (
            bool(manifests)
            and all(
                item.get("completion_status") == "complete"
                and item.get("terminal_torque_disabled") is True
                and item.get(
                    "critical_registers_match_before_after"
                )
                is True
                for item in manifests
            )
        ),
        "all_motor_tables_pass": (
            len(data_results) == len(manifests)
            and all(item["passed"] for item in data_results)
        ),
        "no_manufactured_torque_column": not torque_columns,
        "exact_configured_complete_media_sessions": (
            media_summary.get("status") == "complete"
            and int(media_summary.get("session_count", -1))
            == campaign_total
            and int(
                media_summary.get("expected_session_count", -1)
            )
            == campaign_total
            and int(
                media_summary.get("complete_session_count", -1)
            )
            == campaign_total
            and len(media_results) == campaign_total
            and all(item["passed"] for item in media_results)
        ),
        "full_paired_campaign_media_passes": full_media["passed"],
        "camera_lifecycle_counts_order_and_finalize_timing_pass": (
            lifecycle["passed"]
        ),
        "exact_configured_no_copy_motor_alias_sets": (
            len(alias_results) == campaign_total
            and all(item["passed"] for item in alias_results)
        ),
        "terminal_torque_disable_and_bus_close_confirmed": (
            run_manifest.get("terminal_torque_disabled") is True
            and run_manifest.get("motor_bus_close_succeeded") is True
            and run_manifest.get(
                "motor_bus_closed_host_monotonic_ns"
            )
            is not None
            and run_manifest.get(
                "media_finalized_after_motor_bus_close"
            )
            is True
        ),
        "inventory_nonempty_and_all_hashes_match": inventory["passed"],
        "inventory_lines_paths_and_exact_file_coverage_pass": (
            inventory["passed"]
        ),
        "archived_verification_retained_when_required": (
            inventory["checks"][
                "archived_verification_is_retained_when_required"
            ]
        ),
        "summary_and_human_documents_exist": (
            (run_root / "episode-summary.csv").is_file()
            and (
                run_root / f"{label}_METHOD_AND_RESULTS.md"
            ).is_file()
            and (run_root / "COMMAND_LOG.md").is_file()
            and (run_root / "START_HERE.md").is_file()
        ),
    }
    return {
        "run_root": str(run_root),
        "experiment_number": experiment_number,
        "checks": checks,
        "episode_manifest_count": len(manifests),
        "preparation_episode_count": len(preparations),
        "recorded_motion_episode_count": len(motion_manifests),
        "pilot_episode_count": len(pilots),
        "calibration_episode_count": len(calibration),
        "model_selection_episode_count": len(selection),
        "held_out_episode_count": len(held_out),
        "inventory_entry_count": inventory["entry_count"],
        "inventory_hash_failures": inventory["hash_failures"],
        "inventory_verification": inventory,
        "torque_measurement_columns": sorted(set(torque_columns)),
        "episode_data_verifications": data_results,
        "media_verifications": media_results,
        "motor_data_alias_verifications": alias_results,
        "full_experiment_media_verification": full_media,
        "media_lifecycle_verification": lifecycle,
        "host_timing_preflight": host,
        "passed": all(checks.values()),
    }


def verify_run(
    run_root: Path,
    *,
    require_archived_verification: bool = True,
) -> dict[str, Any]:
    """Verify documented runs strictly while retaining legacy M0/B0 support."""

    run_manifest = base.read_json(run_root / "run.json")
    if (
        int(run_manifest.get("schema_version", 1)) >= 2
        and run_manifest.get("experiment_number") is not None
    ):
        if require_archived_verification:
            return verify_documented_run(run_root)
        return verify_documented_run(
            run_root, require_archived_verification=False
        )
    if run_manifest.get("mechanical_configuration") == "M0":
        legacy_path = HERE / "experiment_config.json"
        prior_path = base.CONFIG_PATH
        prior_config = base.config
        try:
            base.CONFIG_PATH = legacy_path
            base.config = lambda: base.read_json(legacy_path)
            return base.verify_run(run_root)
        finally:
            base.CONFIG_PATH = prior_path
            base.config = prior_config
    return verify_legacy_run(run_root)


def write_archived_verification(
    run_root: Path,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Retain the exact verification report in the regenerated inventory."""

    base.write_inventory(run_root)
    verification = verify_run(
        run_root,
        require_archived_verification=False,
    )
    verification["archive_policy"] = {
        "path": "VERIFICATION.json",
        "verification_basis": (
            "the preliminary inventory containing every artifact that "
            "existed before VERIFICATION.json"
        ),
        "final_inventory_action": (
            "inventory.sha256 was regenerated after this report was written"
        ),
    }
    verification_path = run_root / "VERIFICATION.json"
    base.write_json(verification_path, verification)
    inventory_digest = base.write_inventory(run_root)
    expected_digest = base.sha256_file(verification_path)
    entries = {
        relative: digest
        for digest, relative in (
            line.split("  ", 1)
            for line in (run_root / "inventory.sha256")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
    }
    retained_digest = entries.get("VERIFICATION.json")
    archive = {
        "verification_path": str(verification_path),
        "expected_sha256": expected_digest,
        "inventory_sha256": retained_digest,
        "retained_in_final_inventory": retained_digest == expected_digest,
    }
    if not archive["retained_in_final_inventory"]:
        raise RuntimeError(
            "final inventory did not retain VERIFICATION.json"
        )
    return inventory_digest, verification, archive
def run_documented() -> dict[str, Any]:
    """Collect a fail-closed documented balanced campaign with media."""

    offline = validate()
    if not offline["passed"]:
        return {
            "status": "blocked_by_offline_validation",
            "passed": False,
            "motion_executed": False,
            "motor_device_opened": False,
            "recording_started": False,
        }
    available = base.availability()
    if not available["available"]:
        return {
            "status": "blocked_device_absent_or_owned",
            "availability": available,
            "passed": False,
            "motion_executed": False,
            "motor_device_opened": False,
            "recording_started": False,
        }

    values = cfg()
    label, center_mm, _, stem = configuration_identity(values)
    collector_entrypoint = str(
        values.get("collector_entrypoint", f"collect_{stem}.py")
    )
    if not documented_campaign_enabled(values):
        raise RuntimeError(
            "documented campaign requires B1/B2 or an explicit M0/B0 "
            "documented_media overlay"
        )
    run_started_utc = datetime.now(UTC)
    run_started_local = run_started_utc.astimezone(
        ZoneInfo("Asia/Dubai")
    )
    timestamp = run_started_utc.strftime("%Y%m%dT%H%M%SZ")
    experiment_number = validated_experiment_number(
        run_started_local.strftime("%y%m%d-%H%M%S")
    )
    campaign_total = documented_campaign_total(values)
    campaign_plan = expected_documented_media_campaign(
        values, experiment_number
    )
    role_totals = documented_campaign_role_counts(values)
    fixture_slug = "no-payload" if label == "M0" else f"{center_mm}mm"
    run_root = base.RAW_ROOT / (
        f"v5-{stem}-{fixture_slug}-"
        f"{experiment_number}-{timestamp}-{uuid.uuid4().hex[:8]}"
    )
    run_root.mkdir(parents=True, exist_ok=False)
    all_manifests: list[dict[str, Any]] = []
    campaign_error: str | None = None
    terminal_torque_disabled = False
    motor_device_opened = False
    motor_bus_close_succeeded = False
    motor_bus_closed_host_monotonic_ns: int | None = None
    motor_device_opened_host_monotonic_ns: int | None = None
    camera_preflight_started_host_monotonic_ns: int | None = None
    camera_ready_before_motor_open = False
    camera_ready_status: dict[str, Any] | None = None
    terminal_cleanup: dict[str, Any] | None = None
    media_summary: dict[str, Any] = {
        "status": "preparing",
        "session_count": 0,
        "expected_session_count": campaign_total,
        "complete_session_count": 0,
        "index": None,
        "setup_photo": None,
        "derived_video_has_audio": False,
        "errors": [],
    }
    capture = ExperimentMediaCapture(
        values,
        run_root,
        experiment_number=experiment_number,
    )
    write_start_here(run_root, values)
    host_preflight = host_timing_preflight(values)
    base.write_json(run_root / "HOST_PREFLIGHT.json", host_preflight)

    def add_campaign_error(message: str) -> None:
        nonlocal campaign_error
        campaign_error = (
            f"{campaign_error}; {message}" if campaign_error else message
        )

    try:
        try:
            if not host_preflight["passed"]:
                raise MediaCaptureError(
                    "read-only 1 ms host timing preflight failed: "
                    f"{host_preflight}"
                )
            camera_preflight_started_host_monotonic_ns = (
                time.monotonic_ns()
            )
            ready = capture.start_service()
            age = ready.get("last_color_frame_age_s")
            if age is None:
                age = ready.get("last_frame_age_s")
            if (
                ready.get("asmagic_sdk_version") != "0.1.4"
                or age is None
                or float(age)
                > float(
                    values["iphone_media_capture"][
                        "snapshot_max_age_s"
                    ]
                )
            ):
                raise MediaCaptureError(
                    "camera service returned without the required fresh "
                    "asMagic 0.1.4 color frame"
                )
            camera_ready_before_motor_open = True
            camera_ready_status = {
                "ready": bool(ready.get("ready")),
                "stream_ready": bool(ready.get("stream_ready")),
                "last_frame_age_s": ready.get("last_frame_age_s"),
                "last_color_frame_age_s": age,
                "asmagic_sdk_version": ready.get(
                    "asmagic_sdk_version"
                ),
                "receiver_frames": ready.get("receiver_frames"),
            }
        except (MediaCaptureError, OSError, ValueError) as exc:
            add_campaign_error(
                "camera preflight blocked hardware open: "
                f"{type(exc).__name__}: {exc}"
            )
            media_summary.update(
                {
                    "status": "blocked_before_hardware",
                    "errors": [str(exc)],
                }
            )

        if camera_ready_before_motor_open:
            bus: DynamixelBus | None = None
            try:
                with base.hardware_lock():
                    if not base.availability()["available"]:
                        raise RuntimeError(
                            "serial device became owned before campaign open"
                        )
                    bus = DynamixelBus(
                        str(values["serial_port"]),
                        int(values["baud_rate_bps"]),
                    )
                    motor_device_opened_host_monotonic_ns = (
                        time.monotonic_ns()
                    )
                    motor_device_opened = True
                    try:
                        discovered = bus.discover()
                        base.disable_discovered(bus, discovered)
                        if (
                            set(discovered) != {5}
                            or discovered[5]["model_number"]
                            != int(values["expected_model_number"])
                        ):
                            raise RuntimeError(
                                "exact ID5/model identity gate failed: "
                                f"{discovered}"
                            )
                        canonicalization = (
                            base.canonicalize_torque_off_position_counter(
                                bus
                            )
                        )
                        base.write_json(
                            run_root
                            / "position-counter-canonicalization.json",
                            canonicalization,
                        )
                        live = base.read_only_status_on_open_bus(bus)
                        live["fixture_declaration"] = values["fixture"]
                        live[
                            "camera_ready_before_motor_device_open"
                        ] = True
                        base.write_json(
                            run_root / "live-preflight.json", live
                        )
                        if not live["passed"]:
                            raise RuntimeError(
                                f"live preflight failed: {live['checks']}"
                            )

                        recenter_index = ensure_zero_documented(
                            bus,
                            run_root,
                            1,
                            all_manifests,
                            experiment_number=experiment_number,
                        )
                        pilot = pilot_profile(values)
                        generated = executed_profiles(values)
                        profiles_by_id = {
                            "PILOT_LOW_AMPLITUDE": pilot,
                            **generated,
                        }
                        role_progress = {
                            role: 0 for role in MOTION_ROLES
                        }
                        for planned in campaign_plan:
                            recenter_index = ensure_zero_documented(
                                bus,
                                run_root,
                                recenter_index,
                                all_manifests,
                                experiment_number=experiment_number,
                            )
                            media_ordinal = int(
                                planned["campaign_ordinal"]
                            )
                            episode_id = str(planned["session_id"])
                            role = str(planned["role"])
                            condition_id = str(planned["condition_id"])
                            profile_id = str(planned["profile_id"])
                            repeat_id = planned["repeat_id"]
                            role_progress[role] += 1
                            print(
                                f"{role.upper()} "
                                f"{role_progress[role]:02d}/"
                                f"{role_totals[role]:02d} "
                                f"(session {media_ordinal:02d}/"
                                f"{campaign_total:02d}): {episode_id}",
                                flush=True,
                            )
                            manifest = run_documented_episode(
                                bus=bus,
                                run_root=run_root,
                                capture=capture,
                                media_ordinal=media_ordinal,
                                episode_id=episode_id,
                                condition_id=condition_id,
                                profile=profiles_by_id[profile_id],
                                role=role,
                                repeat_id=repeat_id,
                                manifests=all_manifests,
                            )
                            print(
                                f"RESULT {episode_id}: "
                                f"{manifest['completion_status']}",
                                flush=True,
                            )
                    finally:
                        terminal_cleanup = (
                            documented_support.cleanup_motor_bus_safely(
                                bus,
                                device_id=int(values["dynamixel_id"]),
                                torque_disable_attempts=3,
                            )
                        )
                        for error in terminal_cleanup["errors"]:
                            add_campaign_error(
                                "terminal motor cleanup: " + error
                            )
                        terminal_torque_disabled = bool(
                            terminal_cleanup["torque_disabled"]
                        )
                        if terminal_cleanup["bus_closed"]:
                            motor_bus_close_succeeded = True
                            motor_bus_closed_host_monotonic_ns = (
                                terminal_cleanup[
                                    "bus_closed_host_monotonic_ns"
                                ]
                            )
                            bus = None
            except (
                KeyboardInterrupt,
                RuntimeError,
                OSError,
                ValueError,
                MediaCaptureError,
            ) as exc:
                add_campaign_error(f"{type(exc).__name__}: {exc}")
            finally:
                if bus is not None:
                    outer_cleanup = (
                        documented_support.cleanup_motor_bus_safely(
                            bus,
                            device_id=int(values["dynamixel_id"]),
                            torque_disable_attempts=3,
                        )
                    )
                    if terminal_cleanup is None:
                        terminal_cleanup = outer_cleanup
                    else:
                        terminal_cleanup["outer_retry"] = outer_cleanup
                    for error in outer_cleanup["errors"]:
                        add_campaign_error(
                            "outer terminal motor cleanup: " + error
                        )
                    if outer_cleanup["torque_disabled"]:
                        terminal_torque_disabled = True
                    if outer_cleanup["bus_closed"]:
                        motor_bus_close_succeeded = True
                        motor_bus_closed_host_monotonic_ns = (
                            outer_cleanup[
                                "bus_closed_host_monotonic_ns"
                            ]
                        )
                        bus = None

        motor_cleanup_confirmed = (
            not motor_device_opened
            or (
                terminal_torque_disabled
                and motor_bus_close_succeeded
            )
        )
        motion_manifests = [
            item
            for item in all_manifests
            if item.get("role") in MOTION_ROLES
        ]
        if camera_ready_before_motor_open and motor_cleanup_confirmed:
            if capture.current_session is not None:
                try:
                    capture.stop_episode(
                        outcome="aborted_after_motor_cleanup",
                        events=[
                            {
                                "label": (
                                    "emergency stop after confirmed "
                                    "motor cleanup"
                                ),
                                "host_monotonic_ns": time.monotonic_ns(),
                            }
                        ],
                    )
                except MediaCaptureError as exc:
                    add_campaign_error(
                        "camera emergency STOP after bus close: "
                        f"{type(exc).__name__}: {exc}"
                    )
            try:
                service_status = capture.status()
                retained_sessions = int(
                    service_status.get(
                        "session_count",
                        len(capture.session_results),
                    )
                )
                if (
                    retained_sessions
                    and terminal_torque_disabled
                    and motor_bus_close_succeeded
                ):
                    capture.finalize(
                        {
                            "run_id": run_root.name,
                            "experiment_id": values["experiment_id"],
                            "mechanical_configuration": label,
                            "experiment_number": experiment_number,
                            "scene_label": label,
                            "campaign_artifact_prefix": (
                                f"{experiment_number}_{label}"
                            ),
                            "episode_ids": [
                                item["episode_id"]
                                for item in motion_manifests
                            ],
                            "motor_bus_close_succeeded": True,
                            "motor_bus_closed_before_finalize": True,
                            "terminal_torque_disabled": True,
                        }
                    )
                    media_summary = capture.apply_finalize_result(
                        motion_manifests
                    )
                elif retained_sessions:
                    message = (
                        "camera FINALIZE skipped because torque disable "
                        "and serial close were not both confirmed"
                    )
                    add_campaign_error(message)
                    media_summary.update(
                        {
                            "status": (
                                "raw_capture_retained_not_finalized"
                            ),
                            "session_count": retained_sessions,
                            "complete_session_count": 0,
                            "errors": [message],
                        }
                    )
                else:
                    media_summary.update(
                        {
                            "status": "no_episodes_captured",
                            "session_count": 0,
                            "complete_session_count": 0,
                            "errors": [],
                        }
                    )
            except (
                KeyboardInterrupt,
                MediaCaptureError,
                OSError,
                ValueError,
            ) as exc:
                add_campaign_error(
                    "camera finalization after bus close: "
                    f"{type(exc).__name__}: {exc}"
                )
                media_summary.update(
                    {
                        "status": "failed",
                        "session_count": len(
                            capture.session_results
                        ),
                        "complete_session_count": 0,
                        "errors": [str(exc)],
                    }
                )
        elif camera_ready_before_motor_open:
            message = (
                "camera finalization skipped because terminal motor "
                "cleanup was not confirmed"
            )
            add_campaign_error(message)
            media_summary.update(
                {
                    "status": (
                        "motor_cleanup_unconfirmed_not_finalized"
                    ),
                    "session_count": (
                        len(capture.session_results)
                        + int(capture.current_session is not None)
                    ),
                    "complete_session_count": 0,
                    "errors": [message],
                }
            )
    finally:
        try:
            capture.shutdown()
        except (RuntimeError, OSError) as exc:
            add_campaign_error(
                "camera service shutdown: "
                f"{type(exc).__name__}: {exc}"
            )

    for manifest in all_manifests:
        base.write_json(
            run_root
            / "episodes"
            / manifest["episode_id"]
            / "episode.json",
            manifest,
        )

    motion_manifests = [
        item
        for item in all_manifests
        if item.get("role") in MOTION_ROLES
    ]
    pilots = [
        item for item in motion_manifests if item["role"] == "pilot"
    ]
    calibration = [
        item
        for item in motion_manifests
        if item["role"] == "calibration"
    ]
    selection = [
        item
        for item in motion_manifests
        if item["role"] == "model_selection"
    ]
    held_out = [
        item
        for item in motion_manifests
        if item["role"] == "held_out"
    ]
    observed_role_counts = {
        "pilot": len(pilots),
        "calibration": len(calibration),
        "model_selection": len(selection),
        "held_out": len(held_out),
    }
    media_complete = (
        media_summary.get("status") == "complete"
        and int(media_summary.get("session_count", -1))
        == campaign_total
        and int(media_summary.get("complete_session_count", -1))
        == campaign_total
        and all(
            item.get("media", {}).get("status") == "complete"
            for item in motion_manifests
        )
    )
    if not camera_ready_before_motor_open:
        terminal_status = "blocked_before_hardware"
    else:
        terminal_status = (
            "complete"
            if (
                campaign_error is None
                and observed_role_counts == role_totals
                and len(motion_manifests) == campaign_total
                and all(
                    item["completion_status"] == "complete"
                    for item in all_manifests
                )
                and terminal_torque_disabled
                and motor_bus_close_succeeded
                and media_complete
            )
            else "incomplete"
        )

    run_manifest = {
        "schema_version": 2,
        "experiment_id": values["experiment_id"],
        "collector_entrypoint": collector_entrypoint,
        "run_id": run_root.name,
        "experiment_number": experiment_number,
        "experiment_number_format": "YYMMDD-HHMMSS",
        "experiment_number_timezone": "Asia/Dubai",
        "start_local": run_started_local.isoformat(),
        "mechanical_configuration": label,
        "fixture": values["fixture"],
        "dynamixel_id": int(values["dynamixel_id"]),
        "source_type": "new_V5_physical_hardware_measurement",
        "start_utc": timestamp,
        "end_utc": datetime.now(UTC).isoformat(),
        "host_platform": platform.platform(),
        "operator_declared_u2d2_usb_latency_timer_ms": int(
            values[
                "operator_declared_u2d2_usb_latency_timer_ms"
            ]
        ),
        "host_timing_preflight": host_preflight,
        "camera_preflight_started_host_monotonic_ns": (
            camera_preflight_started_host_monotonic_ns
        ),
        "motor_device_opened_host_monotonic_ns": (
            motor_device_opened_host_monotonic_ns
        ),
        "episode_ids": [
            item["episode_id"] for item in all_manifests
        ],
        "recorded_motion_episode_ids": [
            item["episode_id"] for item in motion_manifests
        ],
        "pilot_episode_count": len(pilots),
        "calibration_episode_count": len(calibration),
        "model_selection_episode_count": len(selection),
        "held_out_episode_count": len(held_out),
        "preparation_episode_count": sum(
            item["role"] == "preparation"
            for item in all_manifests
        ),
        "camera_ready_before_motor_device_open": (
            camera_ready_before_motor_open
        ),
        "camera_ready_status": camera_ready_status,
        "motor_device_opened": motor_device_opened,
        "motor_bus_close_succeeded": motor_bus_close_succeeded,
        "motor_bus_closed_host_monotonic_ns": (
            motor_bus_closed_host_monotonic_ns
        ),
        "terminal_motor_cleanup": terminal_cleanup,
        "iphone_media_capture": media_summary,
        "media_finalized_after_motor_bus_close": (
            capture.finalize_result is not None
            and terminal_torque_disabled
            and motor_bus_close_succeeded
        ),
        "campaign_error": campaign_error,
        "terminal_torque_disabled": terminal_torque_disabled,
        "terminal_status": terminal_status,
        f"stopped_after_{label}": True,
    }
    base.write_json(run_root / "run.json", run_manifest)
    summary = base.summarize_run(run_root, all_manifests)
    write_method_results(run_root, summary)
    write_start_here(
        run_root,
        values,
        run_manifest=run_manifest,
        media_summary=media_summary,
        manifests=motion_manifests,
    )
    fixture_log_line = (
        "M0 motor-only; no horn, link, pin, payload, or payload centers; 0 g external moving mass"
        if label == "M0"
        else f"{label} with centers at -{center_mm} mm and +{center_mm} mm"
    )
    (run_root / "COMMAND_LOG.md").write_text(
        "# Command log\n\n"
        f"- Command: {collector_entrypoint} --run.\n"
        f"- Unified experiment number: {experiment_number}.\n"
        "- Host latency was read and required to be exactly 1 ms "
        "before camera startup.\n"
        "- A fresh asMagic 0.1.4 AR frame was required before serial "
        "open.\n"
        f"- Fixture: {fixture_log_line}.\n"
        f"- Motion sessions: {len(motion_manifests)}/{campaign_total}; "
        f"pilots {len(pilots)}/{role_totals['pilot']}; calibration "
        f"{len(calibration)}/{role_totals['calibration']}; model selection "
        f"{len(selection)}/{role_totals['model_selection']}; held out "
        f"{len(held_out)}/{role_totals['held_out']}.\n"
        f"- Media sessions finalized: "
        f"{media_summary.get('complete_session_count', 0)}/"
        f"{campaign_total}.\n"
        f"- Terminal torque disabled: {terminal_torque_disabled}.\n"
        f"- Motor bus closed before media finalization: "
        f"{motor_bus_close_succeeded}.\n"
        f"- Collection status before independent verification: "
        f"{terminal_status}.\n"
        f"- Campaign error: {campaign_error}.\n",
        encoding="utf-8",
    )
    inventory_digest, verification, verification_archive = (
        write_archived_verification(run_root)
    )
    write_report(f"{stem}_last_verification.json", verification)
    result = {
        "run_root": str(run_root),
        "experiment_number": experiment_number,
        "terminal_status": terminal_status,
        "pilot_episode_count": len(pilots),
        "calibration_episode_count": len(calibration),
        "model_selection_episode_count": len(selection),
        "held_out_episode_count": len(held_out),
        "preparation_episode_count": sum(
            item["role"] == "preparation"
            for item in all_manifests
        ),
        "media_capture_status": media_summary.get("status"),
        "media_session_count": media_summary.get(
            "session_count", 0
        ),
        "campaign_error": campaign_error,
        "motor_device_opened": motor_device_opened,
        "motor_bus_close_succeeded": motor_bus_close_succeeded,
        "terminal_torque_disabled": terminal_torque_disabled,
        "inventory_sha256": inventory_digest,
        "verification_path": str(run_root / "VERIFICATION.json"),
        "verification_archive": verification_archive,
        "verification": verification,
        "motion_executed": bool(all_manifests),
        "passed": (
            terminal_status == "complete"
            and verification["passed"]
        ),
    }
    write_report(f"{stem}_last_run.json", result)
    return result


def run() -> dict[str, Any]:
    """Dispatch explicit schema-2 campaigns while preserving legacy B0."""

    values = cfg()
    if documented_campaign_enabled(values):
        return run_documented()
    return run_legacy()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--validate", action="store_true")
    actions.add_argument("--availability", action="store_true")
    actions.add_argument("--camera-status", action="store_true")
    actions.add_argument("--status", action="store_true")
    actions.add_argument("--run", action="store_true")
    actions.add_argument("--verify", type=Path)
    actions.add_argument("--finalize", type=Path)
    args = parser.parse_args()
    if args.validate:
        result = validate()
    elif args.availability:
        result = base.availability()
        result["passed"] = result["available"]
    elif args.camera_status:
        result = iphone_camera_status()
    elif args.status:
        result = status()
    elif args.run:
        result = run()
    elif args.finalize:
        result = finalize_existing(args.finalize)
    else:
        result = verify_run(args.verify.resolve())
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0 if result.get("passed", False) else 2


if __name__ == "__main__":
    raise SystemExit(main())
