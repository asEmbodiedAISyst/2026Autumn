# Class 08 simulation resources

This is the small, self-contained resource bundle for inspecting the reBot B601-RS model and comparing a smooth joint target with its simulated response. No powered hardware is used.

## Read the saved results

Run from this folder with Python 3.10 or later. This command uses only the standard library; installation and rendering are unnecessary.

```sh
python3 code/analyze_saved.py
```

The supplied `results/inspection.json` records the compiled model, joint ranges, reference configurations and timing. `results/joint2-trace.csv` has simulation time, target degrees and measured degrees **before** the next step. Its maximum absolute target-minus-state error is approximately 1.326°. Sampling boundary and units matter when comparing this result with the post-step errors printed by the full-motion example.

## Reproduce the simulation

The pinned dependency set was checked on macOS with Python 3.12.14, MuJoCo 3.14.0 and NumPy 2.5.4. The lock file is a tested macOS set; other platforms are not qualified by that check.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-tested-macos.txt
.venv/bin/python code/lesson_lab.py inspect
.venv/bin/python code/lesson_lab.py trace
.venv/bin/python code/analyze_saved.py
.venv/bin/python code/view_arm_scene.py --list
.venv/bin/python code/controlled_motion.py --mode joints --no-viewer
.venv/bin/python code/controlled_motion.py --mode letters --no-viewer
```

The first two simulation commands overwrite the corresponding files under `results/`. To retain those files, use `--out` with another output path. The commands resolve model and result paths relative to their scripts, so the bundle can be moved as a whole.

`ArmSim` uses 17 physics steps at `1/510` s per 30 Hz control period. The scene file declares an initial 2 ms physics timestep; `ArmSim` adjusts it at runtime. Simulation timestamps do not measure operating-system scheduling. The ROB example's `DRAW_SPEED = 0.04` m/s sets segment duration; its half-cosine interpolation has a higher peak speed, so this value is not a peak TCP speed bound.

Joint 4's negative 10° excursion is skipped by the motion script because its requested endpoint exceeds the declared software bound. That diagnostic is expected. These configured software limits and simulation results do not certify physical calibration or hardware readiness.

## Optional viewer

On macOS, launch the window through MuJoCo's `mjpython` entrypoint:

```sh
.venv/bin/mjpython code/view_arm_scene.py
```

On other platforms use `.venv/bin/python` for the viewer. `Z` selects the zero model configuration; `H` selects working home. The Control sliders expose the seven actuators. The gripper actuator drives two finger coordinates through a tendon and equality constraint. The independent viewer uses the scene's declared 2 ms timestep, while the headless classroom workflow uses `ArmSim` timing. Only the headless commands and the viewer's `--list` mode were verified for this export.

## Files and source

- `code/`: inspection, trace, standard-library saved-data analysis, bounded-motion example and optional viewer.
- `model/rebot_b601_rs_mjcf/`: scene, arm and table MJCF; source URDF; exactly 32 referenced STL meshes; model license and notice.
- `results/`: saved inspection and joint 2 trace for use without MuJoCo.
- `requirements-tested-macos.txt`: pinned simulation dependencies.
- [SOURCE.md](SOURCE.md): provenance and export modifications.

See the model's [NOTICE.md](model/rebot_b601_rs_mjcf/NOTICE.md) and [CERN-OHL-W-2.0 license](model/rebot_b601_rs_mjcf/LICENSE.CERN-OHL-W) when reusing the model source.
