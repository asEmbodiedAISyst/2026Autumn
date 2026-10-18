#!/usr/bin/env python3
"""Build the complete 32-episode RS06 Sim-Position release."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import generate_chapter02_rs06_sim_position_base as generator


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data/chapter-02/releases/rs06-sim-data-v1"
SOURCE_ROOT = ROOT / "source-assets/mjcf"
PROFILE_DIR = RELEASE / "profile-tables"


def write_profile_tables(contract: dict) -> dict:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    dt = 1.0 / float(contract["simulation"]["sample_rate_hz"])
    records = []
    by_id = {}
    for profile_id, profile in contract["profiles"].items():
        time, command = generator.build_profile(profile, dt)
        destination = PROFILE_DIR / f"{profile_id}.csv"
        with destination.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["profile_time_s", "position_cmd_rad"])
            writer.writerows(zip(time, command))
        record = {
            "profile_id": profile_id,
            "file": str(destination.relative_to(ROOT)),
            "sha256": generator.sha256_file(destination),
            "sample_count": int(time.size),
            "duration_s": float(time[-1] - time[0]),
            "command_min_rad": float(command.min()),
            "command_max_rad": float(command.max()),
        }
        records.append(record)
        by_id[profile_id] = record
    manifest = {
        "schema_version": "phyintel-canonical-rs06-profile-tables-v1",
        "source_release_id": contract["release_id"],
        "sample_rate_hz": contract["simulation"]["sample_rate_hz"],
        "time_column": "profile_time_s",
        "command_column": "position_cmd_rad",
        "profiles": records,
    }
    manifest_path = PROFILE_DIR / "profile-manifest.json"
    generator.write_json(manifest_path, manifest)

    dataset_path = RELEASE / "sim-position-manifest.json"
    dataset = generator.read_json(dataset_path)
    dataset["profile_table_manifest_file"] = str(manifest_path.relative_to(ROOT))
    dataset["profile_table_manifest_sha256"] = generator.sha256_file(manifest_path)
    for episode in dataset["episodes"]:
        episode["simulation_template_episode_id"] = episode["episode_id"]
        episode["profile_table_sha256"] = by_id[episode["profile_id"]]["sha256"]
    generator.write_json(dataset_path, dataset)
    return manifest


def source_model_checks(contract: dict) -> dict[str, bool]:
    models = [RELEASE / "model-sources" / f"{fixture}.xml" for fixture in contract["fixtures"]]
    roots = [ET.parse(path).getroot() for path in models]
    joints = [root.find(".//joint") for root in roots]
    m0_root = roots[list(contract["fixtures"]).index("M0")]
    m0_body = m0_root.find(".//body[@name='playload-1']")
    m0_inertial = None if m0_body is None else m0_body.find("inertial")
    m0_visual = None if m0_body is None else m0_body.find("geom[@name='playload-1_visual']")
    return {
        "all_four_fixture_sources_present": len(models) == 4 and all(path.is_file() for path in models),
        "all_joint_names_are_rs06_joint": all(joint is not None and joint.get("name") == "rs06_joint" for joint in joints),
        "m0_visual_has_no_collision_or_density": (
            m0_visual is not None
            and m0_visual.get("contype") == "0"
            and m0_visual.get("conaffinity") == "0"
            and m0_visual.get("density") == "0"
        ),
        "m0_uses_declared_numerical_regularization": (
            m0_inertial is not None
            and float(m0_inertial.get("mass", "nan")) == 1.0e-6
            and m0_inertial.get("diaginertia") == "1e-12 1e-12 1e-12"
        ),
        "no_B2_fixture_declared": "B2" not in contract["fixtures"],
    }


def finalize_release(contract: dict, profile_manifest: dict) -> dict:
    manifest_path = RELEASE / "sim-position-manifest.json"
    manifest = generator.read_json(manifest_path)
    counts = Counter(episode["split"] for episode in manifest["episodes"])
    verification_path = RELEASE / "verification.json"
    verification = generator.read_json(verification_path)
    checks = source_model_checks(contract)
    checks.update(
        {
            "modified_matrix_has_32_episodes": manifest["episode_count"] == 32,
            "modified_matrix_split_counts_are_18_8_6": counts
            == Counter({"calibration": 18, "model_selection": 8, "held_out": 6}),
            "B1_replaces_B2_in_model_selection": {
                episode["fixture_id"]
                for episode in manifest["episodes"]
                if episode["split"] == "model_selection"
            }
            == {"B0", "B1"},
        }
    )
    verification["checks"].update(checks)
    verification["passed"] = all(verification["checks"].values())
    verification["matrix_split_counts"] = dict(sorted(counts.items()))
    generator.write_json(verification_path, verification)

    family = {
        "schema_version": "phyintel-chapter02-rs06-release-family-v1",
        "release_id": contract["release_id"],
        "sim_position": {
            "manifest_file": str(manifest_path.relative_to(ROOT)),
            "manifest_sha256": generator.sha256_file(manifest_path),
            "episode_count": 32,
            "role": "closed-loop fitting, selection, and held-out evaluation",
        },
        "sim_torque": {
            "manifest_file": "data/chapter-02/releases/rs06-sim-data-v1/sim-torque-manifest.json",
            "status": "generated-by-generate_chapter02_rs06_sim_torque_v1.py",
            "hardware_equivalent_claimed": False,
        },
        "hardware_position": {
            "controllers": ["H1", "H2"],
            "minimum_accepted_repeat_policy": {"calibration": 3, "model_selection": 3, "held_out": 5},
            "status": "collection-plan-only-until-physical-runs-exist",
        },
        "hardware_G1_free_fall": {
            "status": "schema-only-user-implements-protocol",
            "schema_file": "hardware/g1-free-fall-schema.json",
            "part_of_32_closed_loop_episode_matrix": False,
        },
        "canonical_profile_table_count": len(profile_manifest["profiles"]),
    }
    generator.write_json(RELEASE / "release-family-manifest.json", family)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--refresh-model-sources", action="store_true")
    args = parser.parse_args()
    contract = generator.read_json(generator.CONTRACT_PATH)
    generator.prepare_model_sources(args.source_root, contract, args.refresh_model_sources)
    paths = generator.build_models(contract)
    summaries, episodes = generator.write_dataset(contract, paths)
    generator.write_parameter_table(contract)
    generator.create_plots(contract, summaries, episodes)
    generator.verify(contract, summaries, paths)
    profile_manifest = write_profile_tables(contract)
    verification = finalize_release(contract, profile_manifest)
    print(json.dumps(verification, indent=2, sort_keys=True))
    return 0 if verification["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
