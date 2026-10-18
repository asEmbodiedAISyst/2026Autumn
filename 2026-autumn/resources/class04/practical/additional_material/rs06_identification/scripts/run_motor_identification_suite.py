#!/usr/bin/env python3
"""Safely replay an offline RS06 identification suite and log feedback.

The runner imports the already validated MagicLimb control-box transport from
motor_trajectory_identification.py. Hardware access is disabled unless the
operator supplies --execute and explicit mechanical/feedback safety limits.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

try:
    import sharklog
except ImportError:  # Keep the hardware runner usable with only pyserial installed.
    import logging

    class _SharklogCompatibility:
        @staticmethod
        def getLogger(name: str) -> logging.Logger:
            return logging.getLogger(name)

        @staticmethod
        def init(name: str, debug: bool = False) -> None:
            logging.basicConfig(
                level=logging.DEBUG if debug else logging.INFO,
                format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            )

    sharklog = _SharklogCompatibility()

from motor_identification_trajectories import (
    Trajectory,
    load_suite,
    minimum_jerk_transition,
    trajectory_operating_center_offset,
    trajectory_statistics,
)
from motor_trajectory_identification import (
    CAN_ID_TO_SLOT,
    CAN_ROUTE,
    MOTOR_MODEL,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    RS06_LIMITS,
    SLOT_TO_CAN_ID,
    ControlBox,
    acquire_required_feedback,
    wait_for_command_echo,
    wait_for_required_motors_online,
)


LOGGER_NAME = "rs06.trajectory_runner"
LOGGER = sharklog.getLogger(LOGGER_NAME)

RAW_CSV_FIELDS: Tuple[str, ...] = (
    "session_sample_index",
    "trajectory_id",
    "phase",
    "trajectory_sample_index",
    "t_nominal_s",
    "t_send_before_s",
    "t_send_after_s",
    "t_receive_s",
    "host_time_utc",
    "loop_dt_s",
    "schedule_lateness_s",
    "feedback_gap_s",
    "can_id",
    "controller_slot",
    "kp",
    "kd",
    "q_center_rad",
    "q_offset_command_rad",
    "q_command_requested_rad",
    "q_command_encoded_rad",
    "q_command_saturated",
    "target_feedback_rad",
    "target_matches_current_command",
    "echo_delay_steps",
    "q_feedback_rad",
    "qdot_feedback_rad_s",
    "torque_feedback_nm",
    "tracking_error_target_rad",
    "tracking_error_command_rad",
    "raw_q_u16",
    "raw_qdot_u16",
    "raw_torque_u16",
    "raw_target_u16",
    "raw_record_hex",
)

COMPACT_CSV_FIELDS: Tuple[str, ...] = (
    "time",
    "q_target",
    "q",
    "vel",
    "torque",
)


class SafetyAbort(RuntimeError):
    """Raised when a configured runtime safety condition is violated."""


@dataclass
class RunnerState:
    """Mutable state shared by the phase replay helpers."""

    controller: ControlBox
    motor_id: int
    slot: int
    kp: float
    kd: float
    center_rad: float
    sample_rate_hz: float
    session_start_monotonic: float
    raw_writer: csv.DictWriter
    args: argparse.Namespace
    latest_q_rad: float
    last_command_rad: float
    last_send_before: Optional[float] = None
    last_receive: Optional[float] = None
    session_sample_index: int = 0
    command_sequence_index: int = 0
    command_history: Deque[Tuple[int, int]] = field(
        default_factory=lambda: deque(maxlen=32)
    )
    unrecognized_echo_count: int = 0
    command_saturation_count: int = 0
    echo_delay_histogram: Dict[int, int] = field(default_factory=dict)
    max_observed_abs_velocity: float = 0.0
    max_observed_abs_torque: float = 0.0
    max_observed_abs_tracking_error: float = 0.0


def _default_output_dir() -> Path:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("data/motor_identification/runs") / f"run_{timestamp}"


def build_parser() -> argparse.ArgumentParser:
    default_port = "COM7" if os.name == "nt" else "/dev/ttyACM0"
    parser = argparse.ArgumentParser(
        description=(
            "Replay a hash-verified offline RS06 trajectory suite. The default "
            "mode is a dry run and never opens the serial port."
        )
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--trajectory-ids",
        nargs="+",
        help="optional subset such as R01 R03 R05; replay always follows manifest order",
    )
    parser.add_argument("--motor-id", type=int, required=True)
    parser.add_argument("--port", default=default_port)
    parser.add_argument("--baudrate", type=int, default=1_000_000)
    parser.add_argument("--serial-timeout", type=float, default=0.02)
    parser.add_argument("--frame-timeout", type=float, default=0.5)
    parser.add_argument("--max-bad-frames", type=int, default=3)
    parser.add_argument("--online-timeout", type=float, default=10.0)
    parser.add_argument("--allow-shared-port", action="store_true")
    parser.add_argument("--kp", type=float)
    parser.add_argument("--kd", type=float)
    parser.add_argument("--config-delay", type=float, default=1.0)
    parser.add_argument("--command-echo-timeout", type=float, default=3.0)

    parser.add_argument(
        "--center-position",
        type=float,
        help=(
            "required calibrated absolute base center for --execute; use 0 when "
            "the manually calibrated horizontal rod position is zero"
        ),
    )
    parser.add_argument(
        "--position-min",
        type=float,
        help="required absolute mechanical lower position limit for --execute",
    )
    parser.add_argument(
        "--position-max",
        type=float,
        help="required absolute mechanical upper position limit for --execute",
    )
    parser.add_argument(
        "--max-position-deviation",
        type=float,
        default=0.40,
        help="maximum allowed deviation from each trajectory's operating center in rad",
    )
    parser.add_argument(
        "--max-initial-center-distance",
        type=float,
        default=0.40,
        help=(
            "maximum allowed startup-to-base-center move in rad; this does not "
            "increase the trajectory deviation limit"
        ),
    )
    parser.add_argument(
        "--max-operating-center-offset",
        type=float,
        default=0.0,
        help=(
            "maximum allowed per-trajectory operating-center offset from the "
            "base center; default 0 rejects embedded nonzero-center trajectories"
        ),
    )
    parser.add_argument(
        "--max-abs-velocity",
        type=float,
        help="required feedback velocity abort threshold in rad/s for --execute",
    )
    parser.add_argument(
        "--max-abs-torque",
        type=float,
        help="required feedback torque abort threshold in Nm for --execute",
    )
    parser.add_argument(
        "--max-tracking-error",
        type=float,
        default=0.25,
        help="abort threshold for abs(target_feedback - q_feedback) in rad",
    )
    parser.add_argument(
        "--max-feedback-gap",
        type=float,
        default=0.10,
        help="abort when consecutive complete feedback frames are farther apart than this",
    )
    parser.add_argument(
        "--max-schedule-lateness",
        type=float,
        default=0.10,
        help="abort when a phase falls this far behind its nominal 50 Hz schedule",
    )
    parser.add_argument(
        "--max-echo-history-steps",
        type=int,
        default=8,
        help="target feedback must match one of this many recent commands",
    )
    parser.add_argument(
        "--max-unrecognized-echoes",
        type=int,
        default=3,
        help="consecutive unrecognized target echoes allowed before aborting",
    )
    parser.add_argument("--transition-duration", type=float, default=2.0)
    parser.add_argument("--settle-duration", type=float, default=2.0)
    parser.add_argument("--return-settle-duration", type=float, default=1.0)

    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if args.motor_id not in CAN_ID_TO_SLOT:
        raise ValueError("--motor-id must be a physical RS06 CAN ID in 1..16")
    positive = {
        "--baudrate": args.baudrate,
        "--serial-timeout": args.serial_timeout,
        "--frame-timeout": args.frame_timeout,
        "--max-bad-frames": args.max_bad_frames,
        "--online-timeout": args.online_timeout,
        "--command-echo-timeout": args.command_echo_timeout,
        "--max-position-deviation": args.max_position_deviation,
        "--max-initial-center-distance": args.max_initial_center_distance,
        "--max-tracking-error": args.max_tracking_error,
        "--max-feedback-gap": args.max_feedback_gap,
        "--max-schedule-lateness": args.max_schedule_lateness,
        "--max-echo-history-steps": args.max_echo_history_steps,
        "--max-unrecognized-echoes": args.max_unrecognized_echoes,
        "--transition-duration": args.transition_duration,
    }
    for name, value in positive.items():
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    if args.max_operating_center_offset < 0:
        raise ValueError("--max-operating-center-offset must not be negative")
    for name, value in {
        "--config-delay": args.config_delay,
        "--settle-duration": args.settle_duration,
        "--return-settle-duration": args.return_settle_duration,
    }.items():
        if value < 0:
            raise ValueError(f"{name} must not be negative")

    if args.kp is not None and not RS06_LIMITS["kp"][0] <= args.kp <= RS06_LIMITS["kp"][1]:
        raise ValueError(f"--kp must be within {RS06_LIMITS['kp']}")
    if args.kd is not None and not RS06_LIMITS["kd"][0] <= args.kd <= RS06_LIMITS["kd"][1]:
        raise ValueError(f"--kd must be within {RS06_LIMITS['kd']}")

    if args.execute:
        missing = [
            name
            for name, value in {
                "--kp": args.kp,
                "--kd": args.kd,
                "--center-position": args.center_position,
                "--position-min": args.position_min,
                "--position-max": args.position_max,
                "--max-abs-velocity": args.max_abs_velocity,
                "--max-abs-torque": args.max_abs_torque,
            }.items()
            if value is None
        ]
        if missing:
            raise ValueError(
                "The following safety/configuration options are required with --execute: "
                + ", ".join(missing)
            )
        if args.position_min >= args.position_max:
            raise ValueError("--position-min must be less than --position-max")
        if args.max_abs_velocity <= 0 or args.max_abs_torque <= 0:
            raise ValueError("Feedback velocity and torque thresholds must be positive")
        p_min, p_max = RS06_LIMITS["position"]
        if args.position_min < p_min or args.position_max > p_max:
            raise ValueError(
                "Mechanical position limits must stay inside the RS06 wire range "
                f"{p_min}..{p_max} rad"
            )


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _args_for_metadata(args: argparse.Namespace) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in vars(args).items():
        if isinstance(value, Path):
            result[key] = str(value)
        else:
            result[key] = value
    return result


def _validate_manifest_control_configuration(
    manifest: Dict[str, Any], args: argparse.Namespace
) -> None:
    """Reject a replay whose requested gains differ from the generated suite."""

    configuration = manifest["control_configuration"]
    manifest_kp = float(configuration["kp"])
    manifest_kd = float(configuration["kd"])
    for option_name, requested, recorded in (
        ("--kp", args.kp, manifest_kp),
        ("--kd", args.kd, manifest_kd),
    ):
        if requested is not None and not math.isclose(
            float(requested), recorded, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError(
                f"{option_name}={requested:.9g} does not match the manifest value "
                f"{recorded:.9g}; regenerate the suite for the intended gains"
            )


def _prepare_output_paths(
    output_dir: Path,
    trajectories: Sequence[Trajectory],
    overwrite: bool,
) -> Tuple[Path, Path, Dict[str, Path]]:
    output_dir = output_dir.resolve()
    raw_path = output_dir / "raw_session.csv"
    metadata_path = output_dir / "session.metadata.json"
    compact_paths = {
        trajectory.trajectory_id: output_dir
        / f"{trajectory.trajectory_id}_{trajectory.name}.csv"
        for trajectory in trajectories
    }
    planned = [raw_path, metadata_path, *compact_paths.values()]
    existing = [path for path in planned if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Refusing to overwrite existing run files: "
            + ", ".join(str(path) for path in existing)
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    return raw_path, metadata_path, compact_paths


def _print_plan(
    args: argparse.Namespace,
    manifest: Dict[str, Any],
    trajectories: Sequence[Trajectory],
    output_dir: Path,
) -> None:
    slot = CAN_ID_TO_SLOT[args.motor_id]
    board, bus = CAN_ROUTE[args.motor_id]
    total_duration_s = sum(trajectory.duration_s for trajectory in trajectories)
    transition_overhead_s = len(trajectories) * (
        2.0 * args.transition_duration
        + args.settle_duration
        + args.return_settle_duration
    )
    base_offset_rad = 0.0
    current_offset_rad = base_offset_rad
    operating_center_transition_count = 0
    for trajectory in trajectories:
        next_offset_rad = trajectory_operating_center_offset(trajectory)
        if not math.isclose(current_offset_rad, next_offset_rad, abs_tol=1e-9):
            if not math.isclose(current_offset_rad, base_offset_rad, abs_tol=1e-9):
                operating_center_transition_count += 1
                current_offset_rad = base_offset_rad
            if not math.isclose(next_offset_rad, base_offset_rad, abs_tol=1e-9):
                operating_center_transition_count += 1
                current_offset_rad = next_offset_rad
    final_base_settle_s = 0.0
    if not math.isclose(current_offset_rad, base_offset_rad, abs_tol=1e-9):
        operating_center_transition_count += 1
        final_base_settle_s = args.return_settle_duration
    center_transition_overhead_s = (
        operating_center_transition_count * args.transition_duration
        + final_base_settle_s
    )
    print(f"Protocol:     {PROTOCOL_NAME} ({PROTOCOL_VERSION})")
    print(f"Motor:        RS06 CAN ID {args.motor_id}, slot {slot}, {board}/{bus}")
    print(f"Manifest:     {args.manifest.resolve()}")
    print(f"Schema:       {manifest['schema']}")
    print(f"Sample rate:  {manifest['sample_rate_hz']:.6g} Hz")
    print(f"Output:       {output_dir.resolve()}")
    configuration = manifest["control_configuration"]
    print(
        f"Manifest KP/KD: {configuration['kp']:.9g} / "
        f"{configuration['kd']:.9g}"
    )
    if args.kp is not None or args.kd is not None:
        print(f"Replay KP/KD:   {args.kp} / {args.kd}")
    print("Trajectories:")
    for trajectory in trajectories:
        statistics = trajectory_statistics(trajectory)
        center_offset = trajectory_operating_center_offset(trajectory)
        print(
            f"  {trajectory.trajectory_id} {trajectory.name:34s} "
            f"{trajectory.duration_s:7.2f}s peak={statistics['max_abs_offset_rad']:.4f}rad "
            f"vmax={statistics['max_abs_target_velocity_rad_s']:.3f}rad/s "
            f"center={center_offset:+.3f}rad "
            f"[{trajectory.split}]"
        )
    print(
        "Estimated commanded duration: "
        f"{(total_duration_s + transition_overhead_s + center_transition_overhead_s) / 60.0:.2f} min"
    )
    if args.execute:
        print(
            "Safety limits: "
            f"position=[{args.position_min:g}, {args.position_max:g}]rad, "
            f"base center={args.center_position:g}rad, "
            f"trajectory deviation={args.max_position_deviation:g}rad, "
            f"operating-center offset<={args.max_operating_center_offset:g}rad, "
            f"|velocity|<={args.max_abs_velocity:g}rad/s, "
            f"|torque|<={args.max_abs_torque:g}Nm, "
            f"tracking error<={args.max_tracking_error:g}rad"
        )


def _validate_suite_offsets(
    trajectories: Sequence[Trajectory], max_position_deviation: float
) -> None:
    for trajectory in trajectories:
        statistics = trajectory_statistics(trajectory)
        if statistics["max_abs_offset_rad"] > max_position_deviation + 1e-12:
            raise ValueError(
                f"{trajectory.trajectory_id} reaches "
                f"{statistics['max_abs_offset_rad']:.6f} rad, exceeding "
                f"--max-position-deviation {max_position_deviation:.6f} rad"
            )


def _validate_operating_center_offsets(
    trajectories: Sequence[Trajectory], max_operating_center_offset: float
) -> None:
    for trajectory in trajectories:
        center_offset = trajectory_operating_center_offset(trajectory)
        if abs(center_offset) > max_operating_center_offset + 1e-12:
            raise ValueError(
                f"{trajectory.trajectory_id} requests operating-center offset "
                f"{center_offset:+.6f} rad, exceeding "
                f"--max-operating-center-offset {max_operating_center_offset:.6f} rad"
            )


def _validate_absolute_positions(
    base_center_rad: float,
    trajectories: Sequence[Trajectory],
    position_min: float,
    position_max: float,
) -> None:
    if not position_min <= base_center_rad <= position_max:
        raise SafetyAbort(
            f"Run base center {base_center_rad:.6f} rad is outside mechanical limits "
            f"[{position_min:.6f}, {position_max:.6f}]"
        )
    for trajectory in trajectories:
        operating_center_rad = (
            base_center_rad + trajectory_operating_center_offset(trajectory)
        )
        minimum = operating_center_rad + min(trajectory.q_offset_rad)
        maximum = operating_center_rad + max(trajectory.q_offset_rad)
        if minimum < position_min or maximum > position_max:
            raise SafetyAbort(
                f"{trajectory.trajectory_id} absolute range [{minimum:.6f}, "
                f"{maximum:.6f}] rad exceeds mechanical limits "
                f"[{position_min:.6f}, {position_max:.6f}]"
            )


def _send_hold(
    controller: ControlBox,
    motor_id: int,
    position_rad: float,
    repeats: int = 3,
) -> None:
    positions = [0.0] * len(SLOT_TO_CAN_ID)
    positions[CAN_ID_TO_SLOT[motor_id]] = position_rad
    for _ in range(repeats):
        controller.send_positions(positions)
        time.sleep(0.02)


def _find_echo_delay_steps(state: RunnerState, raw_target: int) -> Optional[int]:
    for command_sequence_index, raw_command in reversed(state.command_history):
        if raw_command == raw_target:
            return state.command_sequence_index - command_sequence_index
    return None


def _check_command_safety(
    state: RunnerState,
    requested_rad: float,
    safety_center_rad: float,
    max_center_deviation_rad: float,
) -> None:
    args = state.args
    if not args.position_min <= requested_rad <= args.position_max:
        raise SafetyAbort(
            f"Refusing command {requested_rad:.6f} rad outside mechanical limits "
            f"[{args.position_min:.6f}, {args.position_max:.6f}]"
        )
    deviation = abs(requested_rad - safety_center_rad)
    if deviation > max_center_deviation_rad:
        raise SafetyAbort(
            f"Refusing command deviation {deviation:.6f} rad greater than "
            f"the active phase limit {max_center_deviation_rad:.6f} rad"
        )
    p_min, p_max = RS06_LIMITS["position"]
    if not p_min <= requested_rad <= p_max:
        raise SafetyAbort(
            f"Refusing command {requested_rad:.6f} rad outside RS06 wire range"
        )


def _check_feedback_safety(
    state: RunnerState,
    record: Any,
    feedback_gap_s: float,
    safety_center_rad: float,
    max_center_deviation_rad: float,
) -> None:
    args = state.args
    if not args.position_min <= record.q <= args.position_max:
        raise SafetyAbort(
            f"Feedback position {record.q:.6f} rad left mechanical limits"
        )
    deviation = abs(record.q - safety_center_rad)
    if deviation > max_center_deviation_rad:
        raise SafetyAbort(
            f"Feedback position deviation {deviation:.6f} rad exceeded "
            f"the active phase limit {max_center_deviation_rad:.6f} rad"
        )
    if abs(record.qdot) > args.max_abs_velocity:
        raise SafetyAbort(
            f"Feedback velocity {record.qdot:.6f} rad/s exceeded "
            f"{args.max_abs_velocity:.6f} rad/s"
        )
    if abs(record.torque) > args.max_abs_torque:
        raise SafetyAbort(
            f"Feedback torque {record.torque:.6f} Nm exceeded "
            f"{args.max_abs_torque:.6f} Nm"
        )
    tracking_error = abs(record.target - record.q)
    if tracking_error > args.max_tracking_error:
        raise SafetyAbort(
            f"Tracking error {tracking_error:.6f} rad exceeded "
            f"{args.max_tracking_error:.6f} rad"
        )
    if feedback_gap_s > args.max_feedback_gap:
        raise SafetyAbort(
            f"Feedback gap {feedback_gap_s:.6f}s exceeded "
            f"{args.max_feedback_gap:.6f}s"
        )


def _send_and_record(
    state: RunnerState,
    *,
    requested_rad: float,
    trajectory_id: str,
    phase: str,
    phase_sample_index: int,
    t_nominal_s: float,
    schedule_reference: float,
    compact_writer: Optional[csv.DictWriter],
    safety_center_rad: float,
    max_center_deviation_rad: float,
) -> None:
    _check_command_safety(
        state,
        requested_rad,
        safety_center_rad,
        max_center_deviation_rad,
    )
    scheduled_monotonic = schedule_reference + t_nominal_s
    now = time.perf_counter()
    if now < scheduled_monotonic:
        time.sleep(scheduled_monotonic - now)

    send_before = time.perf_counter()
    schedule_lateness_s = max(0.0, send_before - scheduled_monotonic)
    if schedule_lateness_s > state.args.max_schedule_lateness:
        raise SafetyAbort(
            f"Schedule lateness {schedule_lateness_s:.6f}s exceeded "
            f"{state.args.max_schedule_lateness:.6f}s"
        )
    loop_dt_s = (
        0.0 if state.last_send_before is None else send_before - state.last_send_before
    )

    positions = [0.0] * len(SLOT_TO_CAN_ID)
    positions[state.slot] = requested_rad
    encoding = state.controller.send_positions(positions)
    send_after = time.perf_counter()
    encoded = encoding.encoded_positions[state.slot]
    if encoded.saturated:
        state.command_saturation_count += 1
        raise SafetyAbort("A position command saturated during RS06 wire encoding")

    state.command_sequence_index += 1
    command_changed = (
        not state.command_history or state.command_history[-1][1] != encoded.raw
    )
    state.command_history.append((state.command_sequence_index, encoded.raw))
    while len(state.command_history) > state.args.max_echo_history_steps:
        state.command_history.popleft()

    state.controller.clear_input()
    feedback = acquire_required_feedback(
        state.controller,
        (state.motor_id,),
        state.args.frame_timeout,
        state.args.max_bad_frames,
        f"{trajectory_id}/{phase}",
    )
    record = feedback.motors[state.slot]
    feedback_gap_s = (
        0.0
        if state.last_receive is None
        else feedback.received_monotonic - state.last_receive
    )
    _check_feedback_safety(
        state,
        record,
        feedback_gap_s,
        safety_center_rad,
        max_center_deviation_rad,
    )

    echo_delay_steps = _find_echo_delay_steps(state, record.raw_target)
    if echo_delay_steps is None:
        state.unrecognized_echo_count += 1
        if state.unrecognized_echo_count > state.args.max_unrecognized_echoes:
            raise SafetyAbort(
                "target_feedback did not match any recent command for "
                f"{state.unrecognized_echo_count} consecutive frames"
            )
    else:
        state.unrecognized_echo_count = 0
        if command_changed:
            state.echo_delay_histogram[echo_delay_steps] = (
                state.echo_delay_histogram.get(echo_delay_steps, 0) + 1
            )

    state.latest_q_rad = record.q
    state.last_command_rad = encoded.decoded
    state.last_send_before = send_before
    state.last_receive = feedback.received_monotonic
    state.max_observed_abs_velocity = max(
        state.max_observed_abs_velocity, abs(record.qdot)
    )
    state.max_observed_abs_torque = max(
        state.max_observed_abs_torque, abs(record.torque)
    )
    state.max_observed_abs_tracking_error = max(
        state.max_observed_abs_tracking_error, abs(record.target - record.q)
    )

    row = {
        "session_sample_index": state.session_sample_index,
        "trajectory_id": trajectory_id,
        "phase": phase,
        "trajectory_sample_index": (
            phase_sample_index if phase == "trajectory" else ""
        ),
        "t_nominal_s": f"{t_nominal_s:.9f}",
        "t_send_before_s": f"{send_before - state.session_start_monotonic:.9f}",
        "t_send_after_s": f"{send_after - state.session_start_monotonic:.9f}",
        "t_receive_s": (
            f"{feedback.received_monotonic - state.session_start_monotonic:.9f}"
        ),
        "host_time_utc": feedback.received_utc,
        "loop_dt_s": f"{loop_dt_s:.9f}",
        "schedule_lateness_s": f"{schedule_lateness_s:.9f}",
        "feedback_gap_s": f"{feedback_gap_s:.9f}",
        "can_id": state.motor_id,
        "controller_slot": state.slot,
        "kp": f"{state.kp:.9g}",
        "kd": f"{state.kd:.9g}",
        "q_center_rad": f"{safety_center_rad:.9f}",
        "q_offset_command_rad": f"{requested_rad - safety_center_rad:.9f}",
        "q_command_requested_rad": f"{requested_rad:.9f}",
        "q_command_encoded_rad": f"{encoded.decoded:.9f}",
        "q_command_saturated": int(encoded.saturated),
        "target_feedback_rad": f"{record.target:.9f}",
        "target_matches_current_command": int(record.raw_target == encoded.raw),
        "echo_delay_steps": "" if echo_delay_steps is None else echo_delay_steps,
        "q_feedback_rad": f"{record.q:.9f}",
        "qdot_feedback_rad_s": f"{record.qdot:.9f}",
        "torque_feedback_nm": f"{record.torque:.9f}",
        "tracking_error_target_rad": f"{record.target - record.q:.9f}",
        "tracking_error_command_rad": f"{encoded.decoded - record.q:.9f}",
        "raw_q_u16": record.raw_q,
        "raw_qdot_u16": record.raw_qdot,
        "raw_torque_u16": record.raw_torque,
        "raw_target_u16": record.raw_target,
        "raw_record_hex": record.raw_record.hex(" "),
    }
    state.raw_writer.writerow(row)
    if compact_writer is not None:
        compact_writer.writerow(
            {
                "time": f"{t_nominal_s:.9f}",
                "q_target": f"{record.target:.9f}",
                "q": f"{record.q:.9f}",
                "vel": f"{record.qdot:.9f}",
                "torque": f"{record.torque:.9f}",
            }
        )
    state.session_sample_index += 1


def _run_values(
    state: RunnerState,
    *,
    trajectory_id: str,
    phase: str,
    absolute_positions: Sequence[float],
    compact_writer: Optional[csv.DictWriter] = None,
    safety_center_rad: Optional[float] = None,
    max_center_deviation_rad: Optional[float] = None,
) -> None:
    if not absolute_positions:
        return
    phase_start = time.perf_counter()
    active_center_rad = (
        state.center_rad if safety_center_rad is None else safety_center_rad
    )
    active_deviation_limit = (
        state.args.max_position_deviation
        if max_center_deviation_rad is None
        else max_center_deviation_rad
    )
    for sample_index, requested_rad in enumerate(absolute_positions):
        _send_and_record(
            state,
            requested_rad=requested_rad,
            trajectory_id=trajectory_id,
            phase=phase,
            phase_sample_index=sample_index,
            t_nominal_s=sample_index / state.sample_rate_hz,
            schedule_reference=phase_start,
            compact_writer=compact_writer,
            safety_center_rad=active_center_rad,
            max_center_deviation_rad=active_deviation_limit,
        )


def _settle_values(
    position_rad: float, duration_s: float, sample_rate_hz: float
) -> Tuple[float, ...]:
    count = int(round(duration_s * sample_rate_hz))
    return tuple(position_rad for _ in range(max(0, count)))


def _write_metadata(path: Path, metadata: Dict[str, Any]) -> None:
    path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_suite(
    args: argparse.Namespace,
    manifest: Dict[str, Any],
    trajectories: Sequence[Trajectory],
    output_dir: Path,
) -> int:
    raw_path, metadata_path, compact_paths = _prepare_output_paths(
        output_dir, trajectories, args.overwrite
    )
    slot = CAN_ID_TO_SLOT[args.motor_id]
    kp_by_slot = [0.0] * len(SLOT_TO_CAN_ID)
    kd_by_slot = [0.0] * len(SLOT_TO_CAN_ID)
    kp_by_slot[slot] = float(args.kp)
    kd_by_slot[slot] = float(args.kd)

    metadata: Dict[str, Any] = {
        "status": "initializing",
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "protocol": {"name": PROTOCOL_NAME, "version": PROTOCOL_VERSION},
        "motor_model": MOTOR_MODEL,
        "motor_id": args.motor_id,
        "controller_slot": slot,
        "route": {"board": CAN_ROUTE[args.motor_id][0], "bus": CAN_ROUTE[args.motor_id][1]},
        "kp": args.kp,
        "kd": args.kd,
        "zeroing_policy": (
            "The operator calibrates zero before the run. The runner never requests "
            "a new zero and moves to the explicit center_position with minimum jerk."
        ),
        "manifest_path": str(args.manifest.resolve()),
        "manifest_sha256": _hash_file(args.manifest.resolve()),
        "manifest_schema": manifest["schema"],
        "manifest_control_configuration": manifest["control_configuration"],
        "sample_rate_hz": manifest["sample_rate_hz"],
        "selected_trajectories": [trajectory.trajectory_id for trajectory in trajectories],
        "trajectory_operating_center_offsets_rad": {
            trajectory.trajectory_id: trajectory_operating_center_offset(trajectory)
            for trajectory in trajectories
        },
        "arguments": _args_for_metadata(args),
        "raw_csv": str(raw_path),
        "compact_csv": {key: str(value) for key, value in compact_paths.items()},
    }
    _write_metadata(metadata_path, metadata)

    controller: Optional[ControlBox] = None
    raw_file = None
    state: Optional[RunnerState] = None
    motion_armed = False
    completed_trajectories: List[str] = []
    status = "error"
    error_text: Optional[str] = None
    exit_code = 1

    try:
        controller = ControlBox(
            port=args.port,
            baudrate=args.baudrate,
            serial_timeout_s=args.serial_timeout,
            allow_shared_port=args.allow_shared_port,
        )
        LOGGER.info("Opened %s; waiting for CAN ID %d", args.port, args.motor_id)
        controller.clear_input()
        wait_for_required_motors_online(
            controller,
            (args.motor_id,),
            args.online_timeout,
            args.frame_timeout,
            "Pre-configuration",
        )

        controller.configure_rs06_position_mode(
            kp_by_slot=kp_by_slot,
            kd_by_slot=kd_by_slot,
            delay_s=args.config_delay,
        )
        controller.clear_input()
        configured_frame = wait_for_required_motors_online(
            controller,
            (args.motor_id,),
            args.online_timeout,
            args.frame_timeout,
            "Post-configuration",
        )
        configured_record = configured_frame.motors[slot]
        initial_q = configured_record.q
        if not args.position_min <= initial_q <= args.position_max:
            raise SafetyAbort(
                f"Startup position {initial_q:.6f} rad is outside mechanical limits"
            )
        if abs(configured_record.qdot) > args.max_abs_velocity:
            raise SafetyAbort(
                f"Startup velocity {configured_record.qdot:.6f} rad/s exceeds the limit"
            )
        if abs(configured_record.torque) > args.max_abs_torque:
            raise SafetyAbort(
                f"Startup torque {configured_record.torque:.6f} Nm exceeds the limit"
            )
        center_rad = args.center_position
        _validate_absolute_positions(
            center_rad,
            trajectories,
            args.position_min,
            args.position_max,
        )
        if abs(initial_q - center_rad) > args.max_initial_center_distance:
            raise SafetyAbort(
                f"Requested base center is {abs(initial_q - center_rad):.6f} rad from "
                "the measured startup position, beyond "
                "--max-initial-center-distance"
            )

        positions = [0.0] * len(SLOT_TO_CAN_ID)
        positions[slot] = initial_q
        initial_encoding = controller.send_positions(positions)
        controller.clear_input()
        initial_echo = wait_for_command_echo(
            controller,
            (args.motor_id,),
            initial_encoding,
            args.command_echo_timeout,
            args.frame_timeout,
        )
        initial_record = initial_echo.motors[slot]
        motion_armed = True
        LOGGER.info(
            "Initial q=%.6f rad; run center=%.6f rad; torque=%.6f Nm",
            initial_record.q,
            center_rad,
            initial_record.torque,
        )

        raw_file = raw_path.open("w", newline="", encoding="utf-8", buffering=1)
        raw_writer = csv.DictWriter(raw_file, fieldnames=RAW_CSV_FIELDS)
        raw_writer.writeheader()
        session_start = time.perf_counter()
        state = RunnerState(
            controller=controller,
            motor_id=args.motor_id,
            slot=slot,
            kp=float(args.kp),
            kd=float(args.kd),
            center_rad=center_rad,
            sample_rate_hz=float(manifest["sample_rate_hz"]),
            session_start_monotonic=session_start,
            raw_writer=raw_writer,
            args=args,
            latest_q_rad=initial_record.q,
            last_command_rad=initial_encoding.encoded_positions[slot].decoded,
        )
        state.command_history.append((0, initial_encoding.encoded_positions[slot].raw))

        if not math.isclose(initial_q, center_rad, abs_tol=1e-9):
            transition = minimum_jerk_transition(
                initial_q,
                center_rad,
                args.transition_duration,
                state.sample_rate_hz,
            )
            _run_values(
                state,
                trajectory_id="SESSION",
                phase="move_to_base_center",
                absolute_positions=transition,
                safety_center_rad=center_rad,
                max_center_deviation_rad=args.max_initial_center_distance,
            )

        metadata["status"] = "running"
        metadata["initial_q_rad"] = initial_q
        metadata["base_center_q_rad"] = center_rad
        metadata["center_q_rad"] = center_rad
        _write_metadata(metadata_path, metadata)

        current_operating_center_rad = center_rad
        for trajectory in trajectories:
            operating_center_rad = (
                center_rad + trajectory_operating_center_offset(trajectory)
            )
            if not math.isclose(
                current_operating_center_rad,
                operating_center_rad,
                abs_tol=1e-9,
            ):
                if not math.isclose(
                    current_operating_center_rad,
                    center_rad,
                    abs_tol=1e-9,
                ):
                    transition = minimum_jerk_transition(
                        state.last_command_rad,
                        center_rad,
                        args.transition_duration,
                        state.sample_rate_hz,
                    )
                    _run_values(
                        state,
                        trajectory_id="SESSION",
                        phase="return_to_base_between_centers",
                        absolute_positions=transition,
                        safety_center_rad=center_rad,
                        max_center_deviation_rad=args.max_operating_center_offset,
                    )
                    current_operating_center_rad = center_rad

                transition = minimum_jerk_transition(
                    state.last_command_rad,
                    operating_center_rad,
                    args.transition_duration,
                    state.sample_rate_hz,
                )
                _run_values(
                    state,
                    trajectory_id="SESSION",
                    phase="move_to_operating_center",
                    absolute_positions=transition,
                    safety_center_rad=center_rad,
                    max_center_deviation_rad=args.max_operating_center_offset,
                )
                current_operating_center_rad = operating_center_rad

            LOGGER.info(
                "Starting %s %s (%.2fs, %s, center=%+.3frad)",
                trajectory.trajectory_id,
                trajectory.name,
                trajectory.duration_s,
                trajectory.split,
                operating_center_rad,
            )
            first_position = operating_center_rad + trajectory.q_offset_rad[0]
            transition = minimum_jerk_transition(
                state.last_command_rad,
                first_position,
                args.transition_duration,
                state.sample_rate_hz,
            )
            _run_values(
                state,
                trajectory_id=trajectory.trajectory_id,
                phase="move_to_start",
                absolute_positions=transition,
                safety_center_rad=operating_center_rad,
            )
            _run_values(
                state,
                trajectory_id=trajectory.trajectory_id,
                phase="settle",
                absolute_positions=_settle_values(
                    first_position, args.settle_duration, state.sample_rate_hz
                ),
                safety_center_rad=operating_center_rad,
            )

            compact_path = compact_paths[trajectory.trajectory_id]
            with compact_path.open(
                "w", newline="", encoding="utf-8", buffering=1
            ) as compact_file:
                compact_writer = csv.DictWriter(
                    compact_file, fieldnames=COMPACT_CSV_FIELDS
                )
                compact_writer.writeheader()
                _run_values(
                    state,
                    trajectory_id=trajectory.trajectory_id,
                    phase="trajectory",
                    absolute_positions=tuple(
                        operating_center_rad + offset
                        for offset in trajectory.q_offset_rad
                    ),
                    compact_writer=compact_writer,
                    safety_center_rad=operating_center_rad,
                )

            return_transition = minimum_jerk_transition(
                state.last_command_rad,
                operating_center_rad,
                args.transition_duration,
                state.sample_rate_hz,
            )
            _run_values(
                state,
                trajectory_id=trajectory.trajectory_id,
                phase="return_to_center",
                absolute_positions=return_transition,
                safety_center_rad=operating_center_rad,
            )
            _run_values(
                state,
                trajectory_id=trajectory.trajectory_id,
                phase="return_settle",
                absolute_positions=_settle_values(
                    operating_center_rad,
                    args.return_settle_duration,
                    state.sample_rate_hz,
                ),
                safety_center_rad=operating_center_rad,
            )
            completed_trajectories.append(trajectory.trajectory_id)
            metadata["completed_trajectories"] = list(completed_trajectories)
            _write_metadata(metadata_path, metadata)
            LOGGER.info("Completed %s", trajectory.trajectory_id)

        if not math.isclose(
            current_operating_center_rad,
            center_rad,
            abs_tol=1e-9,
        ):
            transition = minimum_jerk_transition(
                state.last_command_rad,
                center_rad,
                args.transition_duration,
                state.sample_rate_hz,
            )
            _run_values(
                state,
                trajectory_id="SESSION",
                phase="final_return_to_base_center",
                absolute_positions=transition,
                safety_center_rad=center_rad,
                max_center_deviation_rad=args.max_operating_center_offset,
            )
            _run_values(
                state,
                trajectory_id="SESSION",
                phase="final_base_settle",
                absolute_positions=_settle_values(
                    center_rad,
                    args.return_settle_duration,
                    state.sample_rate_hz,
                ),
                safety_center_rad=center_rad,
                max_center_deviation_rad=args.max_operating_center_offset,
            )

        _send_hold(controller, args.motor_id, center_rad)
        status = "complete"
        exit_code = 0
        LOGGER.info("Suite complete; center-position hold command sent")

    except KeyboardInterrupt:
        status = "interrupted"
        exit_code = 130
        error_text = "KeyboardInterrupt"
        LOGGER.error("Interrupted by user")
    except Exception as exc:
        status = "safety_abort" if isinstance(exc, SafetyAbort) else "error"
        exit_code = 2 if isinstance(exc, SafetyAbort) else 1
        error_text = f"{type(exc).__name__}: {exc}"
        LOGGER.error("%s", error_text)
    finally:
        if controller is not None and motion_armed and status != "complete":
            try:
                hold_position = state.latest_q_rad if state is not None else initial_q
                _send_hold(controller, args.motor_id, hold_position)
                LOGGER.warning(
                    "Latest-feedback hold command sent after interruption/error"
                )
            except Exception as hold_exc:
                LOGGER.error("Failed to send final hold command: %s", hold_exc)
        if raw_file is not None:
            raw_file.close()
        if controller is not None:
            try:
                metadata["serial_statistics"] = {
                    "valid_frames_read": controller.frames_read,
                    "invalid_163_byte_candidates": controller.invalid_candidates,
                }
                controller.close()
            except Exception as close_exc:
                LOGGER.error("Failed to close serial port: %s", close_exc)

        metadata.update(
            {
                "status": status,
                "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "error": error_text,
                "completed_trajectories": completed_trajectories,
            }
        )
        if state is not None:
            metadata["runtime_statistics"] = {
                "recorded_samples": state.session_sample_index,
                "position_command_saturations": state.command_saturation_count,
                "echo_delay_steps_histogram": {
                    str(key): value
                    for key, value in sorted(state.echo_delay_histogram.items())
                },
                "unrecognized_echo_count_at_end": state.unrecognized_echo_count,
                "max_observed_abs_velocity_rad_s": state.max_observed_abs_velocity,
                "max_observed_abs_torque_nm": state.max_observed_abs_torque,
                "max_observed_abs_tracking_error_rad": (
                    state.max_observed_abs_tracking_error
                ),
            }
        try:
            _write_metadata(metadata_path, metadata)
        except Exception as metadata_exc:
            LOGGER.error("Failed to write final metadata: %s", metadata_exc)
            if exit_code == 0:
                exit_code = 1

        print(f"Raw CSV:  {raw_path}")
        print(f"Metadata: {metadata_path}")
        if motion_armed:
            print(
                "WARNING: closing the COM port does not disable motor torque; "
                "use the hardware stop/power control.",
                file=sys.stderr,
            )
    return exit_code


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    sharklog.init(name=LOGGER_NAME, debug=args.verbose)
    try:
        _validate_args(args)
        manifest, trajectories = load_suite(args.manifest, args.trajectory_ids)
        _validate_manifest_control_configuration(manifest, args)
        _validate_suite_offsets(trajectories, args.max_position_deviation)
        _validate_operating_center_offsets(
            trajectories,
            args.max_operating_center_offset,
        )
        output_dir = args.output_dir or _default_output_dir()
        _print_plan(args, manifest, trajectories, output_dir)
    except (ValueError, FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        parser.error(str(exc))
        return 2

    if not args.execute:
        print()
        print("DRY RUN ONLY: the serial port was not opened and no files were created.")
        print(
            "Add explicit KP/KD, absolute position limits, feedback velocity/torque "
            "limits, and --execute only after fixture and hardware-stop checks."
        )
        return 0

    return run_suite(args, manifest, trajectories, output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
