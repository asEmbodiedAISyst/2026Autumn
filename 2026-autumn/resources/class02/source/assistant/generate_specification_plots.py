#!/usr/bin/env python3
"""Generate Class 02 figures from documentation and physical hardware records.

No simulated, fitted, or inferred performance series are produced here. The
telemetry figure reads an unchanged XC330 hardware log; the architecture figure
is an explanatory diagram.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
ADD = ROOT / "additional_material"
FONTS_DIR = ADD / "fonts"
RESULTS_DIR = ADD / "results"
PAPER_FIGS = ROOT / "paper" / "figures"
EPISODE = ADD / "data" / "hardware" / "xc330_physical_demo"

FONT_REG = FontProperties(fname=str(FONTS_DIR / "MiSans-Regular.ttf"))
FONT_BOLD = FontProperties(fname=str(FONTS_DIR / "MiSans-Semibold.ttf"))


def _save(fig: plt.Figure, stem: str) -> None:
    for target in (RESULTS_DIR, PAPER_FIGS):
        target.mkdir(parents=True, exist_ok=True)
        fig.savefig(target / f"{stem}.png", dpi=300, bbox_inches="tight")
        fig.savefig(target / f"{stem}.pdf", bbox_inches="tight")


def generate_control_architecture() -> None:
    """Draw a command/feedback path with the return label clear of its arrow."""
    fig, ax = plt.subplots(figsize=(13.0, 4.0), dpi=220)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 4)
    ax.axis("off")

    boxes = [
        (0.3, "Host", "bounded command\nconfigured limits", "#dbeafe"),
        (2.9, "Protocol 2.0", "ID + instruction\nCRC", "#cffafe"),
        (5.5, "Embedded control", "mode + profile\nfeedback", "#ede9fe"),
        (8.1, "Drive + motor", "electrical effort", "#ffedd5"),
        (10.7, "Transmission", "motion + load", "#dcfce7"),
    ]
    width, height, y = 2.0, 1.2, 2.15
    for x, title, detail, color in boxes:
        patch = FancyBboxPatch(
            (x, y), width, height, boxstyle="round,pad=0.08,rounding_size=0.10",
            linewidth=1.5, edgecolor="#1f4b67", facecolor=color,
        )
        ax.add_patch(patch)
        ax.text(x + width / 2, y + 0.78, title, ha="center", va="center",
                fontproperties=FONT_BOLD, fontsize=11, color="#102a43")
        ax.text(x + width / 2, y + 0.34, detail, ha="center", va="center",
                fontproperties=FONT_REG, fontsize=8.8, color="#243b53")

    for index in range(len(boxes) - 1):
        x0 = boxes[index][0] + width + 0.08
        x1 = boxes[index + 1][0] - 0.08
        ax.add_patch(FancyArrowPatch((x0, y + height / 2), (x1, y + height / 2),
                                    arrowstyle="-|>", mutation_scale=14,
                                    linewidth=1.6, color="#1f4b67"))

    feedback = FancyArrowPatch(
        (11.75, 2.03), (1.25, 2.03), connectionstyle="arc3,rad=-0.30",
        arrowstyle="-|>", mutation_scale=16, linewidth=1.8, color="#b45309",
    )
    ax.add_patch(feedback)
    ax.text(
        6.5, 0.38,
        "measured position, velocity, input current, PWM, voltage, temperature and status",
        ha="center", va="center", fontproperties=FONT_REG, fontsize=9.2,
        color="#92400e", bbox={"facecolor": "white", "edgecolor": "none", "pad": 2.5},
    )
    ax.text(6.5, 3.72, "command  →  internal reference  →  physical response",
            ha="center", va="center", fontproperties=FONT_BOLD, fontsize=15,
            color="#102a43")
    _save(fig, "control_architecture")
    plt.close(fig)


def generate_hardware_telemetry_matrix() -> None:
    """Create a 6 x 2 raw-register/decoded-unit view of one hardware episode."""
    data = pd.read_parquet(EPISODE / "telemetry_events.parquet")
    if set(data["source_type"].unique()) != {"physical_hardware_telemetry"}:
        raise ValueError("The input is not exclusively physical hardware telemetry")

    t = data["t_state_s"].to_numpy(float)
    t = t - t[0]
    rows = [
        ("Position", "present_position_raw", "position_meas_rad", "ticks", "rad"),
        ("Velocity", "present_velocity_raw", "velocity_meas_rad_s", "raw", "rad/s"),
        ("Input current", "present_current_raw", "current_meas_A", "raw", "A"),
        ("PWM", "present_pwm_raw", "pwm_meas_fraction", "raw", "fraction"),
        ("Input voltage", "input_voltage_raw", "input_voltage_V", "raw", "V"),
        ("Temperature", "temperature_C", "temperature_C", "°C", "°C"),
    ]
    colors = ["#2563eb", "#0891b2", "#dc2626", "#7c3aed", "#ea580c", "#16a34a"]

    fig, axes = plt.subplots(6, 2, figsize=(10.8, 12.4), sharex=True, dpi=220)
    for index, ((name, raw_col, si_col, raw_unit, si_unit), color) in enumerate(zip(rows, colors)):
        for col, (field, unit, heading) in enumerate(
            ((raw_col, raw_unit, "Raw control-table value"),
             (si_col, si_unit, "Decoded engineering value"))
        ):
            ax = axes[index, col]
            ax.plot(t, data[field].to_numpy(float), color=color, linewidth=0.9)
            ax.grid(True, color="#cbd5e1", linewidth=0.5, alpha=0.65)
            ax.set_ylabel(f"{name}\n[{unit}]", fontproperties=FONT_REG, fontsize=8)
            ax.tick_params(labelsize=7)
            if index == 0:
                ax.set_title(heading, fontproperties=FONT_BOLD, fontsize=10.5)
            if index == 5:
                ax.set_xlabel("Hardware-record time [s]", fontproperties=FONT_BOLD, fontsize=9)

    fig.suptitle(
        "XC330-M288-T physical hardware telemetry",
        fontproperties=FONT_BOLD, fontsize=13, y=0.995,
    )
    fig.text(
        0.5, 0.004,
        "2,601 device reads; ID 5; motor-only fixture; source_type = physical_hardware_telemetry. "
        "Present Current is input-supply current, not output torque.",
        ha="center", va="bottom", fontproperties=FONT_REG, fontsize=7.6, color="#334155",
    )
    fig.tight_layout(rect=(0, 0.025, 1, 0.98), h_pad=0.65, w_pad=0.8)
    _save(fig, "xc330_hardware_telemetry_6x2")
    plt.close(fig)


if __name__ == "__main__":
    generate_control_architecture()
    generate_hardware_telemetry_matrix()
    print("Generated control_architecture and xc330_hardware_telemetry_6x2 (.png/.pdf)")
