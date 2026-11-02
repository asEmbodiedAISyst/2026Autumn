#!/usr/bin/env python3
"""Compare fresh and delayed/dropped visual measurements in a yaw-control toy simulation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def wrap_degrees(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def simulate(latency_ms: float, drop_every: int, duration_s: float = 4.0) -> dict[str, float | int]:
    dt = 0.05
    delay_steps = round(latency_ms / 1000.0 / dt)
    yaw = 0.0
    history = [yaw]
    held_measurement = yaw
    drops = 0
    for step in range(round(duration_s / dt)):
        source_index = max(0, len(history) - 1 - delay_steps)
        candidate = history[source_index]
        if drop_every > 0 and (step + 1) % drop_every == 0:
            drops += 1
        else:
            held_measurement = candidate
        error = wrap_degrees(90.0 - held_measurement)
        # A responsive controller makes stale measurements consequential:
        # delayed feedback continues to apply a correction after the cube has
        # already moved, creating overshoot rather than a coincidental slower
        # approach to the target.
        velocity = float(np.clip(8.0 * error, -60.0, 60.0))
        yaw += velocity * dt
        history.append(yaw)
    return {
        "final_yaw_deg": yaw,
        "final_abs_goal_error_deg": abs(wrap_degrees(90.0 - yaw)),
        "delay_steps": delay_steps,
        "dropped_packets": drops,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latency-ms", type=float, default=150.0)
    parser.add_argument("--drop-every", type=int, default=5)
    args = parser.parse_args()
    if args.latency_ms < 0 or args.drop_every < 0:
        raise SystemExit("latency and drop interval must be nonnegative")
    result = {
        "classification": "simulation-only timing intervention",
        "control_period_ms": 50,
        "goal_yaw_deg": 90,
        "fresh": simulate(0.0, 0),
        "intervention": simulate(args.latency_ms, args.drop_every),
        "prompt": "Explain how capture time, arrival time, held measurements and dropouts change the feedback loop.",
    }
    output = ROOT / "outputs" / "timing_activity.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
