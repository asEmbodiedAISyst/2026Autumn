# Effective Actuator Identification

## Identified Model

A unit-DC-gain first-order command filter and pure delay were fitted on top of
the existing MuJoCo position actuator:

H_corrected(s) = H_baseline(s) * exp(-s * delay) / (1 + s * tau)

| Load | Filter tau (ms) | Extra delay (ms) |
|---|---:|---:|
| Weighted | 26.145 | 7.412 |
| Light | 26.554 | 7.690 |
| Shared | 26.353 | 7.547 |

## Time-Domain Validation

| Load | Metric | Baseline | Fitted | Reduction |
|---|---|---:|---:|---:|
| Weighted | Step RMSE | 4.6733 deg | 2.0110 deg | 57.0% |
| Weighted | Chirp RMSE | 9.2525 deg | 2.5008 deg | 73.0% |
| Weighted | Sine complex RMSE | 0.4114 | 0.0299 | 92.7% |
| Light | Step RMSE | 4.7214 deg | 2.0672 deg | 56.2% |
| Light | Chirp RMSE | 9.3304 deg | 2.5286 deg | 72.9% |
| Light | Sine complex RMSE | 0.4174 | 0.0336 | 92.0% |

## Interpretation

- The independently fitted weighted and light parameters are nearly identical.
- The dominant missing behavior was internal command shaping and latency, not CAD mass.
- The identified values are effective closed-loop dynamics; they are not literal firmware constants.
- Step and chirp data validate the fit outside the sine-response calculation used to estimate it.
- A load-swap crossover remains necessary to isolate weight from motor-to-motor variation.

## Artifacts

- effective_actuator_fit.json: fitted parameters and predicted frequency response.
- fitted_validation.json: baseline and fitted validation metrics.
- fitted_step_validation.png: step overlays.
- fitted_chirp_validation.png: chirp overlays.
- fitted_frequency_validation.png: gain and phase overlays.

## Video Comparison

The videos replay the 30 deg step sequence and the complete 0.1-5 Hz chirp.
The green line is recorded hardware telemetry; it is not camera footage.

- videos/weighted_id1_fitted_vs_real.mp4: weighted model and ID 1 trace.
- videos/light_id2_fitted_vs_real.mp4: light model and ID 2 trace.
- videos/weighted_vs_light_fitted_side_by_side.mp4: synchronized comparison.
