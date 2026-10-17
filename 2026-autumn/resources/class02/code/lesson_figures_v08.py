"""Class 02 physical photographs and measured telemetry figures.

python code/lesson_figures_v08.py paper
python code/lesson_figures_v08.py classroom

Six individually documented figures, no generative images or hardware access.
CSV rows are all retained; zoom is the declared 1.1--2.1 s window at the first
triangle reversal. Source photo pixels are not retouched or fabricated.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import sys
import os
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[1] / ".mpl-cache"))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.text import Text
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))
from figure_typography import apply_publication_style

BLUE, ORANGE, GREY = "#0072B2", "#D55E00", "#333333"
FIGURES = {}


def setup(variant):
    global FS, WIDTH, VARIANT, FONTS
    VARIANT = variant
    FONTS = apply_publication_style([ROOT / "source/fonts/MiSans-Regular.ttf",
                                     ROOT / "source/fonts/MiSans-Semibold.ttf"])
    FS, WIDTH = (17, 11.5) if variant == "classroom" else (7, 182/25.4)
    plt.rcParams.update({"font.family": ["MiSans"], "font.size": FS,
        "axes.labelsize": FS, "axes.titlesize": FS, "xtick.labelsize": FS*.9,
        "ytick.labelsize": FS*.9, "legend.fontsize": FS*.82,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": .8 if variant == "classroom" else .6,
        "lines.linewidth": 1.6 if variant == "classroom" else .8,
        "pdf.fonttype": 42, "svg.fonttype": "none", "text.usetex": False,
        "mathtext.fontset": "custom", "mathtext.rm": "MiSans",
        "mathtext.it": "MiSans", "mathtext.bf": "MiSans:weight=semibold",
        "mathtext.fallback": None, "figure.facecolor": "white",
        "axes.facecolor": "white", "savefig.facecolor": "white"})


def letter(ax, text):
    ax.text(0, 1.07, text, transform=ax.transAxes, va="bottom",
            fontweight="semibold", fontsize=FS*1.05)


def save(fig, name, inputs, selection):
    fig.canvas.draw()
    families = set()
    for obj in fig.findobj(Text):
        if obj.get_text():
            resolved = fm.findfont(obj.get_fontproperties(), fallback_to_default=False)
            family = fm.get_font(resolved).family_name
            if family != "MiSans":
                raise RuntimeError(f"Unexpected font {family}: {obj.get_text()}")
            families.add(family)
            glyphs = fm.get_font(resolved).get_charmap()
            missing = [c for c in obj.get_text() if not c.isspace() and ord(c) not in glyphs]
            if missing:
                raise RuntimeError(f"MiSans glyph missing: {missing}")
    outputs = []
    for ext in ("png", "pdf", "svg"):
        out = ROOT / "media" / f"{name}-v08-{VARIANT}.{ext}"
        fig.savefig(out, dpi=180 if VARIANT == "classroom" else 450)
        outputs.append(str(out.relative_to(ROOT)))
    FIGURES[name] = {"outputs": outputs, "inputs": inputs, "selection": selection,
                     "canvas_inches": list(fig.get_size_inches()), "font_families": sorted(families),
                     "input_sha256": {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs}}
    plt.close(fig)


def hardware_identity():
    source = "media/hardware-source/xc330_photo_and_model_matched.png"
    im = Image.open(ROOT/source)
    # Original source has two 800-pixel panels separated by a white gutter.
    # Preserve each panel and its existing pixels, with a fresh MiSans label.
    w, h = im.size
    panels = (im.crop((20, 20, w//2-5, h-20)), im.crop((w//2+5, 20, w-20, h-20)))
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, WIDTH*.47), layout="constrained")
    for ax, picture, label in zip(axes, panels, ("a  Physical actuator", "b  Geometric representation")):
        ax.imshow(picture); ax.axis("off"); letter(ax, label)
    save(fig, "hardware-identity", [source], "Both source panels; remove only the original white gutter/margin. Photograph and CAD view are not behavioral validation.")


def communication_parts():
    names = ("Xc330.jpg", "3pin_cable.jpg", "u2d2.jpg", "powerhub.jpg")
    labels = ("a  Actuator bus ports", "b  Three-conductor cable",
              "c  USB-to-bus interface", "d  External-power hub")
    fig, axes = plt.subplots(2, 2, figsize=(WIDTH, WIDTH*.61), layout="constrained")
    crops = {"Xc330.jpg": (330,240,700,790), "3pin_cable.jpg": (200,0,750,1280),
             "u2d2.jpg": (365,270,680,935), "powerhub.jpg": (180,230,840,1040)}
    for ax, name, label in zip(axes.flat, names, labels):
        ax.imshow(Image.open(ROOT/"media/hardware-source"/name).crop(crops[name])); ax.axis("off"); letter(ax, label)
    save(fig, "communication-parts", ["media/hardware-source/"+n for n in names],
         "Four original photographs, cropped to remove surrounding table; no object retouching, synthetic content or resolution claim. Pixel crops (left,top,right,bottom): " + str(crops))


def connection_inspection():
    name = "media/hardware-source/sc330_connection.jpg"
    fig = plt.figure(figsize=(WIDTH, WIDTH*.50), layout="constrained")
    axes = fig.subplots(1, 2, width_ratios=[1, 1.1])
    axes[0].imshow(Image.open(ROOT/name)); axes[0].axis("off"); letter(axes[0], "a  Supplied layout")
    axes[1].axis("off"); letter(axes[1], "b  Connection checks")
    rows = [("U2D2", "USB data to the actuator bus"),
            ("Power hub", "External supply to bus power"),
            ("Three conductors", "Data, supply and ground"),
            ("Absent in this photograph", "USB lead and external power source")]
    for i, (title, detail) in enumerate(rows):
        y=.92-i*.23
        axes[1].text(0, y, title, transform=axes[1].transAxes, va="top", fontweight="semibold", fontsize=FS*.95)
        axes[1].text(0, y-.09, detail, transform=axes[1].transAxes, va="top", fontsize=FS*.78)
    save(fig, "connection-inspection", [name], "Complete source photograph, with separate explanatory text. Missing USB/external supply are explicitly identified; no electrical pinout inferred from cable colours.")


def read_data():
    name = "data/xc330-hardware-demo/telemetry_events.csv"
    with (ROOT/name).open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    return {key: np.array([float(row[key]) for row in rows]) for key in (
        "t_state_s", "goal_position_raw", "position_trajectory_raw", "present_position_raw",
        "present_velocity_raw", "present_current_raw", "present_pwm_raw", "input_voltage_raw", "temperature_C")}


def telemetry_motion():
    d = read_data(); t = d["t_state_s"]
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, WIDTH*.40), layout="constrained")
    curves = [("goal_position_raw", "Goal readback", GREY, "--"),
              ("position_trajectory_raw", "Internal reference", ORANGE, ":"),
              ("present_position_raw", "Measured position", BLUE, "-")]
    for i, ax in enumerate(axes):
        mask = np.ones(len(t), bool) if i == 0 else ((t >= 1.1) & (t <= 2.1))
        for key, label, color, style in curves:
            ax.plot(t[mask], (d[key][mask]-2048)*360/4096, color=color, linestyle=style,
                    drawstyle="steps-post" if key != "present_position_raw" else "default", label=label)
        ax.set(xlabel="Host receive-end time (s)", ylabel="Position (deg)")
        letter(ax, "a  Entire episode" if i == 0 else "b  First reversal, 1.1 to 2.1 s")
        if i == 1:
            j = 400
            ax.scatter([t[j]], [(d["present_position_raw"][j]-2048)*360/4096], s=FS*1.5, color=BLUE, zorder=5)
    fig.legend(*axes[0].get_legend_handles_labels(),loc="outside upper center",ncol=3,fontsize=FS*.78)
    save(fig, "telemetry-motion", ["data/xc330-hardware-demo/telemetry_events.csv"], "All 2,601 records in full panel; fixed 1.1–2.1 s first-reversal window in second. Host receive-end clock. No smoothing or resampling; goal is register readback. Marker is original row 400.")


def telemetry_electrical():
    d=read_data();t=d["t_state_s"]
    fig,axes=plt.subplots(1,2,figsize=(WIDTH,WIDTH*.35),layout="constrained")
    axes[0].plot(t,d["present_current_raw"],color=BLUE)
    axes[0].set(xlabel="Host receive-end time (s)",ylabel="Reported input current (mA)")
    letter(axes[0],"a  Present Current")
    axes[1].plot(t,d["present_pwm_raw"]*.113,color=ORANGE)
    axes[1].set(xlabel="Host receive-end time (s)",ylabel="Reported PWM (%)")
    letter(axes[1],"b  Present PWM")
    for ax in axes:ax.axhline(0,color="#777777",lw=.6)
    save(fig,"telemetry-electrical",["data/xc330-hardware-demo/telemetry_events.csv"],"All 2,601 signed records; 1 mA/raw unit and 0.113 percent/raw unit. No torque conversion, power calculation, filtering or statistical aggregation.")


def telemetry_environment():
    d=read_data();t=d["t_state_s"]
    fig,axes=plt.subplots(1,2,figsize=(WIDTH,WIDTH*.35),layout="constrained")
    axes[0].step(t,d["input_voltage_raw"]*.1,where="post",color=BLUE)
    axes[0].set(xlabel="Host receive-end time (s)",ylabel="Reported input voltage (V)",ylim=(4.8,5.3),yticks=[4.8,5.0,5.1,5.3])
    letter(axes[0],"a  Voltage, expanded scale")
    axes[1].step(t,d["temperature_C"],where="post",color=ORANGE)
    axes[1].set(xlabel="Host receive-end time (s)",ylabel="Internal temperature (°C)",ylim=(20,26),yticks=[20,22,24,26])
    letter(axes[1],"b  Temperature, expanded scale")
    save(fig,"telemetry-environment",["data/xc330-hardware-demo/telemetry_events.csv"],"All 2,601 records; raw voltage × 0.1 V, temperature already Celsius; step display of quantized readings. Nonzero y-axis limits stated; no long-duration thermal qualification.")


if __name__ == "__main__":
    functions={"hardware-identity":hardware_identity,"communication-parts":communication_parts,
               "connection-inspection":connection_inspection,"telemetry-motion":telemetry_motion,
               "telemetry-electrical":telemetry_electrical,"telemetry-environment":telemetry_environment}
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant",choices=("paper","classroom"))
    parser.add_argument("--figure",choices=tuple(functions),help="Rebuild one named figure only")
    args=parser.parse_args();setup(args.variant)
    selected=[functions[args.figure]] if args.figure else list(functions.values())
    for function in selected:function()
    out=ROOT/"evidence/consolidation-v0.8";out.mkdir(parents=True,exist_ok=True)
    receipt=out/f"figures-{args.variant}.json"
    all_figures=json.loads(receipt.read_text())["figures"] if receipt.exists() else {}
    all_figures.update(FIGURES)
    receipt.write_text(json.dumps({"fonts":FONTS,"figures":all_figures},indent=2)+"\n")
    print(f"Generated and font-checked {len(FIGURES)} {args.variant} figures")
