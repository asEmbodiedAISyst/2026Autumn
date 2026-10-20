#!/usr/bin/env python3
"""Run full embedded V5 H2 B0 identification and show saved before/after analysis."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import matplotlib
import mujoco
import numpy as np
import pandas as pd

from replay_presentation import present

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "platform_models" / "AsBrainBox-Platform---XC330-B0" / "AsBrainBox-Platform---XC330-B0_actuated_mujoco_compatible.xml"
DATA = ROOT / "data" / "v5_h2_full"
EPISODE_RE = re.compile(r"^B0__H2__(P\d+_[A-Za-z0-9_]+)__R(\d+)$")
REPRESENTATIVE = "B0__H2__P04_chirp__R03"


def replay(frame: pd.DataFrame, commands: pd.DataFrame, damping: float, armature: float) -> np.ndarray:
    model = mujoco.MjModel.from_xml_path(str(MODEL))
    model.dof_damping[0] = damping; model.dof_armature[0] = armature
    data = mujoco.MjData(model)
    data.qpos[0] = float(frame.position_meas_rad.iloc[0]); mujoco.mj_forward(model, data)
    ts = frame.t_state_s.to_numpy(dtype=float) - float(frame.t_state_s.iloc[0])
    tc = commands.t_command_s.to_numpy(dtype=float) - float(commands.t_command_s.iloc[0])
    qc = commands.position_cmd_rad.to_numpy(dtype=float)
    prediction = np.empty(len(frame)); prediction[0] = data.qpos[0]
    for i, t in enumerate(ts[1:], 1):
        while data.time + 1e-12 < t:
            data.ctrl[0] = float(np.interp(data.time, tc, qc)); mujoco.mj_step(model, data)
        prediction[i] = data.qpos[0]
    return prediction


def rmse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean((a - b) ** 2)))


def episode_key(path: Path) -> tuple[int, str, int]:
    match = EPISODE_RE.match(path.name)
    if not match:
        raise ValueError(f"Unexpected V5 H2 episode directory: {path.name}")
    profile, repeat = match.groups()
    return int(profile[1:3]), profile, int(repeat)


def load_records() -> dict[str, tuple[str, int, pd.DataFrame, pd.DataFrame]]:
    if not DATA.is_dir():
        raise FileNotFoundError(f"Full local V5 H2 data is missing: {DATA}")
    records: dict[str, tuple[str, int, pd.DataFrame, pd.DataFrame]] = {}
    for directory in sorted((item for item in DATA.iterdir() if item.is_dir()), key=episode_key):
        _, profile, repeat = episode_key(directory)
        records[directory.name] = (
            profile,
            repeat,
            pd.read_parquet(directory / "telemetry_events.parquet"),
            pd.read_parquet(directory / "command_events.parquet"),
        )
    if len(records) != 15:
        raise RuntimeError(f"Expected all 15 V5 B0/H2 episodes (P01–P05, R01–R03); found {len(records)}")
    return records


def build_summary(metrics: pd.DataFrame, trace: pd.DataFrame, fitted: tuple[float, float], output: Path, *, disabled: bool, save_only: bool) -> Path | None:
    """Create the complete experiment layout after the representative MuJoCo replay."""
    if disabled:
        return None
    if save_only:
        matplotlib.use("Agg", force=True); interactive = False
    else:
        try:
            import PyQt6  # noqa: F401
            matplotlib.use("QtAgg", force=True); interactive = True
        except ImportError:
            matplotlib.use("Agg", force=True); interactive = False
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    figure = plt.figure(figsize=(15, 9), facecolor="#101722")
    grid = figure.add_gridspec(2, 3, width_ratios=(1.25, 1.25, .8), hspace=.38, wspace=.34)
    per_episode = figure.add_subplot(grid[0, :2])
    per_profile = figure.add_subplot(grid[1, 0])
    representative = figure.add_subplot(grid[1, 1])
    card = figure.add_subplot(grid[:, 2]); card.set_axis_off()
    for axis in (per_episode, per_profile, representative):
        axis.set_facecolor("#182433"); axis.grid(alpha=.22, axis="y")

    labels = metrics.episode.str.replace("B0__H2__", "", regex=False).str.replace("__", " ", regex=False)
    x = np.arange(len(metrics)); width = .36
    per_episode.bar(x - width / 2, np.rad2deg(metrics.before_rmse_rad), width, color="#aeb8c4", label="before identification")
    per_episode.bar(x + width / 2, np.rad2deg(metrics.after_rmse_rad), width, color="#ffb347", label="after identification")
    per_episode.set_xticks(x, labels, rotation=45, ha="right", fontsize=8)
    per_episode.set(title="All 15 recorded V5 H2 experiments — RMSE", ylabel="RMSE (deg)")
    per_episode.legend(frameon=False, ncol=2)
    for index, row in metrics.iterrows():
        if row.split == "validation":
            per_episode.axvspan(index - .5, index + .5, color="#4dd0e1", alpha=.05)

    grouped = metrics.groupby("profile", sort=False)[["before_rmse_rad", "after_rmse_rad"]].mean()
    gx = np.arange(len(grouped))
    per_profile.bar(gx - width / 2, np.rad2deg(grouped.before_rmse_rad), width, color="#aeb8c4", label="before")
    per_profile.bar(gx + width / 2, np.rad2deg(grouped.after_rmse_rad), width, color="#ffb347", label="after")
    per_profile.set_xticks(gx, grouped.index.str.slice(0, 3))
    per_profile.set(title="Mean RMSE by test profile", ylabel="RMSE (deg)")
    per_profile.legend(frameon=False)

    representative.plot(trace.time_s, np.rad2deg(trace.hardware_position_rad), color="#4dd0e1", lw=2.0, label="V5 hardware")
    representative.plot(trace.time_s, np.rad2deg(trace.before_identification_rad), color="#aeb8c4", lw=1.5, ls="--", label="before")
    representative.plot(trace.time_s, np.rad2deg(trace.after_identification_rad), color="#ffb347", lw=1.8, label="after")
    representative.set(title="Held-out P04 chirp R03", xlabel="time (s)", ylabel="angle (deg)")
    representative.legend(frameon=False, fontsize=8)

    train = metrics.query("split == 'calibration'")
    validation = metrics.query("split == 'validation'")
    card.text(.05, .96, "CLASS 04\nFULL V5 H2 IDENTIFICATION\n────────────────\n\nDATA COVERAGE\n15 physical V5 episodes\nP01–P05, R01–R03\n\nFIT\nR01/R02: 10 episodes\nVALIDATE\nR03: 5 episodes\n\nEFFECTIVE FIT\ndamping  = %.4g\narmature = %.4g\n\nVALIDATION RMSE\nbefore: %.4f rad\nafter:  %.4f rad\nchange: %+.1f%%\n\nCOLOR KEY\ncyan = V5 hardware\ngray = baseline\norange = identified\n\nAll charts are saved\nfor later analysis." % (fitted[0], fitted[1], validation.before_rmse_rad.mean(), validation.after_rmse_rad.mean(), 100 * (validation.after_rmse_rad.mean() / validation.before_rmse_rad.mean() - 1)), va="top", family="monospace", fontsize=10.5, linespacing=1.5, bbox={"boxstyle": "round,pad=.9", "facecolor": "#182433", "edgecolor": "#4dd0e1", "alpha": .95})
    figure.suptitle("Before and after system identification — complete embedded V5 H2 experiment", fontsize=15, y=.98)
    output.parent.mkdir(exist_ok=True)
    figure.savefig(output, dpi=170, facecolor=figure.get_facecolor(), bbox_inches="tight")
    if interactive:
        figure.canvas.manager.set_window_title("Class 04 — full V5 H2 before/after analysis")
        plt.show(block=True)
    plt.close(figure)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-viewer", action="store_true", help="headless/CI only; normal lesson opens the MuJoCo viewer")
    parser.add_argument("--no-dashboard", action="store_true", help="disable both visual dashboards")
    parser.add_argument("--save-only", action="store_true", help="save analysis images without opening plot windows")
    parser.add_argument("--playback-speed", type=float, default=0.5, help="visual replay multiplier (default: 0.5)")
    args = parser.parse_args()
    if args.playback_speed <= 0:
        parser.error("--playback-speed must be greater than zero")

    records = load_records()
    print("Phase 1/4: loaded 15 recorded V5 B0/H2 hardware episodes.", flush=True)
    candidates = [(d, a) for d in (0.0, .002, .01, .04, .08) for a in (0.0, .0002, .001, .003)]
    calibration_keys = [key for key, (_, repeat, _, _) in records.items() if repeat in (1, 2)]
    validation_keys = [key for key, (_, repeat, _, _) in records.items() if repeat == 3]
    scores: dict[tuple[float, float], float] = {}
    for candidate_number, candidate in enumerate(candidates, start=1):
        print(f"Phase 2/4: fitting candidate {candidate_number}/{len(candidates)} — damping={candidate[0]:.4g}, armature={candidate[1]:.4g}.", flush=True)
        errors = []
        for key in calibration_keys:
            _, _, frame, commands = records[key]
            errors.append(rmse(replay(frame, commands, *candidate), frame.position_meas_rad.to_numpy()))
        scores[candidate] = float(np.mean(errors))
    chosen = min(candidates, key=scores.__getitem__)
    print(f"Phase 2/4: selected effective damping={chosen[0]:.4g}, armature={chosen[1]:.4g} using R01/R02.", flush=True)

    out = ROOT / "outputs"; out.mkdir(exist_ok=True)
    rows: list[dict[str, object]] = []
    full_trace: list[pd.DataFrame] = []
    representative_trace: pd.DataFrame | None = None
    print("Phase 3/4: replaying the baseline and identified models for all 15 episodes.", flush=True)
    for episode_number, (key, (profile, repeat, frame, commands)) in enumerate(records.items(), start=1):
        print(f"Phase 3/4: episode {episode_number}/{len(records)} — {key}.", flush=True)
        measured = frame.position_meas_rad.to_numpy(dtype=float)
        baseline = replay(frame, commands, 0.0, 0.0)
        fitted = replay(frame, commands, *chosen)
        time_s = frame.t_state_s.to_numpy(dtype=float) - float(frame.t_state_s.iloc[0])
        split = "calibration" if repeat in (1, 2) else "validation"
        rows.append({"episode": key, "profile": profile, "repeat": repeat, "split": split, "samples": len(frame), "duration_s": float(time_s[-1]), "before_rmse_rad": rmse(baseline, measured), "after_rmse_rad": rmse(fitted, measured)})
        trace = pd.DataFrame({"episode": key, "profile": profile, "repeat": repeat, "time_s": time_s, "hardware_position_rad": measured, "before_identification_rad": baseline, "after_identification_rad": fitted})
        full_trace.append(trace)
        if key == REPRESENTATIVE:
            representative_trace = trace
    if representative_trace is None:
        raise RuntimeError(f"Representative validation episode not found: {REPRESENTATIVE}")

    metrics = pd.DataFrame(rows).sort_values(["profile", "repeat"], kind="stable").reset_index(drop=True)
    all_replays = pd.concat(full_trace, ignore_index=True)
    metrics.to_csv(out / "b0_full_h2_episode_metrics.csv", index=False)
    all_replays.to_csv(out / "b0_full_h2_replays.csv", index=False)
    representative_trace.to_csv(out / "b0_identification_replay.csv", index=False)

    print("Phase 4/4: opening the paced held-out P04 chirp R03 replay and live comparison dashboard.", flush=True)
    representative_plot = present(MODEL, representative_trace.time_s.to_numpy(), representative_trace.hardware_position_rad.to_numpy(), representative_trace.after_identification_rad.to_numpy(), "Class 04 — full H2 identified replay", "representative held-out V5 P04 chirp, R03\ncalibration used P01–P05, repeats R01/R02\nwhite cursor = moving MuJoCo frame", out / "b0_identification_gap.png", no_viewer=args.no_viewer, no_dashboard=(args.no_dashboard or args.save_only), playback_speed=args.playback_speed, baseline=representative_trace.before_identification_rad.to_numpy())
    summary_plot = build_summary(metrics, representative_trace, chosen, out / "b0_full_h2_before_after_summary.png", disabled=args.no_dashboard, save_only=args.save_only)

    validation = metrics.query("split == 'validation'")
    report = {
        "classification": "full simulation-only identification using locally embedded physical V5 B0/H2 data; no live hardware collection",
        "dataset": "15 V5 B0/H2 episodes: P01–P05, R01–R03",
        "calibration": "P01–P05 repeats R01 and R02 (10 episodes)",
        "validation": "P01–P05 repeat R03 (5 held-out episodes)",
        "representative_visual_replay": REPRESENTATIVE,
        "validation_mean_rmse_before_rad": float(validation.before_rmse_rad.mean()),
        "validation_mean_rmse_after_rad": float(validation.after_rmse_rad.mean()),
        "calibration_mean_rmse_after_rad": scores[chosen],
        "fitted_effective_damping": chosen[0],
        "fitted_effective_armature": chosen[1],
        "saved_episode_metrics": "outputs/b0_full_h2_episode_metrics.csv",
        "saved_full_replays": "outputs/b0_full_h2_replays.csv",
        "saved_representative_plot": str(representative_plot.relative_to(ROOT)) if representative_plot else None,
        "saved_summary_plot": str(summary_plot.relative_to(ROOT)) if summary_plot else None,
    }
    (out / "b0_identification_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
