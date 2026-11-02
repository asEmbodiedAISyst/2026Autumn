#!/usr/bin/env python3
"""Apply a student-selected stale-pose gate to the recorded deployment."""

from __future__ import annotations

import argparse
import json

from demo import load_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pose-age-s", type=float, default=0.15)
    args = parser.parse_args()
    if args.max_pose_age_s <= 0:
        raise SystemExit("maximum pose age must be positive")
    rows = load_rows()
    usable = [row for row in rows if row.get("has_pose") and row.get("pose_age_s") is not None and 0.0 <= row["pose_age_s"] <= args.max_pose_age_s]
    stale = [row for row in rows if row.get("pose_age_s") is not None and row["pose_age_s"] > args.max_pose_age_s]
    future = [row for row in rows if row.get("pose_age_s") is not None and row["pose_age_s"] < 0.0]
    result = {
        "max_pose_age_s": args.max_pose_age_s,
        "total_rows": len(rows),
        "usable_pose_rows": len(usable),
        "stale_pose_rows": len(stale),
        "negative_age_rows": len(future),
        "gate_warning": "negative ages indicate a timestamp/clock interpretation issue and are not silently accepted",
        "prompt": "Choose a safe hold/stop behavior for stale or invalid poses and justify it before any physical trial.",
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
