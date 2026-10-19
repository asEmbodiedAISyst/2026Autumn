# Class 03 — Additional material

[Lecture](../../../module-01-actuator-data-for-1-dof-systems/03-basic-digitization-of-physical-embodiment.md) · [RS06 fixture digitization](../../../module-01-actuator-data-for-1-dof-systems/03-rs06-fixture-digitization.md)

This folder holds the XC330 fixture models of Class 03, their CAD and measurements, and the RS06 fixture models.

| Folder or file | Content |
| --- | --- |
| `models/` | the five fixture models (B0, B1, B2, G1, M0) in MJCF, with the model inventory |
| `cad/` | the CAD of the fixtures (STEP and 3MF) |
| `measurements/` | as-built dimensions, masses and positions, and notes on the comparison with the CAD |
| `design_screenshots/`, `photos/` | CAD screenshots of the parts and photos of the built fixtures |
| `code/` | `validate_models.py` checks that the five models load; `render_models.py` renders them |
| `results/` | the validation result and the comparison tables |
| `rs06_fixtures/` | the RS06 fixture models, their metadata and a renderer (see its README) |
| `demonstration/` | the guide and material of the instructor and TA demonstration |
| `environment.txt`, `SHA256SUMS.txt` | the validation environment and the checksums of the files |

Run the checks:

```bash
cd 2026-autumn/resources/class03/additional_material
uv run --python 3.12 --with mujoco python code/validate_models.py
uv run --python 3.12 --with mujoco --with pillow python code/render_models.py
uv run --python 3.12 --with mujoco --with numpy --with matplotlib python rs06_fixtures/render_rs06_models.py
```

`validate_models.py` prints `"passed": true` for each model. The renderers write their images to `results/` and
`rs06_fixtures/`. On macOS, put `MUJOCO_GL=cgl` in front of the commands that render (for example
`MUJOCO_GL=cgl uv run …`): the scripts use EGL by default, which only Linux has.
