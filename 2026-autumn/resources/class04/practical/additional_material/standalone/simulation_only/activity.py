#!/usr/bin/env python3
"""Measure one saved candidate over a student-selected held-out window."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=("baseline", "fitted"), default="fitted")
    parser.add_argument("--start-s", type=float, default=0.0)
    parser.add_argument("--end-s", type=float, default=9.0)
    args = parser.parse_args()
    frame = pd.read_csv(ROOT / "data" / "minimal_heldout_episode_B1_H2_P06_R01.csv.gz")
    selected = frame[(frame.time_s >= args.start_s) & (frame.time_s <= args.end_s)]
    if len(selected) < 2:
        raise SystemExit("selected window contains fewer than two samples")
    column = "synthetic_baseline_position_rad" if args.candidate == "baseline" else "hardware_fitted_position_rad"
    residual = selected[column].to_numpy() - selected["hardware_position_rad"].to_numpy()
    result = {
        "split": "held_out",
        "candidate": args.candidate,
        "window_s": [args.start_s, args.end_s],
        "samples": len(selected),
        "position_rmse_rad": float(np.sqrt(np.mean(residual**2))),
        "mean_signed_residual_rad": float(np.mean(residual)),
        "maximum_abs_residual_rad": float(np.max(np.abs(residual))),
        "prompt": "Propose one cause and one new measurement that could distinguish it; do not refit this held-out episode.",
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
