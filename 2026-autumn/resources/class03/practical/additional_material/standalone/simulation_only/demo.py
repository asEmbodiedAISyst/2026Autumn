#!/usr/bin/env python3
"""Validate and optionally view the five prepared single-axis MJCF models."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import mujoco

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ("M0", "B0", "B1", "B2", "G1")


def descendants_mass(model: mujoco.MjModel, root_name: str) -> float:
    root_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, root_name)
    total = 0.0
    for body_id in range(1, model.nbody):
        parent = int(model.body_parentid[body_id])
        while parent and parent != root_id:
            parent = int(model.body_parentid[parent])
        if parent == root_id:
            total += float(model.body_mass[body_id])
    return total


def inspect(config: str) -> dict[str, object]:
    path = ROOT / "models" / f"1DOF-{config}.xml"
    model = mujoco.MjModel.from_xml_path(str(path))
    data = mujoco.MjData(model)
    joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "actuator_joint")
    data.qpos[0] = 0.4
    data.ctrl[0] = 0.0
    mujoco.mj_forward(model, data)
    return {
        "configuration": config,
        "nq_nv_nu": [int(model.nq), int(model.nv), int(model.nu)],
        "joint_axis": model.jnt_axis[joint_id].tolist(),
        "joint_range_rad": model.jnt_range[joint_id].tolist(),
        "moving_mass_kg": descendants_mass(model, "XC330-M288-T"),
        "gravity_bias_at_q_0p4_Nm": float(data.qfrc_bias[0]),
        "collision_enabled_geoms": int(((model.geom_contype != 0) | (model.geom_conaffinity != 0)).sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewer", choices=CONFIGS)
    parser.add_argument("--viewer-seconds", type=float, default=10.0)
    args = parser.parse_args()
    report = {
        "scope": "structural MJCF inspection; not physical dynamic validation",
        "mujoco_version": mujoco.__version__,
        "models": [inspect(config) for config in CONFIGS],
    }
    output = ROOT / "outputs" / "model_inspection.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if args.viewer:
        from mujoco import viewer

        model = mujoco.MjModel.from_xml_path(str(ROOT / "models" / f"1DOF-{args.viewer}.xml"))
        data = mujoco.MjData(model)
        with viewer.launch_passive(model, data) as window:
            deadline = time.monotonic() + args.viewer_seconds
            while window.is_running() and time.monotonic() < deadline:
                mujoco.mj_step(model, data)
                window.sync()
                time.sleep(float(model.opt.timestep))


if __name__ == "__main__":
    main()
