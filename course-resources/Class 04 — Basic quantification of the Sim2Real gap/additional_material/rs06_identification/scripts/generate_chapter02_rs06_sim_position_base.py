#!/usr/bin/env python3
"""Generate and verify the Chapter 2 RS06 MuJoCo Sim-Position dataset."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "data" / "chapter-02" / "releases" / "rs06-sim-data-v1"
CONTRACT_PATH = PACKAGE / "experiment-contract.json"
MODEL_SOURCE_DIR = PACKAGE / "model-sources"
MODEL_DIR = PACKAGE / "models"
EPISODE_DIR = PACKAGE / "episodes"
PLOT_DIR = ROOT / "assets" / "chapter-02" / "rs06-sim-position-v1"

NUMERIC_FIELDS = [
    "time_s",
    "t_command_s",
    "t_state_s",
    "position_cmd_rad",
    "position_applied_rad",
    "source_position_true_rad",
    "source_position_meas_rad",
    "source_velocity_true_rad_s",
    "source_velocity_meas_rad_s",
    "source_acceleration_true_rad_s2",
    "source_actuator_torque_Nm",
    "source_bias_torque_Nm",
    "source_passive_torque_Nm",
    "source_constraint_torque_Nm",
    "source_tracking_error_rad",
    "source_saturated",
    "nominal_position_true_rad",
    "nominal_position_meas_rad",
    "nominal_velocity_true_rad_s",
    "nominal_velocity_meas_rad_s",
    "nominal_acceleration_true_rad_s2",
    "nominal_actuator_torque_Nm",
    "nominal_bias_torque_Nm",
    "nominal_passive_torque_Nm",
    "nominal_constraint_torque_Nm",
    "nominal_tracking_error_rad",
    "nominal_saturated",
    "nominal_output_gap_rad",
    "valid",
]


def consecutive_pairs(values):
    """Yield adjacent pairs without requiring Python 3.10 itertools.pairwise."""

    return zip(values, values[1:])


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_model_sources(source_root: Path, contract: dict, refresh: bool) -> None:
    required_models = [
        MODEL_SOURCE_DIR / f"{fixture_id}.xml"
        for fixture_id in contract["fixtures"]
    ]
    if not refresh and all(path.is_file() for path in required_models):
        referenced_meshes = []
        for path in required_models:
            referenced_meshes.extend(
                MODEL_SOURCE_DIR / mesh.get("file", "")
                for mesh in ET.parse(path).getroot().findall("./asset/mesh")
            )
        if referenced_meshes and all(path.is_file() for path in referenced_meshes):
            return
    if refresh and MODEL_SOURCE_DIR.exists():
        shutil.rmtree(MODEL_SOURCE_DIR)
    mesh_dir = MODEL_SOURCE_DIR / "meshes"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    for fixture_id, fixture in contract["fixtures"].items():
        source = source_root / fixture["model_source_file"]
        if not source.is_file():
            raise FileNotFoundError(source)
        tree = ET.parse(source)
        root = tree.getroot()
        for mesh in root.findall("./asset/mesh"):
            source_mesh = source.parent / mesh.get("file", "")
            if not source_mesh.is_file():
                raise FileNotFoundError(source_mesh)
            destination_name = f"{fixture_id}__{source_mesh.name}"
            shutil.copy2(source_mesh, mesh_dir / destination_name)
            mesh.set("file", f"meshes/{destination_name}")
        ET.indent(tree, space="  ")
        tree.write(MODEL_SOURCE_DIR / f"{fixture_id}.xml", encoding="unicode")


def build_models(contract: dict) -> dict[str, dict[str, dict[str, Path]]]:
    paths: dict[str, dict[str, dict[str, Path]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    simulation = contract["simulation"]
    for role in ("source", "nominal"):
        parameters = contract[f"{role}_model"]
        for controller_id, controller in contract["controller_conditions"].items():
            for fixture_id in contract["fixtures"]:
                source = MODEL_SOURCE_DIR / f"{fixture_id}.xml"
                tree = ET.parse(source)
                root = tree.getroot()
                root.set("model", f"chapter02-{role}-{controller_id}-{fixture_id}")
                option = root.find("option")
                if option is None:
                    raise ValueError(f"missing option in {source}")
                option.set("timestep", str(simulation["physics_timestep_s"]))
                option.set("integrator", simulation["integrator"])
                option.set("gravity", f"0 0 {-float(simulation['gravity_m_s2'])}")
                joint = root.find(".//joint[@name='rs06_joint']")
                actuator = root.find(".//actuator/position[@name='rs06_position']")
                if joint is None or actuator is None:
                    raise ValueError(f"missing declared joint or actuator in {source}")
                joint.set("range", " ".join(map(str, simulation["joint_range_rad"])))
                for name in ("armature", "damping", "frictionloss"):
                    joint.set(name, str(parameters[name]))
                actuator.set("kp", str(controller["kp_Nm_per_rad"]))
                actuator.set("kv", str(controller["kv_Nm_s_per_rad"]))
                actuator.set(
                    "ctrlrange", " ".join(map(str, simulation["ctrlrange_rad"]))
                )
                actuator.set(
                    "forcerange", " ".join(map(str, simulation["forcerange_Nm"]))
                )
                for mesh in root.findall("./asset/mesh"):
                    mesh.set(
                        "file",
                        f"../../../model-sources/meshes/{Path(mesh.get('file', '')).name}",
                    )
                destination = MODEL_DIR / role / controller_id / f"{fixture_id}.xml"
                destination.parent.mkdir(parents=True, exist_ok=True)
                ET.indent(tree, space="  ")
                tree.write(destination, encoding="unicode")
                mujoco.MjModel.from_xml_path(str(destination))
                paths[role][controller_id][fixture_id] = destination
    return paths


def smooth_transition(start: float, stop: float, count: int) -> np.ndarray:
    if count <= 1:
        return np.array([stop], dtype=float)
    phase = np.linspace(0.0, 1.0, count, endpoint=False)
    blend = 0.5 - 0.5 * np.cos(np.pi * phase)
    return start + (stop - start) * blend


def build_profile(profile: dict, dt: float) -> tuple[np.ndarray, np.ndarray]:
    kind = profile["kind"]
    if kind == "smooth_levels":
        hold_count = round(float(profile["hold_s"]) / dt)
        transition_count = round(float(profile["transition_s"]) / dt)
        levels = [float(value) for value in profile["levels_rad"]]
        pieces = [np.full(hold_count, levels[0])]
        for start, stop in consecutive_pairs(levels):
            pieces.append(smooth_transition(start, stop, transition_count))
            pieces.append(np.full(hold_count, stop))
        command = np.concatenate(pieces)
        time = np.arange(command.size, dtype=float) * dt
        return time, command
    duration = float(profile["duration_s"])
    time = np.arange(round(duration / dt) + 1, dtype=float) * dt
    if kind == "triangle":
        phase = 2.0 * np.pi * float(profile["frequency_hz"]) * time
        command = float(profile["center_rad"]) + (
            float(profile["amplitude_rad"]) * (2.0 / np.pi) * np.arcsin(np.sin(phase))
        )
    elif kind == "multisine":
        command = np.full_like(time, float(profile["center_rad"]))
        for amplitude, frequency, phase in zip(
            profile["amplitudes_rad"],
            profile["frequencies_hz"],
            profile["phases_rad"],
        ):
            command += float(amplitude) * np.sin(
                2.0 * np.pi * float(frequency) * time + float(phase)
            )
    elif kind == "chirp":
        start = float(profile["start_frequency_hz"])
        stop = float(profile["end_frequency_hz"])
        phase = 2.0 * np.pi * (start * time + 0.5 * (stop - start) / duration * time**2)
        command = float(profile["center_rad"]) + float(
            profile["amplitude_rad"]
        ) * np.sin(phase)
    elif kind == "sine":
        command = float(profile["center_rad"]) + float(
            profile["amplitude_rad"]
        ) * np.sin(2.0 * np.pi * float(profile["frequency_hz"]) * time)
    elif kind == "composite":
        command = np.zeros_like(time)
        for amplitude, frequency, phase in zip(
            profile["amplitudes_rad"],
            profile["frequencies_hz"],
            profile["phases_rad"],
        ):
            command += float(amplitude) * np.sin(
                2.0 * np.pi * float(frequency) * time + float(phase)
            )
        offsets = profile["center_offsets_rad"]
        switches = profile["switch_times_s"]
        command += np.select(
            [time < float(switches[0]), time < float(switches[1])],
            [float(offsets[0]), float(offsets[1])],
            default=float(offsets[2]),
        )
    elif kind == "sine_hold":
        active = float(profile["active_duration_s"])
        center = float(profile["center_rad"])
        amplitude = float(profile["amplitude_rad"])
        frequency = float(profile["frequency_hz"])
        sine = center + amplitude * np.sin(2.0 * np.pi * frequency * time)
        command = sine.copy()
        transition = float(profile["transition_s"])
        hold = float(profile["hold_position_rad"])
        start_value = center + amplitude * math.sin(2.0 * math.pi * frequency * active)
        mask_transition = (time >= active) & (time < active + transition)
        phase = (time[mask_transition] - active) / transition
        blend = 0.5 - 0.5 * np.cos(np.pi * phase)
        command[mask_transition] = start_value + (hold - start_value) * blend
        command[time >= active + transition] = hold
    else:
        raise ValueError(f"unknown profile kind: {kind}")
    return time, command.astype(float)


def episode_specs(contract: dict) -> list[dict]:
    specs = []
    for split, block in contract["episode_matrix"].items():
        for controller_id in block["controllers"]:
            for fixture_id in block["fixtures"]:
                for profile_id in block["profiles"]:
                    specs.append(
                        {
                            "split": split,
                            "controller_id": controller_id,
                            "fixture_id": fixture_id,
                            "profile_id": profile_id,
                        }
                    )
        for fixture_id, profile_id, controller_id in block.get("additional_pairs", []):
            specs.append(
                {
                    "split": split,
                    "controller_id": controller_id,
                    "fixture_id": fixture_id,
                    "profile_id": profile_id,
                }
            )
    return specs


def simulate(
    model_path: Path, time: np.ndarray, command: np.ndarray, contract: dict
) -> dict:
    simulation = contract["simulation"]
    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    sample_dt = 1.0 / float(simulation["sample_rate_hz"])
    substeps_float = sample_dt / model.opt.timestep
    substeps = round(substeps_float)
    if not np.isclose(substeps, substeps_float):
        raise ValueError(
            "sample interval is not an integer multiple of the MuJoCo timestep"
        )
    data.qpos[0] = float(command[0])
    data.qvel[0] = 0.0
    data.ctrl[0] = float(command[0])
    mujoco.mj_forward(model, data)
    for _ in range(round(float(simulation["pre_roll_s"]) / model.opt.timestep)):
        mujoco.mj_step(model, data)
    arrays = {
        "position_true_rad": np.empty(time.size),
        "velocity_true_rad_s": np.empty(time.size),
        "acceleration_true_rad_s2": np.empty(time.size),
        "actuator_torque_Nm": np.empty(time.size),
        "bias_torque_Nm": np.empty(time.size),
        "passive_torque_Nm": np.empty(time.size),
        "constraint_torque_Nm": np.empty(time.size),
        "saturated": np.zeros(time.size, dtype=bool),
    }
    force_limit = max(abs(float(value)) for value in simulation["forcerange_Nm"])
    for index, requested in enumerate(command):
        data.ctrl[0] = float(requested)
        mujoco.mj_forward(model, data)
        arrays["position_true_rad"][index] = data.qpos[0]
        arrays["velocity_true_rad_s"][index] = data.qvel[0]
        arrays["acceleration_true_rad_s2"][index] = data.qacc[0]
        arrays["actuator_torque_Nm"][index] = data.qfrc_actuator[0]
        arrays["bias_torque_Nm"][index] = data.qfrc_bias[0]
        arrays["passive_torque_Nm"][index] = data.qfrc_passive[0]
        arrays["constraint_torque_Nm"][index] = data.qfrc_constraint[0]
        arrays["saturated"][index] = abs(data.qfrc_actuator[0]) >= force_limit - 1.0e-7
        if index + 1 < time.size:
            for _ in range(substeps):
                mujoco.mj_step(model, data)
    sensor = simulation["sensor_emulation"]
    q_resolution = float(sensor["position_resolution_rad"])
    v_resolution = float(sensor["velocity_resolution_rad_s"])
    arrays["position_meas_rad"] = (
        np.round(arrays["position_true_rad"] / q_resolution) * q_resolution
    )
    arrays["velocity_meas_rad_s"] = (
        np.round(arrays["velocity_true_rad_s"] / v_resolution) * v_resolution
    )
    return arrays


def build_episode(spec: dict, contract: dict, paths: dict) -> tuple[dict, dict]:
    profile = contract["profiles"][spec["profile_id"]]
    dt = 1.0 / float(contract["simulation"]["sample_rate_hz"])
    time, requested_command = build_profile(profile, dt)
    command_application = contract["simulation"].get("command_application", {})
    applied_resolution = command_application.get("position_resolution_rad")
    if applied_resolution is None:
        applied_command = requested_command.copy()
    else:
        applied_resolution = float(applied_resolution)
        applied_command = (
            np.round(requested_command / applied_resolution) * applied_resolution
        )
    ctrlrange = contract["simulation"]["ctrlrange_rad"]
    if (
        float(applied_command.min()) < ctrlrange[0]
        or float(applied_command.max()) > ctrlrange[1]
    ):
        raise ValueError(f"profile {spec['profile_id']} exceeds declared ctrlrange")
    source = simulate(
        paths["source"][spec["controller_id"]][spec["fixture_id"]],
        time,
        applied_command,
        contract,
    )
    nominal = simulate(
        paths["nominal"][spec["controller_id"]][spec["fixture_id"]],
        time,
        applied_command,
        contract,
    )
    values: dict[str, np.ndarray] = {
        "time_s": time,
        "t_command_s": time.copy(),
        "t_state_s": time.copy(),
        "position_cmd_rad": requested_command,
        "position_applied_rad": applied_command,
    }
    for role, result in (("source", source), ("nominal", nominal)):
        for name, array in result.items():
            values[f"{role}_{name}"] = array
        values[f"{role}_tracking_error_rad"] = (
            result["position_meas_rad"] - applied_command
        )
    values["nominal_output_gap_rad"] = (
        nominal["position_meas_rad"] - source["position_meas_rad"]
    )
    values["valid"] = np.ones(time.size, dtype=bool)
    episode_id = "__".join(
        [spec["split"], spec["controller_id"], spec["fixture_id"], spec["profile_id"]]
    )
    metadata = {
        **spec,
        "episode_id": episode_id,
        "samples": int(time.size),
        "duration_s": float(time[-1] - time[0]),
        "command_min_rad": float(requested_command.min()),
        "command_max_rad": float(requested_command.max()),
        "applied_command_min_rad": float(applied_command.min()),
        "applied_command_max_rad": float(applied_command.max()),
        "source_model": str(
            paths["source"][spec["controller_id"]][spec["fixture_id"]].relative_to(
                ROOT
            )
        ),
        "nominal_model": str(
            paths["nominal"][spec["controller_id"]][spec["fixture_id"]].relative_to(
                ROOT
            )
        ),
    }
    return metadata, values


def rmse(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def write_episode_csv(
    path: Path, metadata: dict, values: dict[str, np.ndarray]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata_fields = [
        "episode_id",
        "split",
        "controller_id",
        "fixture_id",
        "profile_id",
    ]
    with (
        path.open("wb") as raw_handle,
        gzip.GzipFile(
            filename="", mode="wb", fileobj=raw_handle, mtime=0
        ) as compressed,
        io.TextIOWrapper(compressed, encoding="utf-8", newline="") as handle,
    ):
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow([*metadata_fields, "sequence_id", *NUMERIC_FIELDS])
        for index in range(values["time_s"].size):
            row = [metadata[name] for name in metadata_fields]
            row.append(index)
            row.extend(values[name][index] for name in NUMERIC_FIELDS)
            writer.writerow(row)


def write_dataset(
    contract: dict, paths: dict
) -> tuple[list[dict], list[tuple[dict, dict]]]:
    EPISODE_DIR.mkdir(parents=True, exist_ok=True)
    episodes: list[tuple[dict, dict]] = []
    summaries: list[dict] = []
    offsets = []
    cursor = 0
    concatenated: dict[str, list[np.ndarray]] = {name: [] for name in NUMERIC_FIELDS}
    for spec in episode_specs(contract):
        metadata, values = build_episode(spec, contract, paths)
        csv_path = EPISODE_DIR / f"{metadata['episode_id']}.csv.gz"
        write_episode_csv(csv_path, metadata, values)
        source_tracking = values["source_tracking_error_rad"]
        nominal_tracking = values["nominal_tracking_error_rad"]
        output_gap = values["nominal_output_gap_rad"]
        summary = {
            **metadata,
            "source_tracking_rmse_rad": rmse(source_tracking),
            "source_tracking_max_abs_rad": float(np.max(np.abs(source_tracking))),
            "nominal_tracking_rmse_rad": rmse(nominal_tracking),
            "nominal_tracking_max_abs_rad": float(np.max(np.abs(nominal_tracking))),
            "nominal_source_output_gap_rmse_rad": rmse(output_gap),
            "nominal_source_output_gap_max_abs_rad": float(
                np.max(np.abs(output_gap))
            ),
            "source_saturation_fraction": float(
                np.mean(values["source_saturated"])
            ),
            "nominal_saturation_fraction": float(np.mean(values["nominal_saturated"])),
            "source_peak_abs_actuator_torque_Nm": float(
                np.max(np.abs(values["source_actuator_torque_Nm"]))
            ),
            "nominal_peak_abs_actuator_torque_Nm": float(
                np.max(np.abs(values["nominal_actuator_torque_Nm"]))
            ),
            "source_position_min_rad": float(
                values["source_position_meas_rad"].min()
            ),
            "source_position_max_rad": float(
                values["source_position_meas_rad"].max()
            ),
            "episode_file": str(csv_path.relative_to(ROOT)),
            "episode_sha256": sha256_file(csv_path),
        }
        summaries.append(summary)
        offsets.append(
            {
                **{
                    name: metadata[name]
                    for name in (
                        "episode_id",
                        "split",
                        "controller_id",
                        "fixture_id",
                        "profile_id",
                    )
                },
                "start": cursor,
                "stop": cursor + metadata["samples"],
                "samples": metadata["samples"],
            }
        )
        cursor += metadata["samples"]
        for name in NUMERIC_FIELDS:
            concatenated[name].append(np.asarray(values[name]))
        episodes.append((metadata, values))
    archive_filename = contract.get("artifacts", {}).get(
        "archive_filename", "sim-position-v1.npz"
    )
    npz_path = PACKAGE / archive_filename
    np.savez_compressed(
        npz_path,
        **{name: np.concatenate(parts) for name, parts in concatenated.items()},
    )
    summary_path = PACKAGE / "episode-summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(summaries[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(summaries)
    preview_path = PACKAGE / "sample-preview.csv"
    selected = [episodes[0], episodes[len(episodes) // 2], episodes[-1]]
    with preview_path.open("w", encoding="utf-8", newline="") as handle:
        fields = ["episode_id", "sequence_id", *NUMERIC_FIELDS]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for metadata, values in selected:
            for index in np.linspace(0, values["time_s"].size - 1, 40, dtype=int):
                writer.writerow(
                    {
                        "episode_id": metadata["episode_id"],
                        "sequence_id": int(index),
                        **{name: values[name][index] for name in NUMERIC_FIELDS},
                    }
                )
    manifest = {
        "schema_version": contract["schema_version"],
        "release_id": contract["release_id"],
        "evidence_role": "projected",
        "source": "MuJoCo disclosed synthetic RS06 Source Model",
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "data_file": str(npz_path.relative_to(ROOT)),
        "data_sha256": sha256_file(npz_path),
        "episode_summary_file": str(summary_path.relative_to(ROOT)),
        "episode_summary_sha256": sha256_file(summary_path),
        "sample_preview_file": str(preview_path.relative_to(ROOT)),
        "sample_preview_sha256": sha256_file(preview_path),
        "episode_count": len(episodes),
        "sample_count": cursor,
        "numeric_fields": NUMERIC_FIELDS,
        "episodes": offsets,
        "model_files": {
            str(path.relative_to(ROOT)): sha256_file(path)
            for role in paths.values()
            for controller in role.values()
            for path in controller.values()
        },
    }
    write_json(PACKAGE / "sim-position-manifest.json", manifest)
    return summaries, episodes


def write_parameter_table(contract: dict) -> None:
    source = contract["source_model"]
    nominal = contract["nominal_model"]
    path = PACKAGE / "model-parameters.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "MuJoCo_parameter",
                "unit",
                "source_value",
                "nominal_value",
                "nominal_difference_percent",
                "source_provenance",
            ]
        )
        for name in contract["identification_target"]["joint_parameter_names"]:
            difference = (
                100.0
                * (float(nominal[name]) - float(source[name]))
                / float(source[name])
            )
            writer.writerow(
                [
                    name,
                    contract["identification_target"]["units"][name],
                    source[name],
                    nominal[name],
                    difference,
                    source["provenance"][name],
                ]
            )


def create_plots(
    contract: dict, summaries: list[dict], episodes: list[tuple[dict, dict]]
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    dt = 1.0 / float(contract["simulation"]["sample_rate_hz"])
    fig, axes = plt.subplots(4, 2, figsize=(13, 10), constrained_layout=True)
    for axis, (profile_id, profile) in zip(
        axes.flat, contract["profiles"].items()
    ):
        time, command = build_profile(profile, dt)
        axis.plot(time, command, color="#315f9b", linewidth=1.5)
        axis.set_title(f"{profile_id}: {profile['split']}")
        axis.set_xlabel("Time (s)")
        axis.set_ylabel("Requested position (rad)")
        axis.grid(alpha=0.25)
    axes.flat[-1].axis("off")
    fig.suptitle("Chapter 2 Command-Profile Catalog", fontsize=16)
    fig.savefig(PLOT_DIR / "profile-catalog.png", dpi=170)
    plt.close(fig)

    requested_ids = [
        "calibration__C1__B0__P01_slow_triangle",
        "model_selection__C2__B1__P04_chirp",
        "held_out__C2__G1__P06_heldout_composite",
    ]
    lookup = {
        metadata["episode_id"]: (metadata, values) for metadata, values in episodes
    }
    fig, axes = plt.subplots(3, 2, figsize=(14, 10), constrained_layout=True)
    for row, episode_id in enumerate(requested_ids):
        metadata, values = lookup[episode_id]
        time = values["time_s"]
        left, right = axes[row]
        left.plot(
            time,
            values["position_applied_rad"],
            label="Applied input",
            color="#202020",
            linewidth=1.1,
        )
        left.plot(
            time,
            values["source_position_meas_rad"],
            label="Source Model output",
            color="#2a7b4f",
            linewidth=1.3,
        )
        left.plot(
            time,
            values["nominal_position_meas_rad"],
            label="Nominal Model output",
            color="#bf5b3d",
            linewidth=1.1,
        )
        left.set_title(
            f"{metadata['fixture_id']} / {metadata['controller_id']} / {metadata['profile_id']}"
        )
        left.set_ylabel("Position (rad)")
        left.grid(alpha=0.25)
        left.legend(loc="upper right", fontsize=8)
        gap = values["nominal_output_gap_rad"]
        right.plot(
            time,
            gap,
            color="#7e57a0",
            linewidth=1.2,
            label=f"RMSE = {rmse(gap):.4f} rad",
        )
        right.axhline(0.0, color="#202020", linewidth=0.7)
        right.set_title("Nominal-to-Source Output Gap")
        right.set_ylabel("Position gap (rad)")
        right.grid(alpha=0.25)
        right.legend(loc="upper right", fontsize=8)
    for axis in axes[-1]:
        axis.set_xlabel("Time (s)")
    fig.suptitle(
        "Input, Source Output, Nominal Output, and Quantified Gap", fontsize=16
    )
    fig.savefig(PLOT_DIR / "dataset-review.png", dpi=170)
    plt.close(fig)

    metadata, values = lookup["held_out__C2__G1__P06_heldout_composite"]
    time = values["time_s"]
    source_error = values["source_tracking_error_rad"]
    nominal_error = values["nominal_tracking_error_rad"]
    gap = values["nominal_output_gap_rad"]
    fig, axes = plt.subplots(2, 2, figsize=(14, 8), constrained_layout=True)
    axes[0, 0].plot(
        time, values["position_applied_rad"], label="Applied input", color="#202020"
    )
    axes[0, 0].plot(
        time,
        values["source_position_meas_rad"],
        label="Source Model output",
        color="#2a7b4f",
    )
    axes[0, 0].set_title("Source Model: Input and Output")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].plot(
        time,
        source_error,
        color="#2a7b4f",
        label=f"RMSE = {rmse(source_error):.4f} rad",
    )
    axes[0, 1].axhline(0.0, color="#202020", linewidth=0.7)
    axes[0, 1].set_title("Source Tracking Error")
    axes[0, 1].legend(fontsize=8)
    axes[1, 0].plot(
        time,
        values["source_position_meas_rad"],
        label="Source Model output",
        color="#2a7b4f",
    )
    axes[1, 0].plot(
        time,
        values["nominal_position_meas_rad"],
        label="Nominal Model output",
        color="#bf5b3d",
    )
    axes[1, 0].set_title(f"Nominal-to-Source Output Gap: RMSE = {rmse(gap):.4f} rad")
    axes[1, 0].legend(fontsize=8)
    axes[1, 1].plot(
        time, values["position_applied_rad"], label="Applied input", color="#202020"
    )
    axes[1, 1].plot(
        time,
        values["nominal_position_meas_rad"],
        label="Nominal Model output",
        color="#bf5b3d",
    )
    axes[1, 1].set_title(f"Nominal Model Tracking: RMSE = {rmse(nominal_error):.4f} rad")
    axes[1, 1].legend(fontsize=8)
    for axis in axes.flat:
        axis.set_xlabel("Time (s)")
        axis.set_ylabel("Position (rad)")
        axis.grid(alpha=0.25)
    fig.suptitle(
        f"Representative Frozen Episode: {metadata['fixture_id']} / {metadata['controller_id']} / {metadata['profile_id']}",
        fontsize=15,
    )
    fig.savefig(PLOT_DIR / "source-nominal-comparison.png", dpi=170)
    plt.close(fig)

    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    effort: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in summaries:
        key = (row["fixture_id"], row["controller_id"])
        grouped[key].append(float(row["nominal_source_output_gap_rmse_rad"]))
        effort[key].append(float(row["source_peak_abs_actuator_torque_Nm"]))
    labels = [f"{fixture}\n{controller}" for fixture, controller in sorted(grouped)]
    gaps = [float(np.mean(grouped[key])) for key in sorted(grouped)]
    force_limit = max(
        abs(float(value)) for value in contract["simulation"]["forcerange_Nm"]
    )
    effort_percent = [
        100.0 * float(np.max(effort[key])) / force_limit for key in sorted(effort)
    ]
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), constrained_layout=True)
    axes[0].bar(labels, gaps, color="#4f79a7")
    axes[0].set_ylabel("Mean output-gap RMSE (rad)")
    axes[0].set_title("Nominal-to-Source Discrepancy by Fixture and Controller")
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].bar(labels, effort_percent, color="#d18748")
    axes[1].axhline(
        100.0, color="#202020", linestyle="--", linewidth=0.9, label="Effort limit"
    )
    axes[1].set_ylabel("Peak effort-limit use (%)")
    axes[1].set_title("Maximum Source Model Actuator Effort Across Assigned Episodes")
    axes[1].legend(fontsize=8)
    axes[1].grid(axis="y", alpha=0.25)
    fig.savefig(PLOT_DIR / "quality-summary.png", dpi=170)
    plt.close(fig)


def verify(contract: dict, summaries: list[dict], paths: dict) -> dict:
    expected = len(episode_specs(contract))
    manifest = read_json(PACKAGE / "sim-position-manifest.json")
    data_path = ROOT / manifest["data_file"]
    with np.load(data_path, allow_pickle=False) as archive:
        archive_fields = set(archive.files)
        archive_lengths = {int(archive[name].size) for name in archive.files}
        aligned_clocks = np.array_equal(
            archive["time_s"], archive["t_command_s"]
        ) and np.array_equal(archive["time_s"], archive["t_state_s"])
        applied_resolution = contract["simulation"].get(
            "command_application", {}
        ).get("position_resolution_rad")
        if applied_resolution is None:
            applied_boundary_matches_contract = np.array_equal(
                archive["position_cmd_rad"], archive["position_applied_rad"]
            )
        else:
            expected_applied = (
                np.round(archive["position_cmd_rad"] / float(applied_resolution))
                * float(applied_resolution)
            )
            applied_boundary_matches_contract = np.array_equal(
                expected_applied, archive["position_applied_rad"]
            )
    checks = {
        "episode_count_matches_contract": len(summaries) == expected,
        "both_controllers_present": {row["controller_id"] for row in summaries}
        == {"C1", "C2"},
        "all_splits_present": {row["split"] for row in summaries}
        == {"calibration", "model_selection", "held_out"},
        "held_out_G1_present": any(
            row["split"] == "held_out" and row["fixture_id"] == "G1"
            for row in summaries
        ),
        "models_load_in_mujoco": all(
            path.is_file()
            for role in paths.values()
            for controller in role.values()
            for path in controller.values()
        ),
        "commands_within_ctrlrange": all(
            row["command_min_rad"] >= contract["simulation"]["ctrlrange_rad"][0]
            and row["command_max_rad"] <= contract["simulation"]["ctrlrange_rad"][1]
            for row in summaries
        ),
        "source_motion_within_joint_range": all(
            row["source_position_min_rad"]
            > contract["simulation"]["joint_range_rad"][0]
            and row["source_position_max_rad"]
            < contract["simulation"]["joint_range_rad"][1]
            for row in summaries
        ),
        "no_episode_dominated_by_source_saturation": all(
            row["source_saturation_fraction"] < 0.25 for row in summaries
        ),
        "nominal_gap_is_measurable": float(
            np.median(
                [row["nominal_source_output_gap_rmse_rad"] for row in summaries]
            )
        )
        > contract["simulation"]["sensor_emulation"]["position_resolution_rad"],
        "G1_is_excluded_from_calibration": not any(
            row["split"] == "calibration" and row["fixture_id"] == "G1"
            for row in summaries
        ),
        "archive_fields_match_manifest": archive_fields
        == set(manifest["numeric_fields"]),
        "archive_arrays_have_one_length": archive_lengths == {manifest["sample_count"]},
        "archive_hash_matches_manifest": sha256_file(data_path)
        == manifest["data_sha256"],
        "episode_hashes_match_summary": all(
            sha256_file(ROOT / row["episode_file"]) == row["episode_sha256"]
            for row in summaries
        ),
        "baseline_clocks_are_aligned": aligned_clocks,
        "applied_command_boundary_matches_contract": applied_boundary_matches_contract,
    }
    warnings = []
    maximum_saturation = max(row["source_saturation_fraction"] for row in summaries)
    if maximum_saturation > 0.10:
        warnings.append(
            "Some episodes intentionally exercise the effort limit above 10%; saturated samples must be declared or excluded by the identification method."
        )
    result = {
        "passed": all(checks.values()),
        "checks": checks,
        "episode_count": len(summaries),
        "sample_count": int(sum(row["samples"] for row in summaries)),
        "maximum_source_saturation_fraction": maximum_saturation,
        "median_nominal_source_output_gap_rmse_rad": float(
            np.median(
                [row["nominal_source_output_gap_rmse_rad"] for row in summaries]
            )
        ),
        "warnings": warnings,
    }
    write_json(PACKAGE / "verification.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        default=ROOT / "source-assets" / "mjcf",
        help="Directory containing the four normalized Fusion MJCF export folders.",
    )
    parser.add_argument("--refresh-model-sources", action="store_true")
    args = parser.parse_args()
    contract = read_json(CONTRACT_PATH)
    prepare_model_sources(args.source_root, contract, args.refresh_model_sources)
    paths = build_models(contract)
    summaries, episodes = write_dataset(contract, paths)
    write_parameter_table(contract)
    create_plots(contract, summaries, episodes)
    verification = verify(contract, summaries, paths)
    print(json.dumps(verification, indent=2))
    return 0 if verification["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
