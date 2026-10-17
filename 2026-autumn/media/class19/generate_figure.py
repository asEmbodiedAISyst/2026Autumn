"""Render a schematic evidence review, without simulation or training."""
from pathlib import Path
import argparse
import hashlib
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import FancyArrowPatch
from figure_typography import apply_publication_style

ROOT = Path(__file__).resolve().parent

def claim_to_evidence(summary, variant):
    """Figure 1: preserve the protocol, denominator and conclusion scope."""
    if variant == "paper":
        width, height, size, label = 182/25.4, 96/25.4, 7, 8
    else:
        width, height, size, label = 364/25.4, 192/25.4, 14, 16
    plt.rcParams.update({"font.size": size, "axes.labelsize": size,
                         "xtick.labelsize": size, "ytick.labelsize": size})
    fig = plt.figure(figsize=(width, height))
    outer = fig.add_axes([0, 0, 1, 1]); outer.set_axis_off()
    ink, blue, grey, amber = "#25333F", "#245C83", "#65727D", "#A45B21"
    outer.text(.035, .94, "a", weight="semibold", fontsize=label, va="top")
    outer.text(.075, .94, "Declared experiment", weight="semibold", va="top", color=ink)
    outer.text(.38, .94, "b", weight="semibold", fontsize=label, va="top")
    outer.text(.42, .94, "Retained outcomes", weight="semibold", va="top", color=ink)
    outer.text(.73, .94, "c", weight="semibold", fontsize=label, va="top")
    outer.text(.77, .94, "Supported scope", weight="semibold", va="top", color=ink)

    lines = [("Policy", "Identified exported model"),
             ("Observations", "Original noise (level 1.0)"),
             ("Trials", "Seeds 20000–20099"),
             ("Success", "First target; error < 0.1 rad"),
             ("Limit", "1000 actions; 50 simulated s")]
    for i, (key, val) in enumerate(lines):
        y = .81-i*.105
        outer.text(.035, y, key, weight="semibold", color=ink, va="top")
        outer.text(.035, y-.043, val, color=grey, va="top")

    ax = fig.add_axes([.385, .39, .28, .39])
    counts = [summary["first_goal_successes"], summary["timeouts"], summary["falls"]]
    ax.barh([2, 1, 0], counts, height=.44, color=[blue, amber, grey])
    ax.set_yticks([2,1,0], ["Success", "Timeout", "Fall"])
    ax.set_xlim(0, 105); ax.set_xticks([0,50,100]); ax.set_xlabel("Episodes (n = 100)")
    for y, n in zip([2,1,0], counts):
        ax.text(n+2, y, str(n), va="center", color=ink)
    ax.spines[["left","top","right"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    outer.text(.40, .26, "88 / 100 = 88%", color=blue, weight="semibold")
    outer.text(.40, .21, "All timeouts retained in denominator", color=grey)

    scopes = [("First-goal simulation", "88 / 100 under this protocol", blue),
              ("Continuous replay", "Different protocol / event counter", grey),
              ("Training and hardware", "Not established by this record", grey)]
    for i,(heading,body,col) in enumerate(scopes):
        y=.78-i*.19
        outer.text(.73,y,heading,weight="semibold",color=col,va="top")
        outer.text(.73,y-.055,body,color=grey,va="top")

    for x1,x2 in [(.30,.345),(.675,.71)]:
        outer.add_patch(FancyArrowPatch((x1,.87),(x2,.87), arrowstyle="-|>",
            mutation_scale=size, linewidth=.8 if variant=="paper" else 1.6, color=ink))
    outer.plot([.035,.965],[.135,.135],color="#B8C0C5",lw=.6 if variant=="paper" else 1.2)
    outer.text(.035,.09,"Changing noise, horizon or success rule changes the experiment.",
               color=ink,va="center")
    outer.text(.035,.04,"Saved simulation evidence; this figure does not execute an evaluation.",
               color=grey,va="center")
    outer.set_xlim(0,1); outer.set_ylim(0,1)
    return fig

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--font-regular",type=Path,required=True)
    p.add_argument("--font-semibold",type=Path,required=True)
    p.add_argument("--input",type=Path,default=ROOT/"source-data/class06-first-goal-summary.json")
    p.add_argument("--out",type=Path,default=ROOT)
    a=p.parse_args()
    # Resolve only the explicitly supplied MiSans faces, rather than a cached
    # installed Bold face whose internal weight can be closer to CSS 600.
    fm.fontManager.ttflist=[entry for entry in fm.fontManager.ttflist if entry.name!="MiSans"]
    receipt=apply_publication_style([a.font_regular,a.font_semibold],ROOT/"publication.mplstyle")
    summary=json.loads(a.input.read_text())
    assert summary["completed_episodes"]==100
    assert summary["first_goal_successes"]+summary["timeouts"]+summary["falls"]==100
    a.out.mkdir(parents=True,exist_ok=True)
    outputs=[]
    for variant in ["paper","classroom"]:
        fig=claim_to_evidence(summary,variant)
        fig.canvas.draw()
        for ext in ["png","svg","pdf"]:
            name=f"claim-to-evidence-{variant}.{ext}"
            fig.savefig(a.out/name,dpi=450)
            outputs.append(name)
        plt.close(fig)
    provenance={"figure":"claim-to-evidence", "kind":"schematic evidence review with retained counts",
        "generation":"plotting only; no evaluation or training", "font_receipt":receipt,
        "versions":{"matplotlib":matplotlib.__version__},
        "input":{"path":"source-data/class06-first-goal-summary.json",
                 "sha256":hashlib.sha256(a.input.read_bytes()).hexdigest(),
                 "source":"../../resources/class06/code/results/native-task-10ms-noisy-heldout/summary.json"},
        "outputs":{n:hashlib.sha256((a.out/n).read_bytes()).hexdigest() for n in outputs}}
    (a.out/"figure-provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
    print(json.dumps({"outputs":outputs,"fonts":receipt},indent=2))

if __name__=="__main__":
    main()
