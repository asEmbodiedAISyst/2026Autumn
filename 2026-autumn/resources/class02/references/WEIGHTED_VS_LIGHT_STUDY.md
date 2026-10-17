# Weighted vs Light XC330 Response Study

## Experiment

- Motor ID 1: XC330-M288-T with the new weighted rotor/lever.
- Motor ID 2: XC330-M288-T with the earlier light load.
- Both motors: firmware 53, position mode, P=1100, I=0, D=0, 5 V supply.
- Commands: GroupSyncWrite; telemetry: GroupSyncRead; measured rate: 60 Hz.
- Tests: +/-5/15/30 deg steps, +/-20 deg sine at 0.1-5 Hz, and 0.1-5 Hz chirp.

## Model Audit

| Quantity | Weighted XML | Light XML |
|---|---:|---:|
| Moving mass (kg) | 0.098329 | 0.028212 |
| Generalized inertia (kg m^2) | 0.000105528 | 0.000100784 |
| Armature (kg m^2) | 0.0001000 | 0.0001000 |
| Position kp (N m/rad) | 3.000 | 3.000 |
| Position kv (N m s/rad) | 0.030 | 0.030 |

The moving mass increases strongly, but the generalized inertia changes much less because the shared reflected armature dominates the one-DOF inertia.

## Step Response

| Amplitude | Weighted rise (ms) | Light rise (ms) | Weighted overshoot (%) | Light overshoot (%) |
|---:|---:|---:|---:|---:|
| 5 | 64.0 | 47.9 | 0.00 | 0.00 |
| 15 | 64.0 | 64.1 | 0.00 | 0.00 |
| 30 | 64.1 | 63.9 | 0.00 | 0.00 |

## Frequency Response

| Frequency (Hz) | Weighted RMSE (deg) | Light RMSE (deg) | Weighted gain (dB) | Light gain (dB) |
|---:|---:|---:|---:|---:|
| 0.1 | 0.497 | 0.526 | -0.033 | -0.019 |
| 0.25 | 1.121 | 1.156 | -0.036 | -0.023 |
| 0.5 | 2.176 | 2.216 | -0.057 | -0.045 |
| 1 | 4.275 | 4.318 | -0.128 | -0.119 |
| 2 | 8.309 | 8.389 | -0.395 | -0.389 |
| 3 | 12.000 | 12.093 | -0.866 | -0.892 |
| 5 | 18.027 | 18.140 | -2.642 | -2.745 |

- Estimated -3 dB bandwidth, weighted hardware: >5 Hz (not crossed).
- Estimated -3 dB bandwidth, light hardware: >5 Hz (not crossed).

## Electrical And Thermal Load

| Quantity | Weighted ID 1 | Light ID 2 |
|---|---:|---:|
| Peak current (mA) | 662.0 | 642.0 |
| RMS current (mA) | 90.9 | 84.4 |
| Peak PWM raw | 885 | 885 |
| Minimum voltage (V) | 4.80 | 4.80 |
| Maximum temperature (C) | 25 | 26 |

## Sim-To-Real Findings

- Phase-aligned step RMSE, weighted model vs ID 1: 4.673 deg.
- Phase-aligned step RMSE, light model vs ID 2: 4.721 deg.
- Chirp RMSE, weighted model vs ID 1: 9.253 deg.
- Chirp RMSE, light model vs ID 2: 9.330 deg.

The baseline MuJoCo controller is substantially faster and tracks high frequency commands better than either physical motor. The new CAD mass alone does not close that gap; actuator delay, effective stiffness/damping, saturation, friction, and reflected inertia still require identification.

## Interpretation Limits

This is a comparison of two motor-load assemblies, not a perfectly isolated causal weight experiment. Motor ID and load changed together. To estimate the load effect independently from motor-to-motor variation, repeat a crossover experiment: test ID 1 light and weighted, then test ID 2 light and weighted, without changing controller settings.

## Files

- step_overlay.png: command, both hardware traces, and both MuJoCo traces.
- bode_comparison.png: fitted sine gain and phase.
- sine_tracking_rmse.png: tracking error by frequency.
- chirp_overlay.png: broadband position and command error.
- step_metrics.csv, sine_metrics.csv, summary.json: numerical results.
