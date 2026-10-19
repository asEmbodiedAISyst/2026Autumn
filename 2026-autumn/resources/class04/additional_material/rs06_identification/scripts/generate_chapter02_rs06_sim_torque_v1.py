#!/usr/bin/env python3
"""Generate the simulation-only Chapter 2 RS06 Sim-Torque Data.

The source run is the position-controlled MuJoCo Source Model from the
active Chapter 2 RS06 v1 release. At every physics step, this script records the
generalized actuator effort produced by that controller. The effort is an
output of the source closed loop and becomes the declared input to an
open-loop torque-replay model. This boundary defines Sim-Torque Data and is not claimed
to be available as measured RS06 output torque in ordinary position mode.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "data/chapter-02/releases/rs06-sim-data-v1"
SIM_POSITION_ARCHIVE = RELEASE_DIR / "rs06-sim-position-v1.npz"
SIM_POSITION_MANIFEST = RELEASE_DIR / "sim-position-manifest.json"
EXPERIMENT_CONTRACT = RELEASE_DIR / "experiment-contract.json"
OUTPUT_ARCHIVE = RELEASE_DIR / "rs06-sim-torque-v1.npz"
OUTPUT_CONTRACT = RELEASE_DIR / "sim-torque-contract.json"
OUTPUT_MANIFEST = RELEASE_DIR / "sim-torque-manifest.json"
RELEASE_FAMILY_MANIFEST = RELEASE_DIR / "release-family-manifest.json"

FIELDS = (
    "time_s",
    "position_command_rad",
    "actuator_effort_input_Nm",
    "position_true_rad",
    "velocity_true_rad_s",
    "acceleration_true_rad_s2",
    "bias_torque_Nm",
    "passive_torque_Nm",
    "constraint_torque_Nm",
    "valid",
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_episode(
    metadata: dict,
    sim_position: np.lib.npyio.NpzFile,
    contract: dict,
) -> dict[str, np.ndarray]:
    sample_slice = slice(int(metadata["start"]), int(metadata["stop"]))
    position_time = sim_position["time_s"][sample_slice]
    command = sim_position["position_applied_rad"][sample_slice]
    source_position = sim_position["source_position_true_rad"][sample_slice]
    model_path = (
        RELEASE_DIR
        / "models/source"
        / metadata["controller_id"]
        / f"{metadata['fixture_id']}.xml"
    )
    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    sample_dt = float(np.median(np.diff(position_time)))
    substeps_float = sample_dt / model.opt.timestep
    substeps = round(substeps_float)
    if not np.isclose(substeps_float, substeps):
        raise ValueError("Sim-Position sample interval must be an integer number of physics steps")

    data.qpos[0] = float(command[0])
    data.qvel[0] = 0.0
    data.ctrl[0] = float(command[0])
    mujoco.mj_forward(model, data)
    for _ in range(round(float(contract["simulation"]["pre_roll_s"]) / model.opt.timestep)):
        mujoco.mj_step(model, data)

    records = {field: [] for field in FIELDS}
    for command_index, command_value in enumerate(command):
        interval_steps = 1 if command_index == command.size - 1 else substeps
        for substep in range(interval_steps):
            data.ctrl[0] = float(command_value)
            mujoco.mj_forward(model, data)
            records["time_s"].append(
                float(position_time[command_index] + substep * model.opt.timestep)
            )
            records["position_command_rad"].append(float(command_value))
            records["actuator_effort_input_Nm"].append(float(data.qfrc_actuator[0]))
            records["position_true_rad"].append(float(data.qpos[0]))
            records["velocity_true_rad_s"].append(float(data.qvel[0]))
            records["acceleration_true_rad_s2"].append(float(data.qacc[0]))
            records["bias_torque_Nm"].append(float(data.qfrc_bias[0]))
            records["passive_torque_Nm"].append(float(data.qfrc_passive[0]))
            records["constraint_torque_Nm"].append(float(data.qfrc_constraint[0]))
            records["valid"].append(True)
            if not (
                command_index == command.size - 1 and substep == interval_steps - 1
            ):
                mujoco.mj_step(model, data)

    arrays = {
        field: np.asarray(values, dtype=bool if field == "valid" else float)
        for field, values in records.items()
    }
    sampled = arrays["position_true_rad"][::substeps]
    if sampled.shape != source_position.shape or not np.allclose(
        sampled, source_position, rtol=0.0, atol=1.0e-12
    ):
        raise ValueError(f"Sim-Torque source does not reproduce {metadata['episode_id']}")
    return arrays


def main() -> None:
    contract = read_json(EXPERIMENT_CONTRACT)
    position_manifest = read_json(SIM_POSITION_MANIFEST)
    sim_position = np.load(SIM_POSITION_ARCHIVE, allow_pickle=False)
    blocks = {field: [] for field in FIELDS}
    episodes = []
    offset = 0
    for metadata in position_manifest["episodes"]:
        arrays = generate_episode(metadata, sim_position, contract)
        count = int(arrays["time_s"].size)
        for field in FIELDS:
            blocks[field].append(arrays[field])
        episodes.append(
            {
                "episode_id": metadata["episode_id"],
                "split": metadata["split"],
                "controller_id": metadata["controller_id"],
                "fixture_id": metadata["fixture_id"],
                "profile_id": metadata["profile_id"],
                "start": offset,
                "stop": offset + count,
                "samples": count,
                "source_sim_position_start": int(metadata["start"]),
                "source_sim_position_stop": int(metadata["stop"]),
                "source_model": str(
                    (
                        RELEASE_DIR
                        / "models/source"
                        / metadata["controller_id"]
                        / f"{metadata['fixture_id']}.xml"
                    ).relative_to(ROOT)
                ),
                "candidate_model": str(
                    (
                        RELEASE_DIR
                        / "models/nominal"
                        / metadata["controller_id"]
                        / f"{metadata['fixture_id']}.xml"
                    ).relative_to(ROOT)
                ),
            }
        )
        offset += count

    combined = {field: np.concatenate(values) for field, values in blocks.items()}
    np.savez_compressed(OUTPUT_ARCHIVE, **combined)
    companion_contract = {
        "schema_version": "phyintel-sim-torque-data-v1",
        "release_id": "chapter02-rs06-sim-torque-v1",
        "source_release_id": position_manifest["release_id"],
        "source_archive_sha256": sha256_file(SIM_POSITION_ARCHIVE),
        "evidence_source": "simulation-only Sim-Torque Data from MuJoCo state and effort",
        "hardware_equivalent_claimed": False,
        "physics_timestep_s": float(contract["simulation"]["physics_timestep_s"]),
        "input_field": "actuator_effort_input_Nm",
        "input_meaning": (
            "MuJoCo qfrc_actuator recorded from the position-controlled Source "
            "Model and replayed as generalized joint effort"
        ),
        "source_controller_context": contract["controller_conditions"],
        "identified_parameters": ["armature", "damping", "frictionloss"],
        "controller_gains_identified": False,
        "position_command_is_identification_input": False,
        "rs06_position_mode_availability": (
            "feedback torque is a controller estimate, not a qualified measured output-joint torque trajectory"
        ),
        "purpose": (
            "simulation-only identifiability check and demonstration that C1/C2 "
            "change excitation but do not change the underlying joint parameters"
        ),
    }
    write_json(OUTPUT_CONTRACT, companion_contract)
    manifest = {
        "schema_version": "phyintel-sim-torque-manifest-v1",
        "release_id": companion_contract["release_id"],
        "archive_file": OUTPUT_ARCHIVE.name,
        "archive_sha256": sha256_file(OUTPUT_ARCHIVE),
        "contract_file": OUTPUT_CONTRACT.name,
        "contract_sha256": sha256_file(OUTPUT_CONTRACT),
        "sample_count": offset,
        "episode_count": len(episodes),
        "fields": list(FIELDS),
        "episodes": episodes,
        "verification": {
            "all_32_source_episodes_reproduced_at_sim_position_sample_boundaries": len(episodes) == 32,
            "physics_rate_hz": 1.0 / float(contract["simulation"]["physics_timestep_s"]),
        },
    }
    write_json(OUTPUT_MANIFEST, manifest)
    if RELEASE_FAMILY_MANIFEST.is_file():
        family = read_json(RELEASE_FAMILY_MANIFEST)
        family["sim_torque"] = {
            "release_id": companion_contract["release_id"],
            "role": (
                "simulation-only joint-parameter identifiability and "
                "controller-invariance check"
            ),
            "manifest_file": str(OUTPUT_MANIFEST.relative_to(ROOT)),
            "manifest_sha256": sha256_file(OUTPUT_MANIFEST),
            "admitted_to_sim_position_fit": False,
            "hardware_equivalent_claimed": False,
        }
        write_json(RELEASE_FAMILY_MANIFEST, family)
    print(json.dumps(manifest["verification"], indent=2))
    print(f"Wrote {OUTPUT_ARCHIVE.relative_to(ROOT)} ({offset} samples)")


if __name__ == "__main__":
    main()
