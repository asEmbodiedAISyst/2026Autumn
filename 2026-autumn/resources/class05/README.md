# Class 05 resources

The [complete student lesson](../../module-02-hand-data-for-multi-fingered-manipulation/05-from-single-actuator-to-multi-actuator.md) includes all six topics, ten illustrations, worked examples, demonstration and activity.

From this directory:

```sh
python3 -m venv .venv-class05-data
.venv-class05-data/bin/python code/lesson_lab.py
```

PowerShell: `py -3 -m venv .venv-class05-data`, then `.\.venv-class05-data\Scripts\python.exe code/lesson_lab.py`. No third-party packages are needed.

The script audits4000paired prediction rows/125events, reaggregates the480held-out motor records, and directly recomputes four scores from the two saved episode traces. It writes `results/lesson-summary.json`; no fitting or new simulation occurs. [Data definitions](data/README.md) distinguish the shared baseline, selected vectors, event grouping and nominal113gfixture. [Selection facts](data/selection-record.json) preserve the source declaration without claiming optimizer reconstruction.

For native scene inspection, use the lesson's isolated Python3.12 environment and pinned `requirements-model.txt`. Both B2/H1 and B2/H2 scenes and meshes are included. `code/inspect_scene.py` checks the actual gain/bias input contract, mechanics and bounded effort values. A compiled/stepped scene does not reproduce the population's hardware-data replay.

[Figure source instructions](../../media/class05/FIGURE-CODE.md) document every illustration. Figure regeneration requires licensed local MiSans faces and the pinned authoring packages. No fonts or third-party packages are installed globally; no network, camera or hardware access occurs during the analysis.
