#!/usr/bin/env python3
"""Reproduce the compact Class 05 tables and figures from stored V5 results."""

from pathlib import Path
import json

import cv2

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "additional_material" / "data"
DEMO = ROOT / "additional_material" / "demonstration"
RESULTS = ROOT / "additional_material" / "results"
FIGURES = ROOT / "paper" / "figures"
FONT_DIR = ROOT / "additional_material" / "fonts"
RESULTS.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(parents=True, exist_ok=True)

for path in FONT_DIR.glob("*.ttf"):
    font_manager.fontManager.addfont(path)
plt.rcParams.update({
    "font.family": "MiSans",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

COLORS = {"baseline": "#8c8c8c", "fitted": "#177e89", "accent": "#d95f02"}


def save(fig, name):
    fig.savefig(FIGURES / name, facecolor="white")
    fig.savefig(RESULTS / name, facecolor="white")
    plt.close(fig)


def draw_box(ax, xy, width, height, text, color, fontsize=9):
    box = FancyBboxPatch(xy, width, height, boxstyle="round,pad=0.025",
                         linewidth=1.2, edgecolor=color, facecolor=color + "18")
    ax.add_patch(box)
    ax.text(xy[0] + width / 2, xy[1] + height / 2, text,
            ha="center", va="center", fontsize=fontsize)


metrics = pd.read_csv(DATA / "episode_metrics.csv")
fits = pd.read_csv(DATA / "fitted_parameters.csv")
paired = pd.read_parquet(DATA / "two_motor_heldout_subset.parquet")

hardware_fits = fits[fits.model.eq("hardware_fitted")].copy()
for column, upper in [("armature_kg_m2", 0.010),
                      ("damping_Nm_s_per_rad", 0.150),
                      ("frictionloss_Nm", 0.050)]:
    hardware_fits[column + "_at_upper_bound"] = np.isclose(
        hardware_fits[column], upper, rtol=0, atol=1e-8)
bound_summary = pd.DataFrame({
    "parameter": ["armature_kg_m2", "damping_Nm_s_per_rad", "frictionloss_Nm"],
    "upper_bound": [0.010, 0.150, 0.050],
    "fits_at_upper_bound": [
        int(hardware_fits.armature_kg_m2_at_upper_bound.sum()),
        int(hardware_fits.damping_Nm_s_per_rad_at_upper_bound.sum()),
        int(hardware_fits.frictionloss_Nm_at_upper_bound.sum()),
    ],
    "fit_count": [len(hardware_fits)] * 3,
})
bound_summary.to_csv(RESULTS / "parameter_bound_summary.csv", index=False)

held = metrics[metrics.split.eq("held_out")].copy()
pivot = held.pivot_table(index=["motor_id", "controller_id"], columns="model",
                         values="position_rmse_rad", aggfunc="mean").reset_index()
pivot["reduction_percent"] = 100 * (
    pivot.synthetic_baseline - pivot.hardware_fitted) / pivot.synthetic_baseline
pivot.to_csv(RESULTS / "heldout_per_motor_controller.csv", index=False)

activity = pivot[pivot.motor_id.isin([0, 9])].copy()
activity.to_csv(RESULTS / "two_motor_activity_answer.csv", index=False)

summary = {
    "simultaneous_science_episodes": 125,
    "motor_records": 2000,
    "fits": 32,
    "heldout_simultaneous_episodes": 30,
    "heldout_motor_records": int(held.episode_id.nunique()),
    "heldout_baseline_mean_rmse_rad": float(
        held[held.model.eq("synthetic_baseline")].position_rmse_rad.mean()),
    "heldout_fitted_mean_rmse_rad": float(
        held[held.model.eq("hardware_fitted")].position_rmse_rad.mean()),
    "armature_upper_bound_count": int(hardware_fits.armature_kg_m2_at_upper_bound.sum()),
    "damping_upper_bound_count": int(hardware_fits.damping_Nm_s_per_rad_at_upper_bound.sum()),
    "friction_upper_bound_count": int(hardware_fits.frictionloss_Nm_at_upper_bound.sum()),
}
summary["heldout_rmse_reduction_percent"] = 100 * (
    summary["heldout_baseline_mean_rmse_rad"] - summary["heldout_fitted_mean_rmse_rad"]
) / summary["heldout_baseline_mean_rmse_rad"]
(RESULTS / "verified_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

# Evidence hierarchy: simultaneous independent fixtures are not a coupled hand.
fig, ax = plt.subplots(figsize=(7.1, 2.7))
ax.set_xlim(0, 12); ax.set_ylim(0, 3); ax.axis("off")
draw_box(ax, (0.15, 0.75), 3.1, 1.4,
         "One XC330 fixture\nlocal load and controller\nvalidated replay", "#3c78d8", 8.2)
draw_box(ax, (4.45, 0.75), 3.1, 1.4,
         "16 simultaneous fixtures\nshared power, buses and clock\nmechanically independent", "#177e89", 8.2)
draw_box(ax, (8.75, 0.75), 3.1, 1.4,
         "Coupled robot or hand\njoint and contact interactions\nnew validation required", "#d95f02", 8.2)
for start, end in ((3.35, 4.35), (7.65, 8.65)):
    ax.annotate("", xy=(end, 1.45), xytext=(start, 1.45),
                arrowprops=dict(arrowstyle="->", lw=1.4, color="#555555"))
ax.text(6, 2.65, "Increasing system claim; evidence does not transfer automatically",
        ha="center", va="center", fontweight="semibold", fontsize=9)
save(fig, "evidence_hierarchy.png")

# Shared channels and local channels.
fig, ax = plt.subplots(figsize=(7.1, 3.9))
ax.set_xlim(0, 10); ax.set_ylim(0, 6); ax.axis("off")
shared = [
    (0.20, "Command source\nand host clock", "#3c78d8"),
    (2.70, "Two U2D2 buses\nand USB timing", "#674ea7"),
    (5.20, "Shared 5 V supply\nand distribution", "#bf9000"),
    (7.70, "Room and run\nthermal history", "#a64d79"),
]
for x, text_value, color in shared:
    draw_box(ax, (x, 4.55), 2.1, 0.9, text_value, color, 7.4)
fixture_centers = []
for i in range(4):
    x = 0.20 + i * 2.50
    draw_box(ax, (x, 1.35), 2.1, 1.0,
             f"Fixture group {i + 1}\n4 independent axes", "#177e89", 7.4)
    fixture_centers.append(x + 1.05)
for shared_center in (1.25, 3.75, 6.25, 8.75):
    for fixture_center in fixture_centers:
        ax.plot([shared_center, fixture_center], [4.55, 2.35],
                color="#b8b8b8", lw=0.55, zorder=0)
ax.text(5, 0.55,
        "Local: actuator, printed link, payload, friction and encoder\n"
        "Shared: communication, supply, time base, software load and ambient conditions",
        ha="center", va="center", fontsize=7.8)
save(fig, "shared_and_local_effects.png")

# Data split and fit counts.
fig, ax = plt.subplots(figsize=(6.9, 3.4))
labels = ["Calibration", "Selection", "Held out"]
sim_counts = np.array([72, 23, 30])
motor_counts = sim_counts * 16
x = np.arange(3)
bars = ax.bar(x, sim_counts, color=["#3c78d8", "#177e89", "#d95f02"], width=0.62)
for b, s, m in zip(bars, sim_counts, motor_counts):
    ax.text(b.get_x() + b.get_width()/2, b.get_height() + 2,
            f"{s} simultaneous\n{m} motor records", ha="center", va="bottom", fontsize=8)
ax.set_xticks(x, labels); ax.set_ylabel("Simultaneous episodes")
ax.set_ylim(0, 92); ax.grid(axis="y", alpha=0.25)
ax.set_title("125 accepted science episodes; 2,000 motor-level records")
save(fig, "campaign_split.png")

# Held-out per-motor/controller heatmaps for fitted RMSE and reduction.
fig, axes = plt.subplots(2, 1, figsize=(7.15, 4.5), sharex=True)
for ax, value, title, cmap in [
    (axes[0], "hardware_fitted", "Frozen fitted model: held-out mean RMSE (rad)", "viridis"),
    (axes[1], "reduction_percent", "Reduction relative to synthetic baseline (%)", "RdYlGn")]:
    grid = pivot.pivot(index="controller_id", columns="motor_id", values=value).loc[["H1", "H2"]]
    im = ax.imshow(grid, aspect="auto", cmap=cmap)
    ax.set_yticks([0, 1], ["H1", "H2"]); ax.set_title(title)
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.015)
axes[1].set_xticks(range(16), range(16)); axes[1].set_xlabel("Motor ID")
fig.tight_layout()
save(fig, "per_motor_heldout_comparison.png")

# Example trace for two motors from the same held-out simultaneous episode.
episode = "B1_16__H2__P06_heldout_composite__R01"
trace = paired[paired.simultaneous_episode_id.eq(episode)]
fig, axes = plt.subplots(2, 1, figsize=(7.15, 4.4), sharex=True)
for ax, motor in zip(axes, [0, 9]):
    g = trace[trace.motor_id.eq(motor)]
    ax.plot(g.time_s, g.recorded_inner_position_reference_rad, color="#bbbbbb", lw=1, label="inner reference")
    ax.plot(g.time_s, g.hardware_position_rad, color="#111111", lw=1.25, label="encoder")
    ax.plot(g.time_s, g.synthetic_baseline_position_rad, color=COLORS["baseline"], lw=1, label="synthetic baseline")
    ax.plot(g.time_s, g.hardware_fitted_position_rad, color=COLORS["fitted"], lw=1.2, label="frozen fit")
    ax.set_ylabel(f"Motor {motor} (rad)"); ax.grid(alpha=0.2)
axes[0].legend(ncol=4, fontsize=7, loc="upper center")
axes[1].set_xlabel("Episode time (s)")
fig.suptitle("Two motors in the same held-out B1/H2 episode", y=0.995)
fig.tight_layout()
save(fig, "two_motor_heldout_trace.png")

# Parameter distribution and bound hits.
fig, axes = plt.subplots(1, 3, figsize=(7.15, 2.9))
spec = [("armature_kg_m2", 0.0002, 0.010, "Armature"),
        ("damping_Nm_s_per_rad", 0.003, 0.150, "Damping"),
        ("frictionloss_Nm", 0.002, 0.050, "Friction loss")]
for ax, (column, lower, upper, title) in zip(axes, spec):
    for controller, marker, color in [("H1", "o", "#3c78d8"), ("H2", "s", "#d95f02")]:
        g = hardware_fits[hardware_fits.controller_id.eq(controller)]
        norm = (g[column] - lower) / (upper - lower)
        ax.scatter(g.motor_id.astype(int), norm, label=controller, marker=marker, s=22, color=color)
    ax.axhline(1, color="#555555", lw=0.8, ls="--")
    ax.set_title(title); ax.set_ylim(-0.05, 1.08); ax.set_xticks([0, 5, 10, 15]); ax.grid(alpha=0.2)
axes[0].set_ylabel("Normalized position in fit bounds")
axes[0].legend(fontsize=7)
fig.tight_layout()
save(fig, "fit_parameter_distributions.png")

# Optical measurement role.
fig, ax = plt.subplots(figsize=(7.1, 3.35))
ax.set_xlim(0, 10); ax.set_ylim(0, 4); ax.axis("off")
draw_box(ax, (0.25, 2.25), 2.45, 1.0, "XC330 encoder\nposition register", "#3c78d8", 8.0)
draw_box(ax, (0.25, 0.55), 2.45, 1.0, "asMagic video\nArUco detections", "#d95f02", 8.0)
draw_box(ax, (3.75, 2.25), 2.45, 1.0, "Joint angle used\nin present scores", "#177e89", 8.0)
draw_box(ax, (3.75, 0.55), 2.45, 1.0,
         "Camera calibration,\nmarker transforms,\nand time alignment", "#bf9000", 7.3)
draw_box(ax, (7.15, 1.35), 2.55, 1.1,
         "Independent comparison\nafter calibration", "#674ea7", 8.0)
ax.annotate("", xy=(3.65, 2.75), xytext=(2.8, 2.75), arrowprops=dict(arrowstyle="->"))
ax.annotate("", xy=(3.65, 1.05), xytext=(2.8, 1.05), arrowprops=dict(arrowstyle="->"))
ax.annotate("", xy=(7.05, 1.90), xytext=(6.3, 1.05), arrowprops=dict(arrowstyle="->"))
ax.annotate("", xy=(7.05, 1.90), xytext=(6.3, 2.75), arrowprops=dict(arrowstyle="->"))
ax.text(5, 3.72, "Encoder and optical records are different measurement chains",
        ha="center", fontweight="semibold", fontsize=9)
save(fig, "encoder_optical_measurement_chain.png")

# NeuralActuator: paper method versus the local XC330 adaptation.
fig, ax = plt.subplots(figsize=(7.15, 3.7))
ax.set_xlim(0, 11); ax.set_ylim(0, 5); ax.axis("off")
draw_box(ax, (0.15, 2.95), 2.45, 1.15, "Command, state and\nactuator telemetry\nhistory", "#3c78d8", 7.8)
draw_box(ax, (3.15, 2.95), 2.15, 1.15, "Temporal\nTransformer", "#674ea7", 8.2)
draw_box(ax, (6.05, 3.25), 1.95, 0.72, "Torque surrogate", "#177e89", 7.5)
draw_box(ax, (8.75, 3.25), 2.05, 0.72, "Differentiable\nsimulator rollout", "#177e89", 7.3)
draw_box(ax, (6.05, 1.70), 1.95, 0.72, "Force and contact", "#d95f02", 7.5)
draw_box(ax, (8.75, 1.70), 2.05, 0.72, "Motor condition", "#d95f02", 7.5)
for a, b in [((2.6, 3.52), (3.15, 3.52)), ((5.3, 3.52), (6.05, 3.61)),
             ((8.0, 3.61), (8.75, 3.61)), ((5.3, 3.35), (6.05, 2.06)),
             ((5.3, 3.35), (8.75, 2.06))]:
    ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="->", lw=1.15))
ax.text(0.25, 0.55,
        "Published method: multi-head model evaluated on OpenManipulator-X, SO-101 and Franka.\n"
        "Local XC330 test: ID 0 only; telemetry-conditioned replay with a held-out result.",
        ha="left", va="center", fontsize=7.5)
save(fig, "neural_actuator_scope.png")

# Blurred physical views plus validated combined simulation scenes.
def image_panel(paths, titles, shape, output_name):
    fig, axes = plt.subplots(*shape, figsize=(7.15, 4.5 if shape[0] == 2 else 2.7))
    axes = np.asarray(axes).reshape(-1)
    for ax, path, title in zip(axes, paths, titles):
        ax.imshow(Image.open(path).convert("RGB"))
        ax.set_title(title, fontsize=8)
        ax.axis("off")
    fig.tight_layout(pad=0.45)
    save(fig, output_name)

image_panel(
    [DEMO / "B2_view1_blurred.jpg", DEMO / "B2_view2_blurred.jpg",
     RESULTS / "combined_16_motor_layout_B2_H1.png"],
    ["B2 physical view 1 (blurred)", "B2 physical view 2 (blurred)", "B2/H1 MuJoCo scene"],
    (1, 3), "physical_and_combined_simulation.jpg")

image_panel(
    [DEMO / "G1_view1_blurred.jpg", DEMO / "G1_view2_blurred.jpg",
     RESULTS / "combined_16_motor_layout_B0_H1.png",
     RESULTS / "combined_16_motor_layout_G1_H2.png"],
    ["G1 physical view 1 (blurred)", "G1 physical view 2 (blurred)",
     "B0/H1 MuJoCo scene", "G1/H2 MuJoCo scene"],
    (2, 2), "configuration_real_sim_gallery.jpg")

# Representative assigned-marker coverage on the blurred B2 image pair.
def assigned_marker_ids(motors):
    return {4 * motor + offset for motor in motors for offset in range(4)}

aruco_dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_ARUCO_ORIGINAL)
aruco_detector = cv2.aruco.ArucoDetector(aruco_dictionary, cv2.aruco.DetectorParameters())
marker_views = {
    "view1": (DEMO / "B2_view1_blurred.jpg", [0, 2, 4, 6, 10, 12, 14, 15]),
    "view2": (DEMO / "B2_view2_blurred.jpg", [1, 3, 5, 7, 8, 9, 11, 13]),
}
annotated = []
coverage = {}
for view, (path, motors) in marker_views.items():
    frame = cv2.imread(str(path))
    frame = cv2.resize(frame, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    corners, identifiers, _ = aruco_detector.detectMarkers(frame)
    detected = set() if identifiers is None else {int(value) for value in identifiers.ravel()}
    expected = assigned_marker_ids(motors)
    if identifiers is not None:
        cv2.aruco.drawDetectedMarkers(frame, corners, identifiers)
    assigned = sorted(detected & expected)
    missing = sorted(expected - detected)
    extras = sorted(detected - expected)
    coverage[view] = {
        "assigned_motor_ids": motors,
        "assigned_markers_detected": len(assigned),
        "assigned_markers_expected": len(expected),
        "missing_assigned_marker_ids": missing,
        "opposite_view_or_extra_marker_ids": extras,
    }
    annotated.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

g1_coverage = {}
for view, motors in (("view1", [0, 2, 4, 6, 10, 12, 14, 15]),
                     ("view2", [1, 3, 5, 7, 8, 9, 11, 13])):
    frame = cv2.imread(str(DEMO / f"G1_{view}_blurred.jpg"))
    frame = cv2.resize(frame, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, identifiers, _ = aruco_detector.detectMarkers(frame)
    detected = set() if identifiers is None else {int(value) for value in identifiers.ravel()}
    expected = assigned_marker_ids(motors)
    g1_coverage[view] = {
        "assigned_motor_ids": motors,
        "assigned_markers_detected": len(detected & expected),
        "assigned_markers_expected": len(expected),
        "missing_assigned_marker_ids": sorted(expected - detected),
        "opposite_view_or_extra_marker_ids": sorted(detected - expected),
    }

all_coverage = {"B2": coverage, "G1": g1_coverage}
(RESULTS / "representative_aruco_detection_summary.json").write_text(
    json.dumps(all_coverage, indent=2) + "\n", encoding="utf-8")
fig, axes = plt.subplots(1, 2, figsize=(7.15, 3.0))
for ax, view, frame in zip(axes, marker_views, annotated):
    ax.imshow(frame)
    ax.set_title(f"B2 {view}: assigned-marker detections", fontsize=8)
    ax.axis("off")
fig.tight_layout(pad=0.45)
save(fig, "aruco_assigned_view_detection.png")

print(json.dumps(summary, indent=2))
