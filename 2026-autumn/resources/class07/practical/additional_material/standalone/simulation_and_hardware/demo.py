#!/usr/bin/env python3
"""Summarize the supplied visual-yaw physical deployment log."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load_rows() -> list[dict]:
    with (ROOT / "data" / "deployment_run.jsonl").open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    rows = load_rows()
    pose_ages = np.asarray([row["pose_age_s"] for row in rows if row.get("pose_age_s") is not None], dtype=float)
    report = {
        "classification": "recorded physical visual-yaw run; no hardware command is sent by this script",
        "steps": len(rows),
        "policy_ran_steps": sum(bool(row.get("policy_ran")) for row in rows),
        "pose_available_fraction": sum(bool(row.get("has_pose")) for row in rows) / len(rows),
        "pose_age_s": {"min": float(pose_ages.min()), "median": float(np.median(pose_ages)), "max": float(pose_ages.max())},
        "negative_pose_age_rows": int((pose_ages < 0).sum()),
        "maximum_current_mA": max(float(row.get("max_current_ma", 0.0)) for row in rows),
        "maximum_temperature_C": max(float(row.get("max_temperature_c", 0.0)) for row in rows),
        "maximum_tracking_error_rad": max(float(row.get("tracking_error_rad", 0.0)) for row in rows),
        "visible_marker_ids": sorted({marker for row in rows for marker in row.get("visible_ids", [])}),
        "scope": "one recorded deployment; not a reliability estimate or camera calibration",
    }
    output = ROOT / "outputs" / "hardware_replay.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
