#!/usr/bin/env python3
"""Safely collect RS06 P01--P07 and export a Chapter-2-style dataset."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import sharklog
except ImportError:  # Keep this entry point usable without the optional logger.
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
    PROFILE_BY_TRAJECTORY_ID,
    export_chapter02_hardware_dataset,
    validate_identifier,
)
from motor_identification_trajectories import load_suite
from run_motor_identification_suite import (
    _print_plan,
    _validate_args,
    _validate_operating_center_offsets,
    _validate_suite_offsets,
    build_parser as build_runner_parser,
    run_suite,
)


LOGGER_NAME = "rs06.chapter02_collection"
LOGGER = sharklog.getLogger(LOGGER_NAME)


def build_parser() -> argparse.ArgumentParser:
    parser = build_runner_parser()
    parser.description = (
        "Replay a hash-verified Chapter 2 RS06 P01--P07 suite using the existing "
        "MagicLimb control-box transport, preserve raw feedback, and export a "
        "Chapter-2-style hardware dataset. Without --execute this is a dry run."
    )
    for action in parser._actions:
        if action.dest in {"kp", "kd"}:
            action.help = argparse.SUPPRESS
    parser.add_argument(
        "--run-id",
        required=True,
        help="stable evidence/run label, for example m0_repeat01",
    )
    parser.add_argument(
        "--fixture-id",
        default="M0",
        help="declared hardware fixture/configuration ID (default: %(default)s)",
    )
    parser.add_argument(
        "--fixture-description",
        default="RS06 motor-only M0 configuration",
    )
    parser.add_argument(
        "--fixture-metadata-json",
        type=Path,
        help="optional JSON with measured fixture, mounting, inertia, or revision data",
    )
    parser.add_argument("--operator", help="optional operator label")
    parser.add_argument("--temperature-c", type=float, help="optional measured temperature")
    parser.add_argument(
        "--supply-voltage-v", type=float, help="optional measured supply voltage"
    )
    parser.add_argument("--notes", default="")
    parser.add_argument(
        "--chapter-package-name",
        default="chapter02-hardware",
        help="subdirectory created inside --output-dir",
    )
    parser.add_argument(
        "--acknowledge-p06-position-steps",
        action="store_true",
        help=(
            "required with --execute when P06 is selected; acknowledges that "
            "the source P06 definition contains abrupt operating-point steps"
        ),
    )
    return parser


def _load_optional_json(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("--fixture-metadata-json must contain one JSON object")
    return value


def _validate_chapter_manifest(
    manifest: Dict[str, Any], trajectory_ids: Sequence[str]
) -> None:
    chapter = manifest.get("chapter02")
    if not isinstance(chapter, dict):
        raise ValueError(
            "Manifest is not a Chapter 2 RS06 suite; generate it with "
            "generate_chapter02_rs06_hardware_trajectories.py"
        )
    unknown = set(trajectory_ids) - set(PROFILE_BY_TRAJECTORY_ID)
    if unknown:
        raise ValueError(
            "Chapter 2 collector only accepts P01 through P07; got "
            + ", ".join(sorted(unknown))
        )


def _bind_manifest_gains(manifest: Dict[str, Any], args: argparse.Namespace) -> None:
    """Use the hash-bound manifest as the only replay gain source."""

    if args.kp is not None or args.kd is not None:
        raise ValueError(
            "Do not pass --kp or --kd to the Chapter 2 collector; replay gains "
            "are read exclusively from manifest.json"
        )
    configuration = manifest.get("control_configuration")
    if not isinstance(configuration, dict):
        raise ValueError("Manifest is missing control_configuration")
    try:
        args.kp = float(configuration["kp"])
        args.kd = float(configuration["kd"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "Manifest control_configuration must contain numeric kp and kd"
        ) from exc


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    sharklog.init(name=LOGGER_NAME, debug=args.verbose)
    try:
        validate_identifier("run_id", args.run_id)
        validate_identifier("fixture_id", args.fixture_id)
        validate_identifier("chapter_package_name", args.chapter_package_name)
        if args.execute and args.output_dir is None:
            raise ValueError(
                "--output-dir is required with --execute so the evidence location "
                "is explicit and is not silently selected from the wall clock"
            )
        if args.temperature_c is not None and not -100.0 <= args.temperature_c <= 250.0:
            raise ValueError("--temperature-c is outside the supported metadata range")
        if args.supply_voltage_v is not None and not 0.0 < args.supply_voltage_v <= 100.0:
            raise ValueError("--supply-voltage-v must be within 0..100 V")
        fixture_metadata = _load_optional_json(args.fixture_metadata_json)
        manifest, trajectories = load_suite(args.manifest, args.trajectory_ids)
        _validate_chapter_manifest(
            manifest, [trajectory.trajectory_id for trajectory in trajectories]
        )
        _bind_manifest_gains(manifest, args)
        _validate_args(args)
        selected_ids = {trajectory.trajectory_id for trajectory in trajectories}
        if args.execute and "P06" in selected_ids and not args.acknowledge_p06_position_steps:
            raise ValueError(
                "P06 contains abrupt position-command steps inherited from the "
                "source definition; review its generated vmax/amax and add "
                "--acknowledge-p06-position-steps to execute it"
            )
        _validate_suite_offsets(trajectories, args.max_position_deviation)
        _validate_operating_center_offsets(
            trajectories, args.max_operating_center_offset
        )
        output_dir = (
            args.output_dir
            if args.output_dir is not None
            else Path("course_resources/collected_data") / f"dry_run_{args.run_id}"
        )
        chapter_package = output_dir / args.chapter_package_name
        if args.execute and chapter_package.exists() and not args.overwrite:
            raise FileExistsError(
                f"Refusing to overwrite existing Chapter 2 package: {chapter_package}"
            )
        _print_plan(args, manifest, trajectories, output_dir)
        print(f"Chapter fixture: {args.fixture_id} ({args.fixture_description})")
        print(
            "Chapter profiles: "
            + ", ".join(
                str(trajectory.parameters["chapter_profile_id"])
                for trajectory in trajectories
            )
        )
        print(
            "Hardware controller metadata: "
            f"{manifest['control_configuration']['controller_id']} "
            f"KP={manifest['control_configuration']['kp']:.9g}, "
            f"KD={manifest['control_configuration']['kd']:.9g}"
        )
        if "P06" in selected_ids:
            print(
                "WARNING: P06 preserves abrupt center-offset steps from the source "
                "profile; inspect its discrete target velocity and acceleration."
            )
    except (ValueError, FileNotFoundError, FileExistsError, json.JSONDecodeError, OSError) as exc:
        parser.error(str(exc))
        return 2

    if not args.execute:
        print()
        print("DRY RUN ONLY: the serial port was not opened and no files were created.")
        print(
            "After checking the manifest gains, fixture, and hardware stop, add "
            "mechanical limits, feedback limits, --output-dir, and --execute."
        )
        return 0

    run_exit_code = run_suite(args, manifest, trajectories, output_dir)
    try:
        package_dir = export_chapter02_hardware_dataset(
            output_dir,
            args.manifest,
            manifest,
            trajectories,
            run_id=args.run_id,
            fixture_id=args.fixture_id,
            fixture_description=args.fixture_description,
            fixture_metadata=fixture_metadata,
            extra_context={
                "operator": args.operator,
                "temperature_c": args.temperature_c,
                "supply_voltage_v": args.supply_voltage_v,
                "notes": args.notes,
            },
            package_name=args.chapter_package_name,
            overwrite=args.overwrite,
        )
        verification = json.loads(
            (package_dir / "verification.json").read_text(encoding="utf-8")
        )
        print(f"Chapter 2 package: {package_dir}")
        print(f"Verification passed: {verification['passed']}")
        if not verification["passed"] and run_exit_code == 0:
            return 3
    except Exception as exc:
        LOGGER.error("Failed to export Chapter 2 hardware package: %s", exc)
        return run_exit_code if run_exit_code != 0 else 1
    return run_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
