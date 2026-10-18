#!/usr/bin/env python3
"""Plot normalized Chapter 2 RS06 episodes without accessing hardware."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FIELDS = (
    "time_s",
    "position_cmd_rad",
    "position_transmitted_rad",
    "position_acknowledged_rad",
    "position_meas_rad",
    "velocity_meas_rad_s",
    "torque_feedback_Nm",
    "tracking_error_command_rad",
    "tracking_error_acknowledged_rad",
    "command_saturated",
    "valid",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _float(row: Mapping[str, str], field: str) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field!r} in normalized episode") from exc
    if not math.isfinite(value):
        raise ValueError(f"Non-finite {field!r} in normalized episode")
    return value


def _bool(row: Mapping[str, str], field: str) -> bool:
    value = str(row.get(field, "")).strip().lower()
    if value in {"true", "1"}:
        return True
    if value in {"false", "0"}:
        return False
    raise ValueError(f"Invalid Boolean {field!r} in normalized episode")


def _read_episode(path: Path) -> List[Dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = set(REQUIRED_FIELDS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(
                f"Episode {path} is missing fields: {', '.join(sorted(missing))}"
            )
        rows = list(reader)
    if not rows:
        raise ValueError(f"Episode has no samples: {path}")
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plot every normalized episode in a completed Chapter 2 RS06 run. "
            "This is offline-only and never accesses the serial port."
        )
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="defaults to RUN_DIR/plots",
    )
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_dir = args.run_dir.resolve()
    package_dir = run_dir / "chapter02-hardware"
    manifest_path = package_dir / "dataset-manifest.json"
    verification_path = package_dir / "verification.json"
    if not manifest_path.is_file() or not verification_path.is_file():
        parser.error(
            "RUN_DIR must contain chapter02-hardware/dataset-manifest.json and "
            "verification.json"
        )
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    if verification.get("passed") is not True:
        parser.error("refusing to plot a run whose verification did not pass")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    episodes = manifest.get("episodes")
    if not isinstance(episodes, list) or not episodes:
        parser.error("dataset manifest contains no episodes")
    if not isinstance(args.dpi, int) or not 72 <= args.dpi <= 600:
        parser.error("--dpi must be within 72..600")

    output_dir = (args.output_dir or (run_dir / "plots")).resolve()
    plot_manifest_path = output_dir / "plot-manifest.json"
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite:
        parser.error(
            f"refusing to overwrite non-empty plot directory: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = ROOT / ".cache" / "matplotlib"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    try:
        import matplotlib
        import numpy as np
    except ImportError:
        parser.error(
            "plotting requires matplotlib and numpy; install them with "
            "'python -m pip install matplotlib numpy'"
        )

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    episode_data: List[Dict[str, Any]] = []
    plot_records: List[Dict[str, Any]] = []
    for episode in episodes:
        episode_file = package_dir / str(episode["episode_file"])
        if not episode_file.is_file():
            parser.error(f"episode file not found: {episode_file}")
        expected_hash = episode.get("episode_sha256")
        observed_hash = sha256_file(episode_file)
        if expected_hash and observed_hash != expected_hash:
            parser.error(f"episode hash mismatch: {episode_file}")
        rows = _read_episode(episode_file)
        arrays = {
            field: np.asarray([_float(row, field) for row in rows], dtype=float)
            for field in REQUIRED_FIELDS
            if field not in {"command_saturated", "valid"}
        }
        saturated = np.asarray(
            [_bool(row, "command_saturated") for row in rows], dtype=bool
        )
        valid = np.asarray([_bool(row, "valid") for row in rows], dtype=bool)
        time_s = arrays["time_s"]
        if len(time_s) >= 2:
            target_velocity = np.gradient(
                arrays["position_transmitted_rad"], time_s, edge_order=1
            )
        else:
            target_velocity = np.zeros_like(time_s)

        profile_id = str(episode["profile_id"])
        episode_id = str(episode["episode_id"])
        figure, axes = plt.subplots(4, 1, figsize=(12, 11), sharex=True)
        axes[0].plot(time_s, arrays["position_cmd_rad"], "k--", label="requested")
        axes[0].plot(
            time_s,
            arrays["position_transmitted_rad"],
            color="tab:blue",
            label="transmitted",
        )
        axes[0].plot(
            time_s,
            arrays["position_acknowledged_rad"],
            color="tab:orange",
            alpha=0.8,
            label="acknowledged",
        )
        axes[0].plot(
            time_s,
            arrays["position_meas_rad"],
            color="tab:green",
            label="measured",
        )
        axes[0].set_ylabel("position [rad]")
        axes[0].legend(ncol=4, fontsize=8)

        axes[1].plot(time_s, target_velocity, "k--", label="target finite diff")
        axes[1].plot(
            time_s,
            arrays["velocity_meas_rad_s"],
            color="tab:blue",
            label="measured",
        )
        axes[1].set_ylabel("velocity [rad/s]")
        axes[1].legend(ncol=2, fontsize=8)

        axes[2].plot(
            time_s, arrays["torque_feedback_Nm"], color="tab:red"
        )
        axes[2].axhline(0.0, color="0.5", linewidth=0.7)
        axes[2].set_ylabel("torque feedback [Nm]")

        axes[3].plot(
            time_s,
            arrays["tracking_error_command_rad"],
            label="requested - measured",
        )
        axes[3].plot(
            time_s,
            arrays["tracking_error_acknowledged_rad"],
            label="acknowledged - measured",
        )
        axes[3].axhline(0.0, color="0.5", linewidth=0.7)
        axes[3].set_ylabel("tracking error [rad]")
        axes[3].set_xlabel("nominal time [s]")
        axes[3].legend(ncol=2, fontsize=8)

        for axis in axes:
            axis.grid(True, alpha=0.25)
        rmse = float(
            np.sqrt(np.mean(np.square(arrays["tracking_error_command_rad"])))
        )
        figure.suptitle(
            f"{profile_id} | samples={len(rows)} | valid={np.mean(valid):.3f} | "
            f"saturated={int(np.sum(saturated))} | tracking RMSE={rmse:.5f} rad"
        )
        output_path = output_dir / f"{profile_id}__timeseries.png"
        figure.savefig(output_path, dpi=args.dpi, bbox_inches="tight")
        plt.close(figure)

        episode_data.append(
            {
                "profile_id": profile_id,
                "episode_id": episode_id,
                "time_s": time_s,
                "command": arrays["position_transmitted_rad"],
                "measured": arrays["position_meas_rad"],
            }
        )
        plot_records.append(
            {
                "profile_id": profile_id,
                "episode_id": episode_id,
                "source_episode_file": str(episode_file.relative_to(run_dir)),
                "source_episode_sha256": observed_hash,
                "plot_file": str(output_path.relative_to(output_dir)),
                "plot_sha256": sha256_file(output_path),
            }
        )

    overview, overview_axes = plt.subplots(
        len(episode_data),
        1,
        figsize=(12, max(3.0, 2.4 * len(episode_data))),
        squeeze=False,
    )
    for axis, episode in zip(overview_axes[:, 0], episode_data):
        axis.plot(episode["time_s"], episode["command"], "k--", label="transmitted")
        axis.plot(episode["time_s"], episode["measured"], label="measured")
        axis.set_ylabel(f"{episode['profile_id']}\n[rad]")
        axis.grid(True, alpha=0.25)
        axis.legend(ncol=2, fontsize=8, loc="upper right")
    overview_axes[-1, 0].set_xlabel("nominal time [s]")
    overview.suptitle("Chapter 2 RS06 collection overview")
    overview_path = output_dir / "collection_overview.png"
    overview.savefig(overview_path, dpi=args.dpi, bbox_inches="tight")
    plt.close(overview)

    plot_manifest = {
        "schema_version": "phyintel-chapter02-rs06-plots-v1",
        "run_dir": str(run_dir),
        "source_dataset_manifest_file": str(manifest_path.relative_to(run_dir)),
        "source_dataset_manifest_sha256": sha256_file(manifest_path),
        "source_verification_file": str(verification_path.relative_to(run_dir)),
        "source_verification_sha256": sha256_file(verification_path),
        "matplotlib_version": matplotlib.__version__,
        "dpi": args.dpi,
        "episode_plots": plot_records,
        "overview_plot_file": str(overview_path.relative_to(output_dir)),
        "overview_plot_sha256": sha256_file(overview_path),
    }
    write_json(plot_manifest_path, plot_manifest)
    print(f"Plots: {output_dir}")
    print(f"Plot manifest: {plot_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
