#!/usr/bin/env python3
"""Write the frozen RS06 hardware episode matrix and minimum repeat plan."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
CONTROLLERS = ("H1", "H2")
PROFILE_LONG = {
    "P01": "P01_slow_triangle",
    "P02": "P02_multisine",
    "P03": "P03_smooth_levels",
    "P04": "P04_chirp",
    "P05": "P05_wide_sine",
    "P06": "P06_heldout_composite",
    "P07": "P07_heldout_sine_hold",
}


def unique_episodes() -> list[dict]:
    rows = []
    for controller in CONTROLLERS:
        for fixture in ("M0", "B0", "B1"):
            for profile in ("P01", "P02", "P03"):
                rows.append({"split": "calibration", "controller_id": controller, "fixture_id": fixture, "profile_id": profile})
        for fixture in ("B0", "B1"):
            for profile in ("P04", "P05"):
                rows.append({"split": "model_selection", "controller_id": controller, "fixture_id": fixture, "profile_id": profile})
        for profile in ("P06", "P07"):
            rows.append({"split": "held_out", "controller_id": controller, "fixture_id": "G1", "profile_id": profile})
        rows.append({"split": "held_out", "controller_id": controller, "fixture_id": "B1", "profile_id": "P06"})
    for row in rows:
        row["profile_definition_id"] = PROFILE_LONG[row["profile_id"]]
        row["episode_id"] = "__".join((row["split"], row["controller_id"], row["fixture_id"], row["profile_definition_id"]))
    return rows


def main() -> None:
    episodes = unique_episodes()
    repeats = {"calibration": 3, "model_selection": 3, "held_out": 5}
    matrix = {
        "schema_version": "phyintel-chapter02-rs06-frozen-episode-matrix-v1",
        "unique_episode_count": len(episodes),
        "split_counts": {split: sum(row["split"] == split for row in episodes) for split in repeats},
        "modification_from_reference_v1_1": [
            "remove B2 calibration combinations because no B2 fixture is available",
            "replace B2 by B1 for P04/P05 model selection",
            "retain the six held-out G1/B1 combinations",
        ],
        "controllers": {
            "H1": {"kp": 50.0, "kd": 3.38, "mode": "position"},
            "H2": {"kp": 100.0, "kd": 1.95, "mode": "position"},
        },
        "minimum_accepted_repeats": repeats,
        "minimum_accepted_physical_run_count": sum(repeats[row["split"]] for row in episodes),
        "episodes": episodes,
        "g1_free_fall_note": "Free-fall trials are separate supporting data and are not substitutes for G1/P06 or G1/P07 closed-loop episodes.",
    }
    HARDWARE.mkdir(parents=True, exist_ok=True)
    (HARDWARE / "frozen-episode-matrix.json").write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    plan = []
    for episode in episodes:
        for repeat in range(1, repeats[episode["split"]] + 1):
            run_id = f"{episode['fixture_id'].lower()}_{episode['controller_id'].lower()}_{episode['profile_id'].lower()}_repeat{repeat:02d}"
            manifest = f"hardware/trajectory-suites/{episode['controller_id']}/manifest.json"
            extras = " --acknowledge-p06-position-steps" if episode["profile_id"] == "P06" else ""
            command = (
                "python scripts/run_chapter02_rs06_hardware_collection.py "
                f"--manifest {manifest} --trajectory-ids {episode['profile_id']} "
                f"--run-id {run_id} --fixture-id {episode['fixture_id']} "
                f"--fixture-description '<MEASURED_FIXTURE_DESCRIPTION>' "
                f"--output-dir hardware/collected/{run_id}{extras} "
                "<REQUIRED_PORT_CENTER_AND_SAFETY_ARGUMENTS>"
            )
            plan.append(
                {
                    **episode,
                    "accepted_repeat_index": repeat,
                    "run_id": run_id,
                    "manifest": manifest,
                    "dry_run_command_template": command,
                    "execute_only_after_dry_run_and_review": "append --execute",
                }
            )
    path = HARDWARE / "minimum-run-plan.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(plan[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(plan)
    print(json.dumps({"unique_episodes": len(episodes), "minimum_accepted_runs": len(plan), "matrix": str(HARDWARE / 'frozen-episode-matrix.json'), "run_plan": str(path)}, indent=2))


if __name__ == "__main__":
    main()
