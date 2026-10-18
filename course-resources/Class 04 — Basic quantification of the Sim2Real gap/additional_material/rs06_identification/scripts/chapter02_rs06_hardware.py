#!/usr/bin/env python3
"""Chapter 2 P01--P07 trajectories and RS06 hardware dataset packaging.

The trajectory builder reproduces the definitions shipped in the Chapter 2
simulation package, then samples them on a declared hardware command grid. The
dataset exporter preserves the RS06 runner's raw records and produces a
Chapter-2-style contract, manifest, complete-episode CSVs, summary, compact
NPZ archive, hashes, and verification report.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
ROOT_SCRIPTS = ROOT / "scripts"
if str(ROOT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ROOT_SCRIPTS))

from motor_identification_trajectories import (
    Trajectory,
    trajectory_statistics,
    write_suite,
)


HARDWARE_SCHEMA_VERSION = "phyintel-chapter02-rs06-hardware-v1"
REFERENCE_PROFILE_IDS = (
    "P01_slow_triangle",
    "P02_multisine",
    "P03_smooth_levels",
    "P04_chirp",
    "P05_wide_sine",
    "P06_heldout_composite",
    "P07_heldout_sine_hold",
)
TRAJECTORY_ID_BY_PROFILE = {
    profile_id: profile_id.split("_", 1)[0]
    for profile_id in REFERENCE_PROFILE_IDS
}
PROFILE_BY_TRAJECTORY_ID = {
    value: key for key, value in TRAJECTORY_ID_BY_PROFILE.items()
}

HARDWARE_NUMERIC_FIELDS: Tuple[str, ...] = (
    "time_s",
    "t_command_s",
    "t_state_s",
    "position_cmd_rad",
    "position_transmitted_rad",
    "position_applied_rad",
    "position_acknowledged_rad",
    "position_meas_rad",
    "velocity_meas_rad_s",
    "torque_feedback_Nm",
    "tracking_error_command_rad",
    "tracking_error_acknowledged_rad",
    "command_saturated",
    "target_matches_current_command",
    "echo_delay_steps",
    "loop_dt_s",
    "schedule_lateness_s",
    "feedback_gap_s",
    "valid",
)

HARDWARE_BOOLEAN_FIELDS = {
    "command_saturated",
    "target_matches_current_command",
    "valid",
}

EPISODE_METADATA_FIELDS: Tuple[str, ...] = (
    "episode_id",
    "split",
    "controller_id",
    "fixture_id",
    "profile_id",
    "run_id",
    "sequence_id",
    "host_time_utc",
)

SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write stable, human-readable JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_identifier(name: str, value: str) -> str:
    """Validate an identifier before using it in evidence paths and IDs."""

    if not SAFE_ID_PATTERN.fullmatch(value):
        raise ValueError(
            f"{name} must match {SAFE_ID_PATTERN.pattern!r}; got {value!r}"
        )
    return value


def _finite_positive(name: str, value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def load_reference_contract(path: Path) -> Dict[str, Any]:
    """Load and minimally validate the downloaded Chapter 2 contract."""

    contract = json.loads(path.read_text(encoding="utf-8"))
    profiles = contract.get("profiles")
    if not isinstance(profiles, dict):
        raise ValueError("Reference contract is missing profiles")
    missing = [profile_id for profile_id in REFERENCE_PROFILE_IDS if profile_id not in profiles]
    if missing:
        raise ValueError(
            "Reference contract is missing required profiles: " + ", ".join(missing)
        )
    return contract


def _inclusive_periodic_times(duration_s: float, sample_rate_hz: float) -> List[float]:
    count = int(round(duration_s * sample_rate_hz)) + 1
    return [index / sample_rate_hz for index in range(count)]


def _p03_times(
    profile: Mapping[str, Any], sample_rate_hz: float, speed_scale: float
) -> List[float]:
    levels = profile["levels_rad"]
    duration_s = len(levels) * float(profile["hold_s"]) + (
        len(levels) - 1
    ) * float(profile["transition_s"])
    # P03 in the reference generator is a half-open sampled record. At 100 Hz
    # it contains 755 samples at t=0.00...7.54 s. Sampling the same continuous
    # schedule at 50 Hz therefore contains 378 samples at t=0.00...7.54 s.
    count = int(math.ceil(duration_s / speed_scale * sample_rate_hz - 1e-12))
    return [index / sample_rate_hz for index in range(count)]


def _smooth_levels_value(profile: Mapping[str, Any], time_s: float) -> float:
    levels = [float(value) for value in profile["levels_rad"]]
    hold_s = float(profile["hold_s"])
    transition_s = float(profile["transition_s"])
    if time_s < hold_s:
        return levels[0]
    cursor = hold_s
    for start, stop in zip(levels, levels[1:]):
        transition_stop = cursor + transition_s
        if time_s < transition_stop:
            phase = max(0.0, min(1.0, (time_s - cursor) / transition_s))
            blend = 0.5 - 0.5 * math.cos(math.pi * phase)
            return start + (stop - start) * blend
        cursor = transition_stop
        hold_stop = cursor + hold_s
        if time_s < hold_stop:
            return stop
        cursor = hold_stop
    return levels[-1]


def _profile_values(
    profile_id: str,
    profile: Mapping[str, Any],
    sample_rate_hz: float,
    speed_scale: float,
) -> Tuple[List[float], List[float]]:
    kind = profile["kind"]
    if kind == "smooth_levels":
        times = _p03_times(profile, sample_rate_hz, speed_scale)
    else:
        times = _inclusive_periodic_times(
            float(profile["duration_s"]) / speed_scale, sample_rate_hz
        )
    reference_times = [time_s * speed_scale for time_s in times]

    if kind == "triangle":
        frequency_hz = float(profile["frequency_hz"])
        center_rad = float(profile["center_rad"])
        amplitude_rad = float(profile["amplitude_rad"])
        values = [
            center_rad
            + amplitude_rad
            * (2.0 / math.pi)
            * math.asin(math.sin(2.0 * math.pi * frequency_hz * time_s))
            for time_s in reference_times
        ]
        return times, values
    if kind == "multisine":
        center_rad = float(profile["center_rad"])
        values = []
        for time_s in reference_times:
            command = center_rad
            for amplitude, frequency, phase in zip(
                profile["amplitudes_rad"],
                profile["frequencies_hz"],
                profile["phases_rad"],
            ):
                command += float(amplitude) * math.sin(
                    2.0 * math.pi * float(frequency) * time_s + float(phase)
                )
            values.append(command)
        return times, values
    if kind == "smooth_levels":
        return times, [
            _smooth_levels_value(profile, time_s) for time_s in reference_times
        ]
    if kind == "chirp":
        duration_s = float(profile["duration_s"])
        start_hz = float(profile["start_frequency_hz"])
        stop_hz = float(profile["end_frequency_hz"])
        center_rad = float(profile["center_rad"])
        amplitude_rad = float(profile["amplitude_rad"])
        values = [
            center_rad
            + amplitude_rad
            * math.sin(
                2.0
                * math.pi
                * (
                    start_hz * time_s
                    + 0.5 * (stop_hz - start_hz) / duration_s * time_s**2
                )
            )
            for time_s in reference_times
        ]
        return times, values
    if kind == "sine":
        center_rad = float(profile["center_rad"])
        amplitude_rad = float(profile["amplitude_rad"])
        frequency_hz = float(profile["frequency_hz"])
        return times, [
            center_rad
            + amplitude_rad * math.sin(2.0 * math.pi * frequency_hz * time_s)
            for time_s in reference_times
        ]
    if kind == "composite":
        amplitudes = [float(value) for value in profile["amplitudes_rad"]]
        frequencies = [float(value) for value in profile["frequencies_hz"]]
        phases = [float(value) for value in profile["phases_rad"]]
        offsets = [float(value) for value in profile["center_offsets_rad"]]
        switches = [float(value) for value in profile["switch_times_s"]]
        values = []
        for time_s in reference_times:
            command = sum(
                amplitude * math.sin(2.0 * math.pi * frequency * time_s + phase)
                for amplitude, frequency, phase in zip(
                    amplitudes, frequencies, phases
                )
            )
            if time_s < switches[0]:
                command += offsets[0]
            elif time_s < switches[1]:
                command += offsets[1]
            else:
                command += offsets[2]
            values.append(command)
        return times, values
    if kind == "sine_hold":
        active_s = float(profile["active_duration_s"])
        transition_s = float(profile["transition_s"])
        center_rad = float(profile["center_rad"])
        amplitude_rad = float(profile["amplitude_rad"])
        frequency_hz = float(profile["frequency_hz"])
        hold_rad = float(profile["hold_position_rad"])
        transition_start = center_rad + amplitude_rad * math.sin(
            2.0 * math.pi * frequency_hz * active_s
        )
        values = []
        for time_s in reference_times:
            if time_s < active_s:
                value = center_rad + amplitude_rad * math.sin(
                    2.0 * math.pi * frequency_hz * time_s
                )
            elif time_s < active_s + transition_s:
                phase = (time_s - active_s) / transition_s
                blend = 0.5 - 0.5 * math.cos(math.pi * phase)
                value = transition_start + (hold_rad - transition_start) * blend
            else:
                value = hold_rad
            values.append(value)
        return times, values
    raise ValueError(f"Unsupported Chapter 2 profile kind for {profile_id}: {kind!r}")


def _profile_max_frequency_hz(profile: Mapping[str, Any]) -> float:
    """Return the highest explicitly declared sinusoidal frequency."""

    kind = profile["kind"]
    if kind in {"triangle", "sine", "sine_hold"}:
        return float(profile["frequency_hz"])
    if kind in {"multisine", "composite"}:
        return max(float(value) for value in profile["frequencies_hz"])
    if kind == "chirp":
        return max(
            float(profile["start_frequency_hz"]),
            float(profile["end_frequency_hz"]),
        )
    if kind == "smooth_levels":
        return 0.0
    raise ValueError(f"Unsupported Chapter 2 profile kind: {kind!r}")


def build_chapter02_trajectories(
    reference_contract: Mapping[str, Any],
    *,
    sample_rate_hz: float = 50.0,
    amplitude_scales: Optional[Mapping[str, float]] = None,
    speed_scales: Optional[Mapping[str, float]] = None,
) -> List[Trajectory]:
    """Build deterministic, center-relative RS06 P01--P07 trajectories."""

    sample_rate_hz = _finite_positive("sample_rate_hz", sample_rate_hz)
    requested_scales = dict(amplitude_scales or {})
    unknown = set(requested_scales) - set(REFERENCE_PROFILE_IDS)
    if unknown:
        raise ValueError("Unknown amplitude scale profiles: " + ", ".join(sorted(unknown)))
    requested_speed_scales = dict(speed_scales or {})
    unknown_speed = set(requested_speed_scales) - set(REFERENCE_PROFILE_IDS)
    if unknown_speed:
        raise ValueError(
            "Unknown speed scale profiles: " + ", ".join(sorted(unknown_speed))
        )

    trajectories: List[Trajectory] = []
    for profile_id in REFERENCE_PROFILE_IDS:
        profile = dict(reference_contract["profiles"][profile_id])
        scale = _finite_positive(
            f"amplitude_scales[{profile_id}]", requested_scales.get(profile_id, 1.0)
        )
        speed_scale = _finite_positive(
            f"speed_scales[{profile_id}]",
            requested_speed_scales.get(profile_id, 1.0),
        )
        scaled_max_frequency_hz = _profile_max_frequency_hz(profile) * speed_scale
        if scaled_max_frequency_hz >= 0.5 * sample_rate_hz:
            raise ValueError(
                f"{profile_id} scaled frequency {scaled_max_frequency_hz:.9g} Hz "
                f"must remain below the {0.5 * sample_rate_hz:.9g} Hz Nyquist limit"
            )
        _, base_values = _profile_values(
            profile_id, profile, sample_rate_hz, speed_scale
        )
        center_rad = float(profile.get("center_rad", 0.0))
        # Scale dynamic excursion around the declared center where one exists.
        # P06 has piecewise centers, so its complete center-relative command is
        # scaled around zero, including its deliberately abrupt center changes.
        scaled_values = tuple(
            center_rad + scale * (value - center_rad) for value in base_values
        )
        trajectory_id = TRAJECTORY_ID_BY_PROFILE[profile_id]
        trajectories.append(
            Trajectory(
                trajectory_id=trajectory_id,
                name=profile_id.split("_", 1)[1],
                purpose=str(profile["purpose"]),
                split=str(profile["split"]),
                sample_rate_hz=sample_rate_hz,
                q_offset_rad=scaled_values,
                parameters={
                    "chapter_profile_id": profile_id,
                    "reference_definition": profile,
                    "amplitude_scale": scale,
                    "speed_scale": speed_scale,
                    "scaled_max_explicit_frequency_hz": scaled_max_frequency_hz,
                    "operating_center_offset_rad": 0.0,
                    "sampling_semantics": (
                        "P03 is half-open like the reference generator; all other "
                        "profiles use an endpoint-inclusive sampled duration"
                    ),
                    "time_transform": "reference_time_s = speed_scale * time_s",
                    "contains_declared_position_steps": profile["kind"] == "composite",
                },
            )
        )
    return trajectories


def validate_trajectory_limits(
    trajectories: Sequence[Trajectory],
    *,
    max_offset_rad: float,
    max_velocity_rad_s: float,
    max_acceleration_rad_s2: float,
) -> None:
    """Reject, rather than silently rescale, a trajectory outside declared limits."""

    limits = {
        "max_abs_offset_rad": _finite_positive("max_offset_rad", max_offset_rad),
        "max_abs_target_velocity_rad_s": _finite_positive(
            "max_velocity_rad_s", max_velocity_rad_s
        ),
        "max_abs_target_acceleration_rad_s2": _finite_positive(
            "max_acceleration_rad_s2", max_acceleration_rad_s2
        ),
    }
    for trajectory in trajectories:
        statistics = trajectory_statistics(trajectory)
        for statistic_name, limit in limits.items():
            observed = float(statistics[statistic_name])
            if observed > limit + 1e-12:
                raise ValueError(
                    f"{trajectory.trajectory_id} {statistic_name}={observed:.9g} "
                    f"exceeds the declared limit {limit:.9g}; reduce its amplitude "
                    "scale or explicitly increase the reviewed generation limit"
                )


def write_chapter02_trajectory_suite(
    output_dir: Path,
    trajectories: Sequence[Trajectory],
    *,
    reference_contract_path: Path,
    reference_generator_path: Path,
    controller_id: str,
    controller_kp: float,
    controller_kd: float,
    max_offset_rad: float,
    max_velocity_rad_s: float,
    max_acceleration_rad_s2: float,
    overwrite: bool = False,
) -> Path:
    """Write the RS06 suite and bind it to the downloaded source definition."""

    controller_id = validate_identifier("controller_id", controller_id)
    validate_trajectory_limits(
        trajectories,
        max_offset_rad=max_offset_rad,
        max_velocity_rad_s=max_velocity_rad_s,
        max_acceleration_rad_s2=max_acceleration_rad_s2,
    )
    output_dir = output_dir.resolve()
    source_dir = output_dir / "source-definition"
    copied_contract_path = source_dir / "experiment-contract.json"
    copied_generator_path = source_dir / "generate_chapter02_dataset.py"
    existing_sources = [
        path
        for path in (copied_contract_path, copied_generator_path)
        if path.exists()
    ]
    if existing_sources and not overwrite:
        raise FileExistsError(
            "Refusing to overwrite copied source-definition files: "
            + ", ".join(str(path) for path in existing_sources)
        )
    manifest_path = write_suite(
        output_dir,
        trajectories,
        seed=330288,
        max_offset_rad=max_offset_rad,
        max_velocity_rad_s=max_velocity_rad_s,
        max_acceleration_rad_s2=max_acceleration_rad_s2,
        controller_kp=controller_kp,
        controller_kd=controller_kd,
        max_excitation_frequency_hz=max(
            float(trajectory.parameters["scaled_max_explicit_frequency_hz"])
            for trajectory in trajectories
        ),
        overwrite=overwrite,
    )
    source_dir.mkdir(parents=True, exist_ok=True)
    copied_contract_path.write_bytes(reference_contract_path.read_bytes())
    copied_generator_path.write_bytes(reference_generator_path.read_bytes())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["control_configuration"]["controller_id"] = controller_id
    manifest["chapter02"] = {
        "source_schema_version": "phyintel-chapter02-rs06-sim-position-data-v1",
        "source_contract_file": str(copied_contract_path.relative_to(output_dir)),
        "source_contract_sha256": sha256_file(reference_contract_path),
        "source_generator_file": str(copied_generator_path.relative_to(output_dir)),
        "source_generator_sha256": sha256_file(reference_generator_path),
        "hardware_resampling": {
            "sample_rate_hz": trajectories[0].sample_rate_hz,
            "position_semantics": "center-relative position command in rad",
            "amplitude_transform": (
                "q_scaled = declared_center + amplitude_scale * "
                "(q_reference - declared_center)"
            ),
            "time_transform": "reference_time_s = speed_scale * time_s",
        },
        "profiles": {
            trajectory.parameters["chapter_profile_id"]: {
                "trajectory_id": trajectory.trajectory_id,
                "amplitude_scale": trajectory.parameters["amplitude_scale"],
                "speed_scale": trajectory.parameters["speed_scale"],
                "reference_definition": trajectory.parameters["reference_definition"],
                "statistics": trajectory_statistics(trajectory),
            }
            for trajectory in trajectories
        },
    }
    write_json(manifest_path, manifest)
    return manifest_path


def _float(row: Mapping[str, str], field: str) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Raw session field {field!r} is missing or invalid") from exc
    if not math.isfinite(value):
        raise ValueError(f"Raw session field {field!r} is non-finite")
    return value


def _int(row: Mapping[str, str], field: str) -> int:
    try:
        return int(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Raw session field {field!r} is missing or invalid") from exc


def _rmse(values: Iterable[float]) -> float:
    numbers = list(values)
    if not numbers:
        return math.nan
    return math.sqrt(sum(value * value for value in numbers) / len(numbers))


def _strictly_nondecreasing(values: Sequence[float]) -> bool:
    return all(current >= previous for previous, current in zip(values, values[1:]))


def _write_episode_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open("wb") as raw_handle,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as compressed,
        io.TextIOWrapper(compressed, encoding="utf-8", newline="") as handle,
    ):
        writer = csv.DictWriter(
            handle,
            fieldnames=[*EPISODE_METADATA_FIELDS, *HARDWARE_NUMERIC_FIELDS],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_deterministic_npz(
    path: Path, arrays: Mapping[str, np.ndarray]
) -> None:
    """Write an NPZ with fixed entry timestamps so equal arrays hash equally."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, array in arrays.items():
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, np.asarray(array), allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, buffer.getvalue())


def _normalise_raw_rows(
    raw_rows: Sequence[Mapping[str, str]],
    *,
    trajectory: Trajectory,
    episode_id: str,
    run_id: str,
    fixture_id: str,
    controller_id: str,
    episode_complete: bool,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    profile_id = str(trajectory.parameters["chapter_profile_id"])
    expected_samples = len(trajectory.q_offset_rad)
    sequence_ids = [_int(row, "trajectory_sample_index") for row in raw_rows]
    sequence_contiguous = sequence_ids == list(range(len(raw_rows)))
    expected_count = len(raw_rows) == expected_samples
    t_commands = [_float(row, "t_send_after_s") for row in raw_rows]
    t_states = [_float(row, "t_receive_s") for row in raw_rows]
    clocks_monotonic = _strictly_nondecreasing(t_commands) and _strictly_nondecreasing(
        t_states
    )
    structurally_complete = (
        episode_complete and expected_count and sequence_contiguous and clocks_monotonic
    )

    normalised: List[Dict[str, Any]] = []
    for raw_row, sequence_id in zip(raw_rows, sequence_ids):
        echo_text = str(raw_row.get("echo_delay_steps", "")).strip()
        echo_delay = math.nan if not echo_text else float(echo_text)
        saturated = bool(_int(raw_row, "q_command_saturated"))
        echo_recognised = math.isfinite(echo_delay)
        valid = structurally_complete and not saturated and echo_recognised
        transmitted = _float(raw_row, "q_command_encoded_rad")
        normalised.append(
            {
                "episode_id": episode_id,
                "split": trajectory.split,
                "controller_id": controller_id,
                "fixture_id": fixture_id,
                "profile_id": profile_id,
                "run_id": run_id,
                "sequence_id": sequence_id,
                "host_time_utc": raw_row["host_time_utc"],
                "time_s": _float(raw_row, "t_nominal_s"),
                "t_command_s": _float(raw_row, "t_send_after_s"),
                "t_state_s": _float(raw_row, "t_receive_s"),
                "position_cmd_rad": _float(raw_row, "q_command_requested_rad"),
                "position_transmitted_rad": transmitted,
                # This compatibility field has an explicitly declared boundary
                # in experiment-contract.json; it is not inferred shaft motion.
                "position_applied_rad": transmitted,
                "position_acknowledged_rad": _float(raw_row, "target_feedback_rad"),
                "position_meas_rad": _float(raw_row, "q_feedback_rad"),
                "velocity_meas_rad_s": _float(raw_row, "qdot_feedback_rad_s"),
                "torque_feedback_Nm": _float(raw_row, "torque_feedback_nm"),
                "tracking_error_command_rad": _float(
                    raw_row, "tracking_error_command_rad"
                ),
                "tracking_error_acknowledged_rad": _float(
                    raw_row, "tracking_error_target_rad"
                ),
                "command_saturated": saturated,
                "target_matches_current_command": bool(
                    _int(raw_row, "target_matches_current_command")
                ),
                "echo_delay_steps": echo_delay,
                "loop_dt_s": _float(raw_row, "loop_dt_s"),
                "schedule_lateness_s": _float(raw_row, "schedule_lateness_s"),
                "feedback_gap_s": _float(raw_row, "feedback_gap_s"),
                "valid": valid,
            }
        )
    structure = {
        "expected_samples": expected_samples,
        "observed_samples": len(raw_rows),
        "episode_complete": structurally_complete,
        "expected_sample_count": expected_count,
        "sequence_ids_contiguous": sequence_contiguous,
        "clocks_monotonic": clocks_monotonic,
    }
    return normalised, structure


def export_chapter02_hardware_dataset(
    run_dir: Path,
    trajectory_manifest_path: Path,
    trajectory_manifest: Mapping[str, Any],
    trajectories: Sequence[Trajectory],
    *,
    run_id: str,
    fixture_id: str,
    fixture_description: str = "",
    fixture_metadata: Optional[Mapping[str, Any]] = None,
    extra_context: Optional[Mapping[str, Any]] = None,
    package_name: str = "chapter02-hardware",
    overwrite: bool = False,
) -> Path:
    """Export one RS06 run as an auditable Chapter-2-style data package."""

    run_id = validate_identifier("run_id", run_id)
    fixture_id = validate_identifier("fixture_id", fixture_id)
    validate_identifier("package_name", package_name)
    controller_id = validate_identifier(
        "controller_id",
        str(trajectory_manifest["control_configuration"].get("controller_id", "")),
    )
    if "chapter02" not in trajectory_manifest:
        raise ValueError("Trajectory manifest is not a Chapter 2 RS06 suite")

    run_dir = run_dir.resolve()
    raw_path = run_dir / "raw_session.csv"
    session_metadata_path = run_dir / "session.metadata.json"
    if not raw_path.is_file() or not session_metadata_path.is_file():
        raise FileNotFoundError(
            "Run directory must contain raw_session.csv and session.metadata.json"
        )
    session_metadata = json.loads(session_metadata_path.read_text(encoding="utf-8"))
    completed_ids = {str(value).upper() for value in session_metadata.get("completed_trajectories", [])}
    with raw_path.open("r", newline="", encoding="utf-8") as handle:
        raw_rows = list(csv.DictReader(handle))

    package_dir = run_dir / package_name
    episode_dir = package_dir / "episodes"
    planned_core = [
        package_dir / "experiment-contract.json",
        package_dir / "dataset-manifest.json",
        package_dir / "episode-summary.csv",
        package_dir / "sample-preview.csv",
        package_dir / "verification.json",
        package_dir / "chapter02-rs06-hardware-v1.npz",
    ]
    existing = [path for path in planned_core if path.exists()]
    package_has_content = package_dir.exists() and any(package_dir.iterdir())
    if (existing or package_has_content) and not overwrite:
        raise FileExistsError(
            "Refusing to overwrite existing Chapter 2 package files: "
            + ", ".join(str(path) for path in (existing or [package_dir]))
        )
    package_dir.mkdir(parents=True, exist_ok=True)
    episode_dir.mkdir(parents=True, exist_ok=True)

    source_suite_dir = trajectory_manifest_path.resolve().parent
    copied_suite_dir = package_dir / "trajectory-suite"
    copied_suite_dir.mkdir(parents=True, exist_ok=True)
    source_files = [trajectory_manifest_path.resolve()]
    source_files.extend(
        (source_suite_dir / str(entry["file"])).resolve()
        for entry in trajectory_manifest["trajectories"]
    )
    chapter_source = trajectory_manifest["chapter02"]
    source_files.extend(
        (source_suite_dir / str(chapter_source[field])).resolve()
        for field in ("source_contract_file", "source_generator_file")
    )
    for source_file in source_files:
        if not source_file.is_file():
            raise FileNotFoundError(source_file)
        try:
            relative_source = source_file.relative_to(source_suite_dir)
        except ValueError as exc:
            raise ValueError(
                f"Trajectory suite source escapes its manifest directory: {source_file}"
            ) from exc
        destination = copied_suite_dir / relative_source
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_file.read_bytes())
    copied_trajectory_manifest_path = copied_suite_dir / trajectory_manifest_path.name

    rows_by_trajectory: Dict[str, List[Mapping[str, str]]] = {
        trajectory.trajectory_id: [] for trajectory in trajectories
    }
    for row in raw_rows:
        trajectory_id = str(row.get("trajectory_id", "")).upper()
        if row.get("phase") == "trajectory" and trajectory_id in rows_by_trajectory:
            rows_by_trajectory[trajectory_id].append(row)

    release_id = f"chapter02-rs06-{run_id}"
    concatenated: Dict[str, List[np.ndarray]] = {
        field: [] for field in HARDWARE_NUMERIC_FIELDS
    }
    summaries: List[Dict[str, Any]] = []
    offsets: List[Dict[str, Any]] = []
    episode_checks: List[Dict[str, Any]] = []
    preview_rows: List[Dict[str, Any]] = []
    cursor = 0

    for trajectory in trajectories:
        profile_id = str(trajectory.parameters["chapter_profile_id"])
        episode_id = "__".join(
            [trajectory.split, controller_id, fixture_id, profile_id, run_id]
        )
        raw_episode_rows = rows_by_trajectory[trajectory.trajectory_id]
        normalised, structure = _normalise_raw_rows(
            raw_episode_rows,
            trajectory=trajectory,
            episode_id=episode_id,
            run_id=run_id,
            fixture_id=fixture_id,
            controller_id=controller_id,
            episode_complete=trajectory.trajectory_id in completed_ids,
        )
        episode_path = episode_dir / f"{episode_id}.csv.gz"
        _write_episode_csv(episode_path, normalised)
        samples = len(normalised)
        start = cursor
        stop = start + samples
        cursor = stop

        for field in HARDWARE_NUMERIC_FIELDS:
            dtype = bool if field in HARDWARE_BOOLEAN_FIELDS else float
            concatenated[field].append(
                np.asarray([row[field] for row in normalised], dtype=dtype)
            )

        time_values = [float(row["time_s"]) for row in normalised]
        command_values = [float(row["position_cmd_rad"]) for row in normalised]
        position_values = [float(row["position_meas_rad"]) for row in normalised]
        velocity_values = [float(row["velocity_meas_rad_s"]) for row in normalised]
        torque_values = [float(row["torque_feedback_Nm"]) for row in normalised]
        command_errors = [
            float(row["tracking_error_command_rad"]) for row in normalised
        ]
        valid_values = [bool(row["valid"]) for row in normalised]
        saturated_values = [bool(row["command_saturated"]) for row in normalised]
        summary = {
            "split": trajectory.split,
            "controller_id": controller_id,
            "fixture_id": fixture_id,
            "profile_id": profile_id,
            "episode_id": episode_id,
            "run_id": run_id,
            "samples": samples,
            "expected_samples": structure["expected_samples"],
            "duration_s": (
                time_values[-1] - time_values[0] if len(time_values) >= 2 else 0.0
            ),
            "episode_complete": structure["episode_complete"],
            "command_min_rad": min(command_values) if command_values else math.nan,
            "command_max_rad": max(command_values) if command_values else math.nan,
            "tracking_rmse_rad": _rmse(command_errors),
            "tracking_max_abs_rad": (
                max(map(abs, command_errors)) if command_errors else math.nan
            ),
            "command_saturation_fraction": (
                sum(saturated_values) / samples if samples else math.nan
            ),
            "valid_fraction": sum(valid_values) / samples if samples else 0.0,
            "position_min_rad": min(position_values) if position_values else math.nan,
            "position_max_rad": max(position_values) if position_values else math.nan,
            "peak_abs_velocity_rad_s": (
                max(map(abs, velocity_values)) if velocity_values else math.nan
            ),
            "peak_abs_torque_feedback_Nm": (
                max(map(abs, torque_values)) if torque_values else math.nan
            ),
            "episode_file": str(episode_path.relative_to(package_dir)),
            "episode_sha256": sha256_file(episode_path),
        }
        summaries.append(summary)
        if normalised:
            if len(normalised) <= 40:
                preview_indices = list(range(len(normalised)))
            else:
                preview_indices = [
                    round(index * (len(normalised) - 1) / 39) for index in range(40)
                ]
            preview_rows.extend(normalised[index] for index in preview_indices)
        offsets.append(
            {
                "episode_id": episode_id,
                "split": trajectory.split,
                "controller_id": controller_id,
                "fixture_id": fixture_id,
                "profile_id": profile_id,
                "run_id": run_id,
                "start": start,
                "stop": stop,
                "samples": samples,
                "episode_file": summary["episode_file"],
                "episode_sha256": summary["episode_sha256"],
            }
        )
        episode_checks.append({"episode_id": episode_id, **structure})

    arrays = {
        field: np.concatenate(parts) if parts else np.asarray([], dtype=float)
        for field, parts in concatenated.items()
    }
    npz_path = package_dir / "chapter02-rs06-hardware-v1.npz"
    _write_deterministic_npz(npz_path, arrays)

    summary_path = package_dir / "episode-summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(summaries[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(summaries)

    preview_path = package_dir / "sample-preview.csv"
    with preview_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[*EPISODE_METADATA_FIELDS, *HARDWARE_NUMERIC_FIELDS],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(preview_rows)

    fixture_record: Dict[str, Any] = {
        "description": fixture_description,
        "metadata": dict(fixture_metadata or {}),
    }
    contract = {
        "schema_version": HARDWARE_SCHEMA_VERSION,
        "release_id": release_id,
        "status": (
            "physical-hardware-evidence"
            if session_metadata.get("status") == "complete"
            else "incomplete-physical-hardware-evidence"
        ),
        "evidence_notice": (
            "RS06 position and velocity are device feedback. torque_feedback_Nm "
            "is the RS06/firmware torque estimate, not an independent calibrated "
            "shaft-torque measurement. No unavailable current, temperature, bus "
            "voltage, acceleration, or simulator-true channel is invented."
        ),
        "source_definition": trajectory_manifest["chapter02"],
        "hardware": {
            "motor_model": "RS06",
            "can_id": session_metadata.get("motor_id"),
            "controller_slot": session_metadata.get("controller_slot"),
            "protocol": session_metadata.get("protocol"),
            "sample_rate_hz": trajectory_manifest["sample_rate_hz"],
            "host_clock_boundary": (
                "t_command_s is the host monotonic timestamp immediately after "
                "serial write; t_state_s is the host receive timestamp of the "
                "complete feedback frame. The motor provides no internal timestamp."
            ),
            "position_applied_boundary": (
                "position_applied_rad equals the quantized position transmitted by "
                "the host. position_acknowledged_rad separately stores the control-"
                "box target echo; neither field is inferred shaft motion."
            ),
        },
        "controller_conditions": {
            controller_id: dict(trajectory_manifest["control_configuration"])
        },
        "fixtures": {fixture_id: fixture_record},
        "profiles": {
            str(trajectory.parameters["chapter_profile_id"]): {
                "trajectory_id": trajectory.trajectory_id,
                "split": trajectory.split,
                **dict(trajectory.parameters),
            }
            for trajectory in trajectories
        },
        "episode_matrix": [
            {
                "episode_id": offset["episode_id"],
                "profile_id": offset["profile_id"],
                "fixture_id": fixture_id,
                "controller_id": controller_id,
                "run_id": run_id,
            }
            for offset in offsets
        ],
        "field_contract": {
            "episode_metadata_fields": list(EPISODE_METADATA_FIELDS),
            "numeric_fields": list(HARDWARE_NUMERIC_FIELDS),
            "valid": (
                "true only for structurally complete episodes, unsaturated commands, "
                "and target echoes recognized within the configured command history"
            ),
        },
        "raw_source": {
            "raw_session_file": str(Path("..") / raw_path.name),
            "session_metadata_file": str(Path("..") / session_metadata_path.name),
            "trajectory_manifest_file": str(
                copied_trajectory_manifest_path.relative_to(package_dir)
            ),
        },
        "context": dict(extra_context or {}),
    }
    contract_path = package_dir / "experiment-contract.json"
    write_json(contract_path, contract)

    manifest = {
        "schema_version": HARDWARE_SCHEMA_VERSION,
        "release_id": release_id,
        "evidence_role": "physical",
        "source": "RS06 hardware through the MagicLimb control-box protocol",
        "contract_file": contract_path.name,
        "contract_sha256": sha256_file(contract_path),
        "data_file": npz_path.name,
        "data_sha256": sha256_file(npz_path),
        "episode_summary_file": summary_path.name,
        "episode_summary_sha256": sha256_file(summary_path),
        "sample_preview_file": preview_path.name,
        "sample_preview_sha256": sha256_file(preview_path),
        "raw_session_file": str(Path("..") / raw_path.name),
        "raw_session_sha256": sha256_file(raw_path),
        "session_metadata_file": str(Path("..") / session_metadata_path.name),
        "session_metadata_sha256": sha256_file(session_metadata_path),
        "trajectory_manifest_file": str(
            copied_trajectory_manifest_path.relative_to(package_dir)
        ),
        "trajectory_manifest_sha256": sha256_file(copied_trajectory_manifest_path),
        "episode_count": len(offsets),
        "sample_count": cursor,
        "numeric_fields": list(HARDWARE_NUMERIC_FIELDS),
        "episodes": offsets,
    }
    manifest_path = package_dir / "dataset-manifest.json"
    write_json(manifest_path, manifest)

    with np.load(npz_path, allow_pickle=False) as archive:
        archive_fields = set(archive.files)
        archive_lengths = {int(archive[field].shape[0]) for field in archive.files}
    checks = {
        "source_session_status_complete": session_metadata.get("status") == "complete",
        "all_selected_profiles_have_episode_rows": all(
            check["observed_samples"] > 0 for check in episode_checks
        ),
        "all_episode_sample_counts_match": all(
            check["expected_sample_count"] for check in episode_checks
        ),
        "all_episode_sequences_are_contiguous": all(
            check["sequence_ids_contiguous"] for check in episode_checks
        ),
        "all_episode_clocks_are_monotonic": all(
            check["clocks_monotonic"] for check in episode_checks
        ),
        "all_episodes_complete": all(
            check["episode_complete"] for check in episode_checks
        ),
        "no_command_saturation": not any(
            bool(value) for value in arrays["command_saturated"]
        ),
        "all_samples_valid": all(bool(value) for value in arrays["valid"]),
        "archive_fields_match_manifest": archive_fields == set(HARDWARE_NUMERIC_FIELDS),
        "archive_arrays_have_one_length": archive_lengths == {cursor},
        "archive_hash_matches_manifest": sha256_file(npz_path)
        == manifest["data_sha256"],
        "episode_hashes_match_manifest": all(
            sha256_file(package_dir / offset["episode_file"])
            == offset["episode_sha256"]
            for offset in offsets
        ),
    }
    warnings: List[str] = []
    if not checks["all_samples_valid"]:
        warnings.append(
            "One or more samples are invalid; inspect echo_delay_steps, saturation, "
            "session status, and the raw session before identification."
        )
    if not checks["source_session_status_complete"]:
        warnings.append(
            "The source run did not complete; partial evidence was preserved but must "
            "not be used as a complete calibration episode."
        )
    verification = {
        "passed": all(checks.values()),
        "checks": checks,
        "episode_checks": episode_checks,
        "episode_count": len(offsets),
        "sample_count": cursor,
        "warnings": warnings,
    }
    write_json(package_dir / "verification.json", verification)
    return package_dir
