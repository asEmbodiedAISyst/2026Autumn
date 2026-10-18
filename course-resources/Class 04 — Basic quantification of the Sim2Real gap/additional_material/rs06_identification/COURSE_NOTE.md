# RS06 single-motor identification data (course note)

This folder is the RobStride RS06 counterpart of the XC330 study of Class 04: the same P01--P07 trajectory family,
the same calibration, model-selection and held-out roles, two frozen controller conditions and four fixtures. The
package `README.md` describes the simulation release and how to reproduce it; `hardware/README.md` describes the
hardware campaign of 25 August 2026 and the evidence status of every hardware value; `docs/` gives the model
conventions, the collection procedure and the verification.

| Path | Content |
| --- | --- |
| `data/chapter-02/releases/rs06-sim-data-v1/` | Simulation release: 32 episodes for the fixtures M0, B0, B1, G1 under the controller conditions C1 (kp 50, kv 3.38) and C2 (kp 100, kv 1.95); position data at 100 Hz, torque data at 500 Hz (simulation only); source and nominal MJCF; contracts; identification results |
| `assets/chapter-02/` | Figures of the simulation release |
| `hardware/trajectory-suites/H1`, `H2` | Hash-bound 50 Hz command trajectories P01--P07 for the hardware conditions H1 (KP 50, KD 3.38) and H2 (KP 100, KD 1.95) |
| `hardware/collected/` | 32 captured hardware sessions of the RS06 (motor CAN ID 2, MagicLimb control box, 50 Hz), each with `raw_session.csv`, `session.metadata.json`, one CSV per trajectory and a packaged dataset with its `verification.json` |
| `hardware/gravity-collected/` | Two static-gravity sessions of the G1 fixture: 14 poses, each approached from both directions |
| `hardware/fixture-metadata/` | One JSON per fixture with the CAD-derived mass properties and the hashes of the model files; `manifest.json` binds every captured run to its fixture |
| `hardware/model-sources/`, `source-assets/mjcf/` | The frozen MJCF of the four fixtures with their meshes, and the original Fusion exports with their export reports |
| `scripts/`, `tests/`, `reproduce.sh` | Trajectory generation, simulation data generation, simulation identification (methods 1 and 2), hardware collection runner, release verification |

Status on 15 October 2026:

- The simulation identification is complete and verified (`docs/verification-report.md`).
- The hardware sessions are captured and verified (`verification.json` of every session).
- Hardware identification (added 15 October 2026): `scripts/run_rs06_hardware_identification.py` fits the
  MuJoCo `armature`, `damping` and `frictionloss` of each controller condition from the 108 hardware episodes, by
  integral regression (method 1) and output-error optimisation (method 2). Results in
  `results/hardware-position-v1/`, figures in `assets/hardware-position-v1/`. Rerun from this folder:
  `python scripts/run_rs06_hardware_identification.py hardware --output results/hardware-position-v1 --figures assets/hardware-position-v1`
  (mujoco 3.3.7, numpy, scipy, matplotlib; about 1.5 minutes on the course workstation). The rerun reproduces the published
  parameters to floating-point precision. `scripts/plot_rs06_course_figures.py` draws the commanded profiles and
  one held-out replay for the course page.
- As-built measurements of the fixtures (masses, payload distances, physical range, photographs, motor serial)
  are not recorded; see the table "Measured-fixture record" in `hardware/README.md`.
