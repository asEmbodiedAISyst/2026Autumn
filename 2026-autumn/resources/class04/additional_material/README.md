# Class 04 — Additional material

[Lecture](../../../module-01-actuator-data-for-1-dof-systems/04-basic-quantification-of-sim2real-gap.md) · [RS06 hardware identification](../../../module-01-actuator-data-for-1-dof-systems/04-rs06-hardware-identification.md)

This folder holds the single-actuator identification of Class 04: the raw XC330 campaigns, the fitted models, the
held-out results and the RS06 identification package.

| Folder or file | Content |
| --- | --- |
| `raw_data/` | the asBrain logs of the five fixtures, the identification data and the simulation design |
| `data/` | the episodes used, the frozen held-out selection, the controller conditions, the fitted parameters and paired samples |
| `models/` | the hardware-fitted and synthetic-baseline MJCF models with their parameter sets |
| `code/` | fitting, replay, rendering and analysis scripts |
| `results/` | the held-out results and the episode metrics |
| `rs06_identification/` | the RS06 identification package (see its README) |
| `demonstration/` | the material of the instructor and TA demonstration |
| `EXERCISE_AND_ANSWER.txt`, `SIX_STAGE_DATA_CONTRACT.txt`, `FULL_DATA_CONTENTS.txt` | the exercise, the data contract and the list of all files |
| `requirements.txt` | the Python packages of the scripts |

Reproduce the held-out result:

```bash
cd 2026-autumn/resources/class04/additional_material
uv run --python 3.12 --with-requirements requirements.txt --with pillow python code/render_simulation.py
uv run --python 3.12 --with-requirements requirements.txt python code/analyze_class04.py
```

Render first: the analysis uses the two images. It prints the result on the 30 held-out episodes (mean RMSE
0.0206 rad for the baseline, 0.0148 rad after the fit, 28.3 % lower) and writes its figures to `paper/figures` next to
this folder. The other scripts in `code/` rebuild the fits from the raw data. On macOS, put `MUJOCO_GL=cgl` in front of the commands that render (for example
`MUJOCO_GL=cgl uv run …`): the scripts use EGL by default, which only Linux has.
