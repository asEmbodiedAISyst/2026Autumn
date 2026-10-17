# Class 04 computational resources

The complete lecture, equations, figures, demonstration and student activity are on the [Class 04 page](../../module-01-actuator-data-for-1-dof-systems/04-basic-quantification-of-sim2real-gap.md). These optional resources support the same comparison. All numerical evidence uses the 98 g XC330 campaign, not the separate 110 g structural-inspection example.

## Analyse the supplied activity episode

From the repository root, in a prepared Python environment:

```bash
cd 2026-autumn/resources/class04
python code/analyze_episode.py
```

The command reads frozen predictions and writes `activity-output/metrics.json` and an optional overlay/residual plot. It does not operate an actuator, refit parameters or run MuJoCo. Add `--no-plot` for a Python standard-library-only metric calculation. Matplotlib is needed only for plotting; see [analysis dependencies](code/requirements-analysis.txt). The bundled MiSans fonts include their [license](code/fonts/MiSans-LICENSE.txt).

Use the [configuration and signal guide](data/README.md), [G1 activity samples](data/xc330-98g-H1-G1-P06-R01.csv), [B1 comparison samples](data/xc330-98g-H1-B1-P06-R01.csv), [frozen model configuration](data/xc330-98g-model-config.json), [saved activity metrics](data/xc330-98g-activity-saved-metrics.json) and [condition summaries](data/xc330-98g-heldout-condition-metrics.csv). Correct interpretation of the saved figures and metrics receives equal activity credit.

## Run native MuJoCo replay or identification

The [native experiment guide](native/README.md) provides the exact engines, complete primary adapter-array exports and pinned dependencies for XC330 and RS06. Prepare dependencies before class; no hardware is required. The frozen candidates and source results remain separate from newly generated outputs.

The [source manifest](data/xc330-98g-source-manifest.json) records immutable upstream identifiers and hashes. These arrays are exported processed episodes, not raw telemetry archives. The upstream source is [PhyIntel at commit 9821dae9](https://github.com/asMagicBrain/PhyIntel/tree/9821dae9cb14ecfcd9fde3f97f14308a21f5bc00).

## Prepare an isolated plotting environment

```bash
python3.12 -m venv .venv-analysis
. .venv-analysis/bin/activate
python -m pip install -r code/requirements-analysis.txt
```

Windows: use `py -3.12 -m venv .venv-analysis` and `.venv-analysis\Scripts\python.exe` instead of `python`. The metric-only `--no-plot` route has no third-party dependencies. Native replay has its own requirements and environment described in its guide.
