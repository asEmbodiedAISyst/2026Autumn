#!/usr/bin/env python3
"""Summarize paired physical telemetry and frozen simulation predictions."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def metric(frame: pd.DataFrame, column: str) -> float:
    return float(np.sqrt(np.mean((frame[column] - frame["hardware_position_rad"]) ** 2)))


def main() -> None:
    frame = pd.read_csv(ROOT / "data" / "minimal_heldout_episode_B1_H2_P06_R01.csv.gz")
    baseline = metric(frame, "synthetic_baseline_position_rad")
    fitted = metric(frame, "hardware_fitted_position_rad")
    report = {
        "classification": "paired recorded hardware and simulation data; no live actuator operation",
        "episode_id": str(frame.episode_id.iloc[0]),
        "condition": {"fixture": "B1", "controller": "H2", "profile": "P06", "split": "held_out"},
        "baseline_position_rmse_rad": baseline,
        "fitted_position_rmse_rad": fitted,
        "relative_rmse_change_percent": 100.0 * (fitted / baseline - 1.0),
        "peak_abs_hardware_current_A": float(frame.hardware_current_A.abs().max()),
        "temperature_range_C": [float(frame.hardware_temperature_C.min()), float(frame.hardware_temperature_C.max())],
        "scope": "one reserved episode; use the aggregate table for the 30-episode result",
    }
    output = ROOT / "outputs" / "paired_replay.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
