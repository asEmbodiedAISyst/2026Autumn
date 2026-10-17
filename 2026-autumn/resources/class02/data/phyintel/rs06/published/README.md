# RS06 Real-Position Identification Results v1

This directory contains the derived, machine-readable results reported in
Appendix B. The source archive is not redistributed here.

- Source archive: `hardware_data.zip`
- Source SHA-256: `144d6137e77e8b9b9a41844008ff05d7f063aeda14450546b00dcca85b2386ed`
- Dynamic evidence: 108 episodes, 57,694 samples, 50 Hz
- Controllers: H1 (`Kp=50`, `Kd=3.38`) and H2 (`Kp=100`, `Kd=1.95`)
- Primary interface: recorded applied position to measured position/velocity
- Identified quantities: MuJoCo `armature`, `damping`, and `frictionloss`
- Methods: Method 1 (integral regression) and Method 2 (nonlinear MuJoCo
  output-error optimization)

H1 and H2 are fitted independently. Their hardware controller settings are
copied as fixed MuJoCo controller coefficients for this modeling hypothesis;
they are not identified. The firmware torque estimate is retained only for
supporting diagnostics and is excluded from both primary fits.

## Files

- `dataset-audit.json` records the episode matrix, field availability, source
  hash, fixture provenance, and exclusions.
- `joint-parameter-estimates.csv` contains both three-parameter candidates for
  both controller contexts.
- `aggregate-metrics.csv` summarizes command-tracking error, model-to-hardware
  position gap, and repeatability by split.
- `fixture-metrics.csv` reports the output gap by fixture and evidence split.
- `episode-metrics.csv` preserves episode-level tracking and model gaps.
- `repeatability.csv` reports repeat-to-combination-mean dispersion.
- `static-gravity-diagnostic.csv` contains the G1 steady-state pose diagnostic.
- `result.json` preserves the complete analysis configuration and results.
- `run-analysis.py` is the exact runner copied when these outputs were built.

The corresponding figures are stored under
`assets/appendix-b/rs06-real-position-v1/`.

## Reproduction

From the repository root, with the project environment active:

```bash
.venv/bin/python scripts/run_appendix_b_rs06_hardware_identification_v1.py \
  /path/to/hardware_data.zip \
  --output data/appendix-b/rs06-real-position-v1 \
  --figures assets/appendix-b/rs06-real-position-v1
```

The report interprets the output-error candidates as controller-context-bounded
predictive models, not as unique physical constants of the bare RS06.
