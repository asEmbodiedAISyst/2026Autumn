#!/usr/bin/env python3
"""Replay one reserved reference through baseline and frozen fitted MuJoCo models."""

from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "minimal_heldout_episode_B1_H2_P06_R01.csv.gz"
KP = 2.106448
KV = 0.202115


def replay(model_path: Path, frame: pd.DataFrame) -> np.ndarray:
    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    data.qpos[0] = float(frame["hardware_position_rad"].iloc[0])
    data.qvel[0] = float(frame["hardware_velocity_rad_s"].iloc[0])
    mujoco.mj_forward(model, data)
    sample_time = frame["time_s"].to_numpy()
    q_ref = frame["recorded_inner_position_reference_rad"].to_numpy()
    v_ref = frame["recorded_inner_velocity_reference_rad_s"].to_numpy()
    predictions = np.empty(len(frame))
    predictions[0] = data.qpos[0]
    for index in range(1, len(frame)):
        target_t = sample_time[index]
        while data.time + 1e-12 < target_t:
            position_reference = float(np.interp(data.time, sample_time, q_ref))
            velocity_reference = float(np.interp(data.time, sample_time, v_ref))
            data.ctrl[0] = KP * position_reference + KV * velocity_reference
            mujoco.mj_step(model, data)
        predictions[index] = data.qpos[0]
    return predictions


def rmse(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.sqrt(np.mean((left - right) ** 2)))


def main() -> None:
    frame = pd.read_csv(DATA)
    hardware = frame["hardware_position_rad"].to_numpy()
    records = {}
    for name, path in {
        "baseline": ROOT / "models" / "Synthetic_Baseline" / "H2" / "B1.xml",
        "fitted": ROOT / "models" / "Hardware_Fitted" / "H2" / "B1.xml",
    }.items():
        prediction = replay(path, frame)
        supplied = frame["synthetic_baseline_position_rad" if name == "baseline" else "hardware_fitted_position_rad"].to_numpy()
        records[name] = {
            "replayed_rmse_vs_hardware_rad": rmse(prediction, hardware),
            "supplied_rmse_vs_hardware_rad": rmse(supplied, hardware),
            "replay_vs_supplied_rmse_rad": rmse(prediction, supplied),
        }
    report = {
        "classification": "simulation replay of one reserved episode; no hardware connection",
        "episode_id": str(frame["episode_id"].iloc[0]),
        "samples": len(frame),
        "controller": "H2",
        "records": records,
    }
    output = ROOT / "outputs" / "simulation_replay.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
