"""Replot the six Class08 classroom figures from the bundled retained inputs.

Supply an authorised local MiSans font directory. Outputs go to ./media.
This script does not run the robot simulation or change the retained CSV.
"""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "source"))
import lecture_figures as f


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path, required=True)
    args = parser.parse_args()
    f.ROOT = ROOT
    f.VARIANT = "classroom"
    (ROOT / "media").mkdir(exist_ok=True)
    receipt = f.apply_publication_style(
        [args.font_dir / "MiSans-Regular.ttf", args.font_dir / "MiSans-Semibold.ttf"],
        ROOT / "source/publication.mplstyle",
    )
    f.plt.rcParams.update({
        "font.size": 14, "axes.labelsize": 14, "xtick.labelsize": 13,
        "ytick.labelsize": 13, "legend.fontsize": 12,
        "lines.linewidth": 1.5, "axes.linewidth": 1.1,
    })
    specs = [
        ("model-pipeline", lambda: f.flow([
            "URDF\nmechanism", "MJCF\nactuation", "Configured\nsimulation", "Logged\nexperiment"
        ])),
        ("arm-poses", f.arm_poses),
        ("joint-limits", f.joint_limits),
        ("control-loop", f.feedback_loop),
        ("joint-response", f.joint_response),
        ("control-clock", f.control_clock),
    ]
    for name, draw in specs:
        f.save(draw(), name, "retained source", [])
    (ROOT / "rerender-font-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Rendered six classroom figures from retained inputs into", ROOT / "media")


if __name__ == "__main__":
    main()
