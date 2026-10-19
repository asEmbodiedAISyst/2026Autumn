# Class 05 — Additional material

[Lecture](../../../module-02-hand-data-for-multi-fingered-manipulation/05-from-single-actuator-to-multi-actuator.md)

This folder holds the sixteen-actuator identification of Class 05: the campaign records, the combined models, the
parametric and neural comparison, and the held-out results.

| Folder or file | Content |
| --- | --- |
| `raw_data/` | the asBrain logs, the campaign indices and the episode lists |
| `data/` | the episodes used, the frozen held-out selection, the fitted parameters and the episode metrics |
| `models/` | the combined 16-motor MJCF models and their layout (`LAYOUT_AND_METHOD.txt`) |
| `neural_actuator/` | data, model and results of the NeuralActuator comparison |
| `code/` | building, fitting, analysis and comparison scripts, with `requirements.txt` and `neural_actuator_requirements.txt` |
| `results/` | the validation of the combined models and the held-out results |
| `demonstration/` | photos of the fixtures, the asBrain box and the asMagic app |
| `references/` | the licence of NeuralActuator |
| `ANALYSIS_EXERCISE_AND_ANSWER.txt`, `FULL_DATA_CONTENTS.txt` | the exercise and the list of all files |

Rebuild the combined models and reproduce the tables:

```bash
cd 2026-autumn/resources/class05/additional_material
uv run --python 3.12 --with-requirements code/requirements.txt python code/build_and_validate_combined_16.py
uv run --python 3.12 --with-requirements code/requirements.txt python code/analyze_class05.py
```

Build first: the analysis uses its layout image. The build ends with `"all_models_passed": true`; the analysis
prints the held-out RMSE reduction (32.0 %) and writes its figures to `paper/figures` next to this folder. The
NeuralActuator scripts need the packages of `code/neural_actuator_requirements.txt`. On macOS, put `MUJOCO_GL=cgl` in front of the commands that render (for example
`MUJOCO_GL=cgl uv run …`): the scripts use EGL by default, which only Linux has.
