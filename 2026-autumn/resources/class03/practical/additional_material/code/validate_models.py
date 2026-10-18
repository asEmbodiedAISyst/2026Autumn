#!/usr/bin/env python3
"""Validate the five Class 03 MJCF representations.

The checks are structural. They do not claim agreement with hardware dynamics.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco


CONFIGS = ("M0", "B0", "B1", "B2", "G1")
EXPECTED_EXTERNAL_MASS_KG = {
    "M0": 0.0,
    "B0": 0.110,
    "B1": 0.110,
    "B2": 0.110,
    "G1": 0.110,
}


def moving_mass(model: mujoco.MjModel) -> float:
    """Return mass below the fixed XC330 body."""
    motor_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "XC330-M288-T")
    total = 0.0
    for body_id in range(1, model.nbody):
        parent = int(model.body_parentid[body_id])
        while parent > 0 and parent != motor_id:
            parent = int(model.body_parentid[parent])
        if parent == motor_id:
            total += float(model.body_mass[body_id])
    return total


def validate(xml_path: Path, config: str) -> dict[str, object]:
    root = ET.parse(xml_path).getroot()
    platform_mesh = root.find("./asset/mesh[@name='asbrain_platform']")
    platform_geom = root.find("./worldbody/geom[@name='platform_visual']")

    model = mujoco.MjModel.from_xml_path(str(xml_path.resolve()))
    data = mujoco.MjData(model)
    joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "actuator_joint")
    data.qpos[0] = 0.4
    data.ctrl[:] = 0.0
    mujoco.mj_forward(model, data)

    mass_kg = moving_mass(model)
    external_mass_kg = 0.0 if config == "M0" else mass_kg
    checks = {
        "platform_mesh_declared": platform_mesh is not None,
        "platform_visual_present": platform_geom is not None,
        "one_degree_of_freedom": model.nq == 1 and model.nv == 1,
        "one_actuator": model.nu == 1,
        "joint_limit_is_plus_minus_90_deg": bool(
            model.jnt_limited[joint_id]
            and abs(float(model.jnt_range[joint_id, 0]) + math.pi / 2) < 1e-10
            and abs(float(model.jnt_range[joint_id, 1]) - math.pi / 2) < 1e-10
        ),
        "collision_disabled": int(model.geom_contype.sum()) == 0
        and int(model.geom_conaffinity.sum()) == 0,
        "external_mass_matches_record": abs(
            external_mass_kg - EXPECTED_EXTERNAL_MASS_KG[config]
        ) < 1e-9,
    }

    return {
        "configuration": config,
        "xml": str(xml_path),
        "loaded": True,
        "nq": int(model.nq),
        "nv": int(model.nv),
        "nu": int(model.nu),
        "nbody": int(model.nbody),
        "ngeom": int(model.ngeom),
        "joint_axis": [float(v) for v in model.jnt_axis[joint_id]],
        "joint_range_rad": [float(v) for v in model.jnt_range[joint_id]],
        "moving_mass_kg_including_m0_regularization": mass_kg,
        "declared_external_mass_kg": EXPECTED_EXTERNAL_MASS_KG[config],
        "gravity_probe_q_rad": 0.4,
        "gravity_probe_zero_control_qacc_rad_s2": float(data.qacc[0]),
        "collision_enabled_geom_count": int(
            ((model.geom_contype != 0) | (model.geom_conaffinity != 0)).sum()
        ),
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "models",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "results",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    records = []
    for config in CONFIGS:
        xml_path = args.models / f"1DOF-{config}.xml"
        records.append(validate(xml_path, config))

    report = {
        "mujoco_version": mujoco.__version__,
        "scope": "structural MJCF checks only; no hardware dynamics claim",
        "all_passed": all(bool(record["passed"]) for record in records),
        "models": records,
    }
    (args.output / "model_validation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    with (args.output / "tables" / "model_validation.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "configuration",
                "loaded",
                "nq",
                "nu",
                "joint_axis_x",
                "joint_axis_y",
                "joint_axis_z",
                "limit_min_rad",
                "limit_max_rad",
                "external_mass_kg",
                "gravity_probe_qacc_rad_s2",
                "collision_enabled_geom_count",
                "passed",
            ]
        )
        for record in records:
            writer.writerow(
                [
                    record["configuration"],
                    record["loaded"],
                    record["nq"],
                    record["nu"],
                    *record["joint_axis"],
                    *record["joint_range_rad"],
                    record["declared_external_mass_kg"],
                    record["gravity_probe_zero_control_qacc_rad_s2"],
                    record["collision_enabled_geom_count"],
                    record["passed"],
                ]
            )

    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["all_passed"] else 1)


if __name__ == "__main__":
    main()
