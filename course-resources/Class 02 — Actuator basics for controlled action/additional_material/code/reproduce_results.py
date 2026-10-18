#!/usr/bin/env python3
"""Reproduce the Class 02 single-axis simulation, figures, and summary."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patches
from matplotlib.font_manager import FontProperties
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
ADD = ROOT / "additional_material"
MODEL = ADD / "models" / "single_xc330_reference.xml"
DATA = ADD / "data" / "simulation_response.csv"
SUMMARY = ADD / "results" / "simulation_summary.json"
RESULT_FIGURE = ADD / "results" / "simulation_response.png"
PAPER_FIGURES = ROOT / "paper" / "figures"
FONT_REGULAR = ADD / "fonts" / "MiSans-Regular.ttf"
FONT_SEMIBOLD = ADD / "fonts" / "MiSans-Semibold.ttf"

DURATION_S = 6.0
AMPLITUDE_RAD = 0.25
KP_NM_PER_RAD = 1.579836
KD_NM_S_PER_RAD = 0.202115
EFFORT_LIMIT_NM = 0.1551


def target(t: float) -> float:
    if t < 1.0:
        return 0.0
    if t < 3.0:
        return AMPLITUDE_RAD * 0.5 * (1.0 - np.cos(np.pi * (t - 1.0) / 2.0))
    if t < 4.0:
        return AMPLITUDE_RAD
    if t < 6.0:
        return AMPLITUDE_RAD * 0.5 * (1.0 + np.cos(np.pi * (t - 4.0) / 2.0))
    return 0.0


def run_simulation() -> tuple[np.ndarray, dict[str, float | int | bool | str]]:
    model = mujoco.MjModel.from_xml_path(str(MODEL))
    data = mujoco.MjData(model)
    steps = int(round(DURATION_S / model.opt.timestep))
    rows: list[tuple[float, float, float, float, float]] = []
    for index in range(steps + 1):
        time_s = float(data.time)
        desired = target(time_s)
        effort = float(np.clip(KP_NM_PER_RAD * (desired - data.qpos[0]) - KD_NM_S_PER_RAD * data.qvel[0], -EFFORT_LIMIT_NM, EFFORT_LIMIT_NM))
        rows.append((time_s, desired, float(data.qpos[0]), float(data.qvel[0]), effort))
        if index < steps:
            data.ctrl[0] = effort
            mujoco.mj_step(model, data)
    values = np.asarray(rows)
    error = values[:, 1] - values[:, 2]
    limit_violations = int(np.count_nonzero(np.abs(values[:, 2]) > np.pi / 2 + 1e-12) + np.count_nonzero(np.abs(values[:, 4]) > EFFORT_LIMIT_NM + 1e-12))
    summary = {
        "classification": "simulation-only computational result",
        "mujoco_version": mujoco.__version__,
        "duration_s": DURATION_S,
        "integration_timestep_s": float(model.opt.timestep),
        "sample_count": int(len(values)),
        "target_amplitude_rad": AMPLITUDE_RAD,
        "joint_limit_rad": [-float(np.pi / 2), float(np.pi / 2)],
        "effort_limit_Nm": EFFORT_LIMIT_NM,
        "kp_Nm_per_rad": KP_NM_PER_RAD,
        "kd_Nm_s_per_rad": KD_NM_S_PER_RAD,
        "maximum_abs_simulated_position_rad": float(np.max(np.abs(values[:, 2]))),
        "position_rmse_rad": float(np.sqrt(np.mean(error ** 2))),
        "maximum_abs_commanded_effort_Nm": float(np.max(np.abs(values[:, 4]))),
        "limit_violations": limit_violations,
        "physical_validation": False,
    }
    return values, summary


def write_results(values: np.ndarray, summary: dict) -> None:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    with DATA.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["time_s", "target_position_rad", "simulated_position_rad", "simulated_velocity_rad_s", "commanded_effort_Nm"])
        writer.writerows(values)
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def simulation_plot(values: np.ndarray) -> None:
    regular = FontProperties(fname=str(FONT_REGULAR))
    semibold = FontProperties(fname=str(FONT_SEMIBOLD))
    fig, axes = plt.subplots(2, 1, figsize=(8.8, 5.4), sharex=True, constrained_layout=True)
    axes[0].plot(values[:, 0], values[:, 1], label="Desired position", linewidth=1.8)
    axes[0].plot(values[:, 0], values[:, 2], label="Simulated position", linewidth=1.2)
    axes[0].set_ylabel("Position (rad)")
    axes[0].legend()
    axes[1].plot(values[:, 0], values[:, 4], color="#B45309", label="Commanded effort")
    axes[1].axhline(EFFORT_LIMIT_NM, color="#27364A", linestyle="--", linewidth=0.9)
    axes[1].axhline(-EFFORT_LIMIT_NM, color="#27364A", linestyle="--", linewidth=0.9, label="Declared effort limit")
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("Effort (N·m)")
    axes[1].legend()
    for axis in axes:
        axis.grid(alpha=0.22)
        axis.xaxis.label.set_fontproperties(regular)
        axis.yaxis.label.set_fontproperties(regular)
        for item in axis.get_xticklabels() + axis.get_yticklabels():
            item.set_fontproperties(regular)
        for legend_text in axis.get_legend().get_texts():
            legend_text.set_fontproperties(regular)
    fig.suptitle("Bounded single-axis computational response", fontproperties=semibold)
    RESULT_FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(RESULT_FIGURE, dpi=220)
    fig.savefig(PAPER_FIGURES / "simulation_response.png", dpi=220)
    plt.close(fig)


def architecture_figure() -> None:
    regular = FontProperties(fname=str(FONT_REGULAR))
    semibold = FontProperties(fname=str(FONT_SEMIBOLD))
    fig, axis = plt.subplots(figsize=(12.0, 3.1))
    axis.set_xlim(0, 12); axis.set_ylim(0, 3.1); axis.axis("off")
    boxes = [
        (0.25, 1.45, 1.8, 0.85, "Host", "command + limits"),
        (2.55, 1.45, 2.0, 0.85, "Protocol 2.0", "packet + CRC"),
        (5.05, 1.45, 2.1, 0.85, "Embedded control", "profile + feedback"),
        (7.65, 1.45, 1.7, 0.85, "Drive + motor", "electrical effort"),
        (9.85, 1.45, 1.9, 0.85, "Transmission", "motion + load"),
    ]
    colors = ["#DCEBFA", "#DDF2F5", "#E9E2FA", "#FBE8D5", "#DDF2E3"]
    for (x, y, w, h, title, detail), color in zip(boxes, colors):
        axis.add_patch(patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.08", facecolor=color, edgecolor="#284B68", linewidth=1.4))
        axis.text(x + w / 2, y + 0.56, title, ha="center", va="center", fontproperties=semibold, fontsize=12)
        axis.text(x + w / 2, y + 0.24, detail, ha="center", va="center", fontproperties=regular, fontsize=9)
    for left, right in zip(boxes[:-1], boxes[1:]):
        axis.annotate("", xy=(right[0] - 0.08, 1.88), xytext=(left[0] + left[2] + 0.08, 1.88), arrowprops={"arrowstyle": "->", "lw": 1.6, "color": "#284B68"})
    axis.annotate("", xy=(1.2, 1.27), xytext=(10.8, 1.27), arrowprops={"arrowstyle": "->", "lw": 1.7, "color": "#B45309", "connectionstyle": "arc3,rad=-0.23"})
    axis.text(6.0, 0.35, "measured position, velocity, input current, voltage, temperature, and status", ha="center", fontproperties=regular, fontsize=10, color="#8A3F08")
    axis.text(6.0, 2.8, "command → internal reference → physical response", ha="center", fontproperties=semibold, fontsize=15, color="#172C3E")
    fig.savefig(PAPER_FIGURES / "control_architecture.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def render_model() -> None:
    model = mujoco.MjModel.from_xml_path(str(MODEL))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    renderer = mujoco.Renderer(model, height=700, width=1000)
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.lookat[:] = (0.0, 0.0, 0.08)
    camera.azimuth = 135.0; camera.elevation = -18.0; camera.distance = 1.05
    renderer.update_scene(data, camera=camera)
    image = Image.fromarray(renderer.render())
    renderer.close()
    draw = ImageDraw.Draw(image, "RGBA")
    title = ImageFont.truetype(str(FONT_SEMIBOLD), 27)
    note = ImageFont.truetype(str(FONT_REGULAR), 18)
    draw.rounded_rectangle((22, 20, 525, 91), radius=10, fill=(255, 255, 255, 225))
    draw.text((42, 31), "Single-XC330 reference model", font=title, fill=(16, 25, 38, 255))
    draw.text((42, 64), "MJCF VISUALIZATION · ONE REVOLUTE JOINT", font=note, fill=(47, 72, 98, 255))
    result = ADD / "results" / "single_xc330_model.png"
    image.save(result)
    image.save(PAPER_FIGURES / "single_xc330_model.png")


def main() -> None:
    PAPER_FIGURES.mkdir(parents=True, exist_ok=True)
    values, summary = run_simulation()
    write_results(values, summary)
    simulation_plot(values)
    architecture_figure()
    render_model()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
