#!/usr/bin/env python3
"""Relate prediction residuals to available physical context channels."""

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
    args = parser.parse_args()
    frame = pd.read_csv(ROOT / "data" / "minimal_heldout_episode_B1_H2_P06_R01.csv.gz")
    column = "synthetic_baseline_position_rad" if args.candidate == "baseline" else "hardware_fitted_position_rad"
    absolute_error = (frame[column] - frame.hardware_position_rad).abs()
    current = frame.hardware_current_A.abs()
    correlation = float(np.corrcoef(absolute_error, current)[0, 1])
    result = {
        "candidate": args.candidate,
        "absolute_error_current_correlation": correlation,
        "interpretation_warning": "correlation does not identify a cause; device current is not independent shaft torque",
        "prompt": "Would an external angle, shaft torque, supply-voltage or timing measurement best test your proposed explanation, and why?",
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
