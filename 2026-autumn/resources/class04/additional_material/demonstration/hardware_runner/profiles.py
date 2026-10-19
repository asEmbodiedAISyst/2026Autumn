"""Frozen V5 P01-P03 command generation and low-amplitude safety pilot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ExecutedProfile:
    profile_id: str
    command_rad: np.ndarray
    phase: np.ndarray
    active_start_index: int
    active_sample_count: int


def _count(duration_s: float, dt_s: float, *, inclusive: bool = False) -> int:
    return int(round(duration_s / dt_s)) + int(inclusive)


def _hold(value: float, duration_s: float, dt_s: float) -> np.ndarray:
    return np.full(_count(duration_s, dt_s), value, dtype=float)


def _half_cosine(start: float, stop: float, duration_s: float, dt_s: float) -> np.ndarray:
    count = _count(duration_s, dt_s)
    if count <= 1:
        return np.asarray([stop], dtype=float)
    u = np.linspace(0.0, 1.0, count, endpoint=False)
    blend = 0.5 - 0.5 * np.cos(np.pi * u)
    return start + (stop - start) * blend


def authoritative_active_profiles(config: dict[str, Any]) -> dict[str, np.ndarray]:
    """Generate exactly the active P01-P03 samples declared by V5 Design2Data."""

    dt_s = 1.0 / float(config["command_rate_hz"])
    generated: dict[str, np.ndarray] = {}
    for profile_id, spec in config["profiles"].items():
        kind = spec["kind"]
        if kind == "smooth_levels":
            hold_count = _count(float(spec["hold_s"]), dt_s)
            transition_count = _count(float(spec["transition_s"]), dt_s)
            levels = [float(value) for value in spec["levels_rad"]]
            pieces: list[np.ndarray] = [np.full(hold_count, levels[0], dtype=float)]
            for start, stop in zip(levels[:-1], levels[1:], strict=True):
                if transition_count <= 1:
                    transition = np.asarray([stop], dtype=float)
                else:
                    u = np.linspace(0.0, 1.0, transition_count, endpoint=False)
                    transition = start + (stop - start) * (0.5 - 0.5 * np.cos(np.pi * u))
                pieces.extend([transition, np.full(hold_count, stop, dtype=float)])
            generated[profile_id] = np.concatenate(pieces)
            continue

        duration_s = float(spec["duration_s"])
        time_s = np.arange(_count(duration_s, dt_s, inclusive=True), dtype=float) * dt_s
        if kind == "triangle":
            phase = 2.0 * np.pi * float(spec["frequency_hz"]) * time_s
            command = float(spec["center_rad"]) + (
                float(spec["amplitude_rad"])
                * (2.0 / np.pi)
                * np.arcsin(np.sin(phase))
            )
        elif kind == "multisine":
            command = np.full_like(time_s, float(spec["center_rad"]))
            for amplitude, frequency, phase in zip(
                spec["amplitudes_rad"],
                spec["frequencies_hz"],
                spec["phases_rad"],
                strict=True,
            ):
                command += float(amplitude) * np.sin(
                    2.0 * np.pi * float(frequency) * time_s + float(phase)
                )
        elif kind == "chirp":
            start = float(spec["start_frequency_hz"])
            stop = float(spec["end_frequency_hz"])
            phase = 2.0 * np.pi * (
                start * time_s
                + 0.5 * (stop - start) / duration_s * time_s**2
            )
            command = float(spec["center_rad"]) + float(
                spec["amplitude_rad"]
            ) * np.sin(phase)
        elif kind == "sine":
            command = float(spec["center_rad"]) + float(
                spec["amplitude_rad"]
            ) * np.sin(2.0 * np.pi * float(spec["frequency_hz"]) * time_s)
        elif kind == "composite":
            command = np.zeros_like(time_s)
            for amplitude, frequency, phase in zip(
                spec["amplitudes_rad"],
                spec["frequencies_hz"],
                spec["phases_rad"],
                strict=True,
            ):
                command += float(amplitude) * np.sin(
                    2.0 * np.pi * float(frequency) * time_s + float(phase)
                )
            offsets = spec["center_offsets_rad"]
            switches = spec["switch_times_s"]
            command += np.select(
                [time_s < float(switches[0]), time_s < float(switches[1])],
                [float(offsets[0]), float(offsets[1])],
                default=float(offsets[2]),
            )
        elif kind == "sine_hold":
            active = float(spec["active_duration_s"])
            center = float(spec["center_rad"])
            amplitude = float(spec["amplitude_rad"])
            frequency = float(spec["frequency_hz"])
            command = center + amplitude * np.sin(
                2.0 * np.pi * frequency * time_s
            )
            transition = float(spec["transition_s"])
            hold = float(spec["hold_position_rad"])
            start_value = center + amplitude * np.sin(
                2.0 * np.pi * frequency * active
            )
            transition_mask = (time_s >= active) & (
                time_s < active + transition
            )
            transition_phase = (
                time_s[transition_mask] - active
            ) / transition
            blend = 0.5 - 0.5 * np.cos(np.pi * transition_phase)
            command[transition_mask] = (
                start_value + (hold - start_value) * blend
            )
            command[time_s >= active + transition] = hold
        else:
            raise ValueError(f"unsupported profile kind: {kind}")
        generated[profile_id] = command
    return generated


def executed_profiles(config: dict[str, Any]) -> dict[str, ExecutedProfile]:
    """Wrap active profiles in explicitly labeled, zero-safe preparation/recovery samples."""

    dt_s = 1.0 / float(config["command_rate_hz"])
    active = authoritative_active_profiles(config)
    output: dict[str, ExecutedProfile] = {}
    for profile_id, active_command in active.items():
        spec = config["profiles"][profile_id]
        post_target = float(spec.get("post_profile_target_rad", 0.0))
        pieces: list[np.ndarray] = []
        phases: list[np.ndarray] = []
        if "pre_profile_transition_s" in spec:
            zero_hold = _hold(
                0.0, float(spec.get("pre_profile_zero_hold_s", 0.25)), dt_s
            )
            transition = _half_cosine(
                0.0,
                float(active_command[0]),
                float(spec["pre_profile_transition_s"]),
                dt_s,
            )
            pieces.extend([zero_hold, transition])
            phases.extend(
                [
                    np.full(zero_hold.size, "pre_zero_hold", dtype=object),
                    np.full(transition.size, "pre_transition", dtype=object),
                ]
            )
        active_start = sum(piece.size for piece in pieces)
        pieces.append(active_command)
        phases.append(np.full(active_command.size, "active", dtype=object))
        if "post_profile_return_s" in spec:
            recovery = _half_cosine(
                float(active_command[-1]),
                post_target,
                float(spec["post_profile_return_s"]),
                dt_s,
            )
            pieces.append(recovery)
            phases.append(np.full(recovery.size, "post_return", dtype=object))
        settle = _hold(
            post_target,
            float(
                spec.get(
                    "post_profile_hold_s",
                    spec["post_profile_zero_hold_s"],
                )
            ),
            dt_s,
        )
        pieces.append(settle)
        phases.append(
            np.full(
                settle.size,
                (
                    "post_zero_hold"
                    if abs(post_target) < 1e-12
                    else "post_target_hold"
                ),
                dtype=object,
            )
        )
        output[profile_id] = ExecutedProfile(
            profile_id=profile_id,
            command_rad=np.concatenate(pieces),
            phase=np.concatenate(phases),
            active_start_index=active_start,
            active_sample_count=int(active_command.size),
        )
    return output


def pilot_profile(config: dict[str, Any]) -> ExecutedProfile:
    dt_s = 1.0 / float(config["command_rate_hz"])
    spec = config["pilot"]
    time_s = np.arange(
        _count(float(spec["duration_s"]), dt_s, inclusive=True), dtype=float
    ) * dt_s
    active = float(spec["amplitude_rad"]) * np.sin(
        2.0 * np.pi * float(spec["frequency_hz"]) * time_s
    )
    post_target = float(spec.get("post_profile_target_rad", 0.0))
    pieces = [active]
    phases = [np.full(active.size, "active", dtype=object)]
    if "post_profile_return_s" in spec:
        recovery = _half_cosine(
            float(active[-1]),
            post_target,
            float(spec["post_profile_return_s"]),
            dt_s,
        )
        pieces.append(recovery)
        phases.append(
            np.full(recovery.size, "post_return", dtype=object)
        )
    settle = _hold(
        post_target,
        float(
            spec.get(
                "post_profile_hold_s",
                spec["post_profile_zero_hold_s"],
            )
        ),
        dt_s,
    )
    pieces.append(settle)
    phases.append(
        np.full(
            settle.size,
            (
                "post_zero_hold"
                if abs(post_target) < 1e-12
                else "post_target_hold"
            ),
            dtype=object,
        )
    )
    return ExecutedProfile(
        profile_id="PILOT_LOW_AMPLITUDE",
        command_rad=np.concatenate(pieces),
        phase=np.concatenate(phases),
        active_start_index=0,
        active_sample_count=int(active.size),
    )


def profile_statistics(profile: ExecutedProfile, dt_s: float) -> dict[str, float | int]:
    command = profile.command_rad
    velocity = np.gradient(command, dt_s)
    acceleration = np.gradient(velocity, dt_s)
    return {
        "sample_count": int(command.size),
        "active_start_index": int(profile.active_start_index),
        "active_sample_count": int(profile.active_sample_count),
        "duration_s": float((command.size - 1) * dt_s),
        "minimum_rad": float(np.min(command)),
        "maximum_rad": float(np.max(command)),
        "maximum_abs_velocity_rad_s": float(np.max(np.abs(velocity))),
        "maximum_abs_acceleration_rad_s2": float(np.max(np.abs(acceleration))),
        "maximum_abs_step_rad": float(np.max(np.abs(np.diff(command)))),
    }
