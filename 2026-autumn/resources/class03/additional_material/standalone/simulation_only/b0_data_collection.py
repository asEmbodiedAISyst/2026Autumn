#!/usr/bin/env python3
"""Replay a V5 B0 command profile in the validated 110 g B0 MJCF."""
from __future__ import annotations
import json
import argparse
from pathlib import Path
import mujoco
import numpy as np
import pandas as pd
from replay_presentation import present

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models" / "1DOF-B0.xml"
DATA = ROOT / "data" / "v5_h2_calibration" / "P02_multisine"
KP = 2.5
KV = 0.05
TORQUE_LIMIT_NM = 0.1551

def simulate(frame: pd.DataFrame, commands: pd.DataFrame, damping: float = 0.0) -> np.ndarray:
    model = mujoco.MjModel.from_xml_path(str(MODEL)); model.dof_damping[0] = damping
    data = mujoco.MjData(model); data.qpos[0] = float(frame.position_meas_rad.iloc[0]); mujoco.mj_forward(model, data)
    ts = frame.t_state_s.to_numpy() - float(frame.t_state_s.iloc[0])
    tc = commands.t_command_s.to_numpy() - float(commands.t_command_s.iloc[0])
    qc = commands.position_cmd_rad.to_numpy(); out = np.empty(len(frame)); out[0] = data.qpos[0]
    for i, target_t in enumerate(ts[1:], 1):
        while data.time + 1e-12 < target_t:
            reference = float(np.interp(data.time, tc, qc))
            torque = KP * (reference - float(data.qpos[0])) - KV * float(data.qvel[0])
            data.ctrl[0] = float(np.clip(torque, -TORQUE_LIMIT_NM, TORQUE_LIMIT_NM))
            mujoco.mj_step(model, data)
        out[i] = data.qpos[0]
    return out

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-viewer", action="store_true", help="headless/CI only; normal lesson opens the MuJoCo viewer")
    parser.add_argument("--no-dashboard", action="store_true", help="disable the live comparison dashboard")
    parser.add_argument("--playback-speed", type=float, default=1.0, help="visual replay multiplier (default: 1.0)")
    args = parser.parse_args()
    if args.playback_speed <= 0:
        parser.error("--playback-speed must be greater than zero")
    frame = pd.read_parquet(DATA / "telemetry_events.parquet")
    commands = pd.read_parquet(DATA / "command_events.parquet")
    simulated = simulate(frame, commands)
    t = frame.t_state_s.to_numpy() - float(frame.t_state_s.iloc[0]); measured = frame.position_meas_rad.to_numpy()
    out = ROOT / "outputs"; out.mkdir(exist_ok=True)
    result = pd.DataFrame({"time_s": t, "hardware_position_rad": measured, "simulation_position_rad": simulated})
    result.to_csv(out / "b0_simulation_collection.csv", index=False)
    rmse = float(np.sqrt(np.mean((simulated - measured) ** 2)))
    dashboard = present(MODEL, t, measured, simulated, "Class 03 — pre-identification Sim2Real gap", "B0 XC330 platform\nNo system identification applied", out / "b0_pre_identification_gap.png", no_viewer=args.no_viewer, no_dashboard=args.no_dashboard, playback_speed=args.playback_speed)
    report = {"classification": "simulation-only replay against embedded V5 physical record", "model": str(MODEL.relative_to(ROOT)), "fixture_external_moving_mass_kg": 0.110, "controller": {"type": "explicit saturated PD teaching controller", "kp_Nm_per_rad": KP, "kv_Nm_s_per_rad": KV, "torque_limit_Nm": TORQUE_LIMIT_NM}, "episode": str(frame.episode_id.iloc[0]), "samples": len(frame), "rmse_rad": rmse, "system_identification_applied": False, "plot": str(dashboard.relative_to(ROOT)) if dashboard else None}
    (out / "b0_simulation_collection.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
if __name__ == "__main__": main()
