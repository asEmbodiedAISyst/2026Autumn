# Section 2.3 Sim-Position Candidate Results

Both methods were fitted from the same hardware-realistic logical fields: applied position, measured position, measured velocity, validity/saturation flags, controller metadata, and matched fixture properties. No MuJoCo true-state or generalized-force array was admitted to either fitter.

## Joint Parameters

| MuJoCo Parameter | Source Model (Evaluation Only) | Nominal Model | Sim-Position M1 Candidate | Sim-Position M2 Candidate |
| --- | ---: | ---: | ---: | ---: |
| `armature` | 0.001248489 kg·m² | 0.0005 (-59.95%) | 0.008 (+540.77%) | 0.001243851 (-0.37%) |
| `damping` | 0.0004377348 N·m·s/rad | 0.0001 (-77.16%) | 0.05 (+11322.44%) | 0.0006467031 (+47.74%) |
| `frictionloss` | 0.0481937 N·m | 0.012 (-75.10%) | 0.2 (+314.99%) | 0.04801054 (-0.38%) |

## Fixed Simulation Controller Conditions

| Condition | MuJoCo kp | MuJoCo kv | Applied-Command Delay | Identification Status |
| --- | ---: | ---: | ---: | --- |
| C1 | 50.0000 N·m/rad | 3.3800 N·m·s/rad | 0.000 s | known and fixed; not fitted |
| C2 | 100.0000 N·m/rad | 1.9500 N·m·s/rad | 0.000 s | known and fixed; not fitted |

## Equal-Episode Output-Gap RMSE

| Dataset Split | Nominal Model | Sim-Position M1 Candidate | Reduction | Sim-Position M2 Candidate | Reduction |
| --- | ---: | ---: | ---: | ---: | ---: |
| Calibration | 0.000531 rad | 0.002592 rad | -387.8% | 0.000021 rad | 96.1% |
| Model Selection | 0.000545 rad | 0.002962 rad | -443.3% | 0.000018 rad | 96.7% |
| Held Out | 0.000518 rad | 0.002631 rad | -407.9% | 0.000026 rad | 94.9% |

## Interpretation Boundary

- Method 1 is an integrated closed-loop approximation. It avoids measured torque and numerical acceleration, but remains sensitive to velocity resolution, friction reversal, filtering, and the fixed effective PD controller context.
- Method 2 uses nonlinear MuJoCo replay and the same three-parameter candidate vector. It is more computationally expensive but does not differentiate the measured response.
- The C1/C2 MuJoCo controller gains and zero-delay boundary are fixed generation settings, not fitted parameters. Held-out episodes are evaluated only after the three-parameter candidate is frozen.
- Source parameters are used only for post-fit simulation verification. They will be unavailable in the hardware release.

## Reproduce

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-simulation.txt
python scripts/run_chapter02_rs06_sim_position_identification_v1.py
```
