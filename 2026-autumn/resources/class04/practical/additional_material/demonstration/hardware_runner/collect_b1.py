#!/usr/bin/env python3
"""Collect documented V5 B1 ±80 mm H1/H2 calibration and held-out data."""

from __future__ import annotations

import argparse
import copy
import json
import platform
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import collect_b0 as runner
import collect_m0 as base
from dynamixel_io import DynamixelBus
from profiles import authoritative_active_profiles, executed_profiles, pilot_profile, profile_statistics


HERE = Path(__file__).resolve().parent
BASE_CONFIG_PATH = HERE / "experiment_config.json"
B1_CONFIG_PATH = HERE / "experiment_config_b1.json"


def config() -> dict[str, Any]:
    inherited = copy.deepcopy(base.read_json(BASE_CONFIG_PATH))
    overlay = base.read_json(B1_CONFIG_PATH)
    for spec in inherited["profiles"].values():
        spec["split"] = "calibration"
    inherited["profiles"].update(copy.deepcopy(overlay["profiles"]))
    for key, value in overlay.items():
        if key != "profiles":
            inherited[key] = copy.deepcopy(value)
    return inherited


def _configure_documented_runner() -> None:
    """Bind shared helpers to B1 only when a B1 entry point is invoked."""

    runner.CONFIG_PATH = B1_CONFIG_PATH
    base.CONFIG_PATH = B1_CONFIG_PATH
    runner.base.CONFIG_PATH = B1_CONFIG_PATH
    base.config = config
    runner.cfg = config
    runner.base.config = config


def write_report(name: str, value: Any) -> None:
    base.write_json(base.REPORT_ROOT / name, value)


def validate_legacy() -> dict[str, Any]:
    _configure_documented_runner()
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
    expected_vectors = {
        "H1": (600, 0, 150),
        "H2": (800, 0, 150),
        "H3": (600, 0, 220),
        "H4": (300, 0, 60),
        "H5": (1200, 0, 320),
    }
    goals = {
        name: zero
        + np.rint(profile.command_rad / base.POSITION_RAD_PER_TICK).astype(int)
        for name, profile in executed.items()
    }
    fixture = values["fixture"]
    checks = {
        "scope_is_B1": values["mechanical_configuration"] == "B1",
        "centers_are_minus_plus_80mm": fixture["payload_center_positions_mm"]
        == [-80, 80]
        and int(fixture["absolute_payload_center_distance_mm"]) == 80,
        "preliminary_inertia_not_claimed_measured": "preliminary" in fixture[
            "mass_property_status"
        ],
        "recollection_fixture_mass_declaration_exact": fixture.get(
            "fixture_revision"
        )
        == "2026-08-26-recollection-110g"
        and int(fixture.get("complete_payload_mass_each_g", -1)) == 44
        and fixture.get("complete_payload_includes_pin") is True
        and int(fixture.get("payload_count", -1)) == 2
        and int(fixture.get("link_mass_g", -1)) == 22
        and int(fixture.get("total_external_moving_mass_g", -1)) == 110,
        "target_is_ID5": int(values["dynamixel_id"]) == 5,
        "software_gate_is_exactly_plus_minus_90deg": (minimum, maximum)
        == (1024, 3072),
        "condition_vectors_unchanged": vectors == expected_vectors,
        "calibration_profiles_exact": {
            name
            for name, item in values["profiles"].items()
            if item["split"] == "calibration"
        }
        == {"P01_slow_triangle", "P02_multisine", "P03_smooth_levels"},
        "held_out_profile_is_only_P06": {
            name
            for name, item in values["profiles"].items()
            if item["split"] == "held_out"
        }
        == {"P06_heldout_composite"},
        "active_sample_counts_exact": {
            name: int(command.size) for name, command in active.items()
        }
        == {
            "P01_slow_triangle": 1201,
            "P02_multisine": 1201,
            "P03_smooth_levels": 755,
            "P06_heldout_composite": 1101,
        },
        "all_executed_profiles_start_and_end_at_zero": all(
            abs(float(profile.command_rad[0])) < 1e-12
            and abs(float(profile.command_rad[-1])) < 1e-12
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
        "calibration_design_is_three_repeats_all_H": set(
            values["condition_order_by_repeat"]
        )
        == {"R01", "R02", "R03"}
        and all(
            sorted(order) == sorted(values["controllers"])
            for order in values["condition_order_by_repeat"].values()
        ),
        "held_out_is_five_repeats_H1_H2": set(
            values["held_out_condition_order_by_repeat"]
        )
        == {"R01", "R02", "R03", "R04", "R05"}
        and all(
            sorted(order) == ["H1", "H2"]
            for order in values["held_out_condition_order_by_repeat"].values()
        ),
        "held_out_policy_is_explicit": "must not influence" in values[
            "data_policy"
        ]["held_out_policy"],
        "pilot_covers_baseline_and_extremes": values["pilot"]["controllers"]
        == ["H1", "H4", "H5"],
        "no_torque_channel_claimed": values["measurement_boundary"][
            "torque_channel_available"
        ]
        is False,
        "prior_observations_excluded": values["data_policy"][
            "prior_zip_or_V4_observations_used"
        ]
        is False,
    }
    report = {
        "experiment_id": values["experiment_id"],
        "base_config": str(BASE_CONFIG_PATH),
        "base_config_sha256": base.sha256_file(BASE_CONFIG_PATH),
        "B1_overlay": str(B1_CONFIG_PATH),
        "B1_overlay_sha256": base.sha256_file(B1_CONFIG_PATH),
        "fixture": fixture,
        "checks": checks,
        "profile_statistics": {
            name: profile_statistics(profile, dt_s)
            for name, profile in executed.items()
        },
        "passed": all(checks.values()),
    }
    write_report("b1_validation.json", report)
    return report


def status_legacy() -> dict[str, Any]:
    offline = validate_legacy()
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
        result["fixture_declaration"] = values["fixture"]
        result["offline_validation_passed"] = True
        result["availability_before_open"] = available
    write_report("b1_live_status.json", result)
    return result


def write_method_results(run_root: Path, summary: pd.DataFrame) -> None:
    calibration = summary[summary["role"] == "calibration"]
    held_out = summary[summary["role"] == "held_out"]
    lines = [
        "# V5 B1 ±80 mm hardware collection: method and results",
        "",
        f"Run: `{run_root.name}`",
        "",
        "## Physical fixture",
        "",
        "B1 was physically installed as a balanced fixture with equal payload centers at **−80 mm and +80 mm**. For this recollection, each complete payload is **44 g including its pin**, and the link is **22 g**, giving **110 g total external moving mass**. The PDF's `0.00075 kg·m²` value remains a preliminary design value and is not reused; link rotational inertia still requires link geometry.",
        "",
        "## Episode design",
        "",
        "- Calibration: P01–P03 × H1–H5 × three repeats = 45 episodes.",
        "- Untouched held out: P06 × H1/H2 × five repeats = 10 episodes.",
        "- Safety pilots after the fixture change: H1, H4, and H5 = 3 episodes.",
        "- P06 was not used for fitting, bounds, timing/filter choices, or model selection.",
        "",
        "## Collection outcome",
        "",
        f"- Complete calibration episodes: {int((calibration['completion_status'] == 'complete').sum())} / 45.",
        f"- Complete held-out episodes: {int((held_out['completion_status'] == 'complete').sum())} / 10.",
        f"- Complete pilot episodes: {int(((summary['role'] == 'pilot') & (summary['completion_status'] == 'complete')).sum())} / 3.",
        f"- Maximum input-supply current: {summary['maximum_abs_current_A'].max():.6f} A.",
        f"- Maximum PWM fraction: {summary['maximum_abs_pwm_fraction'].max():.6f}.",
        f"- Maximum temperature: {summary['maximum_temperature_C'].max():.1f} °C.",
        f"- Minimum voltage: {summary['minimum_voltage_V'].min():.1f} V.",
        "",
        "### Calibration tracking",
        "",
        "| H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |",
        "|---|---:|---:|---:|---:|",
    ]
    for condition, group in calibration.groupby("controller_id", sort=True):
        lines.append(
            f"| {condition} | {len(group)} | {group['tracking_rmse_rad_active'].mean():.9f} | "
            f"{group['tracking_rmse_rad_active'].std(ddof=1):.9f} | "
            f"{group['tracking_peak_abs_rad_active'].max():.9f} |"
        )
    lines.extend(
        [
            "",
            "### Frozen held-out hardware tracking",
            "",
            "These statistics describe command tracking only. No candidate MuJoCo model has been evaluated here.",
            "",
            "| H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for condition, group in held_out.groupby("controller_id", sort=True):
        lines.append(
            f"| {condition} | {len(group)} | {group['tracking_rmse_rad_active'].mean():.9f} | "
            f"{group['tracking_rmse_rad_active'].std(ddof=1):.9f} | "
            f"{group['tracking_peak_abs_rad_active'].max():.9f} |"
        )
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            "Present Current remains XC330 input-supply-current telemetry, not measured output torque. No MuJoCo joint parameters or equivalent gains are identified during collection. The campaign stops after B1.",
        ]
    )
    (run_root / "B1_METHOD_AND_RESULTS.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def verify_legacy_run(run_root: Path) -> dict[str, Any]:
    _configure_documented_runner()
    values = config()
    run_manifest = base.read_json(run_root / "run.json")
    inventory_lines = [
        line.split("  ", 1)
        for line in (run_root / "inventory.sha256").read_text(encoding="utf-8").splitlines()
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
    held_out = [item for item in manifests if item["role"] == "held_out"]
    pilots = [item for item in manifests if item["role"] == "pilot"]
    expected_calibration = {
        f"B1__{condition}__{profile}__{repeat}"
        for repeat in ("R01", "R02", "R03")
        for profile in ("P01_slow_triangle", "P02_multisine", "P03_smooth_levels")
        for condition in values["controllers"]
    }
    expected_held_out = {
        f"B1__{condition}__P06_heldout_composite__{repeat}"
        for repeat in ("R01", "R02", "R03", "R04", "R05")
        for condition in ("H1", "H2")
    }
    data_checks: list[bool] = []
    torque_columns: list[str] = []
    for manifest in manifests:
        episode_root = run_root / "episodes" / manifest["episode_id"]
        command = pd.read_parquet(episode_root / "command_events.parquet")
        telemetry = pd.read_parquet(episode_root / "telemetry_events.parquet")
        torque_columns.extend(
            column
            for column in [*command.columns, *telemetry.columns]
            if "torque" in column.lower() and "torque_enable" not in column.lower()
        )
        first_goal = int(command.iloc[0]["goal_position_raw_requested"])
        data_checks.append(
            bool(
                len(command)
                and len(telemetry)
                and command["goal_position_raw_requested"].between(1024, 3072).all()
                and telemetry["present_position_raw"].between(1024, 3072).all()
                and (manifest["role"] == "preparation" or first_goal == 2048)
                and telemetry["hardware_error_status_raw"].eq(0).all()
                and manifest["mechanical_configuration"] == "B1"
                and manifest["fixture"]["payload_center_positions_mm"] == [-80, 80]
            )
        )
    checks = {
        "run_complete": run_manifest["terminal_status"] == "complete",
        "exact_45_calibration": len(calibration) == 45,
        "calibration_matrix_exact": {item["episode_id"] for item in calibration}
        == expected_calibration,
        "exact_10_held_out": len(held_out) == 10,
        "held_out_matrix_exact": {item["episode_id"] for item in held_out}
        == expected_held_out,
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
        "all_episode_data_checks": all(data_checks),
        "all_manifests_record_80mm": all(
            item.get("fixture", {}).get("payload_center_positions_mm") == [-80, 80]
            for item in manifests
        ),
        "run_and_episode_manifests_record_exact_recollection_mass": (
            run_manifest.get("experiment_id")
            != "v5-b1-80mm-h1-h5-p01-p03-p06-hardware-v2-fixture110g"
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
        "held_out_only_H1_H2": {item["controller_id"] for item in held_out}
        == {"H1", "H2"},
        "no_manufactured_torque_column": not torque_columns,
        "inventory_hashes_match": not hash_failures,
        "summary_exists": (run_root / "episode-summary.csv").is_file(),
        "method_results_exists": (run_root / "B1_METHOD_AND_RESULTS.md").is_file(),
    }
    return {
        "run_root": str(run_root),
        "checks": checks,
        "episode_manifest_count": len(manifests),
        "calibration_episode_count": len(calibration),
        "held_out_episode_count": len(held_out),
        "pilot_episode_count": len(pilots),
        "inventory_entry_count": len(inventory_lines),
        "inventory_hash_failures": hash_failures,
        "torque_measurement_columns": sorted(set(torque_columns)),
        "passed": all(checks.values()),
    }


def run_legacy() -> dict[str, Any]:
    offline = validate_legacy()
    if not offline["passed"]:
        return {"status": "blocked_by_offline_validation", "passed": False, "motion_executed": False}
    available = base.availability()
    if not available["available"]:
        return {"status": "blocked_device_absent_or_owned", "availability": available, "passed": False, "motion_executed": False}
    values = config()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = base.RAW_ROOT / f"v5-b1-80mm-{timestamp}-{uuid.uuid4().hex[:8]}"
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
                episode_id = f"B1__{condition}__PILOT_LOW_AMPLITUDE"
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
            held_out_profile = generated["P06_heldout_composite"]
            completed = 0
            for repeat, order in values["condition_order_by_repeat"].items():
                for profile_id, profile in calibration_profiles.items():
                    for condition in order:
                        recenter_index = base.ensure_zero(bus, run_root, recenter_index, manifests)
                        completed += 1
                        episode_id = f"B1__{condition}__{profile_id}__{repeat}"
                        print(f"CALIBRATION {completed:02d}/45: {episode_id}", flush=True)
                        manifest = base.run_episode(bus, run_root, episode_id, condition, profile, "calibration", repeat, True)
                        manifests.append(manifest)
                        print(f"RESULT {episode_id}: {manifest['completion_status']}", flush=True)
                        if manifest["completion_status"] != "complete":
                            raise RuntimeError(f"calibration failed: {manifest['failures']}")

            completed = 0
            for repeat, order in values["held_out_condition_order_by_repeat"].items():
                for condition in order:
                    recenter_index = base.ensure_zero(bus, run_root, recenter_index, manifests)
                    completed += 1
                    episode_id = f"B1__{condition}__P06_heldout_composite__{repeat}"
                    print(f"HELD_OUT {completed:02d}/10: {episode_id}", flush=True)
                    manifest = base.run_episode(bus, run_root, episode_id, condition, held_out_profile, "held_out", repeat, True)
                    manifests.append(manifest)
                    print(f"RESULT {episode_id}: {manifest['completion_status']}", flush=True)
                    if manifest["completion_status"] != "complete":
                        raise RuntimeError(f"held-out episode failed: {manifest['failures']}")
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
    held_out = [item for item in manifests if item["role"] == "held_out"]
    pilots = [item for item in manifests if item["role"] == "pilot"]
    terminal_status = "complete" if (
        campaign_error is None
        and len(calibration) == 45
        and len(held_out) == 10
        and len(pilots) == 3
        and all(item["completion_status"] == "complete" for item in manifests)
        and terminal_torque_disabled
    ) else "incomplete"
    run_manifest = {
        "schema_version": 1,
        "experiment_id": values["experiment_id"],
        "run_id": run_root.name,
        "mechanical_configuration": "B1",
        "fixture": values["fixture"],
        "dynamixel_id": 5,
        "source_type": "new_V5_physical_hardware_measurement",
        "start_utc": timestamp,
        "end_utc": datetime.now(UTC).isoformat(),
        "host_platform": platform.platform(),
        "episode_ids": [item["episode_id"] for item in manifests],
        "calibration_episode_count": len(calibration),
        "held_out_episode_count": len(held_out),
        "pilot_episode_count": len(pilots),
        "preparation_episode_count": sum(item["role"] == "preparation" for item in manifests),
        "campaign_error": campaign_error,
        "terminal_torque_disabled": terminal_torque_disabled,
        "terminal_status": terminal_status,
        "held_out_policy": values["data_policy"]["held_out_policy"],
        "stopped_after_B1": True,
    }
    base.write_json(run_root / "run.json", run_manifest)
    summary = base.summarize_run(run_root, manifests)
    write_method_results(run_root, summary)
    (run_root / "COMMAND_LOG.md").write_text(
        "# Command log\n\n"
        f"- `{datetime.now(UTC).isoformat()}`: `collect_b1.py --run`\n"
        "- Fixture: B1 with payload centers at `-80 mm` and `+80 mm`.\n"
        "- Recollection fixture revision: two complete `44 g` payloads including pins, one `22 g` link, `110 g` total external moving mass.\n"
        f"- Result: `{terminal_status}`; error: `{campaign_error}`.\n"
        f"- Calibration: `{len(calibration)}/45`; held out: `{len(held_out)}/10`; pilots: `{len(pilots)}/3`.\n"
        "- P06 remained excluded from all fitting/model-selection decisions.\n"
        f"- Terminal torque disabled: `{terminal_torque_disabled}`.\n",
        encoding="utf-8",
    )
    inventory_digest = base.write_inventory(run_root)
    verification = verify_run(run_root)
    write_report("b1_last_verification.json", verification)
    result = {
        "run_root": str(run_root),
        "terminal_status": terminal_status,
        "calibration_episode_count": len(calibration),
        "held_out_episode_count": len(held_out),
        "pilot_episode_count": len(pilots),
        "preparation_episode_count": sum(item["role"] == "preparation" for item in manifests),
        "campaign_error": campaign_error,
        "terminal_torque_disabled": terminal_torque_disabled,
        "inventory_sha256": inventory_digest,
        "verification": verification,
        "motion_executed": bool(manifests),
        "passed": terminal_status == "complete" and verification["passed"],
    }
    write_report("b1_last_run.json", result)
    return result


def validate() -> dict[str, Any]:
    """Validate the documented 30-session B1 campaign."""

    _configure_documented_runner()
    return runner.validate()


def status() -> dict[str, Any]:
    """Use the shared balanced-fixture status gate with B1 configuration."""

    _configure_documented_runner()
    return runner.status()


def iphone_camera_status() -> dict[str, Any]:
    """Check the required camera path without opening the motor device."""

    _configure_documented_runner()
    return runner.iphone_camera_status()


def run() -> dict[str, Any]:
    """Collect the new schema-2 B1 campaign through documented support."""

    _configure_documented_runner()
    return runner.run_documented()


def verify_run(run_root: Path) -> dict[str, Any]:
    """Verify schema-2 captures while retaining schema-1 B1 history."""

    _configure_documented_runner()
    run_manifest = base.read_json(run_root / "run.json")
    if (
        int(run_manifest.get("schema_version", 1)) >= 2
        and run_manifest.get("experiment_number") is not None
    ):
        return runner.verify_documented_run(run_root)
    return verify_legacy_run(run_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--validate", action="store_true")
    actions.add_argument("--availability", action="store_true")
    actions.add_argument("--camera-status", action="store_true")
    actions.add_argument("--status", action="store_true")
    actions.add_argument("--run", action="store_true")
    actions.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.validate:
        result = validate()
    elif args.availability:
        _configure_documented_runner()
        result = base.availability()
        result["passed"] = result["available"]
    elif args.camera_status:
        result = iphone_camera_status()
    elif args.status:
        result = status()
    elif args.run:
        result = run()
    else:
        result = verify_run(args.verify.resolve())
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0 if result.get("passed", False) else 2


if __name__ == "__main__":
    raise SystemExit(main())
