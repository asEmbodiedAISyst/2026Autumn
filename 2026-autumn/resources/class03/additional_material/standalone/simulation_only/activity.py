#!/usr/bin/env python3
"""Measure how a controlled mass change alters the B0 dynamic response."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def moving_mass(model: mujoco.MjModel) -> float:
    link_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "Link")
    return float(sum(model.body_mass[body_id] for body_id in range(link_id, model.nbody)))


def response(model: mujoco.MjModel, torque_nm: float, duration_s: float) -> dict[str, float]:
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    full_mass = np.zeros((model.nv, model.nv))
    mujoco.mj_fullM(model, data, full_mass)
    data.ctrl[0] = torque_nm
    mujoco.mj_forward(model, data)
    initial_acceleration = float(data.qacc[0])
    while data.time < duration_s:
        mujoco.mj_step(model, data)
    return {
        "joint_inertia_kg_m2": float(full_mass[0, 0]),
        "initial_acceleration_rad_s2": initial_acceleration,
        "position_after_pulse_rad": float(data.qpos[0]),
        "velocity_after_pulse_rad_s": float(data.qvel[0]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("B0",), default="B0")
    parser.add_argument("--payload-scale", type=float, default=1.25)
    parser.add_argument("--torque-nm", type=float, default=0.05)
    parser.add_argument("--duration-s", type=float, default=0.10)
    args = parser.parse_args()
    if args.payload_scale <= 0:
        raise SystemExit("payload scale must be positive")
    if not 0 < args.torque_nm <= 0.1551:
        raise SystemExit("torque must be greater than zero and no more than 0.1551 N m")
    if args.duration_s <= 0:
        raise SystemExit("duration must be positive")
    model = mujoco.MjModel.from_xml_path(str(ROOT / "models" / f"1DOF-{args.model}.xml"))
    baseline_mass = moving_mass(model)
    baseline = response(model, args.torque_nm, args.duration_s)
    assembly_ids = [body_id for body_id in range(model.nbody) if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or "").startswith(("Pin_", "Payload_"))]
    for body_id in assembly_ids:
        model.body_mass[body_id] *= args.payload_scale
        model.body_inertia[body_id] *= args.payload_scale
    changed_mass = moving_mass(model)
    changed = response(model, args.torque_nm, args.duration_s)
    result = {
        "investigation": "B0 response to the same constant torque before and after a hypothetical complete payload-assembly mass change",
        "model": args.model,
        "accepted_baseline_external_moving_mass_kg": baseline_mass,
        "controlled_change": "mass and rotational inertia of both complete pin-payload assemblies scaled; geometry and link retained",
        "assembly_bodies_changed": len(assembly_ids),
        "payload_scale": args.payload_scale,
        "hypothetical_external_moving_mass_kg": changed_mass,
        "applied_torque_Nm": args.torque_nm,
        "pulse_duration_s": args.duration_s,
        "baseline_response": baseline,
        "hypothetical_response": changed,
        "prompt": "How did the larger joint inertia change acceleration and motion under the same torque, and why is the 132 g case not an as-built B0 claim?",
    }
    path = ROOT / "outputs" / "b0_inertia_response_activity.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
