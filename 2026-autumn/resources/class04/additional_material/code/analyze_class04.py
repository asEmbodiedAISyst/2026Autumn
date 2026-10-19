#!/usr/bin/env python3
"""Reproduce the Class 04 tables, teaching subset, and paper figures."""

from pathlib import Path
import json
import shutil

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import font_manager


ROOT = Path(__file__).resolve().parents[2]
SUPPORT = ROOT / "additional_material"
DATA = SUPPORT / "data"
RESULTS = SUPPORT / "results"
FIGURES = ROOT / "paper" / "figures"
DEMO_ID = "B1__H2__P06_heldout_composite__R01"
POOR_ID = "G1__H1__P06_heldout_composite__R01"


def configure_style() -> None:
    regular = SUPPORT / "fonts" / "MiSans-Regular.ttf"
    semibold = SUPPORT / "fonts" / "MiSans-Semibold.ttf"
    for path in (regular, semibold):
        if path.exists():
            font_manager.fontManager.addfont(path)
    plt.rcParams.update({
        "font.family": "MiSans" if regular.exists() else "sans-serif",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.22,
        "figure.dpi": 160,
        "savefig.dpi": 220,
        "savefig.bbox": "tight",
    })


def rmse(a: pd.Series, b: pd.Series) -> float:
    return float(np.sqrt(np.mean(np.square(a.to_numpy() - b.to_numpy()))))


def episode_metrics(samples: pd.DataFrame) -> pd.DataFrame:
    rows = []
    keys = ["episode_id", "split", "fixture_id", "controller_id", "profile_id", "repetition"]
    for key, frame in samples.groupby(keys, sort=True):
        rows.append(dict(zip(keys, key)) | {
            "sample_count": len(frame),
            "duration_s": float(frame.time_s.max() - frame.time_s.min()),
            "fitted_rmse_rad": rmse(frame.hardware_fitted_position_rad, frame.hardware_position_rad),
            "baseline_rmse_rad": rmse(frame.synthetic_baseline_position_rad, frame.hardware_position_rad),
            "fitted_mae_rad": float(np.mean(np.abs(frame.hardware_fitted_position_rad - frame.hardware_position_rad))),
            "baseline_mae_rad": float(np.mean(np.abs(frame.synthetic_baseline_position_rad - frame.hardware_position_rad))),
            "fitted_bias_rad": float(np.mean(frame.hardware_fitted_position_rad - frame.hardware_position_rad)),
            "baseline_bias_rad": float(np.mean(frame.synthetic_baseline_position_rad - frame.hardware_position_rad)),
        })
    return pd.DataFrame(rows)


def draw_system_roles() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 1.55))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 2)
    ax.axis("off")
    boxes = [
        (0.25, "Experiment runner", "episode, command, time", "#E8F0FE"),
        (3.55, "XC330 controller", "inner reference, response", "#E6F4EA"),
        (6.85, "MuJoCo replay", "model, controller, output", "#FCE8E6"),
    ]
    for x, title, body, color in boxes:
        rect = plt.Rectangle((x, 0.45), 2.9, 1.15, fc=color, ec="#4A5568", lw=1.1)
        ax.add_patch(rect)
        ax.text(x + 1.45, 1.18, title, ha="center", va="center", weight="semibold", fontsize=10.5)
        ax.text(x + 1.45, 0.78, body, ha="center", va="center", fontsize=8.8)
    for start, end in ((3.18, 3.52), (6.48, 6.82)):
        ax.annotate("", xy=(end, 1.02), xytext=(start, 1.02),
                    arrowprops=dict(arrowstyle="->", lw=1.4, color="#4A5568"))
    fig.savefig(FIGURES / "system_roles.png", bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def draw_six_stage() -> None:
    labels = ["Introduction", "Claim2Design", "Design2Data", "Data2Model", "Model2Prototype", "Sim2Real"]
    captions = ["scope", "claims and tests", "synthetic design", "fit and select", "hardware record", "held-out check"]
    fig, ax = plt.subplots(figsize=(7.2, 2.0))
    ax.axis("off")
    for i, (label, caption) in enumerate(zip(labels, captions)):
        x = 0.4 + i * 1.15
        color = "#DCE6F1" if i < 3 else "#E7F2E7" if i < 5 else "#F7E4D6"
        ax.add_patch(plt.Rectangle((x, 0.55), 0.95, 0.95, fc=color, ec="#4A5568", lw=1))
        ax.text(x + 0.475, 1.1, label, ha="center", va="center", fontsize=7.6, weight="semibold")
        ax.text(x + 0.475, 0.76, caption, ha="center", va="center", fontsize=6.8)
        if i < 5:
            ax.annotate("", xy=(x + 1.13, 1.02), xytext=(x + 0.97, 1.02),
                        arrowprops=dict(arrowstyle="->", lw=1))
    ax.set_xlim(0.2, 7.35)
    ax.set_ylim(0.35, 1.7)
    fig.savefig(FIGURES / "six_stage_record.png", bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def draw_split_protocol(metrics: pd.DataFrame) -> None:
    counts = metrics.groupby(["split", "controller_id"]).size().unstack(fill_value=0)
    order = ["calibration", "model_selection", "held_out"]
    counts = counts.reindex(order)
    fig, ax = plt.subplots(figsize=(6.9, 3.35))
    x = np.arange(len(order))
    width = 0.34
    for j, ctrl in enumerate(["H1", "H2"]):
        vals = counts[ctrl].to_numpy()
        bars = ax.bar(x + (j - 0.5) * width, vals, width, label=ctrl,
                      color=["#4C78A8", "#F58518"][j])
        ax.bar_label(bars, padding=3, fontsize=8)
    ax.set_xticks(x, ["Calibration\nP01--P03", "Model selection\nP04--P05", "Held-out\nP06--P07"])
    ax.set_ylabel("Episodes")
    ax.set_ylim(0, max(counts.max()) * 1.26)
    ax.set_title("Data are opened in decision order; held-out records remain sealed until selection", pad=10)
    fig.legend(frameon=False, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 0.015))
    fig.subplots_adjust(left=0.10, right=0.98, top=0.84, bottom=0.24)
    fig.savefig(FIGURES / "data_split_protocol.png", bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
def draw_episode(samples: pd.DataFrame, episode_id: str, filename: str, title: str) -> None:
    frame = samples.loc[samples.episode_id == episode_id].sort_values("time_s")
    if frame.empty:
        raise ValueError(f"missing episode {episode_id}")
    t = frame.time_s.to_numpy()
    hw = frame.hardware_position_rad.to_numpy()
    fitted = frame.hardware_fitted_position_rad.to_numpy()
    baseline = frame.synthetic_baseline_position_rad.to_numpy()
    inner = frame.recorded_inner_position_reference_rad.to_numpy()
    external = frame.external_position_command_rad.to_numpy()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 5.35), sharex=True,
                                   gridspec_kw={"height_ratios": [2.0, 1.0]})
    ax1.plot(t, external, color="#9AA0A6", lw=1.0, ls=":", label="external command")
    ax1.plot(t, inner, color="#7E57C2", lw=1.0, ls="--", label="recorded inner reference")
    ax1.plot(t, hw, color="#202124", lw=1.35, label="hardware")
    ax1.plot(t, baseline, color="#E45756", lw=1.0, label="synthetic baseline")
    ax1.plot(t, fitted, color="#2A9D8F", lw=1.15, label="hardware-fitted model")
    ax1.set_ylabel("Position (rad)")
    ax1.set_title(title, pad=10)
    ax2.plot(t, baseline - hw, color="#E45756", lw=0.9, label="baseline residual")
    ax2.plot(t, fitted - hw, color="#2A9D8F", lw=0.95, label="fitted residual")
    ax2.axhline(0, color="#202124", lw=0.6)
    ax2.set_xlabel("Active-profile time (s)")
    ax2.set_ylabel("Error (rad)")
    ax2.legend(frameon=False, ncol=2, fontsize=7.5, loc="lower left")
    handles, labels = ax1.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, ncol=3, fontsize=7.3,
               loc="upper center", bbox_to_anchor=(0.5, 0.995))
    fig.subplots_adjust(left=0.12, right=0.98, top=0.82, bottom=0.11, hspace=0.30)
    fig.savefig(FIGURES / filename, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def draw_heldout_summary(metrics: pd.DataFrame) -> None:
    held = metrics.loc[metrics.split == "held_out"].copy()
    table = held.groupby(["fixture_id", "controller_id"], as_index=False).agg(
        fitted_rmse_rad=("fitted_rmse_rad", "mean"),
        baseline_rmse_rad=("baseline_rmse_rad", "mean"),
        episodes=("episode_id", "size"),
    )
    table.to_csv(RESULTS / "heldout_summary.csv", index=False)
    labels = [f"{r.fixture_id}-{r.controller_id}" for r in table.itertuples()]
    x = np.arange(len(table))
    width = 0.36
    fig, ax = plt.subplots(figsize=(6.8, 3.65))
    baseline_bars = ax.bar(x - width / 2, table.baseline_rmse_rad, width, label="synthetic baseline", color="#E45756")
    fitted_bars = ax.bar(x + width / 2, table.fitted_rmse_rad, width, label="hardware-fitted", color="#2A9D8F")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Mean episode RMSE (rad)")
    ax.set_title("Held-out position error (five repetitions per group)")
    fig.legend([baseline_bars, fitted_bars], ["synthetic baseline", "hardware-fitted"],
               frameon=False, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 0.015))
    fig.subplots_adjust(left=0.12, right=0.98, top=0.88, bottom=0.22)
    fig.savefig(FIGURES / "heldout_rmse_summary.png", bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def draw_parameter_bounds() -> None:
    with (DATA / "physical_parameter_sets.json").open() as f:
        params = json.load(f)
    names = ["Armature\n(kg m²)", "Damping\n(N m s/rad)", "Friction loss\n(N m)"]
    lower = np.array([0.0002, 0.003, 0.002])
    upper = np.array([0.010, 0.150, 0.050])
    keys = ["armature_kg_m2", "damping_Nm_s_per_rad", "frictionloss_Nm"]
    fig, axes = plt.subplots(1, 3, figsize=(7.6, 3.25))
    for i, ax in enumerate(axes):
        h1 = params["hardware_fitted"]["H1"][keys[i]]
        h2 = params["hardware_fitted"]["H2"][keys[i]]
        base = params["synthetic_baseline"][keys[i]]
        normalized = [(base - lower[i]) / (upper[i] - lower[i]),
                      (h1 - lower[i]) / (upper[i] - lower[i]),
                      (h2 - lower[i]) / (upper[i] - lower[i])]
        ax.bar([0, 1, 2], normalized, color=["#9AA0A6", "#4C78A8", "#F58518"])
        ax.set_xticks([0, 1, 2], ["baseline", "H1", "H2"], fontsize=7.7)
        ax.set_ylim(0, 1.16)
        ax.set_yticks([0, 0.5, 1], ["lower", "mid", "upper"])
        ax.set_title(names[i], fontsize=8.5, pad=7)
    fig.suptitle("Selected parameters within declared fitting bounds", fontsize=10, y=0.98)
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.22, top=0.74, wspace=0.43)
    fig.savefig(FIGURES / "parameter_bounds.png", bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)

    fitted = params["hardware_fitted"]
    pd.DataFrame(
        {
            "parameter": keys,
            "lower_bound": lower,
            "upper_bound": upper,
            "H1_value": [fitted["H1"][key] for key in keys],
            "H2_value": [fitted["H2"][key] for key in keys],
            "H1_at_upper_bound": [
                bool(np.isclose(fitted["H1"][key], limit, rtol=0, atol=1e-8))
                for key, limit in zip(keys, upper)
            ],
            "H2_at_upper_bound": [
                bool(np.isclose(fitted["H2"][key], limit, rtol=0, atol=1e-8))
                for key, limit in zip(keys, upper)
            ],
        }
    ).to_csv(RESULTS / "parameter_bound_summary.csv", index=False)
def draw_real_simulation_comparison(samples: pd.DataFrame) -> None:
    photos = SUPPORT / "demonstration" / "fixture_photos"
    simulations = RESULTS / "simulation_views"
    panels = [
        (photos / "B1_fixture_overview.jpg", "B1 physical experiment"),
        (simulations / "B1_H2_hardware_fitted.png", "B1 MuJoCo model"),
        (photos / "G1_fixture_overview.jpg", "G1 physical experiment"),
        (simulations / "G1_H2_hardware_fitted.png", "G1 MuJoCo model"),
    ]
    fig = plt.figure(figsize=(7.5, 9.35))
    grid = fig.add_gridspec(3, 2, height_ratios=[1.0, 1.0, 0.78], hspace=0.20, wspace=0.05)
    for index, (source, title) in enumerate(panels):
        panel = fig.add_subplot(grid[index // 2, index % 2])
        panel.imshow(plt.imread(source))
        panel.set_title(title, fontsize=11, weight="semibold", pad=7)
        panel.axis("off")

    frame = samples.loc[samples.episode_id == DEMO_ID].sort_values("time_s")
    ax = fig.add_subplot(grid[2, :])
    ax.plot(frame.time_s, frame.recorded_inner_position_reference_rad,
            color="#7E57C2", lw=1.0, ls="--", label="recorded inner reference")
    ax.plot(frame.time_s, frame.hardware_position_rad,
            color="#202124", lw=1.35, label="hardware")
    ax.plot(frame.time_s, frame.synthetic_baseline_position_rad,
            color="#E45756", lw=1.0, label="synthetic baseline")
    ax.plot(frame.time_s, frame.hardware_fitted_position_rad,
            color="#2A9D8F", lw=1.15, label="hardware-fitted model")
    ax.set_title("Matched held-out B1/H2 replay", fontsize=11, weight="semibold", pad=9)
    ax.set_xlabel("Active-profile time (s)")
    ax.set_ylabel("Position (rad)")
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, ncol=2, fontsize=8,
               loc="lower center", bbox_to_anchor=(0.5, 0.015))
    fig.subplots_adjust(left=0.08, right=0.98, top=0.97, bottom=0.09)
    fig.savefig(FIGURES / "physical_and_simulation_configurations.png", bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    configure_style()
    samples = pd.read_csv(DATA / "paired_simulation_hardware_samples.csv.gz")
    metrics = episode_metrics(samples)
    metrics.to_csv(RESULTS / "episode_metrics_recomputed.csv", index=False)
    held = metrics.loc[metrics.split == "held_out"].copy()
    overall = pd.DataFrame([{
        "heldout_episodes": len(held),
        "baseline_mean_episode_rmse_rad": held.baseline_rmse_rad.mean(),
        "fitted_mean_episode_rmse_rad": held.fitted_rmse_rad.mean(),
        "relative_reduction_percent": 100 * (1 - held.fitted_rmse_rad.mean() / held.baseline_rmse_rad.mean()),
    }])
    overall.to_csv(RESULTS / "overall_heldout_result.csv", index=False)
    held.sort_values("fitted_rmse_rad", ascending=False).head(5).to_csv(
        RESULTS / "largest_heldout_errors.csv", index=False)
    samples.loc[samples.episode_id == DEMO_ID].to_csv(
        DATA / "minimal_heldout_episode_B1_H2_P06_R01.csv.gz", index=False, compression="gzip")
    draw_system_roles()
    draw_six_stage()
    draw_split_protocol(metrics)
    draw_episode(samples, DEMO_ID, "heldout_demo_episode.png", "Held-out B1/H2 composite episode")
    draw_episode(samples, POOR_ID, "poor_agreement_episode.png", "Largest held-out fitted error: G1/H1 composite episode")
    draw_heldout_summary(metrics)
    draw_parameter_bounds()
    draw_real_simulation_comparison(samples)
    for figure in FIGURES.glob("*.png"):
        shutil.copy2(figure, RESULTS / figure.name)
    print(overall.to_string(index=False))
    print(f"Wrote {len(metrics)} episode rows and {len(list(FIGURES.glob('*.png')))} figures")


if __name__ == "__main__":
    main()
