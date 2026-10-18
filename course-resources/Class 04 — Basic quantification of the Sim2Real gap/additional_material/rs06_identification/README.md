# Chapter 2 RS06 1-DOF identification package

This directory is a self-contained RS06 adaptation of the Chapter 2 XC330
reference study (v1.1). It contains the normalized
Fusion MJCF exports, a 32-episode Sim-Position release, the corresponding
500 Hz Sim-Torque release, both reference-aligned identification pipelines,
hardware trajectory suites, the minimum-repeat run plan, and the G1 free-fall
data contract.

The generated data are synthetic. They are not measurements from an RS06 and
the disclosed Source Model parameters are not claimed as physical ground
truth.

## Frozen matrix

| Split | Fixtures | Profiles | Controllers | Unique episodes |
|---|---|---|---|---:|
| calibration | M0, B0, B1 | P01–P03 | C1, C2 | 18 |
| model_selection | B0, B1 | P04–P05 | C1, C2 | 8 |
| held_out | G1/P06–P07 plus B1/P06 | as listed | C1, C2 | 6 |
| total | | | | 32 |

This is intentionally not the original 38-episode matrix: the unavailable B2
calibration combinations are removed, and B1 replaces B2 in model selection.
For physical runs, C1/C2 pair with H1/H2 only as a declared commissioning
hypothesis:

- H1: KP=50, KD=3.38
- H2: KP=100, KD=1.95

RS06 protocol gains are not automatically SI-equivalent MuJoCo gains.

## Generated evidence

- Sim-Position: 32 episodes, 34,156 samples at 100 Hz.
- Sim-Torque: the same 32 episodes, 170,652 samples at 500 Hz.
- Sim-Position Method 2 passes model-selection and held-out acceptance; Method
  1 fails predictive acceptance, as the original reference study's Method 1
  also does.
- Sim-Torque Method 2 recovers the disclosed three Source Model parameters to
  better than `1e-4` relative error.
- The aggregate release verifier passes all checks in
  `release-verification.json`.

## Reproduce

Create an environment and install:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-simulation.txt
```

Then either execute each stage or run:

```bash
PYTHON_BIN=.venv/bin/python bash reproduce.sh
```

No hardware is accessed by `reproduce.sh`. Physical RS06 access occurs only
when the operator explicitly invokes the hardware runner with `--execute` and
all required safety limits.

Key files:

- `docs/modeling-and-feasibility.md`: M0/Fusion modeling and fixture limits.
- `docs/hardware-collection.md`: H1/H2 trajectories and the 108-run minimum
  accepted-repeat plan.
- `docs/verification-report.md`: data generation checks and identification results.
- `hardware/g1-free-fall-schema.json`: required interface for the user's G1
  protocol; no free-fall collection script is included.
- `data/chapter-02/releases/rs06-sim-data-v1/`: release contracts, models,
  episodes, archives, manifests, results, and verification.
