#!/usr/bin/env python3
"""Safety-gated V5 M0 hardware campaign for XC330-M288-T ID5."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import platform
import subprocess
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from dynamixel_io import (
    EXPECTED_MODEL_NUMBER,
    REGISTERS,
    BulkTelemetryReader,
    DynamixelBus,
    signed,
    snapshot,
)
from profiles import (
    ExecutedProfile,
    authoritative_active_profiles,
    executed_profiles,
    pilot_profile,
    profile_statistics,
)


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "experiment_config.json"
DATA_ROOT = HERE / "data"
RAW_ROOT = DATA_ROOT / "raw"
REPORT_ROOT = HERE / "reports"
LOCK_PATH = HERE / ".hardware.lock"

POSITION_RAD_PER_TICK = 2.0 * np.pi / 4096.0
VELOCITY_RAD_S_PER_RAW = 0.229 * 2.0 * np.pi / 60.0
PWM_FRACTION_PER_RAW = 0.00113
CURRENT_A_PER_RAW = 0.001


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def config() -> dict[str, Any]:
    return read_json(CONFIG_PATH)


def device_owners(device: Path) -> list[dict[str, Any]]:
    if not device.exists():
        return []
    try:
        result = subprocess.run(
            ["fuser", str(device)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return [{"pid": None, "command": None, "inspection_error": str(exc)}]
    owners: list[dict[str, Any]] = []
    for token in result.stdout.split():
        if not token.isdigit() or int(token) == os.getpid():
            continue
        pid = int(token)
        try:
            command = (
                (Path("/proc") / str(pid) / "cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode()
                .strip()
            )
        except OSError:
            command = None
        owners.append({"pid": pid, "command": command})
    return owners


def availability() -> dict[str, Any]:
    device = Path(str(config()["serial_port"]))
    owners = device_owners(device)
    report = {
        "operation": "ownership_only_no_serial_open",
        "device": str(device),
        "device_exists": device.exists(),
        "owners": owners,
        "available": device.exists() and not owners,
        "motion_executed": False,
    }
    write_json(REPORT_ROOT / "availability.json", report)
    return report


@contextmanager
def hardware_lock() -> Iterator[None]:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("the V5 hardware collector lock is already held") from exc
        stream.seek(0)
        stream.truncate()
        stream.write(f"pid={os.getpid()}\n")
        stream.flush()
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def active_sample_counts() -> dict[str, int]:
    return {
        name: int(values.size)
        for name, values in authoritative_active_profiles(config()).items()
    }


def validate() -> dict[str, Any]:
    cfg = config()
    dt_s = 1.0 / float(cfg["command_rate_hz"])
    conditions = cfg["controllers"]
    executed = executed_profiles(cfg)
    profiles_stats = {
        name: profile_statistics(profile, dt_s)
        for name, profile in executed.items()
    }
    expected_vectors = {
        "H1": (600, 0, 150),
        "H2": (800, 0, 150),
        "H3": (600, 0, 220),
        "H4": (300, 0, 60),
        "H5": (1200, 0, 320),
    }
    actual_vectors = {
        name: (
            int(values["position_p_gain_raw"]),
            int(values["position_i_gain_raw"]),
            int(values["position_d_gain_raw"]),
        )
        for name, values in conditions.items()
    }
    minimum = int(cfg["software_goal_min_raw"])
    maximum = int(cfg["software_goal_max_raw"])
    zero = int(cfg["servo_zero_raw"])
    raw_goals = {
        name: zero + np.rint(profile.command_rad / POSITION_RAD_PER_TICK).astype(int)
        for name, profile in executed.items()
    }
    schedule_conditions = [
        value
        for order in cfg["condition_order_by_repeat"].values()
        for value in order
    ]
    checks = {
        "scope_is_M0": cfg["mechanical_configuration"] == "M0",
        "target_is_ID5": int(cfg["dynamixel_id"]) == 5,
        "model_number_is_XC330_M288": int(cfg["expected_model_number"])
        == EXPECTED_MODEL_NUMBER,
        "zero_is_tick_2048": zero == 2048,
        "software_gate_is_exactly_plus_minus_90deg": minimum == 1024
        and maximum == 3072,
        "condition_vectors_frozen": actual_vectors == expected_vectors,
        "H2_is_P_only_change": actual_vectors["H2"][1:] == actual_vectors["H1"][1:]
        and actual_vectors["H2"][0] != actual_vectors["H1"][0],
        "H3_is_D_only_change": actual_vectors["H3"][:2] == actual_vectors["H1"][:2]
        and actual_vectors["H3"][2] != actual_vectors["H1"][2],
        "H4_is_low_and_H5_is_high": actual_vectors["H4"][0] < actual_vectors["H1"][0]
        and actual_vectors["H4"][2] < actual_vectors["H1"][2]
        and actual_vectors["H5"][0] > actual_vectors["H1"][0]
        and actual_vectors["H5"][2] > actual_vectors["H1"][2],
        "integral_is_fixed_zero": all(vector[1] == 0 for vector in actual_vectors.values()),
        "active_profile_sample_counts_match_V5": active_sample_counts()
        == {
            "P01_slow_triangle": 1201,
            "P02_multisine": 1201,
            "P03_smooth_levels": 755,
        },
        "executed_profiles_start_and_end_at_zero": all(
            math.isclose(float(profile.command_rad[0]), 0.0, abs_tol=1e-12)
            and math.isclose(float(profile.command_rad[-1]), 0.0, abs_tol=1e-12)
            for profile in executed.values()
        ),
        "all_profile_goals_inside_software_gate": all(
            int(values.min()) >= minimum and int(values.max()) <= maximum
            for values in raw_goals.values()
        ),
        "three_repeats_frozen": int(cfg["required_complete_repetitions"]) == 3
        and set(cfg["condition_order_by_repeat"]) == {"R01", "R02", "R03"},
        "each_repeat_contains_each_condition_once": all(
            sorted(order) == sorted(conditions)
            for order in cfg["condition_order_by_repeat"].values()
        ),
        "schedule_contains_15_condition_slots": len(schedule_conditions) == 15,
        "pilot_covers_baseline_and_extremes": cfg["pilot"]["controllers"]
        == ["H1", "H4", "H5"],
        "no_mujoco_gains_in_hardware_config": not any(
            "mujoco" in key.lower()
            for values in conditions.values()
            for key in values
        ),
        "no_torque_channel_claimed": cfg["measurement_boundary"][
            "torque_channel_available"
        ]
        is False,
        "V4_or_prior_observations_excluded": cfg["data_policy"][
            "prior_zip_or_V4_observations_used"
        ]
        is False,
    }
    report = {
        "experiment_id": cfg["experiment_id"],
        "checks": checks,
        "condition_vectors_P_I_D_raw": actual_vectors,
        "executed_profile_statistics": profiles_stats,
        "passed": all(checks.values()),
    }
    write_json(REPORT_ROOT / "validation.json", report)
    return report


def disable_discovered(bus: DynamixelBus, discovered: dict[int, Any]) -> list[str]:
    failures: list[str] = []
    for device_id in discovered:
        try:
            bus.torque_disable(int(device_id))
        except RuntimeError as exc:
            failures.append(str(exc))
    return failures


def read_only_status_on_open_bus(bus: DynamixelBus) -> dict[str, Any]:
    cfg = config()
    device_id = int(cfg["dynamixel_id"])
    discovered = bus.discover()
    cleanup_failures = disable_discovered(bus, discovered)
    exact_device = set(discovered) == {device_id}
    identity = discovered.get(device_id, {})
    if not exact_device or identity.get("model_number") != int(cfg["expected_model_number"]):
        return {
            "discovered": discovered,
            "cleanup_failures": cleanup_failures,
            "checks": {
                "exactly_one_device_and_it_is_ID5": exact_device,
                "model_number": identity.get("model_number")
                == int(cfg["expected_model_number"]),
            },
            "passed": False,
            "motion_executed": False,
        }
    state = snapshot(bus, device_id)
    present = signed(state["present_position"], 32)
    canonical_present = present % 4096
    voltage_v = state["input_voltage"] * 0.1
    temperature_c = state["temperature"]
    checks = {
        "exactly_one_device_and_it_is_ID5": exact_device,
        "model_number": state["model_number"] == int(cfg["expected_model_number"]),
        "firmware_matches_discovery": state["firmware_version"]
        == identity["firmware_version"],
        "id_register": state["id"] == device_id,
        "torque_disabled": state["torque_enable"] == 0,
        "position_inside_software_gate": int(cfg["software_goal_min_raw"])
        <= present
        <= int(cfg["software_goal_max_raw"]),
        "physical_equivalent_position_inside_software_gate": int(
            cfg["software_goal_min_raw"]
        )
        <= canonical_present
        <= int(cfg["software_goal_max_raw"]),
        "voltage": float(cfg["interlocks"]["start_voltage_min_V"])
        <= voltage_v
        <= float(cfg["interlocks"]["start_voltage_max_V"]),
        "temperature": temperature_c
        <= int(cfg["interlocks"]["start_temperature_max_C"]),
        "hardware_error": state["hardware_error_status"] == 0,
        "cleanup_succeeded": not cleanup_failures,
    }
    return {
        "operation": "read_only_status_with_torque_disable_safety_write",
        "device": cfg["serial_port"],
        "discovered": discovered,
        "state": state,
        "present_position_raw_signed": present,
        "present_position_canonical_one_turn_raw": canonical_present,
        "torque_off_counter_canonicalization_needed": present != canonical_present,
        "position_relative_to_zero_deg": (present - int(cfg["servo_zero_raw"]))
        * 360.0
        / 4096.0,
        "input_voltage_V": voltage_v,
        "temperature_C": temperature_c,
        "checks": checks,
        "passed": all(checks.values()),
        "motion_executed": False,
    }


def canonicalize_torque_off_position_counter(bus: DynamixelBus) -> dict[str, Any]:
    """Reset a mode-5 multi-turn count to its equivalent one-turn tick without motion."""

    cfg = config()
    device_id = int(cfg["dynamixel_id"])
    minimum = int(cfg["software_goal_min_raw"])
    maximum = int(cfg["software_goal_max_raw"])
    bus.torque_disable(device_id)
    before_mode = bus.read(device_id, "operating_mode")
    before_raw = signed(bus.read(device_id, "present_position"), 32)
    canonical_before = before_raw % 4096
    physical_minimum = (
        int(cfg.get("gravity_passive_transient_min_raw", minimum))
        if cfg.get("gravity_loaded_active_zero_start", False)
        else minimum
    )
    if not physical_minimum <= canonical_before <= maximum:
        raise RuntimeError(
            "physical-equivalent one-turn position is outside the declared "
            "torque-off physical envelope"
        )
    if before_raw == canonical_before:
        return {
            "performed": False,
            "reason": "position counter already canonical",
            "operating_mode_before": before_mode,
            "present_position_before_raw_signed": before_raw,
            "present_position_after_raw_signed": before_raw,
            "physical_motion_commanded": False,
            "torque_enabled": False,
            "passed": True,
        }
    # Selecting Position Control Mode resets Present Position to its one-turn
    # absolute value. Torque remains disabled and no Goal Position is sent.
    bus.write(device_id, "operating_mode", 3)
    in_position_mode = signed(bus.read(device_id, "present_position"), 32)
    bus.write(device_id, "operating_mode", before_mode)
    restored = signed(bus.read(device_id, "present_position"), 32)
    torque = bus.read(device_id, "torque_enable")
    restored_mode = bus.read(device_id, "operating_mode")
    passed = bool(
        torque == 0
        and physical_minimum <= restored <= maximum
        and abs(restored - canonical_before) <= 2
        and restored_mode == before_mode
    )
    report = {
        "performed": True,
        "reason": "mode-5 continuous counter represented an equivalent multi-turn tick",
        "operating_mode_before": before_mode,
        "temporary_operating_mode": 3,
        "operating_mode_restored": restored_mode,
        "present_position_before_raw_signed": before_raw,
        "canonical_equivalent_before_raw": canonical_before,
        "present_position_in_temporary_position_mode_raw_signed": in_position_mode,
        "present_position_after_raw_signed": restored,
        "physical_motion_commanded": False,
        "torque_enabled": bool(torque),
        "passed": passed,
    }
    if not passed:
        raise RuntimeError(f"torque-off position canonicalization failed: {report}")
    return report


def status() -> dict[str, Any]:
    offline = validate()
    available = availability()
    if not offline["passed"] or not available["available"]:
        result = {
            "offline_validation": offline,
            "availability": available,
            "passed": False,
            "motion_executed": False,
        }
        write_json(REPORT_ROOT / "live_status.json", result)
        return result
    with hardware_lock():
        cfg = config()
        bus = DynamixelBus(str(cfg["serial_port"]), int(cfg["baud_rate_bps"]))
        try:
            result = read_only_status_on_open_bus(bus)
        finally:
            bus.close()
    result["offline_validation_passed"] = offline["passed"]
    result["availability_before_open"] = available
    write_json(REPORT_ROOT / "live_status.json", result)
    return result


def condition_registers(condition_id: str) -> dict[str, int]:
    cfg = config()
    values = {name: int(value) for name, value in cfg["shared_registers"].items()}
    condition = cfg["controllers"][condition_id]
    values.update(
        {
            "position_p_gain": int(condition["position_p_gain_raw"]),
            "position_i_gain": int(condition["position_i_gain_raw"]),
            "position_d_gain": int(condition["position_d_gain_raw"]),
        }
    )
    return values


def write_if_changed(bus: DynamixelBus, device_id: int, name: str, value: int) -> None:
    current = bus.read(device_id, name)
    if name == "bus_watchdog" and current == 255:
        bus.write(device_id, name, 0)
        current = bus.read(device_id, name)
    if current != value:
        bus.write(device_id, name, value)


def apply_condition(
    bus: DynamixelBus, condition_id: str
) -> tuple[dict[str, int], list[str]]:
    cfg = config()
    device_id = int(cfg["dynamixel_id"])
    expected = condition_registers(condition_id)
    order: list[str] = []
    bus.torque_disable(device_id)
    order.append("torque_disable_ID5")
    if bus.read(device_id, "model_number") != int(cfg["expected_model_number"]):
        raise RuntimeError("model-number gate failed")
    if bus.read(device_id, "id") != device_id:
        raise RuntimeError("ID gate failed")
    if bus.read(device_id, "baud_rate") != expected["baud_rate"]:
        raise RuntimeError("baud-rate register gate failed")
    order.append("verify_model_ID_and_baud")
    for name in ("operating_mode", "drive_mode"):
        write_if_changed(bus, device_id, name, expected[name])
    order.append("set_mode_and_direction_while_torque_off")
    for name in (
        "return_delay_time",
        "secondary_id",
        "homing_offset",
        "temperature_limit",
        "max_voltage_limit",
        "min_voltage_limit",
        "pwm_limit",
        "current_limit",
        "velocity_limit",
        "startup_configuration",
        "pwm_slope",
        "shutdown",
        "status_return_level",
        "velocity_i_gain",
        "velocity_p_gain",
        "position_d_gain",
        "position_i_gain",
        "position_p_gain",
        "feedforward_2nd_gain",
        "feedforward_1st_gain",
        "profile_acceleration",
        "profile_velocity",
        "goal_pwm",
        "goal_current",
        "bus_watchdog",
    ):
        write_if_changed(bus, device_id, name, expected[name])
    order.append("write_and_freeze_protection_gain_profile_and_effort_registers")
    readback = {name: bus.read(device_id, name) for name in expected}
    mismatch = {
        name: {"expected": value, "actual": readback[name]}
        for name, value in expected.items()
        if readback[name] != value
    }
    if mismatch:
        raise RuntimeError(f"condition register readback mismatch: {mismatch}")
    matched = False
    last_present: int | None = None
    last_goal_readback: int | None = None
    gravity_loaded = bool(
        config().get("gravity_loaded_active_zero_start", False)
    )
    for _ in range(10):
        present_register = bus.read(device_id, "present_position")
        present = (
            signed(present_register, 32)
            if gravity_loaded
            else present_register
        )
        last_present = present
        # With torque disabled, DYNAMIXEL mirrors Goal Position to Present
        # Position. Preserve that no-jump latch even when passive gravity rest
        # lies just below the energized command gate. The first energized
        # gravity-pickup command is independently clamped inside the gate.
        handoff_goal = present
        bus.write(device_id, "goal_position", handoff_goal)
        goal_register = bus.read(device_id, "goal_position")
        last_goal_readback = (
            signed(goal_register, 32) if gravity_loaded else goal_register
        )
        if gravity_loaded:
            matched = last_goal_readback == handoff_goal
        else:
            matched = last_goal_readback == bus.read(
                device_id, "present_position"
            )
        if matched:
            break
    if not matched:
        raise RuntimeError(
            "goal-equals-present gate failed after bounded retries: "
            f"gravity_loaded={gravity_loaded}, "
            f"last_present={last_present}, "
            f"last_goal_readback={last_goal_readback}"
        )
    order.append(
        "gravity_torque_off_goal_latched_to_latest_position"
        if gravity_loaded
        else "readback_and_goal_equal_present"
    )
    return readback, order


def telemetry_timing_quality(request_ns: np.ndarray) -> dict[str, Any]:
    limits = config()["timing_quality"]
    gaps = np.diff(np.asarray(request_ns, dtype=np.int64)).astype(float) * 1e-9
    if not gaps.size:
        return {"passed": False, "reason": "fewer than two samples"}
    achieved = 1.0 / float(np.mean(gaps))
    p99_9 = float(np.percentile(gaps, 99.9))
    maximum = float(np.max(gaps))
    threshold = float(limits["outlier_gap_threshold_s"])
    count = int(np.count_nonzero(gaps > threshold))
    fraction = float(count / gaps.size)
    checks = {
        "minimum_rate": achieved >= float(limits["minimum_achieved_rate_hz"]),
        "p99_9_gap": p99_9 <= float(limits["p99_9_max_gap_s"]),
        "outlier_fraction": fraction <= float(limits["maximum_outlier_fraction"]),
        "absolute_max_gap": maximum <= float(limits["absolute_max_gap_s"]),
    }
    return {
        "achieved_rate_hz": achieved,
        "mean_gap_s": float(np.mean(gaps)),
        "p99_9_gap_s": p99_9,
        "max_gap_s": maximum,
        "outlier_count": count,
        "outlier_fraction": fraction,
        "checks": checks,
        "passed": all(checks.values()),
    }


def advance_gravity_measured_position_gate(
    *,
    position: int,
    gate_entered: bool,
    passive_minimum: int,
    command_minimum: int,
    command_maximum: int,
    entry_hysteresis_ticks: int,
) -> bool:
    """Advance the one-way measured-position gate used during G1 pickup."""

    if entry_hysteresis_ticks < 0:
        raise RuntimeError(
            "gravity measured-position gate hysteresis must be non-negative"
        )
    entry_raw = command_minimum + entry_hysteresis_ticks
    if entry_raw > command_maximum:
        raise RuntimeError(
            "gravity measured-position gate entry exceeds the software maximum"
        )
    gate_entered = gate_entered or position >= entry_raw
    active_minimum = command_minimum if gate_entered else passive_minimum
    if not active_minimum <= position <= command_maximum:
        raise RuntimeError(
            "gravity-zero measured-position gate: "
            f"position={position}, allowed={active_minimum}..{command_maximum}, "
            f"strict_gate_entered={gate_entered}"
        )
    return gate_entered


def acquire_gravity_loaded_zero(
    bus: DynamixelBus,
    reader: BulkTelemetryReader,
    episode_id: str,
    current_raw: int,
) -> tuple[list[dict[str, Any]], int]:
    """Move to raw zero under torque and keep torque enabled for episode start."""

    cfg = config()
    device_id = int(cfg["dynamixel_id"])
    zero = int(cfg["servo_zero_raw"])
    tolerance = int(cfg["servo_zero_tolerance_ticks"])
    minimum = int(cfg["software_goal_min_raw"])
    maximum = int(cfg["software_goal_max_raw"])
    passive_minimum = int(
        cfg.get("gravity_passive_transient_min_raw", minimum)
    )
    entry_hysteresis_ticks = int(
        cfg.get("gravity_measured_position_gate_entry_hysteresis_ticks", 0)
    )
    entry_raw = minimum + entry_hysteresis_ticks
    dt_s = 1.0 / float(cfg["command_rate_hz"])
    interlocks = cfg["interlocks"]
    bounded_start_raw = int(np.clip(current_raw, minimum, maximum))
    profile = recenter_profile(bounded_start_raw, 0)
    raw_goals = zero + np.rint(
        profile.command_rad / POSITION_RAD_PER_TICK
    ).astype(int)
    events: list[dict[str, Any]] = []
    following_start: float | None = None
    current_start: float | None = None
    pwm_start: float | None = None
    start = time.monotonic()
    start_ns = time.monotonic_ns()
    feedback_position = current_raw
    setup_bias_ticks = 0.0
    entered_command_position_gate = (
        advance_gravity_measured_position_gate(
            position=current_raw,
            gate_entered=False,
            passive_minimum=passive_minimum,
            command_minimum=minimum,
            command_maximum=maximum,
            entry_hysteresis_ticks=entry_hysteresis_ticks,
        )
    )
    for index, goal_raw in enumerate(raw_goals):
        deadline = start + index * dt_s
        sleep_s = deadline - time.monotonic()
        if sleep_s > 0.00025:
            time.sleep(sleep_s - 0.0001)
        nominal_goal_raw = int(goal_raw)
        if profile.phase[index] == "preparation_zero_hold":
            setup_bias_ticks += 0.05 * (
                zero - feedback_position
            )
            correction = int(
                round(np.clip(setup_bias_ticks, -256, 256))
            )
            goal_raw = zero + correction
        else:
            goal_raw = nominal_goal_raw
        if not minimum <= goal_raw <= maximum:
            raise RuntimeError("gravity-zero goal outside software gate")
        request_ns = time.monotonic_ns()
        bus.write(device_id, "goal_position", goal_raw)
        values = reader.read()
        receive_ns = time.monotonic_ns()
        goal = signed(values["goal_position"], 32)
        position = signed(values["present_position"], 32)
        feedback_position = position
        velocity = signed(values["present_velocity"], 32)
        current = signed(values["present_current"], 16)
        pwm = signed(values["present_pwm"], 16)
        now = time.monotonic()
        following_rad = abs(goal - position) * POSITION_RAD_PER_TICK
        current_a = abs(current) * CURRENT_A_PER_RAW
        pwm_fraction = abs(pwm) * PWM_FRACTION_PER_RAW
        velocity_rad_s = velocity * VELOCITY_RAD_S_PER_RAW
        following_start = (
            now
            if following_rad > float(interlocks["following_error_rad"])
            and following_start is None
            else following_start
            if following_rad > float(interlocks["following_error_rad"])
            else None
        )
        current_start = (
            now
            if current_a > float(interlocks["current_stop_A"])
            and current_start is None
            else current_start
            if current_a > float(interlocks["current_stop_A"])
            else None
        )
        pwm_start = (
            now
            if pwm_fraction > float(interlocks["pwm_stop_fraction"])
            and pwm_start is None
            else pwm_start
            if pwm_fraction > float(interlocks["pwm_stop_fraction"])
            else None
        )
        if following_start is not None and now - following_start >= float(
            interlocks["following_error_duration_s"]
        ):
            raise RuntimeError("gravity-zero following-error interlock")
        if current_start is not None and now - current_start >= float(
            interlocks["current_stop_duration_s"]
        ):
            raise RuntimeError("gravity-zero input-current interlock")
        if pwm_start is not None and now - pwm_start >= float(
            interlocks["pwm_stop_duration_s"]
        ):
            raise RuntimeError("gravity-zero PWM interlock")
        if abs(velocity_rad_s) > float(interlocks["velocity_stop_rad_s"]):
            raise RuntimeError("gravity-zero observed-velocity interlock")
        voltage_v = values["input_voltage"] * 0.1
        entered_command_position_gate = (
            advance_gravity_measured_position_gate(
                position=position,
                gate_entered=entered_command_position_gate,
                passive_minimum=passive_minimum,
                command_minimum=minimum,
                command_maximum=maximum,
                entry_hysteresis_ticks=entry_hysteresis_ticks,
            )
        )
        if not float(interlocks["start_voltage_min_V"]) <= voltage_v <= float(
            interlocks["start_voltage_max_V"]
        ):
            raise RuntimeError("gravity-zero voltage interlock")
        if values["temperature"] >= int(
            interlocks["runtime_temperature_stop_C"]
        ):
            raise RuntimeError("gravity-zero temperature interlock")
        if values["hardware_error_status"] != 0:
            raise RuntimeError("gravity-zero hardware-error interlock")
        events.append(
            {
                "episode_id": episode_id,
                "zeroing_index": index,
                "host_write_request_ns": request_ns,
                "host_rx_end_ns": receive_ns,
                "t_zeroing_s": (receive_ns - start_ns) * 1e-9,
                "goal_position_raw": goal,
                "nominal_zeroing_goal_position_raw": nominal_goal_raw,
                "zeroing_goal_bias_ticks": goal_raw - nominal_goal_raw,
                "present_position_raw": position,
                "position_meas_rad": (position - zero)
                * POSITION_RAD_PER_TICK,
                "present_velocity_raw": velocity,
                "velocity_meas_rad_s": velocity_rad_s,
                "present_current_raw": current,
                "current_meas_A": current * CURRENT_A_PER_RAW,
                "present_pwm_raw": pwm,
                "pwm_meas_fraction": pwm * PWM_FRACTION_PER_RAW,
                "input_voltage_V": voltage_v,
                "temperature_C": values["temperature"],
                "hardware_error_status_raw": values[
                    "hardware_error_status"
                ],
                "source_type": "physical_hardware_zero_acquisition",
                "gravity_measured_position_gate_entry_hysteresis_ticks": (
                    entry_hysteresis_ticks
                ),
                "gravity_measured_position_gate_entry_raw": entry_raw,
                "passive_position_exception_active": not entered_command_position_gate,
            }
        )
    final = signed(bus.read(device_id, "present_position"), 32)
    if abs(final - zero) > tolerance:
        raise RuntimeError(
            f"gravity-loaded zero acquisition ended at raw {final}; "
            f"required {zero} ±{tolerance}"
        )
    return events, final


def run_episode(
    bus: DynamixelBus,
    run_root: Path,
    episode_id: str,
    condition_id: str,
    profile: ExecutedProfile,
    role: str,
    repeat_id: str | None,
    require_zero_start: bool,
) -> dict[str, Any]:
    cfg = config()
    device_id = int(cfg["dynamixel_id"])
    zero = int(cfg["servo_zero_raw"])
    tolerance = int(cfg["servo_zero_tolerance_ticks"])
    minimum = int(cfg["software_goal_min_raw"])
    maximum = int(cfg["software_goal_max_raw"])
    dt_s = 1.0 / float(cfg["command_rate_hz"])
    poll_dt_s = 1.0 / float(cfg["telemetry_rate_hz"])
    episode_root = run_root / "episodes" / episode_id
    episode_root.mkdir(parents=True, exist_ok=False)
    commands: list[dict[str, Any]] = []
    telemetry: list[dict[str, Any]] = []
    zeroing: list[dict[str, Any]] = []
    failures: list[str] = []
    before: dict[str, int] = {}
    after: dict[str, int] = {}
    order: list[str] = []
    completion = "aborted"
    timing: dict[str, Any] = {}
    terminal_torque_disabled = False
    reader: BulkTelemetryReader | None = None
    experiment_start_position_raw: int | None = None
    episode_control_exit_host_monotonic_ns: int | None = None
    torque_disabled_host_monotonic_ns: int | None = None
    gravity_zero_start = bool(
        cfg.get("gravity_loaded_active_zero_start", False)
    )
    start_wall_utc = datetime.now(UTC).isoformat()
    start_monotonic_ns = time.monotonic_ns()
    raw_goals = zero + np.rint(profile.command_rad / POSITION_RAD_PER_TICK).astype(int)
    if int(raw_goals.min()) < minimum or int(raw_goals.max()) > maximum:
        raise RuntimeError(f"{episode_id} contains a goal outside the ±90 degree gate")

    try:
        _, order = apply_condition(bus, condition_id)
        before = snapshot(bus, device_id)
        initial = signed(before["present_position"], 32)
        initial_minimum = (
            int(cfg.get("gravity_passive_transient_min_raw", minimum))
            if gravity_zero_start
            else minimum
        )
        if not initial_minimum <= initial <= maximum:
            raise RuntimeError("initial position is outside the ±90 degree gate")
        if (
            require_zero_start
            and not gravity_zero_start
            and abs(initial - zero) > tolerance
        ):
            raise RuntimeError(
                f"episode must start at tick {zero} ±{tolerance}; observed {initial}"
            )
        voltage_v = before["input_voltage"] * 0.1
        interlocks = cfg["interlocks"]
        if not float(interlocks["start_voltage_min_V"]) <= voltage_v <= float(
            interlocks["start_voltage_max_V"]
        ):
            raise RuntimeError(f"starting voltage gate failed: {voltage_v} V")
        if before["temperature"] > int(interlocks["start_temperature_max_C"]):
            raise RuntimeError("starting temperature gate failed")
        if before["hardware_error_status"] != 0:
            raise RuntimeError("starting hardware-error gate failed")
        if before["torque_enable"] != 0:
            raise RuntimeError("torque-off gate failed")

        following_start: float | None = None
        current_start: float | None = None
        pwm_start: float | None = None
        acquisition_initial = initial
        if require_zero_start and gravity_zero_start:
            handoff_latched = False
            handoff_readback: int | None = None
            for _ in range(10):
                acquisition_initial = signed(
                    bus.read(device_id, "present_position"), 32
                )
                handoff_goal = acquisition_initial
                bus.write(device_id, "goal_position", handoff_goal)
                handoff_readback = signed(
                    bus.read(device_id, "goal_position"), 32
                )
                if handoff_readback == handoff_goal:
                    handoff_latched = True
                    break
            if not handoff_latched:
                raise RuntimeError(
                    "gravity torque-enable handoff goal latch failed: "
                    f"requested={acquisition_initial}, "
                    f"readback={handoff_readback}"
                )
            order.append(
                "relatch_latest_gravity_position_immediately_before_enable"
            )
        bus.write(device_id, "torque_enable", 1)
        if bus.read(device_id, "torque_enable") != 1:
            raise RuntimeError("torque-enable readback failed")
        order.append("enable_only_ID5_after_all_live_gates")
        reader = BulkTelemetryReader(bus, device_id)
        reader.read()
        if require_zero_start and gravity_zero_start:
            zeroing, experiment_start_position_raw = (
                acquire_gravity_loaded_zero(
                    bus, reader, episode_id, acquisition_initial
                )
            )
            order.append(
                "actively_acquire_tick_2048_and_keep_torque_enabled"
            )
        else:
            experiment_start_position_raw = signed(
                bus.read(device_id, "present_position"), 32
            )
        if (
            require_zero_start
            and abs(experiment_start_position_raw - zero) > tolerance
        ):
            raise RuntimeError(
                "experiment recording start is outside zero tolerance"
            )
        start_wall_utc = datetime.now(UTC).isoformat()
        start_monotonic_ns = time.monotonic_ns()
        start = time.monotonic()
        next_command = start
        next_poll = start
        command_index = 0
        poll_index = 0
        while command_index < profile.command_rad.size:
            now = time.monotonic()
            if now >= next_command:
                requested_rad = float(profile.command_rad[command_index])
                goal_raw = int(raw_goals[command_index])
                if not minimum <= goal_raw <= maximum:
                    raise RuntimeError("runtime software goal gate failed")
                request_ns = time.monotonic_ns()
                bus.write(device_id, "goal_position", goal_raw)
                commands.append(
                    {
                        "episode_id": episode_id,
                        "command_index": command_index,
                        "sequence_id": command_index,
                        "host_write_request_ns": request_ns,
                        "t_command_s": (request_ns - start_monotonic_ns) * 1e-9,
                        "profile_phase": str(profile.phase[command_index]),
                        "active_profile_sample": str(profile.phase[command_index]) == "active",
                        "position_cmd_rad": requested_rad,
                        "goal_position_raw_requested": goal_raw,
                        "position_applied_rad": (goal_raw - zero) * POSITION_RAD_PER_TICK,
                        "source_type": "physical_hardware_command",
                    }
                )
                command_index += 1
                next_command = start + command_index * dt_s
            if now >= next_poll:
                request_ns = time.monotonic_ns()
                assert reader is not None
                values = reader.read()
                receive_ns = time.monotonic_ns()
                goal = signed(values["goal_position"], 32)
                position = signed(values["present_position"], 32)
                velocity = signed(values["present_velocity"], 32)
                current = signed(values["present_current"], 16)
                pwm = signed(values["present_pwm"], 16)
                following_rad = abs(goal - position) * POSITION_RAD_PER_TICK
                current_a = abs(current) * CURRENT_A_PER_RAW
                pwm_fraction = abs(pwm) * PWM_FRACTION_PER_RAW
                velocity_rad_s = velocity * VELOCITY_RAD_S_PER_RAW
                following_start = (
                    now
                    if following_rad > float(interlocks["following_error_rad"])
                    and following_start is None
                    else following_start
                    if following_rad > float(interlocks["following_error_rad"])
                    else None
                )
                current_start = (
                    now
                    if current_a > float(interlocks["current_stop_A"])
                    and current_start is None
                    else current_start
                    if current_a > float(interlocks["current_stop_A"])
                    else None
                )
                pwm_start = (
                    now
                    if pwm_fraction > float(interlocks["pwm_stop_fraction"])
                    and pwm_start is None
                    else pwm_start
                    if pwm_fraction > float(interlocks["pwm_stop_fraction"])
                    else None
                )
                if following_start is not None and now - following_start >= float(
                    interlocks["following_error_duration_s"]
                ):
                    raise RuntimeError("following-error interlock")
                if current_start is not None and now - current_start >= float(
                    interlocks["current_stop_duration_s"]
                ):
                    raise RuntimeError("input-supply-current interlock")
                if pwm_start is not None and now - pwm_start >= float(
                    interlocks["pwm_stop_duration_s"]
                ):
                    raise RuntimeError("PWM interlock")
                if abs(velocity_rad_s) > float(interlocks["velocity_stop_rad_s"]):
                    raise RuntimeError("observed-velocity interlock")
                if not minimum <= position <= maximum:
                    raise RuntimeError("measured-position software gate")
                voltage_runtime_v = values["input_voltage"] * 0.1
                if not float(interlocks["start_voltage_min_V"]) <= voltage_runtime_v <= float(
                    interlocks["start_voltage_max_V"]
                ):
                    raise RuntimeError("runtime voltage interlock")
                if values["temperature"] >= int(
                    interlocks["runtime_temperature_stop_C"]
                ):
                    raise RuntimeError("runtime temperature interlock")
                if values["hardware_error_status"] != 0:
                    raise RuntimeError("hardware-error-status interlock")
                if values["operating_mode"] != int(
                    cfg["shared_registers"]["operating_mode"]
                ):
                    raise RuntimeError("operating-mode changed during episode")
                telemetry.append(
                    {
                        "episode_id": episode_id,
                        "poll_index": poll_index,
                        "host_read_request_ns": request_ns,
                        "host_rx_end_ns": receive_ns,
                        "t_state_s": (receive_ns - start_monotonic_ns) * 1e-9,
                        "device_realtime_tick_ms_raw": values["realtime_tick"],
                        "torque_enable_raw": values["torque_enable"],
                        "operating_mode_raw": values["operating_mode"],
                        "goal_position_raw": goal,
                        "present_position_raw": position,
                        "position_meas_rad": (position - zero) * POSITION_RAD_PER_TICK,
                        "present_velocity_raw": velocity,
                        "velocity_meas_rad_s": velocity_rad_s,
                        "present_current_raw": current,
                        "current_meas_A": current * CURRENT_A_PER_RAW,
                        "present_pwm_raw": pwm,
                        "pwm_meas_fraction": pwm * PWM_FRACTION_PER_RAW,
                        "input_voltage_raw": values["input_voltage"],
                        "input_voltage_V": voltage_runtime_v,
                        "temperature_C": values["temperature"],
                        "hardware_error_status_raw": values["hardware_error_status"],
                        "moving_raw": values["moving"],
                        "moving_status_raw": values["moving_status"],
                        "position_trajectory_raw": signed(
                            values["position_trajectory"], 32
                        ),
                        "velocity_trajectory_raw": signed(
                            values["velocity_trajectory"], 32
                        ),
                        "source_type": "physical_hardware_telemetry",
                    }
                )
                poll_index += 1
                next_poll = start + poll_index * poll_dt_s
            sleep_s = min(next_command, next_poll) - time.monotonic()
            if sleep_s > 0.00025:
                time.sleep(sleep_s - 0.0001)

        timing = telemetry_timing_quality(
            np.asarray([row["host_read_request_ns"] for row in telemetry], dtype=np.int64)
        )
        if not timing["passed"]:
            raise RuntimeError(f"telemetry timing-quality gate failed: {timing}")
        completion = "complete"
    except (KeyboardInterrupt, RuntimeError, OSError) as exc:
        failures.append(f"{type(exc).__name__}: {exc}")
    finally:
        episode_control_exit_host_monotonic_ns = time.monotonic_ns()
        if reader is not None:
            reader.close()
        try:
            bus.torque_disable(device_id)
            torque_disabled_host_monotonic_ns = time.monotonic_ns()
            terminal_torque_disabled = True
            after = snapshot(bus, device_id)
        except RuntimeError as exc:
            failures.append(f"cleanup: {exc}")
            terminal_torque_disabled = False
    if not terminal_torque_disabled:
        completion = "aborted"

    pd.DataFrame(commands).to_parquet(
        episode_root / "command_events.parquet", index=False, compression="zstd"
    )
    pd.DataFrame(telemetry).to_parquet(
        episode_root / "telemetry_events.parquet", index=False, compression="zstd"
    )
    if zeroing:
        pd.DataFrame(zeroing).to_parquet(
            episode_root / "zeroing_events.parquet",
            index=False,
            compression="zstd",
        )
    write_json(episode_root / "control_table_before.json", before)
    write_json(episode_root / "control_table_after.json", after)
    critical_names = tuple(condition_registers(condition_id))
    critical_match = bool(before and after) and all(
        before.get(name) == after.get(name) for name in critical_names
    )
    manifest = {
        "schema_version": 1,
        "episode_id": episode_id,
        "role": role,
        "repeat_id": repeat_id,
        "mechanical_configuration": str(cfg["mechanical_configuration"]),
        "fixture": cfg.get("fixture"),
        "dynamixel_id": device_id,
        "controller_id": condition_id,
        "hardware_position_p_gain_raw": int(
            cfg["controllers"][condition_id]["position_p_gain_raw"]
        ),
        "hardware_position_i_gain_raw": int(
            cfg["controllers"][condition_id]["position_i_gain_raw"]
        ),
        "hardware_position_d_gain_raw": int(
            cfg["controllers"][condition_id]["position_d_gain_raw"]
        ),
        "mujoco_kp": None,
        "mujoco_kv": None,
        "profile_id": profile.profile_id,
        "profile_statistics": profile_statistics(profile, dt_s),
        "start_required_at_zero": require_zero_start,
        "experiment_start_goal_position_raw": zero
        if require_zero_start
        else None,
        "experiment_start_position_raw_signed": experiment_start_position_raw,
        "experiment_start_position_error_ticks": (
            abs(experiment_start_position_raw - zero)
            if experiment_start_position_raw is not None
            else None
        ),
        "zero_start_tolerance_ticks": tolerance,
        "gravity_loaded_active_zero_start": gravity_zero_start,
        "gravity_measured_position_gate_entry_hysteresis_ticks": (
            int(
                cfg.get(
                    "gravity_measured_position_gate_entry_hysteresis_ticks",
                    0,
                )
            )
            if gravity_zero_start
            else None
        ),
        "gravity_measured_position_gate_entry_raw": (
            minimum
            + int(
                cfg.get(
                    "gravity_measured_position_gate_entry_hysteresis_ticks",
                    0,
                )
            )
            if gravity_zero_start
            else None
        ),
        "zeroing_event_count": len(zeroing),
        "zeroing_data_file": "zeroing_events.parquet" if zeroing else None,
        "initial_position_raw_signed": signed(before.get("present_position", 0), 32)
        if before
        else None,
        "start_utc": start_wall_utc,
        "start_host_monotonic_ns": start_monotonic_ns,
        "episode_control_exit_host_monotonic_ns": (
            episode_control_exit_host_monotonic_ns
        ),
        "torque_disabled_host_monotonic_ns": (
            torque_disabled_host_monotonic_ns
        ),
        "end_utc": datetime.now(UTC).isoformat(),
        "completion_status": completion,
        "failures": failures,
        "terminal_torque_disabled": terminal_torque_disabled,
        "critical_registers_match_before_after": critical_match,
        "controller_write_order": order,
        "command_count": len(commands),
        "telemetry_count": len(telemetry),
        "telemetry_timing_quality": timing,
        "measurement_boundary": cfg["measurement_boundary"],
        "torque_channel_created": False,
        "source_type": "new_V5_physical_hardware_measurement",
    }
    if completion == "complete" and not critical_match:
        manifest["completion_status"] = "aborted"
        manifest["failures"].append("critical register drift before/after episode")
    write_json(episode_root / "episode.json", manifest)
    return manifest


def recenter_profile(current_raw: int, index: int) -> ExecutedProfile:
    cfg = config()
    zero = int(cfg["servo_zero_raw"])
    dt_s = 1.0 / float(cfg["command_rate_hz"])
    start_rad = (current_raw - zero) * POSITION_RAD_PER_TICK
    duration_s = max(2.0, abs(start_rad) * 4.0)
    count = int(round(duration_s / dt_s))
    u = np.linspace(0.0, 1.0, count, endpoint=False)
    blend = 10.0 * u**3 - 15.0 * u**4 + 6.0 * u**5
    move = start_rad + (0.0 - start_rad) * blend
    settle_duration_s = (
        2.0
        if cfg.get("gravity_loaded_active_zero_start", False)
        else 1.0
    )
    settle = np.zeros(
        int(round(settle_duration_s / dt_s)), dtype=float
    )
    return ExecutedProfile(
        profile_id=f"RECENTER_{index:03d}",
        command_rad=np.concatenate([move, settle]),
        phase=np.concatenate(
            [
                np.full(move.size, "preparation_move", dtype=object),
                np.full(settle.size, "preparation_zero_hold", dtype=object),
            ]
        ),
        active_start_index=0,
        active_sample_count=int(move.size),
    )


def ensure_zero(
    bus: DynamixelBus,
    run_root: Path,
    recenter_index: int,
    manifests: list[dict[str, Any]],
) -> int:
    cfg = config()
    device_id = int(cfg["dynamixel_id"])
    zero = int(cfg["servo_zero_raw"])
    tolerance = int(cfg["servo_zero_tolerance_ticks"])
    current = signed(bus.read(device_id, "present_position"), 32)
    if abs(current - zero) <= tolerance:
        return recenter_index
    profile = recenter_profile(current, recenter_index)
    episode_id = (
        f"{config()['mechanical_configuration']}__H1__{profile.profile_id}"
    )
    print(
        f"PREPARATION {episode_id}: recenter raw {current} -> {zero}",
        flush=True,
    )
    manifest = run_episode(
        bus,
        run_root,
        episode_id,
        "H1",
        profile,
        "preparation",
        None,
        False,
    )
    manifests.append(manifest)
    if manifest["completion_status"] != "complete":
        raise RuntimeError(f"recenter failed: {manifest['failures']}")
    final = signed(bus.read(device_id, "present_position"), 32)
    if abs(final - zero) > tolerance:
        raise RuntimeError(f"recenter ended at raw {final}, outside zero tolerance")
    return recenter_index + 1


def summarize_run(run_root: Path, manifests: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for manifest in manifests:
        episode_root = run_root / "episodes" / manifest["episode_id"]
        command = pd.read_parquet(episode_root / "command_events.parquet")
        telemetry = pd.read_parquet(episode_root / "telemetry_events.parquet")
        media = manifest.get("media", {})
        row: dict[str, Any] = {
            "episode_id": manifest["episode_id"],
            "role": manifest["role"],
            "repeat_id": manifest["repeat_id"],
            "controller_id": manifest["controller_id"],
            "profile_id": manifest["profile_id"],
            "completion_status": manifest["completion_status"],
            "hardware_position_p_gain_raw": manifest["hardware_position_p_gain_raw"],
            "hardware_position_i_gain_raw": manifest["hardware_position_i_gain_raw"],
            "hardware_position_d_gain_raw": manifest["hardware_position_d_gain_raw"],
            "command_samples": int(len(command)),
            "telemetry_samples": int(len(telemetry)),
            "terminal_torque_disabled": manifest["terminal_torque_disabled"],
            "critical_registers_match": manifest[
                "critical_registers_match_before_after"
            ],
        }
        if media:
            row.update(
                {
                    "media_capture_status": media.get("status"),
                    "media_directory": media.get("directory"),
                    "media_video": media.get("video"),
                    "media_key_frame_count": media.get("key_frame_count"),
                    "media_source_frame_count": media.get(
                        "source_frame_count"
                    ),
                }
            )
        if len(command) and len(telemetry):
            command_time = command["host_write_request_ns"].to_numpy(dtype=np.int64)
            telemetry_time = telemetry["host_rx_end_ns"].to_numpy(dtype=np.int64)
            measured = np.interp(
                command_time.astype(float),
                telemetry_time.astype(float),
                telemetry["position_meas_rad"].to_numpy(dtype=float),
            )
            active = command["active_profile_sample"].to_numpy(dtype=bool)
            error = (
                measured[active]
                - command.loc[active, "position_applied_rad"].to_numpy(dtype=float)
                if np.any(active)
                else np.asarray([], dtype=float)
            )
            row.update(
                {
                    "tracking_rmse_rad_active": float(np.sqrt(np.mean(error**2)))
                    if error.size
                    else np.nan,
                    "tracking_mae_rad_active": float(np.mean(np.abs(error)))
                    if error.size
                    else np.nan,
                    "tracking_peak_abs_rad_active": float(np.max(np.abs(error)))
                    if error.size
                    else np.nan,
                    "maximum_abs_current_A": float(
                        telemetry["current_meas_A"].abs().max()
                    ),
                    "maximum_abs_pwm_fraction": float(
                        telemetry["pwm_meas_fraction"].abs().max()
                    ),
                    "maximum_abs_velocity_rad_s": float(
                        telemetry["velocity_meas_rad_s"].abs().max()
                    ),
                    "minimum_voltage_V": float(telemetry["input_voltage_V"].min()),
                    "maximum_temperature_C": float(telemetry["temperature_C"].max()),
                    "hardware_error_count": int(
                        (telemetry["hardware_error_status_raw"] != 0).sum()
                    ),
                    "achieved_telemetry_rate_hz": manifest[
                        "telemetry_timing_quality"
                    ].get("achieved_rate_hz"),
                }
            )
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary.to_csv(run_root / "episode-summary.csv", index=False)
    return summary


def write_method_results(run_root: Path, summary: pd.DataFrame) -> None:
    cfg = config()
    calibration = summary[summary["role"] == "calibration"].copy()
    lines = [
        "# V5 M0 hardware collection: method and results",
        "",
        f"Run: `{run_root.name}`",
        "",
        "## Scope and method",
        "",
        "This release contains new physical M0 measurements only. It targets XC330-M288-T ID5, uses raw tick 2048 as zero, enforces the software goal gate 1024–3072 (±90°), and stops before any mechanical fixture change.",
        "",
        "The calibration matrix is H1–H5 × P01–P03 × three repeats. P01–P03 retain the active samples declared by V5 Design2Data. P02 receives labeled zero-safe preparation/recovery samples outside its active segment. Low-amplitude pilots for H1, H4, and H5 precede calibration.",
        "",
        "H conditions are native DYNAMIXEL P/I/D registers, not MuJoCo gains:",
        "",
        "| H | P | I | D | Role |",
        "|---|---:|---:|---:|---|",
    ]
    for name, values in cfg["controllers"].items():
        lines.append(
            f"| {name} | {values['position_p_gain_raw']} | "
            f"{values['position_i_gain_raw']} | {values['position_d_gain_raw']} | "
            f"{values['role']} |"
        )
    lines.extend(
        [
            "",
            "## Collection result",
            "",
            f"- Complete calibration episodes: {int((calibration['completion_status'] == 'complete').sum())} / 45.",
            f"- Complete pilot episodes: {int(((summary['role'] == 'pilot') & (summary['completion_status'] == 'complete')).sum())} / 3.",
            f"- Maximum observed input-supply current: {float(summary['maximum_abs_current_A'].max()):.6f} A.",
            f"- Maximum observed PWM fraction: {float(summary['maximum_abs_pwm_fraction'].max()):.6f}.",
            f"- Maximum temperature: {float(summary['maximum_temperature_C'].max()):.1f} °C.",
            f"- Minimum supply voltage: {float(summary['minimum_voltage_V'].min()):.1f} V.",
            "",
            "### Calibration tracking by hardware condition",
            "",
            "| H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for condition, group in calibration.groupby("controller_id", sort=True):
        lines.append(
            f"| {condition} | {len(group)} | "
            f"{group['tracking_rmse_rad_active'].mean():.9f} | "
            f"{group['tracking_rmse_rad_active'].std(ddof=1):.9f} | "
            f"{group['tracking_peak_abs_rad_active'].max():.9f} |"
        )
    lines.extend(
        [
            "",
            "## Torque/current interpretation",
            "",
            "Present Current is preserved as raw counts and amperes, but for XC330 it is input-supply-current telemetry. No output-torque channel was manufactured. Output torque requires an independent lever/load-cell or inline-transducer calibration; see `TORQUE_MEASUREMENT.md` in the parent hardware-experiment directory.",
            "",
            "## What happens next",
            "",
            "No passive MuJoCo joint parameters or equivalent controller gains are identified during collection. This M0 release is the first mechanical block. The operator changes the physical configuration only after this run is reported complete.",
        ]
    )
    (run_root / "M0_METHOD_AND_RESULTS.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_inventory(run_root: Path) -> str:
    inventory_path = run_root / "inventory.sha256"
    files = sorted(
        path
        for path in run_root.rglob("*")
        if path.is_file() and path != inventory_path
    )
    inventory_path.write_text(
        "\n".join(
            f"{sha256_file(path)}  {path.relative_to(run_root)}" for path in files
        )
        + "\n",
        encoding="utf-8",
    )
    return sha256_file(inventory_path)


def verify_run(run_root: Path) -> dict[str, Any]:
    cfg = config()
    run_manifest = read_json(run_root / "run.json")
    inventory_path = run_root / "inventory.sha256"
    inventory_lines = [
        line.split("  ", 1)
        for line in inventory_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    hash_failures = [
        relative
        for expected, relative in inventory_lines
        if not (run_root / relative).is_file()
        or sha256_file(run_root / relative) != expected
    ]
    manifests = [
        read_json(path)
        for path in sorted((run_root / "episodes").glob("*/episode.json"))
    ]
    calibration = [item for item in manifests if item["role"] == "calibration"]
    pilots = [item for item in manifests if item["role"] == "pilot"]
    data_checks: list[bool] = []
    torque_named_columns: list[str] = []
    for manifest in manifests:
        episode_root = run_root / "episodes" / manifest["episode_id"]
        commands = pd.read_parquet(episode_root / "command_events.parquet")
        telemetry = pd.read_parquet(episode_root / "telemetry_events.parquet")
        torque_named_columns.extend(
            column
            for column in [*commands.columns, *telemetry.columns]
            if "torque" in column.lower()
            and "torque_enable" not in column.lower()
        )
        first_goal = int(commands.iloc[0]["goal_position_raw_requested"])
        data_checks.append(
            bool(
                len(commands)
                and len(telemetry)
                and commands["goal_position_raw_requested"].between(
                    int(cfg["software_goal_min_raw"]),
                    int(cfg["software_goal_max_raw"]),
                ).all()
                and telemetry["present_position_raw"].between(
                    int(cfg["software_goal_min_raw"]),
                    int(cfg["software_goal_max_raw"]),
                ).all()
                and (
                    manifest["role"] == "preparation"
                    or first_goal == int(cfg["servo_zero_raw"])
                )
                and telemetry["hardware_error_status_raw"].eq(0).all()
                and np.isfinite(
                    telemetry[
                        [
                            "position_meas_rad",
                            "velocity_meas_rad_s",
                            "current_meas_A",
                            "pwm_meas_fraction",
                        ]
                    ].to_numpy(dtype=float)
                ).all()
            )
        )
    expected_calibration_ids = {
        f"M0__{condition}__{profile_id}__{repeat_id}"
        for repeat_id in ("R01", "R02", "R03")
        for profile_id in cfg["profiles"]
        for condition in cfg["controllers"]
    }
    actual_calibration_ids = {item["episode_id"] for item in calibration}
    checks = {
        "run_terminal_status_complete": run_manifest["terminal_status"] == "complete",
        "exact_45_calibration_episodes": len(calibration) == 45,
        "calibration_matrix_exact": actual_calibration_ids == expected_calibration_ids,
        "exact_3_pilot_episodes": len(pilots) == 3,
        "all_episode_manifests_complete": all(
            item["completion_status"] == "complete" for item in manifests
        ),
        "all_episodes_terminal_torque_disabled": all(
            item["terminal_torque_disabled"] for item in manifests
        ),
        "all_critical_registers_stable": all(
            item["critical_registers_match_before_after"] for item in manifests
        ),
        "all_episode_data_checks": all(data_checks),
        "no_manufactured_torque_column": not torque_named_columns,
        "inventory_nonempty": bool(inventory_lines),
        "inventory_hashes_match": not hash_failures,
        "summary_exists": (run_root / "episode-summary.csv").is_file(),
        "method_results_exists": (run_root / "M0_METHOD_AND_RESULTS.md").is_file(),
    }
    return {
        "run_root": str(run_root),
        "checks": checks,
        "episode_manifest_count": len(manifests),
        "calibration_episode_count": len(calibration),
        "pilot_episode_count": len(pilots),
        "inventory_entry_count": len(inventory_lines),
        "inventory_hash_failures": hash_failures,
        "torque_named_columns": sorted(set(torque_named_columns)),
        "passed": all(checks.values()),
    }


def run() -> dict[str, Any]:
    offline = validate()
    if not offline["passed"]:
        return {
            "status": "blocked_by_offline_validation",
            "passed": False,
            "motion_executed": False,
        }
    available = availability()
    if not available["available"]:
        return {
            "status": "blocked_device_absent_or_owned",
            "availability": available,
            "passed": False,
            "motion_executed": False,
        }
    cfg = config()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = RAW_ROOT / f"v5-m0-{timestamp}-{uuid.uuid4().hex[:8]}"
    run_root.mkdir(parents=True, exist_ok=False)
    manifests: list[dict[str, Any]] = []
    campaign_error: str | None = None
    terminal_torque_disabled = False
    with hardware_lock():
        if not availability()["available"]:
            raise RuntimeError("serial device became owned before campaign open")
        bus = DynamixelBus(str(cfg["serial_port"]), int(cfg["baud_rate_bps"]))
        try:
            discovered = bus.discover()
            disable_discovered(bus, discovered)
            if set(discovered) != {int(cfg["dynamixel_id"])} or discovered[
                int(cfg["dynamixel_id"])
            ]["model_number"] != int(cfg["expected_model_number"]):
                raise RuntimeError(f"exact ID5/model identity gate failed: {discovered}")
            canonicalization = canonicalize_torque_off_position_counter(bus)
            write_json(run_root / "position-counter-canonicalization.json", canonicalization)
            live = read_only_status_on_open_bus(bus)
            write_json(run_root / "live-preflight.json", live)
            if not live["passed"]:
                raise RuntimeError(f"live preflight failed: {live['checks']}")
            recenter_index = 1
            recenter_index = ensure_zero(bus, run_root, recenter_index, manifests)

            pilot = pilot_profile(cfg)
            for condition_id in cfg["pilot"]["controllers"]:
                recenter_index = ensure_zero(bus, run_root, recenter_index, manifests)
                episode_id = f"M0__{condition_id}__PILOT_LOW_AMPLITUDE"
                print(f"PILOT {episode_id}", flush=True)
                manifest = run_episode(
                    bus,
                    run_root,
                    episode_id,
                    condition_id,
                    pilot,
                    "pilot",
                    None,
                    True,
                )
                manifests.append(manifest)
                print(
                    f"RESULT {episode_id}: {manifest['completion_status']}", flush=True
                )
                if manifest["completion_status"] != "complete":
                    raise RuntimeError(f"pilot failed: {manifest['failures']}")

            generated = executed_profiles(cfg)
            total = len(cfg["profiles"]) * len(cfg["controllers"]) * int(
                cfg["required_complete_repetitions"]
            )
            completed = 0
            for repeat_id, condition_order in cfg[
                "condition_order_by_repeat"
            ].items():
                for profile_id, profile in generated.items():
                    for condition_id in condition_order:
                        recenter_index = ensure_zero(
                            bus, run_root, recenter_index, manifests
                        )
                        episode_id = (
                            f"M0__{condition_id}__{profile_id}__{repeat_id}"
                        )
                        print(
                            f"CALIBRATION {completed + 1:02d}/{total}: {episode_id}",
                            flush=True,
                        )
                        manifest = run_episode(
                            bus,
                            run_root,
                            episode_id,
                            condition_id,
                            profile,
                            "calibration",
                            repeat_id,
                            True,
                        )
                        manifests.append(manifest)
                        print(
                            f"RESULT {episode_id}: {manifest['completion_status']}",
                            flush=True,
                        )
                        if manifest["completion_status"] != "complete":
                            raise RuntimeError(
                                f"calibration episode failed: {manifest['failures']}"
                            )
                        completed += 1
        except (KeyboardInterrupt, RuntimeError, OSError) as exc:
            campaign_error = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                bus.torque_disable(int(cfg["dynamixel_id"]))
                terminal_torque_disabled = True
            except RuntimeError as exc:
                campaign_error = (
                    f"{campaign_error}; terminal cleanup: {exc}"
                    if campaign_error
                    else f"terminal cleanup: {exc}"
                )
            bus.close()

    calibration = [item for item in manifests if item["role"] == "calibration"]
    pilots = [item for item in manifests if item["role"] == "pilot"]
    terminal_status = (
        "complete"
        if campaign_error is None
        and len(calibration) == 45
        and len(pilots) == 3
        and all(item["completion_status"] == "complete" for item in manifests)
        and terminal_torque_disabled
        else "incomplete"
    )
    run_manifest = {
        "schema_version": 1,
        "experiment_id": cfg["experiment_id"],
        "run_id": run_root.name,
        "mechanical_configuration": "M0",
        "dynamixel_id": int(cfg["dynamixel_id"]),
        "source_type": "new_V5_physical_hardware_measurement",
        "start_utc": timestamp,
        "end_utc": datetime.now(UTC).isoformat(),
        "host_platform": platform.platform(),
        "episode_ids": [item["episode_id"] for item in manifests],
        "calibration_episode_count": len(calibration),
        "pilot_episode_count": len(pilots),
        "preparation_episode_count": sum(
            item["role"] == "preparation" for item in manifests
        ),
        "campaign_error": campaign_error,
        "terminal_torque_disabled": terminal_torque_disabled,
        "terminal_status": terminal_status,
        "stopped_after_M0": True,
    }
    write_json(run_root / "run.json", run_manifest)
    summary = summarize_run(run_root, manifests)
    write_method_results(run_root, summary)
    (run_root / "COMMAND_LOG.md").write_text(
        "# Command log\n\n"
        f"- `{datetime.now(UTC).isoformat()}`: `collect_m0.py --run`\n"
        f"- Result: `{terminal_status}`.\n"
        f"- Campaign error: `{campaign_error}`.\n"
        f"- Calibration episodes complete: `{len(calibration)}/45`.\n"
        f"- Pilot episodes complete: `{len(pilots)}/3`.\n"
        f"- Terminal torque disabled: `{terminal_torque_disabled}`.\n",
        encoding="utf-8",
    )
    inventory_digest = write_inventory(run_root)
    verification = verify_run(run_root)
    write_json(REPORT_ROOT / "last_verification.json", verification)
    result = {
        "run_root": str(run_root),
        "terminal_status": terminal_status,
        "calibration_episode_count": len(calibration),
        "pilot_episode_count": len(pilots),
        "preparation_episode_count": sum(
            item["role"] == "preparation" for item in manifests
        ),
        "campaign_error": campaign_error,
        "terminal_torque_disabled": terminal_torque_disabled,
        "inventory_sha256": inventory_digest,
        "verification": verification,
        "motion_executed": bool(manifests),
        "passed": terminal_status == "complete" and verification["passed"],
    }
    write_json(REPORT_ROOT / "last_run.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--validate", action="store_true")
    actions.add_argument("--availability", action="store_true")
    actions.add_argument("--status", action="store_true")
    actions.add_argument("--run", action="store_true")
    actions.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.validate:
        result = validate()
    elif args.availability:
        result = availability()
        result["passed"] = result["available"]
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
