#!/usr/bin/env python3
"""Generate hash-protected 50 Hz RS06 versions of Chapter 2 P01--P07."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Optional

try:
    import sharklog
except ImportError:  # Keep offline generation usable without the optional logger.
    import logging

    class _SharklogCompatibility:
        @staticmethod
        def getLogger(name: str) -> logging.Logger:
            return logging.getLogger(name)

        @staticmethod
        def init(name: str, debug: bool = False) -> None:
            logging.basicConfig(
                level=logging.DEBUG if debug else logging.INFO,
                format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            )

    sharklog = _SharklogCompatibility()

from chapter02_rs06_hardware import (
    REFERENCE_PROFILE_IDS,
    build_chapter02_trajectories,
    load_reference_contract,
    write_chapter02_trajectory_suite,
)
from motor_identification_trajectories import trajectory_statistics


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_ROOT = ROOT / "data/chapter-02/releases/rs06-sim-data-v1"
LOGGER_NAME = "rs06.chapter02_trajectory_generator"
LOGGER = sharklog.getLogger(LOGGER_NAME)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate deterministic, center-relative 50 Hz RS06 P01--P07 "
            "trajectories from the downloaded Chapter 2 contract. No hardware "
            "is accessed."
        )
    )
    parser.add_argument(
        "--reference-contract",
        type=Path,
        default=DEFAULT_REFERENCE_ROOT / "experiment-contract.json",
    )
    parser.add_argument(
        "--reference-generator",
        type=Path,
        default=ROOT / "scripts" / "generate_chapter02_rs06_sim_position_v1.py",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "hardware" / "trajectory-suites" / "H1",
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=50.0,
        help="hardware command/sample rate in Hz (requested workflow default: 50)",
    )
    parser.add_argument(
        "--amplitude-scale",
        type=float,
        default=1.0,
        help=(
            "default position-excursion multiplier for all seven profiles "
            "(reference-form default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--speed-scale",
        type=float,
        default=1.0,
        help=(
            "default time-compression multiplier for all seven profiles "
            "(reference-form default: %(default)s)"
        ),
    )
    for profile_id in REFERENCE_PROFILE_IDS:
        short_id = profile_id.split("_", 1)[0].lower()
        parser.add_argument(
            f"--{short_id}-amplitude-scale",
            type=float,
            help=(
                f"{short_id.upper()}-only position override; defaults to "
                "--amplitude-scale"
            ),
        )
        parser.add_argument(
            f"--{short_id}-speed-scale",
            type=float,
            help=(
                f"{short_id.upper()}-only time-compression override; defaults "
                "to --speed-scale"
            ),
        )
    parser.add_argument(
        "--controller-id",
        default="H1",
        help=(
            "hardware controller-condition ID, such as H1 or H2; this is "
            "independent of the source simulation C1/C2 labels "
            "(default: %(default)s)"
        ),
    )
    parser.add_argument("--kp", type=float, required=True)
    parser.add_argument("--kd", type=float, required=True)
    parser.add_argument(
        "--max-offset",
        type=float,
        default=1.0,
        help="reviewed maximum center-relative target magnitude in rad",
    )
    parser.add_argument(
        "--max-target-velocity",
        type=float,
        default=10.0,
        help="reviewed maximum discrete target velocity in rad/s",
    )
    parser.add_argument(
        "--max-target-acceleration",
        type=float,
        default=500.0,
        help="reviewed maximum discrete target acceleration in rad/s^2",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    sharklog.init(name=LOGGER_NAME, debug=args.verbose)
    try:
        if not args.reference_contract.is_file():
            raise FileNotFoundError(args.reference_contract)
        if not args.reference_generator.is_file():
            raise FileNotFoundError(args.reference_generator)
        reference_contract = load_reference_contract(args.reference_contract)
        amplitude_overrides = {
            profile_id: getattr(
                args, f"{profile_id.split('_', 1)[0].lower()}_amplitude_scale"
            )
            for profile_id in REFERENCE_PROFILE_IDS
        }
        speed_overrides = {
            profile_id: getattr(
                args, f"{profile_id.split('_', 1)[0].lower()}_speed_scale"
            )
            for profile_id in REFERENCE_PROFILE_IDS
        }
        amplitude_scales = {
            profile_id: (
                float(amplitude_overrides[profile_id])
                if amplitude_overrides[profile_id] is not None
                else float(args.amplitude_scale)
            )
            for profile_id in REFERENCE_PROFILE_IDS
        }
        speed_scales = {
            profile_id: (
                float(speed_overrides[profile_id])
                if speed_overrides[profile_id] is not None
                else float(args.speed_scale)
            )
            for profile_id in REFERENCE_PROFILE_IDS
        }
        trajectories = build_chapter02_trajectories(
            reference_contract,
            sample_rate_hz=args.sample_rate,
            amplitude_scales=amplitude_scales,
            speed_scales=speed_scales,
        )
        manifest_path = write_chapter02_trajectory_suite(
            args.output_dir,
            trajectories,
            reference_contract_path=args.reference_contract,
            reference_generator_path=args.reference_generator,
            controller_id=args.controller_id,
            controller_kp=args.kp,
            controller_kd=args.kd,
            max_offset_rad=args.max_offset,
            max_velocity_rad_s=args.max_target_velocity,
            max_acceleration_rad_s2=args.max_target_acceleration,
            overwrite=args.overwrite,
        )
    except (ValueError, FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        LOGGER.error("%s", exc)
        return 2

    LOGGER.info("Generated Chapter 2 RS06 trajectories:")
    for trajectory in trajectories:
        statistics = trajectory_statistics(trajectory)
        LOGGER.info(
            "  %s %-18s samples=%d span=%.2fs amp=%.6g speed=%.6g "
            "range=[%+.4f,%+.4f]rad vmax=%.4frad/s amax=%.4frad/s^2",
            trajectory.trajectory_id,
            trajectory.name,
            len(trajectory.q_offset_rad),
            (len(trajectory.q_offset_rad) - 1) / trajectory.sample_rate_hz,
            trajectory.parameters["amplitude_scale"],
            trajectory.parameters["speed_scale"],
            statistics["min_offset_rad"],
            statistics["max_offset_rad"],
            statistics["max_abs_target_velocity_rad_s"],
            statistics["max_abs_target_acceleration_rad_s2"],
        )
    LOGGER.info("Manifest: %s", manifest_path.resolve())
    LOGGER.info(
        "No hardware was accessed. Dry-run the collection script before adding --execute."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
