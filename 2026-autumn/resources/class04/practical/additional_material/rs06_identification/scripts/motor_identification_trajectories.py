#!/usr/bin/env python3
"""Generate and validate deterministic RS06 identification trajectories.

All trajectory positions in this module are offsets from a center position. The
hardware runner is responsible for adding the measured center position and for
enforcing absolute mechanical limits.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SUITE_SCHEMA = "rs06-identification-trajectory-suite/v2"
TRAJECTORY_CSV_FIELDS = ("sample_index", "time_s", "q_offset_rad")
DEFAULT_MAX_EXCITATION_FREQUENCY_HZ = 3.0
DEFAULT_MAX_OFFSET_RAD = 1.0
DEFAULT_MAX_TARGET_VELOCITY_RAD_S = 8.0
DEFAULT_MAX_TARGET_ACCELERATION_RAD_S2 = 400.0


@dataclass(frozen=True)
class Trajectory:
    """One uniformly sampled, center-relative position trajectory."""

    trajectory_id: str
    name: str
    purpose: str
    split: str
    sample_rate_hz: float
    q_offset_rad: Tuple[float, ...]
    parameters: Dict[str, Any]

    @property
    def dt_s(self) -> float:
        return 1.0 / self.sample_rate_hz

    @property
    def duration_s(self) -> float:
        return len(self.q_offset_rad) / self.sample_rate_hz


def _sample_count(duration_s: float, sample_rate_hz: float) -> int:
    count = int(round(duration_s * sample_rate_hz))
    if count <= 0:
        raise ValueError("A trajectory segment must contain at least one sample")
    return count


def _repeat(value: float, duration_s: float, sample_rate_hz: float) -> List[float]:
    return [float(value)] * _sample_count(duration_s, sample_rate_hz)


def _minimum_jerk_values(
    start: float,
    end: float,
    duration_s: float,
    sample_rate_hz: float,
    *,
    include_endpoint: bool = False,
) -> List[float]:
    count = _sample_count(duration_s, sample_rate_hz)
    denominator = count - 1 if include_endpoint and count > 1 else count
    values: List[float] = []
    for index in range(count):
        u = min(1.0, index / denominator)
        blend = 10.0 * u**3 - 15.0 * u**4 + 6.0 * u**5
        values.append(start + (end - start) * blend)
    if include_endpoint:
        values[-1] = end
    return values


def minimum_jerk_transition(
    start: float,
    end: float,
    duration_s: float,
    sample_rate_hz: float,
) -> Tuple[float, ...]:
    """Return a transition that includes its exact endpoint."""

    return tuple(
        _minimum_jerk_values(
            start,
            end,
            duration_s,
            sample_rate_hz,
            include_endpoint=True,
        )
    )


def _minimum_jerk_move_values(
    start: float,
    end: float,
    duration_s: float,
    sample_rate_hz: float,
) -> List[float]:
    """Return an endpoint-inclusive move whose sample intervals span the duration."""

    interval_count = _sample_count(duration_s, sample_rate_hz)
    values: List[float] = []
    for index in range(interval_count + 1):
        u = index / interval_count
        blend = 10.0 * u**3 - 15.0 * u**4 + 6.0 * u**5
        values.append(start + (end - start) * blend)
    values[-1] = end
    return values


def _cosine_envelope(t_s: float, duration_s: float, ramp_s: float) -> float:
    if ramp_s <= 0.0:
        return 1.0
    if t_s < ramp_s:
        return 0.5 * (1.0 - math.cos(math.pi * t_s / ramp_s))
    if t_s > duration_s - ramp_s:
        remaining = max(0.0, duration_s - t_s)
        return 0.5 * (1.0 - math.cos(math.pi * remaining / ramp_s))
    return 1.0


def _variable_amplitude_log_chirp(
    start_frequency_hz: float,
    end_frequency_hz: float,
    low_frequency_amplitude_rad: float,
    high_frequency_amplitude_rad: float,
    duration_s: float,
    sample_rate_hz: float,
    ramp_s: float,
) -> List[float]:
    """Generate a log chirp with amplitude defined by instantaneous frequency."""

    if start_frequency_hz <= 0.0 or end_frequency_hz <= 0.0:
        raise ValueError("Log-chirp frequencies must be positive")
    frequency_min = min(start_frequency_hz, end_frequency_hz)
    frequency_max = max(start_frequency_hz, end_frequency_hz)
    frequency_log_span = math.log(frequency_max / frequency_min)
    sweep_log_ratio = math.log(end_frequency_hz / start_frequency_hz)
    count = _sample_count(duration_s, sample_rate_hz)
    values: List[float] = []
    for index in range(count):
        t_s = index / sample_rate_hz
        instantaneous_frequency_hz = start_frequency_hz * math.exp(
            sweep_log_ratio * t_s / duration_s
        )
        amplitude_fraction = (
            math.log(instantaneous_frequency_hz / frequency_min)
            / frequency_log_span
        )
        amplitude_rad = low_frequency_amplitude_rad + amplitude_fraction * (
            high_frequency_amplitude_rad - low_frequency_amplitude_rad
        )
        phase = (
            2.0
            * math.pi
            * start_frequency_hz
            * duration_s
            / sweep_log_ratio
            * (math.exp(sweep_log_ratio * t_s / duration_s) - 1.0)
        )
        values.append(
            amplitude_rad
            * _cosine_envelope(t_s, duration_s, ramp_s)
            * math.sin(phase)
        )
    return values


def _sine_segment(
    frequency_hz: float,
    amplitude_rad: float,
    duration_s: float,
    sample_rate_hz: float,
    ramp_s: float,
) -> List[float]:
    count = _sample_count(duration_s, sample_rate_hz)
    return [
        amplitude_rad
        * _cosine_envelope(index / sample_rate_hz, duration_s, ramp_s)
        * math.sin(2.0 * math.pi * frequency_hz * index / sample_rate_hz)
        for index in range(count)
    ]


def _normalized_sine_segment(
    frequency_hz: float,
    amplitude_rad: float,
    duration_s: float,
    sample_rate_hz: float,
    ramp_s: float,
) -> List[float]:
    """Generate a sampled sine whose discrete peak equals the requested amplitude."""

    values = _sine_segment(
        frequency_hz,
        amplitude_rad,
        duration_s,
        sample_rate_hz,
        ramp_s,
    )
    sampled_peak = max((abs(value) for value in values), default=0.0)
    if sampled_peak <= 0.0:
        raise ValueError("Generated sine segment has zero peak")
    scale = amplitude_rad / sampled_peak
    return [value * scale for value in values]


def _multisine(
    frequencies_hz: Sequence[float],
    peak_rad: float,
    period_s: float,
    repeats: int,
    sample_rate_hz: float,
) -> Tuple[List[float], List[float]]:
    if repeats <= 0:
        raise ValueError("Multisine repeats must be positive")
    samples_per_period = _sample_count(period_s, sample_rate_hz)
    tone_count = len(frequencies_hz)
    if tone_count == 0:
        raise ValueError("A multisine requires at least one tone")

    phases = [
        -math.pi * tone_index * (tone_index - 1) / tone_count
        for tone_index in range(tone_count)
    ]
    one_period: List[float] = []
    for index in range(samples_per_period):
        t_s = index / sample_rate_hz
        value = sum(
            math.sin(2.0 * math.pi * frequency_hz * t_s + phase)
            for frequency_hz, phase in zip(frequencies_hz, phases)
        )
        one_period.append(value)

    raw_peak = max(abs(value) for value in one_period)
    if raw_peak <= 0.0:
        raise ValueError("Generated multisine has zero peak")
    scale = peak_rad / raw_peak
    one_period = [value * scale for value in one_period]
    return one_period * repeats, phases


def _rounded_triangle(
    amplitude_rad: float,
    frequency_hz: float,
    cycles: int,
    sample_rate_hz: float,
) -> List[float]:
    duration_s = cycles / frequency_hz
    count = _sample_count(duration_s, sample_rate_hz)
    values: List[float] = []
    for index in range(count):
        phase = 2.0 * math.pi * frequency_hz * index / sample_rate_hz
        values.append(2.0 * amplitude_rad / math.pi * math.asin(math.sin(phase)))
    return values


def _multiscale_smooth_steps(
    sample_rate_hz: float,
) -> Tuple[List[float], List[Dict[str, float]]]:
    cases = ((0.25, 0.80), (0.50, 0.40), (1.00, 0.25))
    hold_duration_s = 1.0
    repeats_per_direction = 2
    values: List[float] = []
    metadata: List[Dict[str, float]] = []
    current = 0.0
    for amplitude_rad, transition_duration_s in cases:
        for _ in range(repeats_per_direction):
            for level in (amplitude_rad, 0.0, -amplitude_rad, 0.0):
                values.extend(
                    _minimum_jerk_move_values(
                        current,
                        level,
                        transition_duration_s,
                        sample_rate_hz,
                    )
                )
                values.extend(_repeat(level, hold_duration_s, sample_rate_hz))
                current = level
        metadata.append(
            {
                "amplitude_rad": amplitude_rad,
                "transition_duration_s": transition_duration_s,
                "hold_duration_s": hold_duration_s,
                "repeats_per_direction": repeats_per_direction,
            }
        )
    return values, metadata


def _trapezoidal_move(
    start: float,
    end: float,
    max_velocity: float,
    acceleration: float,
    sample_rate_hz: float,
) -> List[float]:
    distance = abs(end - start)
    if distance <= 0.0:
        return [start]
    if max_velocity <= 0.0 or acceleration <= 0.0:
        raise ValueError("Velocity and acceleration must be positive")

    t_accel = max_velocity / acceleration
    accel_distance = 0.5 * acceleration * t_accel**2
    if 2.0 * accel_distance > distance:
        t_accel = math.sqrt(distance / acceleration)
        peak_velocity = acceleration * t_accel
        t_flat = 0.0
        accel_distance = 0.5 * acceleration * t_accel**2
    else:
        peak_velocity = max_velocity
        t_flat = (distance - 2.0 * accel_distance) / peak_velocity

    total_s = 2.0 * t_accel + t_flat
    count = max(2, _sample_count(total_s, sample_rate_hz) + 1)
    direction = 1.0 if end > start else -1.0
    values: List[float] = []
    for index in range(count):
        t_s = min(total_s, index / sample_rate_hz)
        if t_s < t_accel:
            traveled = 0.5 * acceleration * t_s**2
        elif t_s < t_accel + t_flat:
            traveled = accel_distance + peak_velocity * (t_s - t_accel)
        else:
            remaining = max(0.0, total_s - t_s)
            traveled = distance - 0.5 * acceleration * remaining**2
        values.append(start + direction * traveled)
    values[-1] = end
    return values


def _wide_constant_velocity_suite(
    sample_rate_hz: float,
) -> Tuple[List[float], List[Dict[str, float]]]:
    """Build bounded round trips with at least five steady seconds per direction."""

    amplitude_rad = 1.0
    acceleration_rad_s2 = 40.0
    requested_velocities_rad_s = (0.10, 0.25, 0.50, 1.0, 2.0, 4.0)
    required_steady_duration_s = 5.0
    steady_duration_guard_s = 0.25
    edge_hold_duration_s = 0.10
    values: List[float] = []
    metadata: List[Dict[str, float]] = []

    values.extend(
        _minimum_jerk_values(0.0, -amplitude_rad, 1.0, sample_rate_hz)
    )
    values.extend(_repeat(-amplitude_rad, edge_hold_duration_s, sample_rate_hz))
    distance_rad = 2.0 * amplitude_rad
    for velocity_rad_s in requested_velocities_rad_s:
        acceleration_time_s = velocity_rad_s / acceleration_rad_s2
        steady_time_per_move_s = (
            distance_rad / velocity_rad_s - acceleration_time_s
        )
        if steady_time_per_move_s <= 0.0:
            raise ValueError("R05 has no constant-velocity portion")
        repeats = math.ceil(
            (required_steady_duration_s + steady_duration_guard_s)
            / steady_time_per_move_s
        )
        for _ in range(repeats):
            values.extend(
                _trapezoidal_move(
                    -amplitude_rad,
                    amplitude_rad,
                    velocity_rad_s,
                    acceleration_rad_s2,
                    sample_rate_hz,
                )
            )
            values.extend(
                _repeat(amplitude_rad, edge_hold_duration_s, sample_rate_hz)
            )
            values.extend(
                _trapezoidal_move(
                    amplitude_rad,
                    -amplitude_rad,
                    velocity_rad_s,
                    acceleration_rad_s2,
                    sample_rate_hz,
                )
            )
            values.extend(
                _repeat(-amplitude_rad, edge_hold_duration_s, sample_rate_hz)
            )
        metadata.append(
            {
                "amplitude_rad": amplitude_rad,
                "requested_velocity_rad_s": velocity_rad_s,
                "acceleration_rad_s2": acceleration_rad_s2,
                "round_trip_repeats": repeats,
                "steady_time_per_move_s": steady_time_per_move_s,
                "cumulative_steady_time_per_direction_s": (
                    repeats * steady_time_per_move_s
                ),
            }
        )
    values.extend(
        _minimum_jerk_values(-amplitude_rad, 0.0, 1.0, sample_rate_hz)
    )
    return values, metadata


def _wide_acceleration_suite(
    sample_rate_hz: float,
) -> Tuple[List[float], List[Dict[str, float]]]:
    amplitude_rad = 0.80
    move_durations_s = (1.60, 0.80, 0.55, 0.40)
    repeats_per_direction = 3
    edge_hold_duration_s = 0.20
    values: List[float] = []
    metadata: List[Dict[str, float]] = []
    values.extend(
        _minimum_jerk_values(0.0, -amplitude_rad, 1.0, sample_rate_hz)
    )
    for duration_s in move_durations_s:
        for _ in range(repeats_per_direction):
            values.extend(
                _minimum_jerk_move_values(
                    -amplitude_rad,
                    amplitude_rad,
                    duration_s,
                    sample_rate_hz,
                )
            )
            values.extend(_repeat(amplitude_rad, edge_hold_duration_s, sample_rate_hz))
            values.extend(
                _minimum_jerk_move_values(
                    amplitude_rad,
                    -amplitude_rad,
                    duration_s,
                    sample_rate_hz,
                )
            )
            values.extend(_repeat(-amplitude_rad, edge_hold_duration_s, sample_rate_hz))
        metadata.append(
            {
                "amplitude_rad": amplitude_rad,
                "move_duration_s": duration_s,
                "repeats_per_direction": repeats_per_direction,
                "edge_hold_duration_s": edge_hold_duration_s,
            }
        )
    values.extend(
        _minimum_jerk_values(-amplitude_rad, 0.0, 1.0, sample_rate_hz)
    )
    return values, metadata


def _filtered_binary_sequence(
    amplitude_rad: float,
    duration_s: float,
    bit_period_s: float,
    cutoff_hz: float,
    sample_rate_hz: float,
    seed: int,
) -> List[float]:
    rng = random.Random(seed)
    count = _sample_count(duration_s, sample_rate_hz)
    bit_samples = max(1, _sample_count(bit_period_s, sample_rate_hz))
    # Two cascaded first-order stages make the position and velocity continuous.
    # Raising each stage cutoff preserves the requested -3 dB cutoff overall.
    stage_cutoff_hz = cutoff_hz * math.sqrt(math.sqrt(2.0) + 1.0)
    alpha = 1.0 - math.exp(-2.0 * math.pi * stage_cutoff_hz / sample_rate_hz)
    stage_one = 0.0
    stage_two = 0.0
    target = 0.0
    result: List[float] = []
    for index in range(count):
        if index % bit_samples == 0:
            target = amplitude_rad if rng.getrandbits(1) else -amplitude_rad
        stage_one += alpha * (target - stage_one)
        stage_two += alpha * (stage_one - stage_two)
        t_s = index / sample_rate_hz
        result.append(stage_two * _cosine_envelope(t_s, duration_s, 1.0))
    return result


def _micro_sine_suite(sample_rate_hz: float) -> Tuple[List[float], List[Dict[str, float]]]:
    cases = ((0.010, 0.10), (0.030, 0.20), (0.060, 0.40))
    values: List[float] = []
    metadata: List[Dict[str, float]] = []
    for amplitude, frequency in cases:
        duration_s = 20.0
        values.extend(
            _sine_segment(
                frequency,
                amplitude,
                duration_s,
                sample_rate_hz,
                ramp_s=1.0,
            )
        )
        values.extend(_repeat(0.0, 0.5, sample_rate_hz))
        metadata.append(
            {
                "amplitude_rad": amplitude,
                "frequency_hz": frequency,
                "duration_s": duration_s,
            }
        )
    return values, metadata


def _validation_sine_bank(
    sample_rate_hz: float,
    max_frequency_hz: float,
) -> Tuple[List[float], List[Dict[str, float]]]:
    nominal_cases = (
        (0.15, 0.80),
        (0.35, 0.70),
        (0.70, 0.50),
        (1.10, 0.35),
        (1.70, 0.25),
        (2.30, 0.18),
        (2.90, 0.12),
    )
    cases = tuple(
        case for case in nominal_cases if case[0] <= max_frequency_hz + 1e-12
    )
    if not cases:
        raise ValueError("The maximum excitation frequency excludes the sine bank")
    values: List[float] = []
    metadata: List[Dict[str, float]] = []
    for frequency, amplitude in cases:
        duration_s = max(8.0, 5.0 / frequency)
        ramp_s = min(1.0, 0.15 * duration_s)
        values.extend(
            _normalized_sine_segment(
                frequency,
                amplitude,
                duration_s,
                sample_rate_hz,
                ramp_s,
            )
        )
        values.extend(_repeat(0.0, 0.5, sample_rate_hz))
        metadata.append(
            {
                "frequency_hz": frequency,
                "amplitude_rad": amplitude,
                "duration_s": duration_s,
            }
        )
    return values, metadata


def _smooth_clipped_sine(sample_rate_hz: float) -> List[float]:
    frequency_hz = 1.0
    raw_amplitude_rad = 0.60
    clip_rad = 0.40
    duration_s = 25.0
    count = _sample_count(duration_s, sample_rate_hz)
    values: List[float] = []
    normalization = math.tanh(raw_amplitude_rad / clip_rad)
    for index in range(count):
        t_s = index / sample_rate_hz
        raw = raw_amplitude_rad * math.sin(2.0 * math.pi * frequency_hz * t_s)
        clipped = clip_rad * math.tanh(raw / clip_rad) / normalization
        values.append(clipped * _cosine_envelope(t_s, duration_s, 1.0))
    return values


def _balance_holds(sample_rate_hz: float) -> List[float]:
    values: List[float] = []
    current = 0.0
    for level in (-0.20, 0.0, 0.20):
        values.extend(_minimum_jerk_values(current, level, 1.0, sample_rate_hz))
        values.extend(_repeat(level, 8.0, sample_rate_hz))
        current = level
    values.extend(_minimum_jerk_values(current, 0.0, 1.0, sample_rate_hz))
    return values


def _finite_difference_extrema(
    values: Sequence[float], sample_rate_hz: float
) -> Tuple[float, float]:
    if len(values) < 2:
        return 0.0, 0.0
    velocities = [
        (values[index] - values[index - 1]) * sample_rate_hz
        for index in range(1, len(values))
    ]
    accelerations = [
        (velocities[index] - velocities[index - 1]) * sample_rate_hz
        for index in range(1, len(velocities))
    ]
    max_velocity = max((abs(value) for value in velocities), default=0.0)
    max_acceleration = max((abs(value) for value in accelerations), default=0.0)
    return max_velocity, max_acceleration


def _scale_to_limits(
    values: Sequence[float],
    sample_rate_hz: float,
    max_offset_rad: float,
    max_velocity_rad_s: float,
    max_acceleration_rad_s2: float,
) -> Tuple[Tuple[float, ...], float]:
    if not values:
        raise ValueError("A trajectory cannot be empty")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("A trajectory contains a non-finite position")

    peak = max(abs(value) for value in values)
    max_velocity, max_acceleration = _finite_difference_extrema(values, sample_rate_hz)
    scales = [1.0]
    if peak > 0.0:
        scales.append(max_offset_rad / peak)
    if max_velocity > 0.0:
        scales.append(max_velocity_rad_s / max_velocity)
    if max_acceleration > 0.0:
        scales.append(max_acceleration_rad_s2 / max_acceleration)
    scale = min(scales)
    if scale <= 0.0:
        raise ValueError("Trajectory safety limits must be positive")
    return tuple(float(value * scale) for value in values), scale


def _make_trajectory(
    trajectory_id: str,
    name: str,
    purpose: str,
    split: str,
    sample_rate_hz: float,
    values: Sequence[float],
    parameters: Dict[str, Any],
    max_offset_rad: float,
    max_velocity_rad_s: float,
    max_acceleration_rad_s2: float,
    *,
    safety_profile: str = "standard",
) -> Trajectory:
    limited_values, applied_scale = _scale_to_limits(
        values,
        sample_rate_hz,
        max_offset_rad,
        max_velocity_rad_s,
        max_acceleration_rad_s2,
    )
    final_parameters = dict(parameters)
    final_parameters["safety_scale"] = applied_scale
    final_parameters["safety_profile"] = safety_profile
    final_parameters.setdefault("operating_center_offset_rad", 0.0)
    return Trajectory(
        trajectory_id=trajectory_id,
        name=name,
        purpose=purpose,
        split=split,
        sample_rate_hz=sample_rate_hz,
        q_offset_rad=limited_values,
        parameters=final_parameters,
    )


def build_default_suite(
    *,
    sample_rate_hz: float = 50.0,
    seed: int = 20260813,
    max_offset_rad: float = DEFAULT_MAX_OFFSET_RAD,
    max_velocity_rad_s: float = DEFAULT_MAX_TARGET_VELOCITY_RAD_S,
    max_acceleration_rad_s2: float = DEFAULT_MAX_TARGET_ACCELERATION_RAD_S2,
    max_excitation_frequency_hz: float = DEFAULT_MAX_EXCITATION_FREQUENCY_HZ,
) -> List[Trajectory]:
    """Build the deterministic 13-group balanced-load identification suite."""

    if sample_rate_hz <= 0.0:
        raise ValueError("sample_rate_hz must be positive")
    if min(max_offset_rad, max_velocity_rad_s, max_acceleration_rad_s2) <= 0.0:
        raise ValueError("All trajectory safety limits must be positive")
    if max_excitation_frequency_hz < 1.0:
        raise ValueError("max_excitation_frequency_hz must be at least 1.0 Hz")
    if max_excitation_frequency_hz >= 0.5 * sample_rate_hz:
        raise ValueError(
            "max_excitation_frequency_hz must be below the Nyquist frequency"
        )

    specifications: List[
        Tuple[str, str, str, str, Sequence[float], Dict[str, Any]]
    ] = []

    specifications.append(
        (
            "R01",
            "balance_holds",
            "Check balance, torque bias, and static behavior at several positions.",
            "fit",
            _balance_holds(sample_rate_hz),
            {"hold_offsets_rad": [-0.20, 0.0, 0.20], "hold_duration_s": 8.0},
        )
    )

    micro_values, micro_cases = _micro_sine_suite(sample_rate_hz)
    specifications.append(
        (
            "R02",
            "micro_sines",
            "Excite breakaway friction, dead zone, and low-amplitude tracking.",
            "fit",
            micro_values,
            {"segments": micro_cases},
        )
    )

    step_values, step_cases = _multiscale_smooth_steps(sample_rate_hz)
    specifications.append(
        (
            "R03",
            "multiscale_smooth_steps",
            "Estimate delay, effective PD behavior, and multi-scale transients.",
            "fit",
            step_values,
            {"segments": step_cases},
        )
    )
    specifications.append(
        (
            "R04",
            "rounded_triangle",
            "Excite low-speed friction, reversal behavior, and backlash.",
            "fit",
            _rounded_triangle(0.20, 0.05, 2, sample_rate_hz),
            {"amplitude_rad": 0.20, "frequency_hz": 0.05, "cycles": 2},
        )
    )

    velocity_values, velocity_cases = _wide_constant_velocity_suite(sample_rate_hz)
    specifications.append(
        (
            "R05",
            "wide_constant_velocity_round_trips",
            "Separate Coulomb, dynamic, and viscous friction over a wide speed range.",
            "fit",
            velocity_values,
            {
                "segments": velocity_cases,
                "required_steady_duration_per_direction_s": 5.0,
            },
        )
    )

    acceleration_values, acceleration_cases = _wide_acceleration_suite(sample_rate_hz)
    specifications.append(
        (
            "R06",
            "wide_minimum_jerk_acceleration_sweeps",
            "Excite armature and total reflected inertia with wide symmetric moves.",
            "fit",
            acceleration_values,
            {
                "amplitude_rad": 0.80,
                "move_durations_s": [1.60, 0.80, 0.55, 0.40],
                "repeats_per_direction": 3,
                "segments": acceleration_cases,
            },
        )
    )

    chirp_low_frequency_amplitude_rad = 0.45
    chirp_high_frequency_amplitude_rad = 0.12
    specifications.append(
        (
            "R07",
            "variable_amplitude_log_chirp_up",
            "Measure wide-amplitude broadband closed-loop dynamics with increasing frequency.",
            "fit",
            _variable_amplitude_log_chirp(
                0.1,
                max_excitation_frequency_hz,
                chirp_low_frequency_amplitude_rad,
                chirp_high_frequency_amplitude_rad,
                45.0,
                sample_rate_hz,
                2.0,
            ),
            {
                "start_frequency_hz": 0.1,
                "end_frequency_hz": max_excitation_frequency_hz,
                "duration_s": 45.0,
                "ramp_s": 2.0,
                "amplitude_envelope": {
                    "law": "linear_in_log_instantaneous_frequency",
                    "amplitude_at_0p1_hz_rad": chirp_low_frequency_amplitude_rad,
                    "amplitude_at_end_frequency_rad": chirp_high_frequency_amplitude_rad,
                },
            },
        )
    )
    specifications.append(
        (
            "R08",
            "variable_amplitude_log_chirp_down",
            "Check sweep-direction, thermal drift, and time-varying effects.",
            "fit",
            _variable_amplitude_log_chirp(
                max_excitation_frequency_hz,
                0.1,
                chirp_low_frequency_amplitude_rad,
                chirp_high_frequency_amplitude_rad,
                45.0,
                sample_rate_hz,
                2.0,
            ),
            {
                "start_frequency_hz": max_excitation_frequency_hz,
                "end_frequency_hz": 0.1,
                "duration_s": 45.0,
                "ramp_s": 2.0,
                "amplitude_envelope": {
                    "law": "linear_in_log_instantaneous_frequency",
                    "amplitude_at_0p1_hz_rad": chirp_low_frequency_amplitude_rad,
                    "amplitude_at_start_frequency_rad": chirp_high_frequency_amplitude_rad,
                },
            },
        )
    )

    nominal_multisine_frequencies = (
        0.1,
        0.2,
        0.3,
        0.5,
        0.8,
        1.2,
        1.8,
        2.5,
        3.2,
        4.0,
    )
    multisine_frequencies = tuple(
        frequency
        for frequency in nominal_multisine_frequencies
        if frequency <= max_excitation_frequency_hz + 1e-12
    )
    multisine_small, multisine_phases = _multisine(
        multisine_frequencies, 0.15, 10.0, 5, sample_rate_hz
    )
    multisine_large = [value * 3.0 for value in multisine_small]
    common_multisine_parameters = {
        "frequencies_hz": list(multisine_frequencies),
        "phases_rad": multisine_phases,
        "period_s": 10.0,
        "repeats": 5,
    }
    specifications.append(
        (
            "R09",
            "multisine_small",
            "Provide periodic broadband excitation in the medium-amplitude regime.",
            "fit",
            multisine_small,
            {**common_multisine_parameters, "requested_peak_rad": 0.15},
        )
    )
    specifications.append(
        (
            "R10",
            "multisine_large",
            "Measure amplitude-dependent nonlinearity with the exact R09 phases.",
            "fit",
            multisine_large,
            {**common_multisine_parameters, "requested_peak_rad": 0.45},
        )
    )
    specifications.append(
        (
            "R11",
            "wide_filtered_binary_sequence",
            "Excite wide-amplitude delay and broadband dynamics with smooth random switching.",
            "fit",
            _filtered_binary_sequence(0.30, 40.0, 0.20, 2.5, sample_rate_hz, seed),
            {
                "amplitude_rad": 0.30,
                "duration_s": 40.0,
                "bit_period_s": 0.20,
                "low_pass_cutoff_hz": 2.5,
                "filter_order": 2,
                "seed": seed,
            },
        )
    )

    sine_values, sine_cases = _validation_sine_bank(
        sample_rate_hz,
        max_excitation_frequency_hz,
    )
    specifications.append(
        (
            "R12",
            "held_out_sine_bank",
            "Validate frequency response at held-out frequencies and larger amplitudes.",
            "validation",
            sine_values,
            {"segments": sine_cases},
        )
    )
    specifications.append(
        (
            "R13",
            "smooth_clipped_sine",
            "Validate nonlinear and transient mismatch with a smooth clipped reference.",
            "validation",
            _smooth_clipped_sine(sample_rate_hz),
            {
                "frequency_hz": 1.0,
                "raw_amplitude_rad": 0.60,
                "clip_rad": 0.40,
                "duration_s": 25.0,
                "smoothing": "normalized_tanh",
                "max_target_acceleration_rad_s2": 50.0,
            },
        )
    )

    trajectories: List[Trajectory] = []
    for trajectory_id, name, purpose, split, values, parameters in specifications:
        trajectory_acceleration_limit = (
            min(max_acceleration_rad_s2, 50.0)
            if trajectory_id == "R13"
            else max_acceleration_rad_s2
        )
        trajectories.append(
            _make_trajectory(
                trajectory_id,
                name,
                purpose,
                split,
                sample_rate_hz,
                values,
                parameters,
                max_offset_rad,
                max_velocity_rad_s,
                trajectory_acceleration_limit,
            )
        )
    return trajectories


def trajectory_operating_center_offset(trajectory: Trajectory) -> float:
    """Return the trajectory-local operating-center offset from the run base."""

    value = float(trajectory.parameters.get("operating_center_offset_rad", 0.0))
    if not math.isfinite(value):
        raise ValueError(
            f"{trajectory.trajectory_id} has a non-finite operating-center offset"
        )
    return value


def trajectory_statistics(trajectory: Trajectory) -> Dict[str, float]:
    """Calculate discrete-time safety statistics for one trajectory."""

    max_velocity, max_acceleration = _finite_difference_extrema(
        trajectory.q_offset_rad, trajectory.sample_rate_hz
    )
    return {
        "sample_count": len(trajectory.q_offset_rad),
        "duration_s": trajectory.duration_s,
        "min_offset_rad": min(trajectory.q_offset_rad),
        "max_offset_rad": max(trajectory.q_offset_rad),
        "max_abs_offset_rad": max(abs(value) for value in trajectory.q_offset_rad),
        "max_abs_target_velocity_rad_s": max_velocity,
        "max_abs_target_acceleration_rad_s2": max_acceleration,
    }


def _trajectory_csv_bytes(trajectory: Trajectory) -> bytes:
    lines = [",".join(TRAJECTORY_CSV_FIELDS)]
    for index, value in enumerate(trajectory.q_offset_rad):
        lines.append(f"{index},{index / trajectory.sample_rate_hz:.9f},{value:.12f}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_suite(
    output_dir: Path,
    trajectories: Sequence[Trajectory],
    *,
    seed: int,
    max_offset_rad: float,
    max_velocity_rad_s: float,
    max_acceleration_rad_s2: float,
    controller_kp: float,
    controller_kd: float,
    max_excitation_frequency_hz: Optional[float] = None,
    overwrite: bool = False,
) -> Path:
    """Write trajectory CSV files and a hash-protected manifest."""

    if not trajectories:
        raise ValueError("No trajectories were provided")
    if not math.isfinite(controller_kp) or not 0.0 <= controller_kp <= 5000.0:
        raise ValueError("controller_kp must be finite and within 0..5000")
    if not math.isfinite(controller_kd) or not 0.0 <= controller_kd <= 100.0:
        raise ValueError("controller_kd must be finite and within 0..100")
    output_dir = output_dir.resolve()
    manifest_path = output_dir / "manifest.json"
    planned_paths = [
        output_dir / f"{trajectory.trajectory_id}_{trajectory.name}.csv"
        for trajectory in trajectories
    ] + [manifest_path]
    existing = [path for path in planned_paths if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Refusing to overwrite existing suite files: "
            + ", ".join(str(path) for path in existing)
        )

    stale_paths: List[Path] = []
    if overwrite and manifest_path.exists():
        try:
            previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            planned_set = {path.resolve() for path in planned_paths}
            for entry in previous_manifest.get("trajectories", []):
                previous_file = entry.get("file")
                if not isinstance(previous_file, str):
                    continue
                candidate = (output_dir / previous_file).resolve()
                if (
                    candidate.parent == output_dir
                    and candidate.suffix.lower() == ".csv"
                    and candidate not in planned_set
                    and candidate.exists()
                ):
                    stale_paths.append(candidate)
        except (json.JSONDecodeError, OSError):
            stale_paths = []

    output_dir.mkdir(parents=True, exist_ok=True)
    entries: List[Dict[str, Any]] = []
    for trajectory, csv_path in zip(trajectories, planned_paths):
        csv_bytes = _trajectory_csv_bytes(trajectory)
        csv_path.write_bytes(csv_bytes)
        entries.append(
            {
                "id": trajectory.trajectory_id,
                "name": trajectory.name,
                "purpose": trajectory.purpose,
                "split": trajectory.split,
                "file": csv_path.name,
                "sha256": _sha256_bytes(csv_bytes),
                "sample_rate_hz": trajectory.sample_rate_hz,
                "statistics": trajectory_statistics(trajectory),
                "parameters": trajectory.parameters,
            }
        )

    sample_rates = {trajectory.sample_rate_hz for trajectory in trajectories}
    if len(sample_rates) != 1:
        raise ValueError("All trajectories in a suite must use one sample rate")
    manifest = {
        "schema": SUITE_SCHEMA,
        "trajectory_count": len(trajectories),
        "sample_rate_hz": trajectories[0].sample_rate_hz,
        "control_configuration": {
            "motor_model": "RS06",
            "mode": "position",
            "kp": float(controller_kp),
            "kd": float(controller_kd),
        },
        "position_semantics": (
            "q_target = operator_base_center + "
            "trajectory.parameters.operating_center_offset_rad + q_offset_rad"
        ),
        "seed": seed,
        "generation_safety_limits": {
            "max_abs_offset_rad": max_offset_rad,
            "max_abs_target_velocity_rad_s": max_velocity_rad_s,
            "max_abs_target_acceleration_rad_s2": max_acceleration_rad_s2,
        },
        "trajectories": entries,
    }
    if max_excitation_frequency_hz is not None:
        manifest["generation_safety_limits"][
            "max_explicit_excitation_frequency_hz"
        ] = max_excitation_frequency_hz
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for stale_path in stale_paths:
        stale_path.unlink()
    return manifest_path


def _read_trajectory_csv(path: Path, sample_rate_hz: float) -> Tuple[float, ...]:
    values: List[float] = []
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if tuple(reader.fieldnames or ()) != TRAJECTORY_CSV_FIELDS:
            raise ValueError(
                f"Unexpected trajectory CSV header in {path}: {reader.fieldnames}"
            )
        for expected_index, row in enumerate(reader):
            sample_index = int(row["sample_index"])
            time_s = float(row["time_s"])
            value = float(row["q_offset_rad"])
            if sample_index != expected_index:
                raise ValueError(f"Non-contiguous sample_index in {path}")
            expected_time = expected_index / sample_rate_hz
            if not math.isclose(time_s, expected_time, rel_tol=0.0, abs_tol=5e-9):
                raise ValueError(
                    f"Unexpected time_s at sample {expected_index} in {path}: {time_s}"
                )
            if not math.isfinite(value):
                raise ValueError(f"Non-finite q_offset_rad in {path}")
            values.append(value)
    if not values:
        raise ValueError(f"Trajectory CSV is empty: {path}")
    return tuple(values)


def load_suite(
    manifest_path: Path,
    selected_ids: Optional[Iterable[str]] = None,
) -> Tuple[Dict[str, Any], List[Trajectory]]:
    """Load a suite, verify all hashes, and optionally select trajectory IDs."""

    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SUITE_SCHEMA:
        raise ValueError(
            f"Unsupported trajectory manifest schema: {manifest.get('schema')!r}"
        )
    entries = manifest.get("trajectories")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Manifest trajectories must be a non-empty list")
    try:
        trajectory_count = int(manifest["trajectory_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Manifest trajectory_count is invalid") from exc
    if trajectory_count != len(entries):
        raise ValueError(
            f"Manifest trajectory_count is {trajectory_count}, but it contains "
            f"{len(entries)} entries"
        )
    control_configuration = manifest.get("control_configuration")
    if not isinstance(control_configuration, dict):
        raise ValueError("Manifest is missing control_configuration")
    if control_configuration.get("motor_model") != "RS06":
        raise ValueError("Manifest control_configuration.motor_model must be RS06")
    if control_configuration.get("mode") != "position":
        raise ValueError("Manifest control_configuration.mode must be position")
    gain_limits = {"kp": (0.0, 5000.0), "kd": (0.0, 100.0)}
    for gain_name, (gain_min, gain_max) in gain_limits.items():
        try:
            gain_value = float(control_configuration[gain_name])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Manifest control_configuration.{gain_name} is invalid"
            ) from exc
        if not math.isfinite(gain_value):
            raise ValueError(
                f"Manifest control_configuration.{gain_name} must be finite"
            )
        if not gain_min <= gain_value <= gain_max:
            raise ValueError(
                f"Manifest control_configuration.{gain_name} must be within "
                f"{gain_min:g}..{gain_max:g}"
            )
        control_configuration[gain_name] = gain_value
    try:
        sample_rate_hz = float(manifest["sample_rate_hz"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Manifest sample_rate_hz is invalid") from exc
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("Manifest sample_rate_hz must be finite and positive")
    wanted = None if selected_ids is None else {value.upper() for value in selected_ids}
    trajectories: List[Trajectory] = []
    seen_ids = set()
    for entry in entries:
        trajectory_id = str(entry["id"]).upper()
        if trajectory_id in seen_ids:
            raise ValueError(f"Duplicate trajectory ID in manifest: {trajectory_id}")
        seen_ids.add(trajectory_id)
        if wanted is not None and trajectory_id not in wanted:
            continue
        entry_sample_rate_hz = float(entry.get("sample_rate_hz", sample_rate_hz))
        if not math.isclose(
            entry_sample_rate_hz,
            sample_rate_hz,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                f"{trajectory_id} sample rate does not match the manifest"
            )
        csv_path = manifest_path.parent / entry["file"]
        csv_bytes = csv_path.read_bytes()
        actual_sha256 = _sha256_bytes(csv_bytes)
        if actual_sha256 != entry["sha256"]:
            raise ValueError(
                f"Trajectory hash mismatch for {csv_path}: "
                f"expected {entry['sha256']}, got {actual_sha256}"
            )
        values = _read_trajectory_csv(csv_path, sample_rate_hz)
        trajectories.append(
            Trajectory(
                trajectory_id=trajectory_id,
                name=str(entry["name"]),
                purpose=str(entry["purpose"]),
                split=str(entry["split"]),
                sample_rate_hz=sample_rate_hz,
                q_offset_rad=values,
                parameters=dict(entry.get("parameters", {})),
            )
        )
    if wanted is not None:
        missing = wanted - seen_ids
        if missing:
            raise ValueError(
                "Requested trajectory IDs are missing from the manifest: "
                + ", ".join(sorted(missing))
            )
    if not trajectories:
        raise ValueError("No trajectories were selected")
    return manifest, trajectories
