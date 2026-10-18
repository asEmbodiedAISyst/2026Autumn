#!/usr/bin/env python3
"""Verify the generated simulation release and hardware preparation artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import mujoco
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data/chapter-02/releases/rs06-sim-data-v1"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write release-verification.json")
    args = parser.parse_args()
    contract = read_json(RELEASE / "experiment-contract.json")
    position = read_json(RELEASE / "sim-position-manifest.json")
    torque = read_json(RELEASE / "sim-torque-manifest.json")
    simulation_checks = read_json(RELEASE / "verification.json")
    hardware = read_json(ROOT / "hardware/frozen-episode-matrix.json")
    position_result = read_json(RELEASE / "sim-position-results-v1/result.json")
    torque_result = read_json(RELEASE / "sim-torque-results-v1/result.json")

    measured_fixture_inertia = {}
    measured_bias_at_zero = {}
    for fixture_id in contract["fixtures"]:
        model = mujoco.MjModel.from_xml_path(str(RELEASE / f"models/source/C1/{fixture_id}.xml"))
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        full_mass = np.zeros((model.nv, model.nv), dtype=float)
        mujoco.mj_fullM(model, full_mass, data.qM)
        measured_fixture_inertia[fixture_id] = float(full_mass[0, 0] - model.dof_armature[0])
        measured_bias_at_zero[fixture_id] = float(data.qfrc_bias[0])

    translated_sim = {
        (episode["split"], {"C1": "H1", "C2": "H2"}[episode["controller_id"]], episode["fixture_id"], episode["profile_id"])
        for episode in position["episodes"]
    }
    planned_hardware = {
        (episode["split"], episode["controller_id"], episode["fixture_id"], episode["profile_definition_id"])
        for episode in hardware["episodes"]
    }
    source_xmls = list((RELEASE / "model-sources").glob("*.xml"))
    joint_names = [ET.parse(path).find(".//joint").get("name") for path in source_xmls]
    h1 = read_json(ROOT / "hardware/trajectory-suites/H1/manifest.json")
    h2 = read_json(ROOT / "hardware/trajectory-suites/H2/manifest.json")
    m2 = next(item for item in position_result["fits"] if item["method"] == "method2")
    torque_shared = torque_result["fits"]["method2"]["shared"]
    source = torque_result["source_model"]
    torque_relative_error = max(
        abs(torque_shared["joint_parameters"][name] - source[name]) / source[name]
        for name in source
    )
    checks = {
        "simulation_generator_verification_passed": simulation_checks["passed"],
        "position_has_32_episodes": position["episode_count"] == 32,
        "position_split_counts_are_18_8_6": Counter(e["split"] for e in position["episodes"]) == Counter({"calibration": 18, "model_selection": 8, "held_out": 6}),
        "position_archive_hash_matches": sha256(ROOT / position["data_file"]) == position["data_sha256"],
        "torque_has_same_32_episodes": torque["episode_count"] == 32,
        "torque_archive_hash_matches": sha256(RELEASE / torque["archive_file"]) == torque["archive_sha256"],
        "simulation_and_hardware_unique_matrices_pair_exactly": translated_sim == planned_hardware,
        "all_source_joint_names_are_rs06_joint": len(source_xmls) == 4 and set(joint_names) == {"rs06_joint"},
        "mujoco_fixture_inertias_match_cad_contract": all(
            abs(measured_fixture_inertia[fixture_id] - float(values["target_external_inertia_kg_m2"]))
            < (1.0e-10 if fixture_id == "M0" else 1.0e-12)
            for fixture_id, values in contract["fixtures"].items()
        ),
        "mujoco_zero_pose_bias_matches_gravity_first_moment": all(
            abs(abs(measured_bias_at_zero[fixture_id]) - 9.81 * float(values["gravity_first_moment_kg_m"])) < 1.0e-12
            for fixture_id, values in contract["fixtures"].items()
        ),
        "H1_is_50_3p38": h1["control_configuration"]["controller_id"] == "H1" and h1["control_configuration"]["kp"] == 50.0 and h1["control_configuration"]["kd"] == 3.38,
        "H2_is_100_1p95": h2["control_configuration"]["controller_id"] == "H2" and h2["control_configuration"]["kp"] == 100.0 and h2["control_configuration"]["kd"] == 1.95,
        "hardware_plan_requires_108_accepted_runs": hardware["minimum_accepted_physical_run_count"] == 108,
        "g1_free_fall_schema_present": (ROOT / "hardware/g1-free-fall-schema.json").is_file(),
        "sim_position_method2_accepted": m2["method"] == "method2" and position_result["simulation_predictive_acceptance"]["sim_position_m2"]["accepted"],
        "sim_torque_method2_recovers_source": torque_relative_error < 1.0e-4,
        "no_physical_evidence_claimed": contract["status"] == "simulation-only-projected-evidence" and not torque_result["hardware_equivalent_claimed"],
    }
    result = {
        "schema_version": "phyintel-chapter02-rs06-release-verification-v1",
        "passed": all(checks.values()),
        "checks": checks,
        "position_samples": position["sample_count"],
        "torque_samples": torque["sample_count"],
        "minimum_accepted_hardware_runs": hardware["minimum_accepted_physical_run_count"],
        "sim_position_method1_accepted": position_result["simulation_predictive_acceptance"]["sim_position_m1"]["accepted"],
        "sim_position_method2_accepted": position_result["simulation_predictive_acceptance"]["sim_position_m2"]["accepted"],
        "sim_torque_method2_max_relative_source_error": torque_relative_error,
        "mujoco_fixture_inertia_kg_m2": measured_fixture_inertia,
        "mujoco_qfrc_bias_at_zero_Nm": measured_bias_at_zero,
    }
    if args.write:
        (ROOT / "release-verification.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
