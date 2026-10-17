# Sim-Position Candidate Results v1.2

Both methods were fitted from the same hardware-realistic logical fields: applied position, measured position, measured velocity, validity/saturation flags, controller metadata, and matched fixture properties. No MuJoCo true-state or generalized-force array was admitted to either fitter.

## Joint Parameters

| MuJoCo Parameter | Source Model (Evaluation Only) | Nominal Model | Sim-Position M1 Candidate | Sim-Position M2 Candidate |
| --- | ---: | ---: | ---: | ---: |
| `armature` | 0.001 kg·m² | 0.0007 (-30.00%) | 0.001729633 (+72.96%) | 0.001003984 (+0.40%) |
| `damping` | 0.015 N·m·s/rad | 0.009 (-40.00%) | 0.0267502 (+78.33%) | 0.01505372 (+0.36%) |
| `frictionloss` | 0.01 N·m | 0.006 (-40.00%) | 0.01055065 (+5.51%) | 0.01000014 (+0.00%) |

## Fixed Simulation Controller Conditions

| Condition | MuJoCo kp | MuJoCo kv | Applied-Command Delay | Identification Status |
| --- | ---: | ---: | ---: | --- |
| C1 | 2.5000 N·m/rad | 0.0500 N·m·s/rad | 0.000 s | known and fixed; not fitted |
| C2 | 3.1000 N·m/rad | 0.1500 N·m·s/rad | 0.000 s | known and fixed; not fitted |

## Equal-Episode Output Gap to the Source Model

Every RMSE is measured against Source Model output. The Nominal Model is the pre-identification baseline; improvement over it is a secondary summary.
Version 1.2 did not preregister an absolute pass threshold. Model-selection gap chooses the preferred candidate; held-out gap then reports generalization without participating in that choice.

| Dataset Split | Nominal-to-Source Baseline | M1-to-Source Gap | Improvement Over Baseline | M2-to-Source Gap | Improvement Over Baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| Calibration | 0.002895 rad | 0.003444 rad | -19.0% | 0.000093 rad | 96.8% |
| Model Selection | 0.003787 rad | 0.004972 rad | -31.3% | 0.000187 rad | 95.1% |
| Held Out | 0.003002 rad | 0.003675 rad | -22.4% | 0.000137 rad | 95.4% |

## Interpretation Boundary

- Method 1 is an integrated closed-loop approximation. It avoids measured torque and numerical acceleration, but remains sensitive to velocity resolution, friction reversal, filtering, and the fixed effective PD controller context.
- Method 2 uses nonlinear MuJoCo replay and the same three-parameter candidate vector. It is more computationally expensive but does not differentiate the measured response.
- The C1/C2 MuJoCo controller gains and zero-delay boundary are fixed generation settings, not fitted parameters. Held-out episodes are evaluated only after the three-parameter candidate is frozen.
- Source parameters are used only for post-fit simulation verification. They will be unavailable in the hardware release.
- Gap to Source Model output is the primary evaluation quantity. Percentage improvement over the Nominal baseline is descriptive and does not create an acceptance criterion.

## Reproduce

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-simulation.txt
.venv/bin/python scripts/run_chapter02_sim_position_identification_v1_2.py
```
