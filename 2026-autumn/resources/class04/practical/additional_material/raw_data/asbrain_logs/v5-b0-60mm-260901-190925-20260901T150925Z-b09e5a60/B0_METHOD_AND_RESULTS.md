# V5 B0 ±60 mm hardware collection: method and results

Run: `v5-b0-60mm-260901-190925-20260901T150925Z-b09e5a60`

## Physical fixture

B0 was physically configured with equal payload centers at **−60 mm and +60 mm**. This user-confirmed value supersedes the PDF's preliminary ±50 mm declaration. For this recollection, each complete payload is **44 g including its pin**, and the link is **22 g**, giving **110 g total external moving mass**. The PDF's preliminary `0.00025 kg·m²` inertia is not reused. Payload point inertia is calculated from the measured payload masses; link rotational inertia still requires link geometry.

## Episode design

- Calibration: P01–P03 × H1/H2 × three repeats = 18 episodes.
- Model selection: P04–P05 × H1/H2 × three repeats = 12 episodes.
- Safety pilots: H1 and H2 = 2 episodes.
- P04/P05 remain model-selection data and must not influence calibration fitting.
- Every episode began at raw tick 2048 within ±5 ticks and used the 1024–3072 software goal gate.

## Collection outcome

- Retained episode rows: 33.
- Complete calibration episodes: 18 / 18.
- Complete model-selection episodes: 12 / 12.
- Complete held-out episodes: 0 / 0.
- Complete pilot episodes: 2 / 2.
- Maximum input-supply current: 0.204000 A.
- Maximum PWM fraction: 0.442960.
- Maximum temperature: 26.0 °C.
- Minimum voltage: 4.9 V.

### Calibration tracking

| H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |
|---|---:|---:|---:|---:|
| H1 | 9 | 0.073949214 | 0.062606118 | 0.514955415 |
| H2 | 9 | 0.067660741 | 0.059839261 | 0.488780860 |

### Model-selection tracking

| H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |
|---|---:|---:|---:|---:|
| H1 | 6 | 0.118403922 | 0.025908397 | 0.388988221 |
| H2 | 6 | 0.108807263 | 0.025544756 | 0.376224894 |

## Evidence boundary

Present Current remains XC330 input-supply-current telemetry, not output torque. No MuJoCo joint parameters or equivalent gains are identified during this collection step. Model-selection episodes must not be used as calibration data.

The campaign stops after B0. Do not change the B0 record to ±50 mm when the documentation is revised.
