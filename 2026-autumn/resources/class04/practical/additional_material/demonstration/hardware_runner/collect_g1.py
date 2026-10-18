#!/usr/bin/env python3
"""Collect V5 G1 +60/+100 mm untouched P06/P07 hardware episodes."""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import collect_m0 as base
from dynamixel_io import DynamixelBus
from experiment_media import (
    ExperimentMediaCapture,
    MediaCaptureError,
    camera_only_status,
    episode_media_identity,
    validated_experiment_number,
    write_start_here,
)
from profiles import (
    authoritative_active_profiles,
    executed_profiles,
    pilot_profile,
    profile_statistics,
)


HERE = Path(__file__).resolve().parent
BASE_CONFIG_PATH = HERE / "experiment_config.json"
G1_CONFIG_PATH = HERE / "experiment_config_g1.json"


def config() -> dict[str, Any]:
    inherited = copy.deepcopy(base.read_json(BASE_CONFIG_PATH))
    overlay = base.read_json(G1_CONFIG_PATH)
    for key, value in overlay.items():
        if key not in {"extends", "profiles"}:
            inherited[key] = copy.deepcopy(value)
    inherited["profiles"] = copy.deepcopy(overlay["profiles"])
    return inherited


base.config = config


def write_report(name: str, value: Any) -> None:
    base.write_json(base.REPORT_ROOT / name, value)


def host_timing_preflight(
    values: dict[str, Any],
    *,
    sys_class_tty_root: Path = Path("/sys/class/tty"),
) -> dict[str, Any]:
    """Read and enforce the U2D2 USB latency timer without opening serial."""

    started_wall_ns = time.time_ns()
    started_monotonic_ns = time.monotonic_ns()
    serial_port = Path(str(values["serial_port"]))
    resolved_serial_port = serial_port.resolve(strict=False)
    tty_name = resolved_serial_port.name
    latency_path = sys_class_tty_root / tty_name / "device" / "latency_timer"
    configured_ms = int(
        values["operator_declared_u2d2_usb_latency_timer_ms"]
    )
    observed_ms: int | None = None
    read_error: str | None = None
    raw_value: str | None = None
    try:
        raw_value = latency_path.read_text(encoding="utf-8").strip()
        observed_ms = int(raw_value)
    except (OSError, ValueError) as exc:
        read_error = f"{type(exc).__name__}: {exc}"

    checks = {
        "configured_latency_timer_is_exactly_1_ms": configured_ms == 1,
        "latency_timer_sysfs_value_is_readable_integer": (
            read_error is None and observed_ms is not None
        ),
        "observed_latency_timer_is_exactly_1_ms": observed_ms == 1,
    }
    completed_wall_ns = time.time_ns()
    completed_monotonic_ns = time.monotonic_ns()
    return {
        "operation": "read_only_u2d2_usb_latency_timer_preflight",
        "serial_port": str(serial_port),
        "resolved_serial_port": str(resolved_serial_port),
        "tty_name": tty_name,
        "latency_timer_path": str(latency_path),
        "required_latency_timer_ms": 1,
        "configured_latency_timer_ms": configured_ms,
        "observed_latency_timer_ms": observed_ms,
        "raw_sysfs_value": raw_value,
        "read_error": read_error,
        "started_host_wall_time_ns": started_wall_ns,
        "started_host_monotonic_ns": started_monotonic_ns,
        "completed_host_wall_time_ns": completed_wall_ns,
        "completed_host_monotonic_ns": completed_monotonic_ns,
        "checks": checks,
        "passed": all(checks.values()),
        "motor_device_opened": False,
        "camera_service_started": False,
        "motion_executed": False,
    }


def accept_stable_passive_gravity_rest(
    result: dict[str, Any], values: dict[str, Any]
) -> dict[str, Any]:
    """Accept torque-off G1 rest below 1024 without widening command goals."""

    position = int(result["present_position_raw_signed"])
    passive_minimum = int(values["gravity_passive_transient_min_raw"])
    command_maximum = int(values["software_goal_max_raw"])
    passive_ok = passive_minimum <= position <= command_maximum
    excluded = {
        "position_inside_software_gate",
        "physical_equivalent_position_inside_software_gate",
    }
    other_checks_pass = all(
        bool(value)
        for name, value in result["checks"].items()
        if name not in excluded
    )
    result["checks"]["stable_passive_gravity_rest_inside_950_3072"] = passive_ok
    result["commanded_goal_gate_remains_1024_3072"] = True
    result["passed"] = passive_ok and other_checks_pass
    return result


def validate() -> dict[str, Any]:
    values = config()
    dt_s = 1.0 / float(values["command_rate_hz"])
    active = authoritative_active_profiles(values)
    executed = executed_profiles(values)
    zero = int(values["servo_zero_raw"])
    minimum = int(values["software_goal_min_raw"])
    maximum = int(values["software_goal_max_raw"])
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
    fixture = values["fixture"]
    media = values["iphone_media_capture"]
    media_python = Path(str(media["python_executable"]))
    media_script = Path(str(media["service_script"]))
    if not media_script.is_absolute():
        media_script = HERE / media_script
    checks = {
        "scope_is_G1": values["mechanical_configuration"] == "G1",
        "corrected_centers_are_plus60_plus100mm": fixture[
            "payload_center_positions_mm"
        ]
        == [60, 100]
        and fixture["payload_side"] == "positive",
        "PDF_plus50_plus100_geometry_explicitly_superseded": fixture[
            "pdf_preliminary_center_positions_mm_superseded"
        ]
        == [50, 100],
        "old_PDF_mass_properties_not_reused": "invalid" in fixture[
            "mass_property_status"
        ].lower(),
        "common_weight_50pct_infill_recorded": fixture[
            "payload_print_infill_percent"
        ]
        == 50
        and "same" in fixture["payload_commonality"].lower(),
        "recollection_fixture_mass_declaration_exact": fixture.get(
            "fixture_revision"
        )
        == "2026-08-26-recollection-110g"
        and int(fixture.get("complete_payload_mass_each_g", -1)) == 44
        and fixture.get("complete_payload_includes_pin") is True
        and int(fixture.get("payload_count", -1)) == 2
        and int(fixture.get("link_mass_g", -1)) == 22
        and int(fixture.get("total_external_moving_mass_g", -1)) == 110
        and abs(float(fixture.get("payload_point_inertia_kg_m2", -1.0)) - 0.0005984)
        < 1e-12
        and abs(float(fixture.get("payload_first_moment_kg_m", -1.0)) - 0.00704)
        < 1e-12,
        "target_is_ID5": int(values["dynamixel_id"]) == 5,
        "operator_declared_u2d2_usb_latency_timer_is_1ms": int(
            values["operator_declared_u2d2_usb_latency_timer_ms"]
        )
        == 1,
        "tick_to_tick_zero_is_2048": zero == 2048,
        "gravity_active_zero_acquisition_enabled": values[
            "gravity_loaded_active_zero_start"
        ]
        is True,
        "gravity_zero_method_preserves_first_experiment_command": (
            "first experimental command is raw 2048"
            in values["gravity_zero_acquisition_method"]
        ),
        "gravity_rest_wait_is_declared": float(
            values["gravity_rest_settle_s"]
        )
        >= 3.0
        and int(values["gravity_rest_stability_span_ticks"]) <= 4
        and int(values["gravity_passive_transient_min_raw"]) == 950,
        "gravity_measured_gate_entry_hysteresis_is_exact": int(
            values[
                "gravity_measured_position_gate_entry_hysteresis_ticks"
            ]
        )
        == 5
        and minimum
        + int(
            values[
                "gravity_measured_position_gate_entry_hysteresis_ticks"
            ]
        )
        == 1029
        and "measured raw 1029"
        in values["gravity_zero_acquisition_method"],
        "software_gate_is_exactly_plus_minus_90deg": (minimum, maximum)
        == (1024, 3072),
        "condition_vectors_unchanged": vectors
        == {
            "H1": (600, 0, 150),
            "H2": (800, 0, 150),
            "H3": (600, 0, 220),
            "H4": (300, 0, 60),
            "H5": (1200, 0, 320),
        },
        "held_out_profiles_are_exactly_P06_P07": set(values["profiles"])
        == {"P06_heldout_composite", "P07_heldout_sine_hold"}
        and all(
            item["split"] == "held_out"
            for item in values["profiles"].values()
        ),
        "active_sample_counts_exact": {
            name: int(command.size) for name, command in active.items()
        }
        == {
            "P06_heldout_composite": 1101,
            "P07_heldout_sine_hold": 1001,
        },
        "all_executed_profiles_start_at_zero_and_recover_to_raw1024": all(
            abs(float(profile.command_rad[0])) < 1e-12
            and abs(
                float(profile.command_rad[-1])
                + np.pi / 2.0
            )
            < 1e-12
            for profile in executed.values()
        ),
        "active_profile_samples_unchanged": all(
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
        "held_out_is_five_repeats_H1_H2": set(
            values["held_out_condition_order_by_repeat"]
        )
        == {"R01", "R02", "R03", "R04", "R05"}
        and all(
            sorted(order) == ["H1", "H2"]
            for order in values[
                "held_out_condition_order_by_repeat"
            ].values()
        ),
        "pilots_are_only_H1_H2": values["pilot"]["controllers"]
        == ["H1", "H2"],
        "held_out_policy_is_explicit": "must not influence" in values[
            "data_policy"
        ]["held_out_policy"],
        "no_torque_channel_claimed": values["measurement_boundary"][
            "torque_channel_available"
        ]
        is False,
        "prior_observations_excluded": values["data_policy"][
            "prior_zip_or_V4_observations_used"
        ]
        is False,
        "iphone_media_capture_is_required_before_motion": (
            media["enabled_for_run"] is True
            and media["required_before_motion"] is True
            and str(media["iphone_ip"]) == "10.127.52.4"
            and int(media["ar_port"]) == 8000
            and str(media["required_asmagic_sdk_version"]) == "0.1.4"
            and media["audio_available"] is False
        ),
        "iphone_media_runtime_files_are_present": (
            media_python.is_file()
            and media_python.stat().st_mode & 0o111 != 0
            and media_script.is_file()
        ),
        "iphone_media_primary_and_derived_evidence_are_separate": (
            "raw/<experiment_number>_<scene>_ar.csv"
            in media["primary_evidence"]
            and "raw/ar.csv" in media.get("compatibility_aliases", [])
            and "raw/color_frames/<experiment_number>_<scene>_frame_*.jpg"
            in media["primary_evidence"]
            and "raw/depth_frames/<experiment_number>_<scene>_depth_*.npy"
            in media["primary_evidence"]
            and "video/<experiment_number>_<scene>_experiment-labeled.mp4"
            in media["derived_convenience_artifacts"]
            and "video/<experiment_number>_<scene>_experiment-unlabeled.mp4"
            in media["derived_convenience_artifacts"]
            and "video/<experiment_number>_<scene>_frame-map.csv"
            in media["derived_convenience_artifacts"]
            and media.get("experiment_number_format") == "YYMMDD-HHMMSS"
            and media.get("experiment_number_timezone") == "Asia/Dubai"
            and int(media.get("native_video_width_px", 0)) == 640
            and int(media.get("native_video_height_px", 0)) == 480
            and media.get("paired_labeled_unlabeled_video_required") is True
            and 0.0 < float(media["maximum_recording_duration_s"]) <= 180.0
            and media["capture_scope"].startswith(
                "one continuously connected service"
            )
        ),
    }
    report = {
        "experiment_id": values["experiment_id"],
        "fixture": fixture,
        "G1_overlay": str(G1_CONFIG_PATH),
        "G1_overlay_sha256": base.sha256_file(G1_CONFIG_PATH),
        "checks": checks,
        "profile_statistics": {
            name: profile_statistics(profile, dt_s)
            for name, profile in executed.items()
        },
        "passed": all(checks.values()),
    }
    write_report("g1_validation.json", report)
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
            values = config()
            bus = DynamixelBus(
                str(values["serial_port"]), int(values["baud_rate_bps"])
            )
            try:
                result = base.read_only_status_on_open_bus(bus)
            finally:
                bus.close()
        result = accept_stable_passive_gravity_rest(result, values)
        result["fixture_declaration"] = values["fixture"]
        result["offline_validation_passed"] = True
        result["availability_before_open"] = available
        result["gravity_rest_position_is_not_experiment_zero"] = True
        result["experiment_zero_goal_raw"] = 2048
    write_report("g1_live_status.json", result)
    return result


def handoff_status() -> dict[str, Any]:
    """Exercise only the torque-off H2 goal latch; never enable torque."""

    offline = validate()
    available = base.availability()
    if not offline["passed"] or not available["available"]:
        return {
            "offline_validation": offline,
            "availability": available,
            "passed": False,
            "motion_executed": False,
            "torque_enabled": False,
        }
    values = config()
    result: dict[str, Any]
    with base.hardware_lock():
        bus = DynamixelBus(
            str(values["serial_port"]), int(values["baud_rate_bps"])
        )
        try:
            discovered = bus.discover()
            base.disable_discovered(bus, discovered)
            before = base.snapshot(bus, 5)
            _, order = base.apply_condition(bus, "H2")
            after = base.snapshot(bus, 5)
            result = {
                "operation": "torque_off_H2_goal_latch_diagnostic",
                "discovered": discovered,
                "position_before_raw": base.signed(
                    before["present_position"], 32
                ),
                "goal_before_raw": base.signed(
                    before["goal_position"], 32
                ),
                "position_after_raw": base.signed(
                    after["present_position"], 32
                ),
                "goal_after_raw": base.signed(
                    after["goal_position"], 32
                ),
                "controller_write_order": order,
                "torque_enabled": bool(after["torque_enable"]),
                "motion_executed": False,
                "passed": after["torque_enable"] == 0,
            }
        except (RuntimeError, OSError) as exc:
            result = {
                "operation": "torque_off_H2_goal_latch_diagnostic",
                "error": f"{type(exc).__name__}: {exc}",
                "torque_enabled": False,
                "motion_executed": False,
                "passed": False,
            }
        finally:
            try:
                bus.torque_disable(5)
            finally:
                bus.close()
    write_report("g1_handoff_status.json", result)
    return result


def iphone_camera_status() -> dict[str, Any]:
    """Require a fresh AR frame without opening or commanding the motor."""

    offline = validate()
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
            result = camera_only_status(config())
            result["offline_validation_passed"] = True
            result["motion_executed"] = False
        except (MediaCaptureError, OSError) as exc:
            result = {
                "operation": "iphone_camera_status_only",
                "iphone_ip": config()["iphone_media_capture"]["iphone_ip"],
                "error": f"{type(exc).__name__}: {exc}",
                "offline_validation_passed": True,
                "motor_device_opened": False,
                "recording_started": False,
                "motion_executed": False,
                "passed": False,
            }
    write_report("g1_camera_status.json", result)
    return result


def wait_for_gravity_rest(
    bus: DynamixelBus, after_episode_id: str
) -> dict[str, Any]:
    """Record a bounded torque-off interval and require a stable bottom rest."""

    values = config()
    duration_s = float(values["gravity_rest_settle_s"])
    interval_s = 0.1
    count = int(round(duration_s / interval_s)) + 1
    positions: list[int] = []
    command_minimum = int(values["software_goal_min_raw"])
    command_maximum = int(values["software_goal_max_raw"])
    passive_minimum = int(
        values["gravity_passive_transient_min_raw"]
    )
    start_ns = time.monotonic_ns()
    for index in range(count):
        if bus.read(5, "torque_enable") != 0:
            raise RuntimeError(
                "gravity-rest interval found torque enabled"
            )
        position = base.signed(
            bus.read(5, "present_position"), 32
        )
        if not passive_minimum <= position <= command_maximum:
            raise RuntimeError(
                "passive gravity-rest position outside declared "
                f"transient envelope: {position}"
            )
        positions.append(position)
        if index + 1 < count:
            time.sleep(interval_s)
    tail = positions[-6:]
    span = max(tail) - min(tail)
    allowed = int(values["gravity_rest_stability_span_ticks"])
    tail_inside_command_gate = all(
        command_minimum <= position <= command_maximum
        for position in tail
    )
    tail_inside_passive_envelope = all(
        passive_minimum <= position <= command_maximum
        for position in tail
    )
    result = {
        "after_episode_id": after_episode_id,
        "duration_s": duration_s,
        "sample_count": len(positions),
        "start_host_monotonic_ns": start_ns,
        "end_host_monotonic_ns": time.monotonic_ns(),
        "initial_position_raw": positions[0],
        "final_position_raw": positions[-1],
        "minimum_position_raw": min(positions),
        "maximum_position_raw": max(positions),
        "positions_raw": positions,
        "last_six_position_span_ticks": span,
        "allowed_span_ticks": allowed,
        "passive_transient_minimum_raw": passive_minimum,
        "tail_inside_1024_3072_command_gate": (
            tail_inside_command_gate
        ),
        "tail_inside_950_3072_passive_envelope": tail_inside_passive_envelope,
        "commanded_goal_gate_remained_1024_3072": True,
        "torque_enabled": False,
        "passed": span <= allowed and tail_inside_passive_envelope,
    }
    if not result["passed"]:
        raise RuntimeError(
            f"gravity-rest stability gate failed: {result}"
        )
    return result


def write_method_results(
    run_root: Path,
    summary: pd.DataFrame,
    manifests: list[dict[str, Any]],
) -> None:
    if "role" not in summary.columns:
        summary = pd.DataFrame(
            columns=[
                "role",
                "completion_status",
                "profile_id",
                "controller_id",
                "tracking_rmse_rad_active",
                "tracking_peak_abs_rad_active",
            ]
        )
    held_out = summary[summary["role"] == "held_out"]
    start_errors = [
        int(item["experiment_start_position_error_ticks"])
        for item in manifests
        if item["role"] in {"pilot", "held_out"}
        and item.get("experiment_start_position_error_ticks") is not None
    ]
    current_result = (
        f"{summary['maximum_abs_current_A'].max():.6f} A"
        if "maximum_abs_current_A" in summary
        else "unavailable (no experimental telemetry)"
    )
    pwm_result = (
        f"{summary['maximum_abs_pwm_fraction'].max():.6f}"
        if "maximum_abs_pwm_fraction" in summary
        else "unavailable (no experimental telemetry)"
    )
    temperature_result = (
        f"{summary['maximum_temperature_C'].max():.1f} °C"
        if "maximum_temperature_C" in summary
        else "unavailable (no experimental telemetry)"
    )
    voltage_result = (
        f"{summary['minimum_voltage_V'].min():.1f} V"
        if "minimum_voltage_V" in summary
        else "unavailable (no experimental telemetry)"
    )
    lines = [
        "# V5 G1 +60/+100 mm hardware collection: method and results",
        "",
        f"Run: `{run_root.name}`",
        "",
        "## Corrected physical fixture",
        "",
        "G1 used two complete **44 g payload assemblies, each including its pin**, on the positive side at **+60 mm and +100 mm**, plus the **22 g link**. Total external moving mass is **110 g**. The user-corrected +60 mm location supersedes the PDF's preliminary +50 mm location, so the PDF inertia and gravity moment are not reused. The two payloads contribute `0.0005984 kg·m²` point inertia and `0.00704 kg·m` first moment; complete link inertia/gravity terms still require link geometry.",
        "",
        "## Tick-to-tick zero procedure",
        "",
        "Torque-off gravity rest was never treated as experiment zero. After each frozen active segment, a non-active four-second recovery commanded raw tick **1024** (−90°), held it there, and only then disabled torque. With torque off, the heavier unbalanced fixture may settle slightly below 1024 inside the separately declared passive envelope 950–3072. The torque-off DYNAMIXEL goal latch was kept equal to that passive present position to prevent a torque-enable jump; this disabled-torque latch was not an energized motion command. The first energized pickup goal was clamped to 1024, and no energized commanded goal was allowed outside 1024–3072. The temporary passive measured-position allowance remained active through boundary chatter until the encoder reached raw 1029 (a five-tick entry hysteresis), after which the strict 1024–3072 measured-position gate latched permanently. Before every pilot and held-out episode, ID5 then moved slowly toward zero. During setup only, a bounded and logged integral goal bias compensated steady gravity error until the **measured encoder** reached raw tick **2048 ±5**. Torque stayed enabled and the first experimental command was exactly raw tick **2048**, with no setup bias. Every successful zero-acquisition time series is stored as `zeroing_events.parquet` beside its episode data.",
        "",
        "## Episode design",
        "",
        "- Safety pilots: H1 and H2 = 2 episodes.",
        "- Untouched held out: P06–P07 × H1/H2 × five repeats = 20 episodes.",
        "- P06/P07 were not used for fitting, bounds, timing/filter choices, or model selection.",
        "",
        "## Collection outcome",
        "",
        f"- Complete held-out episodes: {int((held_out['completion_status'] == 'complete').sum())} / 20.",
        f"- Complete pilot episodes: {int(((summary['role'] == 'pilot') & (summary['completion_status'] == 'complete')).sum())} / 2.",
        (
            f"- Maximum experiment-start encoder error: {max(start_errors)} ticks relative to 2048."
            if start_errors
            else "- No episode reached the verified experiment-start gate."
        ),
        f"- Maximum input-supply current: {current_result}.",
        f"- Maximum PWM fraction: {pwm_result}.",
        f"- Maximum temperature: {temperature_result}.",
        f"- Minimum voltage: {voltage_result}.",
        "",
        "### Frozen held-out hardware tracking",
        "",
        "These statistics describe hardware command tracking only. No candidate MuJoCo model was evaluated.",
        "",
        "| Profile | H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for (profile, condition), group in held_out.groupby(
        ["profile_id", "controller_id"], sort=True
    ):
        lines.append(
            f"| {profile} | {condition} | {len(group)} | "
            f"{group['tracking_rmse_rad_active'].mean():.9f} | "
            f"{group['tracking_rmse_rad_active'].std(ddof=1):.9f} | "
            f"{group['tracking_peak_abs_rad_active'].max():.9f} |"
        )
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            "Present Current remains XC330 input-supply-current telemetry, not measured output torque. No MuJoCo joint parameters or equivalent gains are identified during collection. G1 P06/P07 remain untouched held-out evidence.",
            "",
        ]
    )
    (run_root / "G1_METHOD_AND_RESULTS.md").write_text(
        "\n".join(lines), encoding="utf-8"
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

FULL_EXPERIMENT_FRAME_MAP_COLUMNS = [
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

FULL_EXPERIMENT_CHAPTER_COLUMNS = [
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

FULL_EXPERIMENT_INDEX_KEYS = {
    "status",
    "path",
    "absolute_path",
    "unlabeled_path",
    "unlabeled_absolute_path",
    "frame_map",
    "frame_map_absolute_path",
    "chapters",
    "chapters_absolute_path",
    "codec",
    "unlabeled_codec",
    "constant_frame_rate_fps",
    "unlabeled_constant_frame_rate_fps",
    "video_frame_count",
    "unlabeled_video_frame_count",
    "decoded_frame_count_verified",
    "unlabeled_decoded_frame_count_verified",
    "width_px",
    "height_px",
    "unlabeled_width_px",
    "unlabeled_height_px",
    "source_resolution_consistent",
    "shared_frame_map",
    "included_session_count",
    "total_session_count",
    "included_session_ids",
    "omitted_sessions",
    "session_order",
    "inter_episode_gaps_included",
    "burned_in_labels",
    "unlabeled_burned_in_labels",
    "paired_frame_timing_identical",
    "experiment_number",
    "scene_label",
    "campaign_artifact_prefix",
    "raw_jpegs_modified",
    "audio_track",
}


def expected_g1_media_campaign(
    values: dict[str, Any], experiment_number: str
) -> list[dict[str, Any]]:
    """Generate the exact media order and labels used by the G1 run loops."""

    experiment_number = validated_experiment_number(experiment_number)
    expected: list[dict[str, Any]] = []

    def append(
        episode_id: str,
        role: str,
        condition: str,
        profile_id: str,
        repeat_id: str | None,
        display_profile: str,
    ) -> None:
        ordinal = len(expected) + 1
        identity = episode_media_identity(
            ordinal,
            episode_id,
            role,
            condition,
            profile_id,
            repeat_id,
            experiment_number=experiment_number,
        )
        artifact_prefix = str(identity["artifact_prefix"])
        display_code = f"{condition}-G1-{display_profile}"
        if repeat_id is not None:
            display_code += f"-{repeat_id}"
        relative_directory = f"episodes/{identity['directory_name']}"
        expected.append(
            {
                "campaign_ordinal": ordinal,
                "session_id": episode_id,
                "session_title": identity["title"],
                "episode_display_code": display_code,
                "scene_label": display_code,
                "experiment_number": experiment_number,
                "artifact_prefix": identity["artifact_prefix"],
                "session_relative_directory": relative_directory,
                "episode_video": (
                    f"{relative_directory}/video/"
                    f"{artifact_prefix}_experiment-labeled.mp4"
                ),
                "episode_unlabeled_video": (
                    f"{relative_directory}/video/"
                    f"{artifact_prefix}_experiment-unlabeled.mp4"
                ),
                "episode_frame_map": (
                    f"{relative_directory}/video/"
                    f"{artifact_prefix}_frame-map.csv"
                ),
                "keyframe_index": (
                    f"{relative_directory}/keyframes/"
                    f"{artifact_prefix}_keyframes.csv"
                ),
            }
        )

    for condition in values["pilot"]["controllers"]:
        append(
            f"G1__{condition}__PILOT_LOW_AMPLITUDE",
            "pilot",
            condition,
            "PILOT_LOW_AMPLITUDE",
            None,
            "PILOT",
        )
    for repeat_id, condition_order in values[
        "held_out_condition_order_by_repeat"
    ].items():
        for profile_id, display_profile in (
            ("P06_heldout_composite", "P06"),
            ("P07_heldout_sine_hold", "P07"),
        ):
            for condition in condition_order:
                append(
                    f"G1__{condition}__{profile_id}__{repeat_id}",
                    "held_out",
                    condition,
                    profile_id,
                    repeat_id,
                    display_profile,
                )
    return expected


def _csv_values_are_true(values: pd.Series) -> bool:
    """Accept only explicit CSV boolean true representations."""

    return bool(len(values)) and all(
        str(value).strip().lower() == "true" for value in values.tolist()
    )


def verify_episode_media(
    run_root: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    """Verify that derived media maps back to preserved source evidence."""

    episode_id = str(manifest.get("episode_id", ""))
    media_value = manifest.get("media", {})
    media = media_value if isinstance(media_value, dict) else {}
    errors: list[str] = []
    try:
        experiment_number = validated_experiment_number(
            str(manifest.get("experiment_number", ""))
        )
    except ValueError as exc:
        errors.append(str(exc))
        return {
            "episode_id": episode_id,
            "checks": {"experiment_number_is_valid": False},
            "errors": errors,
            "passed": False,
        }
    expected_by_id = {
        item["session_id"]: item
        for item in expected_g1_media_campaign(config(), experiment_number)
    }
    expected_identity = expected_by_id.get(episode_id)
    if expected_identity is None:
        errors.append("episode_id is not in the canonical G1 campaign")
        return {
            "episode_id": episode_id,
            "checks": {"canonical_episode_id": False},
            "errors": errors,
            "passed": False,
        }
    expected_display_code = (
        str(expected_identity["episode_display_code"])
        if expected_identity is not None
        else None
    )
    expected_ordinal = (
        int(expected_identity["campaign_ordinal"])
        if expected_identity is not None
        else None
    )
    expected_prefix = str(expected_identity["artifact_prefix"])
    checks: dict[str, bool] = {
        "experiment_number_is_valid": True,
        "motor_and_media_manifests_share_run_and_scene_identity": (
            manifest.get("experiment_number") == experiment_number
            and manifest.get("scene_label") == expected_display_code
            and manifest.get("artifact_prefix") == expected_prefix
            and media.get("experiment_number") == experiment_number
            and media.get("scene_label") == expected_display_code
            and media.get("artifact_prefix") == expected_prefix
        ),
        "manifest_status_complete": media.get("status") == "complete",
        "derived_video_has_no_audio": (
            media.get("derived_video_has_audio") is False
        ),
    }
    directory_value = media.get("directory")
    if not isinstance(directory_value, str):
        errors.append("media directory is missing")
        return {
            "episode_id": episode_id,
            "checks": checks,
            "errors": errors,
            "passed": False,
        }

    episode_media = (run_root / directory_value).resolve()
    try:
        episode_media.relative_to(run_root.resolve())
    except ValueError:
        errors.append("media directory escapes the run folder")
        return {
            "episode_id": episode_id,
            "checks": checks,
            "errors": errors,
            "passed": False,
        }
    checks["friendly_episode_directory"] = directory_value.startswith(
        "media/episodes/"
    )

    required = {
        "capture_manifest": episode_media / "capture.json",
        "media_index": episode_media / "media-index.json",
        "ar_csv": episode_media / "raw" / "ar.csv",
        "prefixed_ar_csv": (
            episode_media / "raw" / f"{expected_prefix}_ar.csv"
        ),
        "color_directory": episode_media / "raw" / "color_frames",
        "depth_directory": episode_media / "raw" / "depth_frames",
        "video": (
            episode_media
            / "video"
            / f"{expected_prefix}_experiment-labeled.mp4"
        ),
        "unlabeled_video": (
            episode_media
            / "video"
            / f"{expected_prefix}_experiment-unlabeled.mp4"
        ),
        "frame_map": (
            episode_media / "video" / f"{expected_prefix}_frame-map.csv"
        ),
        "keyframe_index": (
            episode_media
            / "keyframes"
            / f"{expected_prefix}_keyframes.csv"
        ),
        "snapshot_directory": episode_media / "snapshots",
    }
    artifact_checks: list[str] = []
    for label, path in required.items():
        check_name = f"{label}_exists"
        artifact_checks.append(check_name)
        try:
            checks[check_name] = (
                path.is_dir()
                if label.endswith("_directory")
                else path.is_file() and path.stat().st_size > 0
            )
        except OSError as exc:
            checks[check_name] = False
            errors.append(f"could not inspect {label}: {exc}")
    if not all(checks[name] for name in artifact_checks):
        errors.append("one or more required media artifacts are missing")
        return {
            "episode_id": episode_id,
            "checks": checks,
            "errors": errors,
            "passed": False,
        }

    def references_exist(values: Any) -> bool:
        for raw_value in values:
            candidate = (episode_media / str(raw_value)).resolve()
            try:
                candidate.relative_to(episode_media)
                if not candidate.is_file() or candidate.stat().st_size == 0:
                    return False
            except (OSError, ValueError):
                return False
        return True

    def references_use_prefix(values: Any, prefix: str) -> bool:
        items = [str(value) for value in values if str(value).strip()]
        return bool(items) and all(
            Path(value).name.startswith(prefix + "_") for value in items
        )

    try:
        ar = pd.read_csv(required["prefixed_ar_csv"])
        frame_map = pd.read_csv(required["frame_map"])
        keyframes = pd.read_csv(required["keyframe_index"])
        capture_manifest_value = base.read_json(
            required["capture_manifest"]
        )
        capture_manifest = (
            capture_manifest_value
            if isinstance(capture_manifest_value, dict)
            else {}
        )
        capture_session = capture_manifest.get("session", {})
        capture_metadata = (
            capture_session.get("metadata", {})
            if isinstance(capture_session, dict)
            else {}
        )
        if not isinstance(capture_metadata, dict):
            capture_metadata = {}
        media_index_value = base.read_json(required["media_index"])
        media_index = (
            media_index_value if isinstance(media_index_value, dict) else {}
        )
        human_viewable = media_index.get("human_viewable", {})
        video_metadata = (
            human_viewable.get("video", {})
            if isinstance(human_viewable, dict)
            else {}
        )
        if not isinstance(video_metadata, dict):
            video_metadata = {}
        color_files = [
            str(value)
            for value in ar["color_file"].dropna().tolist()
            if str(value).strip()
        ]
        depth_files = [
            str(value)
            for value in ar["depth_file"].dropna().tolist()
            if str(value).strip()
        ]
        keyframe_files = [
            str(value)
            for value in keyframes["keyframe_file"].dropna().tolist()
            if str(value).strip()
        ]
        keyframe_source_files = (
            [
                str(value)
                for value in keyframes["source_color_file"].dropna().tolist()
                if str(value).strip()
            ]
            if "source_color_file" in keyframes.columns
            else []
        )
        snapshot_files = list(
            required["snapshot_directory"].glob("*.jpg")
        )
        source_indices = {
            int(value) for value in ar["frame_index"].tolist()
        }
        mapped_indices = {
            int(value)
            for value in frame_map["source_frame_index"].tolist()
        }
        keyframe_indices = {
            int(value)
            for value in keyframes["source_frame_index"].tolist()
        }
        display_values = frame_map["episode_display_code"].fillna("").astype(str)
        phase_values = frame_map["phase_label"].fillna("").astype(str)
        ordinal_values = pd.to_numeric(
            frame_map["campaign_ordinal"], errors="coerce"
        )
        video_frame_count = int(video_metadata.get("video_frame_count", -1))
        decoded_frame_count = int(
            video_metadata.get("decoded_frame_count_verified", -1)
        )
        unlabeled_decoded_frame_count = int(
            video_metadata.get(
                "unlabeled_decoded_frame_count_verified", -1
            )
        )
        expected_video_relative = (
            "video/" + expected_prefix + "_experiment-labeled.mp4"
        )
        expected_unlabeled_relative = (
            "video/" + expected_prefix + "_experiment-unlabeled.mp4"
        )
        expected_frame_map_relative = (
            "video/" + expected_prefix + "_frame-map.csv"
        )
        expected_keyframes_relative = (
            "keyframes/" + expected_prefix + "_keyframes.csv"
        )
        checks.update(
            {
                "canonical_G1_episode_id_and_display_code": (
                    expected_identity is not None
                    and expected_display_code is not None
                    and "P05" not in expected_display_code.upper()
                ),
                "ar_csv_has_required_timestamps": {
                    "iphone_timestamp_unix_s",
                    "host_receive_timestamp_unix_s",
                    "host_receive_monotonic_ns",
                }.issubset(ar.columns),
                "ar_csv_compatibility_resolves_to_prefixed_primary": (
                    required["ar_csv"].samefile(required["prefixed_ar_csv"])
                ),
                "episode_frame_map_schema_is_exact": (
                    list(frame_map.columns) == EPISODE_FRAME_MAP_COLUMNS
                ),
                "episode_frame_map_has_nonempty_phase_labels": bool(
                    len(phase_values) > 0
                    and phase_values.str.strip().ne("").all()
                ),
                "every_episode_video_frame_has_burned_in_labels": (
                    _csv_values_are_true(frame_map["burned_in_label"])
                ),
                "episode_frame_map_display_code_is_exact_and_not_P05": bool(
                    expected_display_code is not None
                    and len(display_values) > 0
                    and display_values.eq(expected_display_code).all()
                    and display_values.str.upper().str.contains("P05").sum() == 0
                ),
                "episode_frame_map_campaign_ordinal_is_exact": bool(
                    expected_ordinal is not None
                    and len(ordinal_values) > 0
                    and ordinal_values.notna().all()
                    and ordinal_values.astype(int).eq(expected_ordinal).all()
                ),
                "episode_video_metadata_declares_exact_identity_and_labels": (
                    video_metadata.get("burned_in_labels") is True
                    and video_metadata.get("unlabeled_burned_in_labels")
                    is False
                    and video_metadata.get("paired_frame_timing_identical")
                    is True
                    and video_metadata.get("shared_frame_map") is True
                    and video_metadata.get("source_resolution_consistent")
                    is True
                    and video_metadata.get("raw_jpegs_modified") is False
                    and video_metadata.get("experiment_number")
                    == experiment_number
                    and video_metadata.get("scene_label")
                    == expected_display_code
                    and video_metadata.get("artifact_prefix")
                    == expected_prefix
                    and video_metadata.get("episode_display_code")
                    == expected_display_code
                    and video_metadata.get("campaign_ordinal")
                    == expected_ordinal
                    and int(
                        video_metadata.get("campaign_total_episodes", -1)
                    )
                    == 22
                    and video_metadata.get("path")
                    == expected_video_relative
                    and video_metadata.get("unlabeled_path")
                    == expected_unlabeled_relative
                    and video_metadata.get("frame_map")
                    == expected_frame_map_relative
                    and human_viewable.get("keyframe_index")
                    == expected_keyframes_relative
                ),
                "capture_manifest_records_exact_run_and_scene_identity": (
                    capture_metadata.get("experiment_number")
                    == experiment_number
                    and capture_metadata.get("scene_label")
                    == expected_display_code
                    and capture_metadata.get("display_code")
                    == expected_display_code
                    and capture_metadata.get("artifact_prefix")
                    == expected_prefix
                ),
                "manifest_paths_are_primary_prefixed_artifacts": (
                    media.get("video")
                    == "media/" + str(expected_identity["episode_video"])
                    and media.get("unlabeled_video")
                    == "media/"
                    + str(expected_identity["episode_unlabeled_video"])
                    and media.get("frame_map")
                    == "media/" + str(expected_identity["episode_frame_map"])
                ),
                "episode_frame_count_matches_video_metadata": (
                    len(frame_map) > 0
                    and video_frame_count == len(frame_map)
                    and decoded_frame_count == len(frame_map)
                    and unlabeled_decoded_frame_count == len(frame_map)
                    and int(
                        video_metadata.get(
                            "unlabeled_video_frame_count", -1
                        )
                    )
                    == len(frame_map)
                ),
                "episode_videos_are_paired_native_640x480": (
                    int(video_metadata.get("width_px", 0)) == 640
                    and int(video_metadata.get("height_px", 0)) == 480
                    and int(
                        video_metadata.get("unlabeled_width_px", 0)
                    )
                    == 640
                    and int(
                        video_metadata.get("unlabeled_height_px", 0)
                    )
                    == 480
                    and video_metadata.get("codec")
                    == video_metadata.get("unlabeled_codec")
                    and float(
                        video_metadata.get("constant_frame_rate_fps", 0.0)
                    )
                    == float(
                        video_metadata.get(
                            "unlabeled_constant_frame_rate_fps", -1.0
                        )
                    )
                    and float(
                        video_metadata.get("constant_frame_rate_fps", 0.0)
                    )
                    > 0.0
                    and video_metadata.get("paired_frame_timing_identical")
                    is True
                ),
                "episode_source_count_matches_video_metadata": (
                    int(video_metadata.get("source_jpeg_count", -1))
                    == len(color_files)
                ),
                "exact_jpegs_are_nonempty_and_all_referenced": (
                    bool(color_files) and references_exist(color_files)
                ),
                "raw_jpeg_references_share_experiment_and_scene_prefix": (
                    references_use_prefix(color_files, expected_prefix)
                ),
                "depth_arrays_are_nonempty_and_all_referenced": (
                    bool(depth_files) and references_exist(depth_files)
                ),
                "depth_references_share_experiment_and_scene_prefix": (
                    references_use_prefix(depth_files, expected_prefix)
                ),
                "manifest_source_count_matches_csv": (
                    int(media.get("source_frame_count", -1))
                    == len(color_files)
                ),
                "frame_map_is_nonempty": len(frame_map) > 0,
                "frame_map_only_uses_ar_source_frames": (
                    bool(mapped_indices)
                    and mapped_indices.issubset(source_indices)
                    and references_exist(
                        frame_map["color_file"].dropna().tolist()
                    )
                ),
                "frame_map_source_references_share_identity_prefix": (
                    references_use_prefix(
                        frame_map["color_file"].dropna().tolist(),
                        expected_prefix,
                    )
                ),
                "exact_five_labeled_keyframes": (
                    len(keyframes) == 5
                    and keyframe_indices.issubset(source_indices)
                    and references_exist(keyframe_files)
                    and int(media.get("key_frame_count", -1)) == 5
                ),
                "keyframe_references_share_experiment_and_scene_prefix": (
                    references_use_prefix(keyframe_files, expected_prefix)
                    and (
                        not keyframe_source_files
                        or references_use_prefix(
                            keyframe_source_files, expected_prefix
                        )
                    )
                ),
                "pre_motion_snapshot_exists_with_identity_prefix": (
                    bool(snapshot_files)
                    and all(
                        path.name.startswith(expected_prefix + "_")
                        for path in snapshot_files
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
        errors.append(f"media table verification failed: {exc}")
        checks["media_tables_parse_and_cross_reference"] = False

    return {
        "episode_id": episode_id,
        "checks": checks,
        "errors": errors,
        "passed": not errors and all(checks.values()),
    }



def verify_full_experiment_media(
    run_root: Path,
    run_manifest: dict[str, Any],
    manifests: list[dict[str, Any]],
    values: dict[str, Any],
) -> dict[str, Any]:
    """Verify the labeled, gap-free campaign viewing video and its mappings."""

    try:
        experiment_number = validated_experiment_number(
            str(run_manifest.get("experiment_number", ""))
        )
    except ValueError as exc:
        return {
            "paths": {},
            "checks": {"experiment_number_is_valid": False},
            "errors": [str(exc)],
            "passed": False,
        }
    campaign_prefix = experiment_number + "_G1"
    media_root = (run_root / "media").resolve()
    paths = {
        "video": (
            media_root
            / "video"
            / f"{campaign_prefix}_full-experiment-labeled.mp4"
        ),
        "unlabeled_video": (
            media_root
            / "video"
            / f"{campaign_prefix}_full-experiment-unlabeled.mp4"
        ),
        "frame_map": (
            media_root
            / "video"
            / f"{campaign_prefix}_full-experiment-frame-map.csv"
        ),
        "chapters": (
            media_root / "video" / f"{campaign_prefix}_chapters.csv"
        ),
        "root_index": media_root / "index.json",
    }
    checks: dict[str, bool] = {}
    errors: list[str] = []
    for label, path in paths.items():
        try:
            checks[f"{label}_exists_and_is_nonempty"] = (
                path.is_file() and path.stat().st_size > 0
            )
        except OSError as exc:
            checks[f"{label}_exists_and_is_nonempty"] = False
            errors.append(f"could not inspect {label}: {exc}")
    if not all(checks.values()):
        errors.append("one or more full-experiment media artifacts are missing")
        return {
            "paths": {name: str(path) for name, path in paths.items()},
            "checks": checks,
            "errors": errors,
            "passed": False,
        }

    expected = expected_g1_media_campaign(values, experiment_number)
    expected_ids = [str(item["session_id"]) for item in expected]
    expected_codes = [str(item["episode_display_code"]) for item in expected]
    expected_by_id = {str(item["session_id"]): item for item in expected}

    def existing_media_reference(raw_value: Any) -> bool:
        if not isinstance(raw_value, str) or not raw_value.strip():
            return False
        candidate = (media_root / raw_value).resolve()
        try:
            candidate.relative_to(media_root)
            return candidate.is_file() and candidate.stat().st_size > 0
        except (OSError, ValueError):
            return False

    try:
        frame_map = pd.read_csv(paths["frame_map"])
        chapters = pd.read_csv(paths["chapters"])
        root_index_value = base.read_json(paths["root_index"])
        root_index = (
            root_index_value if isinstance(root_index_value, dict) else {}
        )
        full_metadata = root_index.get("full_experiment_video", {})
        if not isinstance(full_metadata, dict):
            full_metadata = {}
        run_media = run_manifest.get("iphone_media_capture", {})
        if not isinstance(run_media, dict):
            run_media = {}
        run_summary = run_media.get("full_experiment_video", {})
        if not isinstance(run_summary, dict):
            run_summary = {}

        frame_indices = [int(value) for value in frame_map["campaign_frame_index"]]
        chapter_indices = [int(value) for value in chapters["chapter_index"]]
        map_session_ids = frame_map["session_id"].fillna("").astype(str)
        chapter_session_ids = chapters["session_id"].fillna("").astype(str).tolist()
        collapsed_map_session_ids = list(dict.fromkeys(map_session_ids.tolist()))
        map_codes = frame_map["episode_display_code"].fillna("").astype(str)
        chapter_codes = chapters["episode_display_code"].fillna("").astype(str)
        phase_labels = frame_map["phase_label"].fillna("").astype(str)

        chapter_contiguity = len(chapters) == len(expected)
        if chapter_contiguity:
            previous_end = -1
            previous_end_time = 0.0
            for row in chapters.to_dict(orient="records"):
                start = int(row["campaign_start_frame"])
                end = int(row["campaign_end_frame_inclusive"])
                start_time = float(row["campaign_start_time_s"])
                end_time = float(row["campaign_end_time_s_exclusive"])
                if (
                    start != previous_end + 1
                    or end < start
                    or not np.isfinite(start_time)
                    or not np.isfinite(end_time)
                    or abs(start_time - previous_end_time) > 1e-9
                    or end_time <= start_time
                ):
                    chapter_contiguity = False
                    break
                previous_end = end
                previous_end_time = end_time
            chapter_contiguity = (
                chapter_contiguity
                and bool(frame_indices)
                and previous_end == frame_indices[-1]
            )

        session_rows_match = len(expected) == 22
        source_artifacts_exist = True
        if session_rows_match:
            for item in expected:
                session_id = str(item["session_id"])
                ordinal = int(item["campaign_ordinal"])
                rows = frame_map[map_session_ids == session_id]
                chapter = chapters.iloc[ordinal - 1]
                session_frame_indices = [
                    int(value)
                    for value in rows["campaign_session_frame_index"].tolist()
                ]
                session_rows_match = session_rows_match and (
                    bool(len(rows))
                    and session_frame_indices == list(range(len(rows)))
                    and [
                        int(value)
                        for value in rows["episode_video_frame_index"].tolist()
                    ]
                    == session_frame_indices
                    and pd.to_numeric(
                        rows["campaign_session_order"], errors="coerce"
                    ).notna().all()
                    and pd.to_numeric(
                        rows["campaign_session_order"], errors="coerce"
                    ).astype(int).eq(ordinal).all()
                    and pd.to_numeric(
                        rows["campaign_ordinal"], errors="coerce"
                    ).notna().all()
                    and pd.to_numeric(
                        rows["campaign_ordinal"], errors="coerce"
                    ).astype(int).eq(ordinal).all()
                    and rows["episode_display_code"].astype(str).eq(
                        item["episode_display_code"]
                    ).all()
                    and rows["session_title"].astype(str).eq(
                        item["session_title"]
                    ).all()
                    and rows["session_relative_directory"].astype(str).eq(
                        item["session_relative_directory"]
                    ).all()
                    and rows["episode_video"].astype(str).eq(
                        item["episode_video"]
                    ).all()
                    and rows["episode_frame_map"].astype(str).eq(
                        item["episode_frame_map"]
                    ).all()
                    and all(
                        Path(str(value)).name.startswith(
                            str(item["artifact_prefix"]) + "_"
                        )
                        for value in rows["source_color_file"].tolist()
                    )
                    and int(chapter["chapter_index"]) == ordinal
                    and str(chapter["session_id"]) == session_id
                    and str(chapter["session_title"]) == item["session_title"]
                    and str(chapter["episode_display_code"])
                    == item["episode_display_code"]
                    and int(chapter["campaign_ordinal"]) == ordinal
                    and int(chapter["episode_video_frame_count"]) == len(rows)
                    and str(chapter["raw_capture_status"]) == "complete"
                    and int(chapter["campaign_start_frame"])
                    == int(rows.iloc[0]["campaign_frame_index"])
                    and int(chapter["campaign_end_frame_inclusive"])
                    == int(rows.iloc[-1]["campaign_frame_index"])
                )
                source_artifacts_exist = source_artifacts_exist and (
                    existing_media_reference(item["episode_video"])
                    and existing_media_reference(
                        item["episode_unlabeled_video"]
                    )
                    and existing_media_reference(item["episode_frame_map"])
                )

        expected_root_metadata = dict(full_metadata)
        expected_root_metadata.update(
            {
                "path": (
                    "media/video/"
                    + campaign_prefix
                    + "_full-experiment-labeled.mp4"
                ),
                "unlabeled_path": (
                    "media/video/"
                    + campaign_prefix
                    + "_full-experiment-unlabeled.mp4"
                ),
                "frame_map": (
                    "media/video/"
                    + campaign_prefix
                    + "_full-experiment-frame-map.csv"
                ),
                "chapters": (
                    "media/video/" + campaign_prefix + "_chapters.csv"
                ),
            }
        )
        checks.update(
            {
                "full_frame_map_schema_is_exact": (
                    list(frame_map.columns)
                    == FULL_EXPERIMENT_FRAME_MAP_COLUMNS
                ),
                "chapter_schema_is_exact": (
                    list(chapters.columns) == FULL_EXPERIMENT_CHAPTER_COLUMNS
                ),
                "exact_22_session_campaign_generated_from_config": (
                    len(expected) == 22
                    and len(manifests) == 22
                    and run_manifest.get("episode_ids") == expected_ids
                    and {str(item.get("episode_id")) for item in manifests}
                    == set(expected_ids)
                    and collapsed_map_session_ids == expected_ids
                    and chapter_session_ids == expected_ids
                ),
                "run_and_episode_manifests_share_experiment_and_scene": (
                    run_manifest.get("experiment_number")
                    == experiment_number
                    and all(
                        item.get("experiment_number")
                        == experiment_number
                        and item.get("scene_label")
                        == expected_by_id[str(item.get("episode_id"))][
                            "scene_label"
                        ]
                        and item.get("artifact_prefix")
                        == expected_by_id[str(item.get("episode_id"))][
                            "artifact_prefix"
                        ]
                        for item in manifests
                        if str(item.get("episode_id")) in expected_by_id
                    )
                    and len(manifests) == len(expected_by_id)
                ),
                "campaign_frames_are_zero_based_and_contiguous": (
                    bool(frame_indices)
                    and frame_indices == list(range(len(frame_map)))
                ),
                "campaign_times_are_finite_and_monotonic": (
                    len(frame_map) > 0
                    and np.isfinite(
                        pd.to_numeric(
                            frame_map["campaign_time_s"], errors="coerce"
                        ).to_numpy(dtype=float)
                    ).all()
                    and pd.to_numeric(
                        frame_map["campaign_time_s"], errors="coerce"
                    ).is_monotonic_increasing
                ),
                "chapters_are_one_based_contiguous_and_cover_every_frame": (
                    chapter_indices == list(range(1, len(expected) + 1))
                    and chapter_contiguity
                ),
                "every_session_mapping_and_chapter_matches_canonical_order": (
                    session_rows_match
                ),
                "all_source_episode_videos_and_maps_exist": (
                    source_artifacts_exist
                ),
                "all_full_video_frames_have_nonempty_phase_and_burned_labels": (
                    len(phase_labels) > 0
                    and phase_labels.str.strip().ne("").all()
                    and _csv_values_are_true(frame_map["burned_in_label"])
                ),
                "all_display_codes_are_exact_and_no_P05_is_present": (
                    map_codes.tolist()
                    == [
                        expected_by_id[session_id]["episode_display_code"]
                        for session_id in map_session_ids.tolist()
                    ]
                    and chapter_codes.tolist() == expected_codes
                    and not map_codes.str.upper().str.contains("P05").any()
                    and not chapter_codes.str.upper().str.contains("P05").any()
                ),
                "root_index_has_complete_full_video_contract": (
                    FULL_EXPERIMENT_INDEX_KEYS.issubset(full_metadata)
                    and full_metadata.get("status") == "complete"
                    and full_metadata.get("experiment_number")
                    == experiment_number
                    and full_metadata.get("scene_label") == "G1"
                    and full_metadata.get("campaign_artifact_prefix")
                    == campaign_prefix
                    and full_metadata.get("path")
                    == (
                        "video/"
                        + campaign_prefix
                        + "_full-experiment-labeled.mp4"
                    )
                    and full_metadata.get("absolute_path")
                    == str(paths["video"])
                    and full_metadata.get("unlabeled_path")
                    == (
                        "video/"
                        + campaign_prefix
                        + "_full-experiment-unlabeled.mp4"
                    )
                    and full_metadata.get("unlabeled_absolute_path")
                    == str(paths["unlabeled_video"])
                    and full_metadata.get("frame_map")
                    == (
                        "video/"
                        + campaign_prefix
                        + "_full-experiment-frame-map.csv"
                    )
                    and full_metadata.get("frame_map_absolute_path")
                    == str(paths["frame_map"])
                    and full_metadata.get("chapters")
                    == "video/" + campaign_prefix + "_chapters.csv"
                    and full_metadata.get("chapters_absolute_path")
                    == str(paths["chapters"])
                    and float(
                        full_metadata.get("constant_frame_rate_fps", 0.0)
                    ) > 0.0
                    and float(
                        full_metadata.get(
                            "unlabeled_constant_frame_rate_fps", -1.0
                        )
                    )
                    == float(
                        full_metadata.get(
                            "constant_frame_rate_fps", 0.0
                        )
                    )
                    and full_metadata.get("codec")
                    == full_metadata.get("unlabeled_codec")
                    and int(full_metadata.get("video_frame_count", -1))
                    == len(frame_map)
                    and int(
                        full_metadata.get("unlabeled_video_frame_count", -1)
                    )
                    == len(frame_map)
                    and int(
                        full_metadata.get("decoded_frame_count_verified", -1)
                    )
                    == len(frame_map)
                    and int(
                        full_metadata.get(
                            "unlabeled_decoded_frame_count_verified", -1
                        )
                    )
                    == len(frame_map)
                    and int(full_metadata.get("width_px", 0)) == 640
                    and int(full_metadata.get("height_px", 0)) == 480
                    and int(
                        full_metadata.get("unlabeled_width_px", 0)
                    )
                    == 640
                    and int(
                        full_metadata.get("unlabeled_height_px", 0)
                    )
                    == 480
                    and full_metadata.get("source_resolution_consistent")
                    is True
                    and full_metadata.get("shared_frame_map") is True
                    and int(full_metadata.get("included_session_count", -1))
                    == len(expected)
                    and int(full_metadata.get("total_session_count", -1))
                    == len(expected)
                    and full_metadata.get("included_session_ids")
                    == expected_ids
                    and full_metadata.get("omitted_sessions") == []
                    and full_metadata.get("session_order") == "capture_order"
                    and full_metadata.get("inter_episode_gaps_included") is False
                    and full_metadata.get("burned_in_labels") is True
                    and full_metadata.get("unlabeled_burned_in_labels")
                    is False
                    and full_metadata.get("paired_frame_timing_identical")
                    is True
                    and full_metadata.get("raw_jpegs_modified") is False
                    and full_metadata.get("audio_track") is False
                ),
                "run_manifest_retains_root_relative_full_video_summary": (
                    run_summary == expected_root_metadata
                ),
            }
        )
    except (
        KeyError,
        OSError,
        ValueError,
        TypeError,
        IndexError,
        json.JSONDecodeError,
        pd.errors.EmptyDataError,
    ) as exc:
        errors.append(f"full-experiment media verification failed: {exc}")
        checks["full_experiment_tables_parse_and_cross_reference"] = False

    return {
        "paths": {name: str(path) for name, path in paths.items()},
        "expected_session_ids": expected_ids,
        "expected_display_codes": expected_codes,
        "frame_count": len(frame_map) if "frame_map" in locals() else 0,
        "chapter_count": len(chapters) if "chapters" in locals() else 0,
        "checks": checks,
        "errors": errors,
        "passed": not errors and all(checks.values()),
    }


def verify_media_lifecycle(
    run_root: Path,
    run_manifest: dict[str, Any],
    expected_sessions: int,
) -> dict[str, Any]:
    """Verify START/SNAPSHOT/STOP ordering and post-bus FINALIZE timing."""

    path = run_root / "media" / "capture-lifecycle.jsonl"
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    if path.is_file():
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_number}: {exc}")
                continue
            if isinstance(value, dict):
                rows.append(value)
            else:
                errors.append(f"line {line_number}: not a JSON object")
    else:
        errors.append("capture lifecycle log is missing")

    commands = [str(row.get("command")) for row in rows]
    start_rows = [row for row in rows if row.get("command") == "START"]
    snapshot_rows = [
        row for row in rows if row.get("command") == "SNAPSHOT"
    ]
    stop_rows = [row for row in rows if row.get("command") == "STOP"]
    finalize_rows = [
        row for row in rows if row.get("command") == "FINALIZE"
    ]
    shutdown_rows = [
        row for row in rows if row.get("command") == "SHUTDOWN"
    ]
    bus_close_succeeded = (
        run_manifest.get("motor_bus_close_succeeded") is True
    )
    bus_closed = run_manifest.get(
        "motor_bus_closed_host_monotonic_ns"
    )
    last_stop_ack = max(
        (
            int(row["ack_host_monotonic_ns"])
            for row in stop_rows
            if row.get("ack_host_monotonic_ns") is not None
        ),
        default=None,
    )
    first_finalize_request = min(
        (
            int(row["request_host_monotonic_ns"])
            for row in finalize_rows
            if row.get("request_host_monotonic_ns") is not None
        ),
        default=None,
    )
    last_finalize_ack = max(
        (
            int(row["ack_host_monotonic_ns"])
            for row in finalize_rows
            if row.get("ack_host_monotonic_ns") is not None
        ),
        default=None,
    )
    first_shutdown_request = min(
        (
            int(row["request_host_monotonic_ns"])
            for row in shutdown_rows
            if row.get("request_host_monotonic_ns") is not None
        ),
        default=None,
    )
    checks = {
        "lifecycle_log_exists_and_parses": path.is_file() and not errors,
        "exact_start_count": len(start_rows) == expected_sessions,
        "exact_snapshot_count": len(snapshot_rows) == expected_sessions,
        "exact_stop_count": len(stop_rows) == expected_sessions,
        "one_finalize_command": len(finalize_rows) == 1,
        "shutdown_follows_finalize": (
            last_finalize_ack is not None
            and first_shutdown_request is not None
            and first_shutdown_request >= last_finalize_ack
        ),
        "finalize_follows_all_stops_and_motor_bus_close": (
            last_stop_ack is not None
            and run_manifest.get("terminal_torque_disabled") is True
            and bus_close_succeeded
            and bus_closed is not None
            and first_finalize_request is not None
            and first_finalize_request > int(bus_closed)
            and first_finalize_request >= last_stop_ack
        ),
        "all_lifecycle_commands_acknowledged_without_error": all(
            row.get("error") is None
            and isinstance(row.get("response"), dict)
            and row["response"].get("ok") is True
            for row in rows
            if row.get("command")
            in {"START", "SNAPSHOT", "STOP", "FINALIZE", "SHUTDOWN"}
        ),
        "command_sequence_contains_no_unknown_actions": set(commands).issubset(
            {"STATUS", "START", "SNAPSHOT", "STOP", "FINALIZE", "SHUTDOWN"}
        ),
    }
    return {
        "path": str(path),
        "row_count": len(rows),
        "command_counts": {
            command: commands.count(command)
            for command in sorted(set(commands))
        },
        "checks": checks,
        "errors": errors,
        "passed": all(checks.values()),
    }


def verify_run(run_root: Path) -> dict[str, Any]:
    values = config()
    expected_gate_hysteresis = int(
        values["gravity_measured_position_gate_entry_hysteresis_ticks"]
    )
    expected_gate_entry_raw = (
        int(values["software_goal_min_raw"]) + expected_gate_hysteresis
    )
    run_manifest = base.read_json(run_root / "run.json")
    host_preflight_path = run_root / "HOST_PREFLIGHT.json"
    host_preflight = (
        base.read_json(host_preflight_path)
        if host_preflight_path.is_file()
        else {}
    )
    rest_path = run_root / "gravity-rest-intervals.json"
    gravity_rests = (
        base.read_json(rest_path) if rest_path.is_file() else []
    )
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
    media_verifications = [
        verify_episode_media(run_root, manifest)
        for manifest in manifests
    ]
    motor_alias_verifications = [
        verify_motor_data_hardlink_aliases(run_root, manifest)
        for manifest in manifests
    ]
    full_experiment_media = verify_full_experiment_media(
        run_root,
        run_manifest,
        manifests,
        values,
    )
    media_lifecycle = verify_media_lifecycle(
        run_root,
        run_manifest,
        expected_sessions=22,
    )
    run_media = run_manifest.get("iphone_media_capture", {})
    try:
        run_experiment_number = validated_experiment_number(
            str(run_manifest.get("experiment_number", ""))
        )
        start_local = datetime.fromisoformat(
            str(run_manifest.get("start_local", ""))
        )
    except ValueError:
        run_experiment_number = ""
        start_local = None
    held_out = [item for item in manifests if item["role"] == "held_out"]
    pilots = [item for item in manifests if item["role"] == "pilot"]
    expected_held_out = {
        f"G1__{condition}__{profile}__{repeat}"
        for repeat in ("R01", "R02", "R03", "R04", "R05")
        for profile in (
            "P06_heldout_composite",
            "P07_heldout_sine_hold",
        )
        for condition in ("H1", "H2")
    }
    episode_checks: list[bool] = []
    torque_columns: list[str] = []
    start_errors: list[int] = []
    for manifest in manifests:
        episode_root = run_root / "episodes" / manifest["episode_id"]
        command = pd.read_parquet(episode_root / "command_events.parquet")
        telemetry = pd.read_parquet(
            episode_root / "telemetry_events.parquet"
        )
        zeroing_path = episode_root / "zeroing_events.parquet"
        zeroing = (
            pd.read_parquet(zeroing_path)
            if zeroing_path.is_file()
            else pd.DataFrame()
        )
        torque_columns.extend(
            column
            for column in [*command.columns, *telemetry.columns]
            if "torque" in column.lower()
            and "torque_enable" not in column.lower()
        )
        start_value = manifest.get(
            "experiment_start_position_error_ticks"
        )
        start_error = (
            int(start_value) if start_value is not None else 999999
        )
        start_errors.append(start_error)
        episode_checks.append(
            bool(
                len(command)
                and len(telemetry)
                and len(zeroing)
                and int(command.iloc[0]["goal_position_raw_requested"])
                == 2048
                and command["goal_position_raw_requested"]
                .between(1024, 3072)
                .all()
                and telemetry["present_position_raw"]
                .between(1024, 3072)
                .all()
                and int(
                    zeroing.iloc[-1][
                        "nominal_zeroing_goal_position_raw"
                    ]
                )
                == 2048
                and abs(
                    int(zeroing.iloc[-1]["present_position_raw"]) - 2048
                )
                <= int(values["servo_zero_tolerance_ticks"])
                and manifest["experiment_start_goal_position_raw"] == 2048
                and start_error
                <= int(values["servo_zero_tolerance_ticks"])
                and manifest["gravity_loaded_active_zero_start"] is True
                and manifest["mechanical_configuration"] == "G1"
                and manifest["fixture"]["payload_center_positions_mm"]
                == [60, 100]
                and manifest["fixture"]["payload_print_infill_percent"]
                == 50
                and telemetry["hardware_error_status_raw"].eq(0).all()
            )
        )
    checks = {
        "run_complete": run_manifest["terminal_status"] == "complete",
        "experiment_number_has_unambiguous_dubai_provenance": (
            bool(run_experiment_number)
            and run_manifest.get("experiment_number_format")
            == "YYMMDD-HHMMSS"
            and run_manifest.get("experiment_number_timezone")
            == "Asia/Dubai"
            and start_local is not None
            and start_local.utcoffset() is not None
            and start_local.utcoffset().total_seconds() == 4 * 60 * 60
            and start_local.strftime("%y%m%d-%H%M%S")
            == run_experiment_number
            and run_experiment_number in str(run_manifest.get("run_id", ""))
        ),
        "exact_20_held_out": len(held_out) == 20,
        "held_out_matrix_exact": {
            item["episode_id"] for item in held_out
        }
        == expected_held_out,
        "exact_2_pilots": len(pilots) == 2,
        "exact_22_gravity_rest_intervals": len(gravity_rests) == 22,
        "all_gravity_rest_intervals_stable_and_torque_off": all(
            item["passed"] is True
            and item["torque_enabled"] is False
            for item in gravity_rests
        ),
        "all_manifests_complete": all(
            item["completion_status"] == "complete" for item in manifests
        ),
        "all_terminal_torque_disabled": all(
            item["terminal_torque_disabled"] for item in manifests
        ),
        "all_registers_stable": all(
            item["critical_registers_match_before_after"]
            for item in manifests
        ),
        "all_episodes_actively_start_at_tick_2048": all(episode_checks),
        "all_motor_data_have_verified_prefixed_no_copy_aliases": (
            len(motor_alias_verifications) == 22
            and all(
                item["passed"] for item in motor_alias_verifications
            )
        ),
        "run_and_episode_manifests_record_exact_gravity_gate_entry_hysteresis": (
            expected_gate_hysteresis == 5
            and expected_gate_entry_raw == 1029
            and run_manifest.get(
                "gravity_measured_position_gate_entry_hysteresis_ticks"
            )
            == expected_gate_hysteresis
            and run_manifest.get(
                "gravity_measured_position_gate_entry_raw"
            )
            == expected_gate_entry_raw
            and bool(manifests)
            and all(
                item.get(
                    "gravity_measured_position_gate_entry_hysteresis_ticks"
                )
                == expected_gate_hysteresis
                and item.get(
                    "gravity_measured_position_gate_entry_raw"
                )
                == expected_gate_entry_raw
                for item in manifests
            )
        ),
        "run_and_episode_manifests_record_exact_recollection_mass": (
            run_manifest.get("fixture", {}).get("fixture_revision")
            != "2026-08-26-recollection-110g"
        )
        or (
            int(
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
        "maximum_start_error_within_tolerance": bool(start_errors)
        and max(start_errors)
        <= int(values["servo_zero_tolerance_ticks"]),
        "held_out_only_H1_H2": {
            item["controller_id"] for item in held_out
        }
        == {"H1", "H2"},
        "camera_was_ready_before_motor_device_open": (
            run_manifest.get("camera_ready_before_motor_device_open")
            is True
            and run_manifest.get("motor_device_opened") is True
        ),
        "read_only_1ms_host_preflight_passed_before_camera_and_motor": (
            host_preflight_path.is_file()
            and host_preflight.get("passed") is True
            and host_preflight.get("required_latency_timer_ms") == 1
            and host_preflight.get("configured_latency_timer_ms") == 1
            and host_preflight.get("observed_latency_timer_ms") == 1
            and host_preflight.get("motor_device_opened") is False
            and host_preflight.get("camera_service_started") is False
            and run_manifest.get("host_timing_preflight")
            == host_preflight
            and run_manifest.get(
                "camera_preflight_started_host_monotonic_ns"
            )
            is not None
            and run_manifest.get(
                "motor_device_opened_host_monotonic_ns"
            )
            is not None
            and int(host_preflight["completed_host_monotonic_ns"])
            <= int(
                run_manifest[
                    "camera_preflight_started_host_monotonic_ns"
                ]
            )
            <= int(
                run_manifest["motor_device_opened_host_monotonic_ns"]
            )
        ),
        "media_was_finalized_only_after_motor_bus_close": (
            run_manifest.get("media_finalized_after_motor_bus_close")
            is True
            and run_manifest.get("terminal_torque_disabled") is True
            and run_manifest.get("motor_bus_close_succeeded") is True
            and run_manifest.get(
                "motor_bus_closed_host_monotonic_ns"
            )
            is not None
            and media_lifecycle["passed"]
        ),
        "run_media_summary_is_complete_for_exactly_22_sessions": (
            run_media.get("status") == "complete"
            and int(run_media.get("session_count", -1)) == 22
            and int(run_media.get("complete_session_count", -1)) == 22
            and run_media.get("derived_video_has_audio") is False
        ),
        "all_22_episode_media_sets_cross_reference_primary_evidence": (
            len(media_verifications) == 22
            and all(item["passed"] for item in media_verifications)
        ),
        "full_experiment_video_maps_exact_labeled_campaign_order": (
            full_experiment_media["passed"]
        ),
        "human_media_index_and_setup_photo_exist": (
            (run_root / "media" / "index.html").is_file()
            and (run_root / "media" / "index.json").is_file()
            and (
                run_root
                / "media"
                / "setup"
                / "fixture-overview.jpg"
            ).is_file()
        ),
        "human_start_here_exists": (run_root / "START_HERE.md").is_file(),
        "host_preflight_is_retained_by_inventory": any(
            relative == "HOST_PREFLIGHT.json"
            for _expected, relative in inventory_lines
        ),
        "inventory_hashes_match": not hash_failures,
        "no_manufactured_torque_column": not torque_columns,
        "summary_exists": (run_root / "episode-summary.csv").is_file(),
        "method_results_exists": (
            run_root / "G1_METHOD_AND_RESULTS.md"
        ).is_file(),
    }
    return {
        "run_root": str(run_root),
        "checks": checks,
        "episode_manifest_count": len(manifests),
        "held_out_episode_count": len(held_out),
        "pilot_episode_count": len(pilots),
        "gravity_rest_interval_count": len(gravity_rests),
        "maximum_experiment_start_error_ticks": max(start_errors)
        if start_errors
        else None,
        "inventory_entry_count": len(inventory_lines),
        "inventory_hash_failures": hash_failures,
        "media_verifications": media_verifications,
        "motor_data_alias_verifications": motor_alias_verifications,
        "full_experiment_media_verification": full_experiment_media,
        "media_lifecycle_verification": media_lifecycle,
        "host_timing_preflight": host_preflight,
        "torque_measurement_columns": sorted(set(torque_columns)),
        "passed": all(checks.values()),
    }


def write_archived_verification(
    run_root: Path,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Verify the run, then retain that exact report in the final inventory."""

    base.write_inventory(run_root)
    verification = verify_run(run_root)
    verification["archive_policy"] = {
        "path": "VERIFICATION.json",
        "verification_basis": (
            "the preliminary inventory containing every run artifact that "
            "existed before VERIFICATION.json"
        ),
        "final_inventory_action": (
            "inventory.sha256 was regenerated after this report was written "
            "so it retains the exact VERIFICATION.json bytes"
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
    archive_check = {
        "verification_path": str(verification_path),
        "expected_sha256": expected_digest,
        "inventory_sha256": retained_digest,
        "retained_in_final_inventory": retained_digest == expected_digest,
    }
    if not archive_check["retained_in_final_inventory"]:
        raise RuntimeError(
            "final inventory failed to retain the per-run VERIFICATION.json"
        )
    return inventory_digest, verification, archive_check


def cleanup_motor_bus_safely(
    bus: DynamixelBus,
    *,
    device_id: int = 5,
    torque_disable_attempts: int = 3,
) -> dict[str, Any]:
    """Disable torque with readback before allowing the serial bus to close."""

    errors: list[str] = []
    torque_disabled_host_monotonic_ns: int | None = None
    for attempt in range(1, torque_disable_attempts + 1):
        try:
            bus.torque_disable(device_id)
        except (RuntimeError, OSError) as exc:
            errors.append(
                f"torque-disable attempt {attempt}/{torque_disable_attempts}: "
                f"{type(exc).__name__}: {exc}"
            )
        else:
            torque_disabled_host_monotonic_ns = time.monotonic_ns()
            break

    if torque_disabled_host_monotonic_ns is None:
        return {
            "torque_disabled": False,
            "torque_disabled_host_monotonic_ns": None,
            "bus_close_attempted": False,
            "bus_closed": False,
            "bus_closed_host_monotonic_ns": None,
            "errors": errors,
        }

    try:
        bus.close()
    except (RuntimeError, OSError) as exc:
        errors.append(f"serial close: {type(exc).__name__}: {exc}")
        bus_closed_host_monotonic_ns = None
    else:
        bus_closed_host_monotonic_ns = time.monotonic_ns()
    return {
        "torque_disabled": True,
        "torque_disabled_host_monotonic_ns": (
            torque_disabled_host_monotonic_ns
        ),
        "bus_close_attempted": True,
        "bus_closed": bus_closed_host_monotonic_ns is not None,
        "bus_closed_host_monotonic_ns": bus_closed_host_monotonic_ns,
        "errors": errors,
    }


MOTOR_DATA_CANONICAL_FILES = {
    "command_events": "command_events.parquet",
    "telemetry_events": "telemetry_events.parquet",
    "control_table_before": "control_table_before.json",
    "control_table_after": "control_table_after.json",
    "episode_manifest": "episode.json",
}


def create_motor_data_hardlink_aliases(
    run_root: Path,
    manifest: dict[str, Any],
    identity: dict[str, Any],
) -> dict[str, Any]:
    """Add human-prefixed, no-copy names for canonical motor episode data."""

    run_root = run_root.resolve()
    episode_id = str(manifest["episode_id"])
    experiment_number = validated_experiment_number(
        str(identity["experiment_number"])
    )
    scene_label = str(identity["scene_label"])
    artifact_prefix = str(identity["artifact_prefix"])
    if artifact_prefix != f"{experiment_number}_{scene_label}":
        raise RuntimeError("motor-data artifact prefix does not match run and scene")

    episode_root = (run_root / "episodes" / episode_id).resolve()
    try:
        episode_root.relative_to(run_root)
    except ValueError:
        raise RuntimeError("motor episode directory escapes the run folder") from None
    if not episode_root.is_dir():
        raise RuntimeError(f"motor episode directory is missing: {episode_root}")

    canonical_files = dict(MOTOR_DATA_CANONICAL_FILES)
    zeroing_path = episode_root / "zeroing_events.parquet"
    if zeroing_path.is_file():
        canonical_files["zeroing_events"] = "zeroing_events.parquet"
    missing = [
        name
        for name in canonical_files.values()
        if not (episode_root / name).is_file()
    ]
    if missing:
        raise RuntimeError(
            "cannot publish motor-data aliases; canonical files are missing: "
            + ", ".join(missing)
        )

    aliases = {
        role: f"{artifact_prefix}_{name}"
        for role, name in canonical_files.items()
    }
    artifact_map = {
        "experiment_number": experiment_number,
        "scene_label": scene_label,
        "artifact_prefix": artifact_prefix,
        "episode_directory": (
            Path("episodes") / episode_id
        ).as_posix(),
        "storage_policy": (
            "human-prefixed files are POSIX hard links to the canonical files; "
            "they consume no duplicate file payload"
        ),
        "byte_copy_created": False,
        "canonical_files": canonical_files,
        "human_prefixed_hardlinks": aliases,
        "hardlinks_verified_same_inode": False,
    }
    manifest["motor_data_artifacts"] = artifact_map
    canonical_manifest = episode_root / "episode.json"
    base.write_json(canonical_manifest, manifest)

    created: list[Path] = []
    try:
        for role, canonical_name in canonical_files.items():
            source = episode_root / canonical_name
            alias = episode_root / aliases[role]
            if alias.exists() or alias.is_symlink():
                if alias.is_symlink() or not alias.is_file():
                    raise RuntimeError(
                        f"motor-data alias is not a regular hard link: {alias}"
                    )
                if not alias.samefile(source):
                    raise RuntimeError(
                        f"motor-data alias already names different data: {alias}"
                    )
                continue
            os.link(source, alias)
            created.append(alias)
        if not all(
            not (episode_root / aliases[role]).is_symlink()
            and (episode_root / aliases[role]).samefile(
                episode_root / canonical_name
            )
            for role, canonical_name in canonical_files.items()
        ):
            raise RuntimeError("one or more motor-data hard links failed verification")
    except Exception:
        for alias in reversed(created):
            alias.unlink(missing_ok=True)
        raise

    artifact_map["hardlinks_verified_same_inode"] = True
    base.write_json(canonical_manifest, manifest)
    return artifact_map


def verify_motor_data_hardlink_aliases(
    run_root: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    """Verify the manifest-declared human names share canonical file inodes."""

    errors: list[str] = []
    checks: dict[str, bool] = {}
    episode_id = str(manifest.get("episode_id", ""))
    episode_root = (run_root.resolve() / "episodes" / episode_id).resolve()
    artifact_map = manifest.get("motor_data_artifacts", {})
    if not isinstance(artifact_map, dict):
        artifact_map = {}
    canonical = artifact_map.get("canonical_files", {})
    aliases = artifact_map.get("human_prefixed_hardlinks", {})
    if not isinstance(canonical, dict) or not isinstance(aliases, dict):
        canonical, aliases = {}, {}
    prefix = str(manifest.get("artifact_prefix", ""))
    expected = dict(MOTOR_DATA_CANONICAL_FILES)
    if (episode_root / "zeroing_events.parquet").is_file():
        expected["zeroing_events"] = "zeroing_events.parquet"
    checks["manifest_identity_and_file_map_are_exact"] = (
        bool(prefix)
        and artifact_map.get("experiment_number")
        == manifest.get("experiment_number")
        and artifact_map.get("scene_label") == manifest.get("scene_label")
        and artifact_map.get("artifact_prefix") == prefix
        and artifact_map.get("byte_copy_created") is False
        and artifact_map.get("hardlinks_verified_same_inode") is True
        and canonical == expected
        and aliases
        == {
            role: f"{prefix}_{name}"
            for role, name in expected.items()
        }
    )
    same_inode = bool(expected)
    for role, canonical_name in expected.items():
        source = episode_root / canonical_name
        alias_name = aliases.get(role)
        alias = episode_root / str(alias_name or "")
        try:
            same_inode = (
                same_inode
                and source.is_file()
                and alias.is_file()
                and not alias.is_symlink()
                and alias.samefile(source)
                and source.stat().st_ino == alias.stat().st_ino
                and source.stat().st_dev == alias.stat().st_dev
            )
        except OSError as exc:
            same_inode = False
            errors.append(f"{role}: {exc}")
    checks["all_human_prefixed_files_are_no_copy_hardlinks"] = same_inode
    return {
        "episode_id": episode_id,
        "checks": checks,
        "errors": errors,
        "passed": not errors and all(checks.values()),
    }


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
    gravity_rests: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run one motor episode inside a separately persisted camera session."""

    identity = episode_media_identity(
        media_ordinal,
        episode_id,
        role,
        condition_id,
        str(profile.profile_id),
        repeat_id,
        experiment_number=capture.experiment_number,
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
    rest: dict[str, Any] | None = None
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
        manifests.append(manifest)
        if manifest["completion_status"] != "complete":
            raise RuntimeError(
                f"{role} episode failed: {manifest['failures']}"
            )
        create_motor_data_hardlink_aliases(run_root, manifest, identity)
        rest = wait_for_gravity_rest(bus, episode_id)
        gravity_rests.append(rest)
        base.write_json(
            run_root / "gravity-rest-intervals.json",
            gravity_rests,
        )
    except BaseException as exc:
        operation_error = exc
    finally:
        retry_failed = False
        if (
            manifest is None
            or manifest.get("terminal_torque_disabled") is not True
        ):
            try:
                bus.torque_disable(5)
                retry_ns = time.monotonic_ns()
            except (RuntimeError, OSError) as exc:
                retry_failed = True
                media_error = (
                    "camera STOP deferred until outer motor cleanup because "
                    "the immediate torque-disable retry failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                if manifest is not None:
                    manifest["torque_disable_retry_before_media"] = {
                        "required": True,
                        "succeeded": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                    manifest.setdefault("failures", []).append(media_error)
                if operation_error is None:
                    operation_error = RuntimeError(media_error)
            else:
                if manifest is not None:
                    manifest["terminal_torque_disabled"] = True
                    manifest["torque_disabled_host_monotonic_ns"] = retry_ns
                    manifest["torque_disable_retry_before_media"] = {
                        "required": True,
                        "succeeded": True,
                        "host_monotonic_ns": retry_ns,
                    }
        events: list[dict[str, Any]] = [
            {
                "label": "01 before motion",
                "host_monotonic_ns": before_motion_ns,
            }
        ]
        if manifest is not None:
            timed_events = (
                (
                    "02 experiment zero and profile start",
                    manifest.get("start_host_monotonic_ns"),
                ),
                (
                    "03 motion finished or aborted",
                    manifest.get(
                        "episode_control_exit_host_monotonic_ns"
                    ),
                ),
                (
                    "04 torque disabled",
                    manifest.get("torque_disabled_host_monotonic_ns"),
                ),
            )
            events.extend(
                {
                    "label": label,
                    "host_monotonic_ns": int(timestamp),
                }
                for label, timestamp in timed_events
                if timestamp is not None
            )
        if rest is not None:
            events.append(
                {
                    "label": "05 settled under gravity",
                    "host_monotonic_ns": int(
                        rest["end_host_monotonic_ns"]
                    ),
                }
            )
        outcome = (
            "complete"
            if operation_error is None
            and manifest is not None
            and rest is not None
            else "aborted"
        )
        if not retry_failed:
            try:
                combined_media = capture.stop_episode(
                    outcome=outcome,
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
                    "title": identity["title"],
                    "directory": (
                        "media/episodes/" + identity["directory_name"]
                    ),
                    "video": None,
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


def run() -> dict[str, Any]:
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

    values = config()
    run_started_utc = datetime.now(UTC)
    run_started_local = run_started_utc.astimezone(
        ZoneInfo("Asia/Dubai")
    )
    timestamp = run_started_utc.strftime("%Y%m%dT%H%M%SZ")
    experiment_number = validated_experiment_number(
        run_started_local.strftime("%y%m%d-%H%M%S")
    )
    run_root = base.RAW_ROOT / (
        "v5-g1-plus60-plus100mm-"
        + experiment_number
        + "-"
        + timestamp
        + "-"
        + uuid.uuid4().hex[:8]
    )
    run_root.mkdir(parents=True, exist_ok=False)
    manifests: list[dict[str, Any]] = []
    gravity_rests: list[dict[str, Any]] = []
    campaign_error: str | None = None
    terminal_torque_disabled = False
    motor_device_opened = False
    motor_bus_close_succeeded = False
    motor_bus_closed_host_monotonic_ns: int | None = None
    motor_device_opened_host_monotonic_ns: int | None = None
    camera_preflight_started_host_monotonic_ns: int | None = None
    camera_ready_before_motor_open = False
    camera_ready_status: dict[str, Any] | None = None
    media_summary: dict[str, Any] = {
        "status": "preparing",
        "session_count": 0,
        "expected_session_count": 22,
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
            camera_preflight_started_host_monotonic_ns = time.monotonic_ns()
            ready = capture.start_service()
            camera_ready_before_motor_open = True
            camera_ready_status = {
                "ready": bool(ready.get("ready")),
                "stream_ready": bool(ready.get("stream_ready")),
                "last_frame_age_s": ready.get("last_frame_age_s"),
                "last_color_frame_age_s": ready.get(
                    "last_color_frame_age_s"
                ),
                "asmagic_sdk_version": ready.get("asmagic_sdk_version"),
                "receiver_frames": ready.get("receiver_frames"),
            }
        except (MediaCaptureError, OSError) as exc:
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
                    motor_device_opened_host_monotonic_ns = time.monotonic_ns()
                    motor_device_opened = True
                    try:
                        discovered = bus.discover()
                        base.disable_discovered(bus, discovered)
                        if set(discovered) != {5} or discovered[5][
                            "model_number"
                        ] != int(values["expected_model_number"]):
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
                        live = accept_stable_passive_gravity_rest(
                            live, values
                        )
                        live["fixture_declaration"] = values["fixture"]
                        live[
                            "gravity_rest_position_is_not_experiment_zero"
                        ] = True
                        live[
                            "camera_ready_before_motor_device_open"
                        ] = camera_ready_before_motor_open
                        base.write_json(
                            run_root / "live-preflight.json", live
                        )
                        if not live["passed"]:
                            raise RuntimeError(
                                f"live preflight failed: {live['checks']}"
                            )

                        media_ordinal = 0
                        pilot = pilot_profile(values)
                        for condition in values["pilot"]["controllers"]:
                            media_ordinal += 1
                            episode_id = (
                                f"G1__{condition}__PILOT_LOW_AMPLITUDE"
                            )
                            print(f"PILOT {episode_id}", flush=True)
                            manifest = run_documented_episode(
                                bus=bus,
                                run_root=run_root,
                                capture=capture,
                                media_ordinal=media_ordinal,
                                episode_id=episode_id,
                                condition_id=condition,
                                profile=pilot,
                                role="pilot",
                                repeat_id=None,
                                manifests=manifests,
                                gravity_rests=gravity_rests,
                            )
                            print(
                                f"RESULT {episode_id}: "
                                f"{manifest['completion_status']}",
                                flush=True,
                            )

                        generated = executed_profiles(values)
                        completed = 0
                        for repeat, order in values[
                            "held_out_condition_order_by_repeat"
                        ].items():
                            for profile_id in (
                                "P06_heldout_composite",
                                "P07_heldout_sine_hold",
                            ):
                                for condition in order:
                                    completed += 1
                                    media_ordinal += 1
                                    episode_id = (
                                        f"G1__{condition}__"
                                        f"{profile_id}__{repeat}"
                                    )
                                    print(
                                        "HELD_OUT "
                                        f"{completed:02d}/20: {episode_id}",
                                        flush=True,
                                    )
                                    manifest = run_documented_episode(
                                        bus=bus,
                                        run_root=run_root,
                                        capture=capture,
                                        media_ordinal=media_ordinal,
                                        episode_id=episode_id,
                                        condition_id=condition,
                                        profile=generated[profile_id],
                                        role="held_out",
                                        repeat_id=repeat,
                                        manifests=manifests,
                                        gravity_rests=gravity_rests,
                                    )
                                    print(
                                        f"RESULT {episode_id}: "
                                        f"{manifest['completion_status']}",
                                        flush=True,
                                    )
                    finally:
                        cleanup = cleanup_motor_bus_safely(
                            bus,
                            device_id=5,
                            torque_disable_attempts=3,
                        )
                        for error in cleanup["errors"]:
                            add_campaign_error(
                                "terminal motor cleanup: " + error
                            )
                        if cleanup["torque_disabled"]:
                            terminal_torque_disabled = True
                        if cleanup["bus_closed"]:
                            motor_bus_close_succeeded = True
                            motor_bus_closed_host_monotonic_ns = cleanup[
                                "bus_closed_host_monotonic_ns"
                            ]
                            bus = None
            except (KeyboardInterrupt, RuntimeError, OSError) as exc:
                add_campaign_error(f"{type(exc).__name__}: {exc}")
            finally:
                if bus is not None:
                    cleanup = cleanup_motor_bus_safely(
                        bus,
                        device_id=5,
                        torque_disable_attempts=3,
                    )
                    for error in cleanup["errors"]:
                        add_campaign_error(
                            "outer terminal motor cleanup: " + error
                        )
                    if cleanup["torque_disabled"]:
                        terminal_torque_disabled = True
                    if cleanup["bus_closed"]:
                        motor_bus_close_succeeded = True
                        motor_bus_closed_host_monotonic_ns = cleanup[
                            "bus_closed_host_monotonic_ns"
                        ]
                        bus = None

        motor_cleanup_confirmed = (
            not motor_device_opened
            or (
                terminal_torque_disabled and motor_bus_close_succeeded
            )
        )
        if camera_ready_before_motor_open and motor_cleanup_confirmed:
            if capture.current_session is not None:
                try:
                    capture.stop_episode(
                        outcome="aborted_after_motor_cleanup",
                        events=[
                            {
                                "label": "emergency stop after motor cleanup",
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
                        "session_count", len(capture.session_results)
                    )
                )
                if (
                    retained_sessions
                    and motor_bus_close_succeeded
                    and terminal_torque_disabled
                ):
                    capture.finalize(
                        {
                            "run_id": run_root.name,
                            "experiment_id": values["experiment_id"],
                            "mechanical_configuration": "G1",
                            "experiment_number": experiment_number,
                            "scene_label": "G1",
                            "campaign_artifact_prefix": (
                                experiment_number + "_G1"
                            ),
                            "episode_ids": [
                                item["episode_id"] for item in manifests
                            ],
                            "motor_bus_close_succeeded": (
                                motor_bus_close_succeeded
                            ),
                            "motor_bus_closed_before_finalize": (
                                motor_bus_close_succeeded
                            ),
                            "terminal_torque_disabled": (
                                terminal_torque_disabled
                            ),
                        }
                    )
                    media_summary = capture.apply_finalize_result(
                        manifests
                    )
                elif retained_sessions:
                    message = (
                        "camera FINALIZE skipped because terminal torque "
                        "disable and serial close were not both confirmed"
                    )
                    add_campaign_error(message)
                    media_summary.update(
                        {
                            "status": "raw_capture_retained_not_finalized",
                            "session_count": retained_sessions,
                            "expected_session_count": len(manifests),
                            "complete_session_count": 0,
                            "errors": [message],
                        }
                    )
                else:
                    media_summary.update(
                        {
                            "status": "no_episodes_captured",
                            "session_count": 0,
                            "expected_session_count": len(manifests),
                            "errors": [],
                        }
                    )
            except (KeyboardInterrupt, MediaCaptureError, OSError) as exc:
                add_campaign_error(
                    "camera finalization after bus close: "
                    f"{type(exc).__name__}: {exc}"
                )
                media_summary.update(
                    {
                        "status": "failed",
                        "session_count": len(capture.session_results),
                        "expected_session_count": len(manifests),
                        "errors": [str(exc)],
                    }
                )
        elif camera_ready_before_motor_open:
            message = (
                "camera STOP, STATUS, and FINALIZE were skipped because "
                "terminal torque disable and serial close were not both "
                "confirmed; service shutdown preserves available raw evidence"
            )
            add_campaign_error(message)
            retained_sessions = len(capture.session_results) + int(
                capture.current_session is not None
            )
            media_summary.update(
                {
                    "status": "motor_cleanup_unconfirmed_not_finalized",
                    "session_count": retained_sessions,
                    "expected_session_count": len(manifests),
                    "complete_session_count": 0,
                    "errors": [message],
                }
            )
    finally:
        try:
            capture.shutdown()
        except (RuntimeError, OSError) as exc:
            add_campaign_error(
                f"camera service shutdown: {type(exc).__name__}: {exc}"
            )

    for manifest in manifests:
        base.write_json(
            run_root
            / "episodes"
            / manifest["episode_id"]
            / "episode.json",
            manifest,
        )

    held_out = [item for item in manifests if item["role"] == "held_out"]
    pilots = [item for item in manifests if item["role"] == "pilot"]
    media_complete = (
        media_summary.get("status") == "complete"
        and int(media_summary.get("session_count", -1)) == 22
        and int(media_summary.get("complete_session_count", -1)) == 22
        and all(
            item.get("media", {}).get("status") == "complete"
            for item in manifests
        )
    )
    if not camera_ready_before_motor_open:
        terminal_status = "blocked_before_hardware"
    else:
        terminal_status = (
            "complete"
            if (
                campaign_error is None
                and len(held_out) == 20
                and len(pilots) == 2
                and all(
                    item["completion_status"] == "complete"
                    for item in manifests
                )
                and terminal_torque_disabled
                and media_complete
            )
            else "incomplete"
        )

    run_manifest = {
        "schema_version": 2,
        "experiment_id": values["experiment_id"],
        "run_id": run_root.name,
        "experiment_number": experiment_number,
        "experiment_number_format": "YYMMDD-HHMMSS",
        "experiment_number_timezone": "Asia/Dubai",
        "start_local": run_started_local.isoformat(),
        "mechanical_configuration": "G1",
        "fixture": values["fixture"],
        "dynamixel_id": 5,
        "source_type": "new_V5_physical_hardware_measurement",
        "start_utc": timestamp,
        "end_utc": datetime.now(UTC).isoformat(),
        "host_platform": platform.platform(),
        "operator_declared_u2d2_usb_latency_timer_ms": int(
            values["operator_declared_u2d2_usb_latency_timer_ms"]
        ),
        "host_timing_preflight": host_preflight,
        "camera_preflight_started_host_monotonic_ns": (
            camera_preflight_started_host_monotonic_ns
        ),
        "motor_device_opened_host_monotonic_ns": (
            motor_device_opened_host_monotonic_ns
        ),
        "episode_ids": [item["episode_id"] for item in manifests],
        "held_out_episode_count": len(held_out),
        "pilot_episode_count": len(pilots),
        "gravity_rest_interval_count": len(gravity_rests),
        "gravity_measured_position_gate_entry_hysteresis_ticks": int(
            values[
                "gravity_measured_position_gate_entry_hysteresis_ticks"
            ]
        ),
        "gravity_measured_position_gate_entry_raw": (
            int(values["software_goal_min_raw"])
            + int(
                values[
                    "gravity_measured_position_gate_entry_hysteresis_ticks"
                ]
            )
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
        "iphone_media_capture": media_summary,
        "media_finalized_after_motor_bus_close": (
            capture.finalize_result is not None
            and motor_bus_close_succeeded
            and terminal_torque_disabled
        ),
        "campaign_error": campaign_error,
        "terminal_torque_disabled": terminal_torque_disabled,
        "terminal_status": terminal_status,
        "held_out_policy": values["data_policy"]["held_out_policy"],
        "stopped_after_G1": True,
    }
    base.write_json(run_root / "run.json", run_manifest)
    summary = base.summarize_run(run_root, manifests)
    write_method_results(run_root, summary, manifests)
    write_start_here(
        run_root,
        values,
        run_manifest=run_manifest,
        media_summary=media_summary,
        manifests=manifests,
    )
    camera_session_count = int(media_summary.get("session_count", 0) or 0)
    camera_evidence_line = (
        f"- The computer-side asMagic receiver retained "
        f"{camera_session_count} camera session(s); per-session indexes report "
        "the exact JPEG, depth, and AR CSV availability. It did not control "
        "the iPhone app's local Record button.\n"
        if camera_session_count
        else "- No camera episode evidence was captured or finalized.\n"
    )
    (run_root / "COMMAND_LOG.md").write_text(
        "# Command log\n\n"
        f"- `{datetime.now(UTC).isoformat()}`: "
        "`collect_g1.py --run`\n"
        "- Camera readiness was required before the Dynamixel device "
        f"could open: `{camera_ready_before_motor_open}`.\n"
        + camera_evidence_line
        + "- Corrected fixture: two complete 44 g payloads at +60 mm and "
        "+100 mm, plus one 22 g link, 110 g total external moving mass.\n"
        f"- Operator-declared U2D2 USB latency timer: "
        f"`{values['operator_declared_u2d2_usb_latency_timer_ms']} ms`.\n"
        f"- Read-only sysfs latency preflight: "
        f"`passed={host_preflight['passed']}`, "
        f"`observed={host_preflight['observed_latency_timer_ms']} ms`, "
        f"path `{host_preflight['latency_timer_path']}`. It completed before "
        "camera startup or motor-device open.\n"
        "- Every successful episode actively acquired measured raw tick "
        "2048 under torque before experimental recording.\n"
        f"- Collection status before independent verification: `{terminal_status}`; error: "
        f"`{campaign_error}`.\n"
        f"- Held out: `{len(held_out)}/20`; pilots: "
        f"`{len(pilots)}/2`.\n"
        f"- Camera sessions finalized: "
        f"`{media_summary.get('complete_session_count', 0)}/22`.\n"
        f"- Logged torque-off gravity-rest intervals: "
        f"`{len(gravity_rests)}`.\n"
        "- P06/P07 remained excluded from identification and "
        "model-selection decisions.\n"
        f"- Terminal torque disabled: "
        f"`{terminal_torque_disabled}`.\n"
        "- Video finalization, when applicable, ran only after the "
        "motor bus was closed.\n",
        encoding="utf-8",
    )
    inventory_digest, verification, verification_archive = (
        write_archived_verification(run_root)
    )
    write_report("g1_last_verification.json", verification)
    result = {
        "run_root": str(run_root),
        "experiment_number": experiment_number,
        "terminal_status": terminal_status,
        "held_out_episode_count": len(held_out),
        "pilot_episode_count": len(pilots),
        "gravity_rest_interval_count": len(gravity_rests),
        "camera_ready_before_motor_device_open": (
            camera_ready_before_motor_open
        ),
        "media_capture_status": media_summary.get("status"),
        "media_session_count": media_summary.get("session_count", 0),
        "campaign_error": campaign_error,
        "motor_device_opened": motor_device_opened,
        "motor_bus_close_succeeded": motor_bus_close_succeeded,
        "terminal_torque_disabled": terminal_torque_disabled,
        "inventory_sha256": inventory_digest,
        "verification_path": str(run_root / "VERIFICATION.json"),
        "verification_archive": verification_archive,
        "verification": verification,
        "motion_executed": bool(manifests),
        "passed": (
            terminal_status == "complete" and verification["passed"]
        ),
    }
    write_report("g1_last_run.json", result)
    return result


def finalize_incomplete(run_root: Path) -> dict[str, Any]:
    """Finish documentation for an already safely closed incomplete run."""

    run_root = run_root.resolve()
    run_manifest = base.read_json(run_root / "run.json")
    if run_manifest.get("terminal_status") != "incomplete":
        raise RuntimeError(
            "this action is only for an incomplete G1 run"
        )
    if run_manifest.get("terminal_torque_disabled") is not True:
        raise RuntimeError(
            "refusing finalization without terminal torque-off evidence"
        )
    if run_manifest.get("motor_bus_close_succeeded") is not True:
        raise RuntimeError(
            "refusing finalization without confirmed motor-bus close evidence"
        )
    manifests = [
        base.read_json(path)
        for path in sorted((run_root / "episodes").glob("*/episode.json"))
    ]
    summary = base.summarize_run(run_root, manifests)
    write_method_results(run_root, summary, manifests)
    media_summary_value = run_manifest.get("iphone_media_capture", {})
    media_summary = (
        dict(media_summary_value)
        if isinstance(media_summary_value, dict)
        else {
            "status": "unavailable",
            "session_count": 0,
            "index": None,
        }
    )
    write_start_here(
        run_root,
        config(),
        run_manifest=run_manifest,
        media_summary=media_summary,
        manifests=manifests,
    )

    command_log_path = run_root / "COMMAND_LOG.md"
    previous_log = (
        command_log_path.read_text(encoding="utf-8")
        if command_log_path.is_file()
        else ""
    )
    finalized_utc = datetime.now(UTC).isoformat()
    with command_log_path.open("a", encoding="utf-8") as stream:
        if not previous_log:
            stream.write("# Command log\n")
        if previous_log and not previous_log.endswith("\n"):
            stream.write("\n")
        stream.write(
            "\n## Offline documentation finalization\n\n"
            f"- Time (UTC): `{finalized_utc}`.\n"
            "- Action: `collect_g1.py --finalize <run-folder>`.\n"
            "- Physical collection status remains "
            f"`{run_manifest['terminal_status']}`; this documentation action "
            "does not change the physical outcome.\n"
            "- Prerequisite evidence in `run.json`: terminal torque disabled "
            "and motor bus close both confirmed.\n"
            "- Regenerated `START_HERE.md`, `G1_METHOD_AND_RESULTS.md`, "
            "`VERIFICATION.json`, and `inventory.sha256` from the artifacts "
            "already present in this run folder.\n"
            "- No motor device, camera service, or network connection was "
            "opened by this offline finalization.\n"
        )

    inventory_digest, verification, verification_archive = (
        write_archived_verification(run_root)
    )
    write_report("g1_last_verification.json", verification)
    result = {
        "run_root": str(run_root),
        "physical_terminal_status": str(run_manifest["terminal_status"]),
        "physical_collection_passed": False,
        "held_out_episode_count": int(
            run_manifest.get(
                "held_out_episode_count",
                sum(item.get("role") == "held_out" for item in manifests),
            )
        ),
        "pilot_episode_count": int(
            run_manifest.get(
                "pilot_episode_count",
                sum(item.get("role") == "pilot" for item in manifests),
            )
        ),
        "campaign_error": run_manifest.get("campaign_error"),
        "terminal_torque_disabled": True,
        "motor_bus_close_succeeded": True,
        "inventory_sha256": inventory_digest,
        "verification_path": str(run_root / "VERIFICATION.json"),
        "verification_archive": verification_archive,
        "verification": verification,
        "verification_passed": bool(verification.get("passed", False)),
        "motion_executed_during_finalize": False,
        "documentation_finalized": True,
        "operation_succeeded": True,
        "passed": False,
    }
    write_report("g1_incomplete_finalization.json", result)
    return result


def finalize_complete(run_root: Path) -> dict[str, Any]:
    """Recover documentation for an already closed, physically complete run."""

    run_root = run_root.resolve()
    run_manifest = base.read_json(run_root / "run.json")
    if run_manifest.get("terminal_status") != "complete":
        raise RuntimeError("refusing complete finalization for a non-complete run")
    if run_manifest.get("terminal_torque_disabled") is not True:
        raise RuntimeError(
            "refusing finalization without terminal torque-off evidence"
        )
    if run_manifest.get("motor_bus_close_succeeded") is not True:
        raise RuntimeError(
            "refusing finalization without confirmed motor-bus close evidence"
        )
    if run_manifest.get("media_finalized_after_motor_bus_close") is not True:
        raise RuntimeError(
            "refusing finalization without post-bus media-finalization evidence"
        )

    manifests = [
        base.read_json(path)
        for path in sorted((run_root / "episodes").glob("*/episode.json"))
    ]
    held_out = [item for item in manifests if item.get("role") == "held_out"]
    pilots = [item for item in manifests if item.get("role") == "pilot"]
    if (len(held_out), len(pilots)) != (20, 2):
        raise RuntimeError(
            "raw physical campaign is not complete: "
            f"held_out={len(held_out)}, pilots={len(pilots)}"
        )
    if not all(
        item.get("completion_status") == "complete"
        and item.get("terminal_torque_disabled") is True
        for item in manifests
    ):
        raise RuntimeError(
            "an episode is incomplete or lacks torque-off confirmation"
        )

    values = config()
    experiment_number = validated_experiment_number(
        str(run_manifest.get("experiment_number", ""))
    )
    expected_ids = [
        str(item["session_id"])
        for item in expected_g1_media_campaign(values, experiment_number)
    ]
    if run_manifest.get("episode_ids") != expected_ids:
        raise RuntimeError(
            "run manifest does not contain the exact 22-episode G1 campaign order"
        )
    manifests_by_id = {
        str(item.get("episode_id")): item for item in manifests
    }
    if (
        len(manifests_by_id) != len(expected_ids)
        or set(manifests_by_id) != set(expected_ids)
    ):
        raise RuntimeError(
            "saved episode manifests do not match the exact G1 campaign"
        )
    manifests = [manifests_by_id[episode_id] for episode_id in expected_ids]
    held_out = [item for item in manifests if item.get("role") == "held_out"]
    pilots = [item for item in manifests if item.get("role") == "pilot"]
    media_summary_value = run_manifest.get("iphone_media_capture", {})
    media_summary = (
        dict(media_summary_value)
        if isinstance(media_summary_value, dict)
        else {}
    )
    if not (
        media_summary.get("status") == "complete"
        and int(media_summary.get("session_count", -1)) == 22
        and int(media_summary.get("complete_session_count", -1)) == 22
    ):
        raise RuntimeError("the saved 22-session camera campaign is not complete")

    summary = base.summarize_run(run_root, manifests)
    write_method_results(run_root, summary, manifests)
    write_start_here(
        run_root,
        values,
        run_manifest=run_manifest,
        media_summary=media_summary,
        manifests=manifests,
    )

    command_log_path = run_root / "COMMAND_LOG.md"
    previous_log = (
        command_log_path.read_text(encoding="utf-8")
        if command_log_path.is_file()
        else ""
    )
    with command_log_path.open("a", encoding="utf-8") as stream:
        if not previous_log:
            stream.write("# Command log\n")
        if previous_log and not previous_log.endswith("\n"):
            stream.write("\n")
        stream.write(
            "\n## Offline complete-run finalization recovery\n\n"
            f"- Time (UTC): `{datetime.now(UTC).isoformat()}`.\n"
            "- Action: `collect_g1.py --finalize <run-folder>`.\n"
            "- The saved physical outcome remains `complete`; all 22 "
            "episodes had already ended and terminal torque-off plus motor-bus "
            "closure were confirmed before this action.\n"
            "- Regenerated the human-readable summaries, archived verification, "
            "inventory, and latest-run reports from existing artifacts.\n"
            "- No motor device, camera service, network connection, or motion "
            "was opened by this offline finalization.\n"
        )

    inventory_digest, verification, verification_archive = (
        write_archived_verification(run_root)
    )
    write_report("g1_last_verification.json", verification)
    result = {
        "run_root": str(run_root),
        "terminal_status": "complete",
        "held_out_episode_count": len(held_out),
        "pilot_episode_count": len(pilots),
        "gravity_rest_interval_count": int(
            run_manifest.get("gravity_rest_interval_count", 0)
        ),
        "camera_ready_before_motor_device_open": run_manifest.get(
            "camera_ready_before_motor_device_open"
        ),
        "media_capture_status": media_summary.get("status"),
        "media_session_count": media_summary.get("session_count", 0),
        "campaign_error": run_manifest.get("campaign_error"),
        "motor_device_opened": run_manifest.get("motor_device_opened"),
        "motor_bus_close_succeeded": True,
        "terminal_torque_disabled": True,
        "inventory_sha256": inventory_digest,
        "verification_path": str(run_root / "VERIFICATION.json"),
        "verification_archive": verification_archive,
        "verification": verification,
        "physical_motion_previously_executed": True,
        "motion_executed_during_finalize": False,
        "documentation_finalized": True,
        "passed": bool(verification.get("passed", False)),
    }
    write_report("g1_last_run.json", result)
    return result


def finalize_existing(run_root: Path) -> dict[str, Any]:
    """Finalize a safely closed G1 run without opening hardware or camera."""

    status = base.read_json(run_root.resolve() / "run.json").get(
        "terminal_status"
    )
    if status == "complete":
        return finalize_complete(run_root)
    if status == "incomplete":
        return finalize_incomplete(run_root)
    raise RuntimeError(f"unsupported saved terminal status: {status!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--validate", action="store_true")
    actions.add_argument("--availability", action="store_true")
    actions.add_argument("--camera-status", action="store_true")
    actions.add_argument("--status", action="store_true")
    actions.add_argument("--handoff-status", action="store_true")
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
    elif args.handoff_status:
        result = handoff_status()
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
