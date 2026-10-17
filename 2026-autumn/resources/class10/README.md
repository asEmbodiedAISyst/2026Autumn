# Class 10 resources — audit demonstration data

This self-contained teaching bundle supplies the simulated handheld Push Cube pilot, its images and metadata, a dataset-contract template, a numerical audit, and a prepared model/IK check. It contains 10 episodes and 638 retained frames at nominal 30 Hz. No hardware, policy checkpoint, GPU or training is required for the main activity.

## Run the contract and numeric audit

Python 3.9 or newer is sufficient; these commands use only the Python standard library. Run from this folder (the scripts also resolve input paths from their own location).

```sh
python3 -m venv .venv
.venv/bin/python lesson_lab.py verify
.venv/bin/python lesson_lab.py contract --out results/contract.json
.venv/bin/python lesson_lab.py audit --out results/numeric-audit.json
```

`verify` checks distributed files against `MANIFEST.json`. Audit warnings are teaching evidence, so the audit command completes even when it finds flagged episodes. Episode 4 ends about 32.03 mm from the goal; episode 6's action-pose finite difference peaks near 0.60 m/s. Saved outputs are in `saved/`; the scripts write new outputs to `results/`.

The CSV is an exact scalar/vector export of the retained Parquet rows, not a new recording. `data/pilot_push_cube_handheld/frames.csv` has JSON arrays in the three vector columns. Original Parquet tables and the AV1 phone MP4 are retained. `tasks.json`, `episodes.json`, `meta/info.json` and `meta/stats.json` permit inspection without a Parquet dependency. The nominal timestamps are episode-local sampled trace times; they are not a wall-clock camera-acquisition measurement.

Both state and action have nine entries: `x,y,z,r11,r21,r31,r12,r22,r32`. Position is in metres in the gravity-aligned episode frame. The remaining six dimensionless values are the first two rotation-matrix columns; these are not nine joints. The retained handheld recorder builds an action from the next measured pose in the episode sequence. The numeric audit computes differences of `action[:3]` multiplied by nominal fps; IK computes the analogous speed from decoded `observation.state`. Neither is a calibrated measurement of physical command or acquisition velocity. `observation.environment_state` is simulation-only cube x/y/yaw plus goal x/y and must not become an undeclared policy input.

The metadata's `train: 0:10` assigns all ten pilot episodes to training. This bundle does not create or execute a held-out split. Use the [blank contract](dataset-contract-template.md) to specify the intended generalization claim and a split by complete episode or by the factor held out.

## Run the prepared simulation/IK check

Use CPython 3.12 and install the pinned optional dependencies into the same isolated environment:

```sh
.venv/bin/python -m pip install -r requirements-ik.txt
.venv/bin/python check_ik.py --out results/canonical-ik.json
```

This command loads the bundled `pusher_table` MuJoCo scene, reconstructs every observed pose at the canonical start `[0.33,0,0.12]` m with the documented downward orientation, and checks all 638 poses. It then advances the scene for 30 headless control periods (one simulated second). It opens no viewer and renders no images. The optional stack was qualified on macOS arm64, CPython 3.12.14, MuJoCo 3.14.0 and NumPy 2.2.6; other platforms have not been qualified here.

All thresholds, start pose and solver parameters are in `config.json`. Retained solver success is position error below 5 mm and its small-angle rotation residual below 0.05; the 98% episode reach fraction, 30° tilt and ±60° yaw are audit thresholds. The speed-warning calculation has a 5% reporting margin above 0.25 m/s; that margin is not an execution limit. With the retained solver/model, episodes 2 and 7 yield about 46% and 31% reachable frames. Reachability depends on frame, model, limits, numerical solver and initial guess. It does not certify collision avoidance, contact, effort, acceleration, visibility or physical operation, and solver failure does not establish global impossibility.

## Inspect images and recorded policy evidence

`data/images/pilot-nominal.png` and `pilot-turned.png` are unmodified decoded frames 0 and 116 from the supplied phone video. Their video hash, frame indices and times are in `data/images/provenance.json`. Use the video and these frames to inspect visibility separately from numeric checks. The pilot is simulated; it does not prove physical data collection.

The [recorded-policy folder](recorded-policy/README.md) contains a separate 7-channel arm/gripper ACT baseline recipe, 50-episode result JSON, and selected success/failure clips. Its 24/50 outcome is not a result for this 9D handheld pilot. Weights/processors are absent; this is retained source evidence, not reproduced inference or training.

## Source, model and scope

`SOURCE.json` records the source archive hash and the retained model file hashes. `model/rebot_b601_rs_mjcf/NOTICE.md` attributes the upstream Seeed model to commit `c247ea9cb0da29cd52c31953659cc8c47e6d1a6e`; the CERN-OHL-W-2.0 license, URDF and meshes are included. Course tool meshes and MJCF files retain their source attribution. Course code/data are retained for the authorized course publication; no new blanket license is applied to them. The source MJCF builder was referenced by the supplied notice but was not present in the teaching package; the actual editable MJCF and original URDF/meshes are supplied.

The bundle excludes hardware drivers, full training dependencies, weights, raw archives, instructor answers, preparation logs, virtual environments and local workstation paths. `saved/numeric-audit-source.json` and `saved/canonical-ik-source.txt` retain the supplied audit results; `saved/audit-reference-source.json` retains the original injected-fault reference. The reference's episode 4 distance is 23.9 mm, while recomputing the last saved frame gives 32.03 mm; these remain separately identified records. `saved/numeric-audit.json`, `saved/contract.json`, and `saved/canonical-ik.json` are regenerated portable-workflow outputs.
