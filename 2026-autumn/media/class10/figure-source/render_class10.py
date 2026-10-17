"""Replot seven Class 10 classroom figures using only the retained inputs.

Supply an authorised local MiSans font directory. Outputs go to ./media by
default. This plots saved records; it does not run IK, physics or a policy.
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
    parser.add_argument("--output-dir", type=Path, default=ROOT / "media")
    args = parser.parse_args()
    f.ROOT = ROOT
    f.VARIANT = "classroom"
    args.output_dir.mkdir(parents=True, exist_ok=True)
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
        ("learning-records", f.learning_records),
        ("tool-schema", f.tool_schema),
        ("pilot-views", f.pilot_views),
        ("pilot-audit", f.pilot_audit),
        ("pilot-reach", f.pilot_reach),
        ("episode-splits", f.split_episodes),
        ("action-chunks", f.action_chunks),
    ]
    for name, draw in specs:
        figure = draw()
        figure.tight_layout(pad=.7)
        if name == "pilot-views":
            figure.subplots_adjust(bottom=.18, top=.98)
        stem = args.output_dir / (name + "-classroom")
        for ext in ("png", "pdf", "svg"):
            figure.savefig(stem.with_suffix("." + ext), dpi=450,
                           bbox_inches=None, facecolor="white")
        f.plt.close(figure)
    (args.output_dir / "rerender-font-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    print("Rendered seven classroom figures from retained inputs into", args.output_dir)


if __name__ == "__main__":
    main()
