# V5 B2 ±100 mm hardware collection: method and results

Run: `v5-b2-100mm-260901-172518-20260901T132518Z-c247b11c`

## Physical fixture

B2 was physically configured with equal payload centers at **−100 mm and +100 mm**. For this recollection, each complete payload is **44 g including its pin**, and the link is **22 g**, giving **110 g total external moving mass**. The PDF's `0.00150 kg·m²` value remains a preliminary design value and is not reused; link rotational inertia still requires link geometry.

## Episode design

- Calibration: P01–P03 × H1–H5 × three repeats = 45 episodes.
- Model selection: P04–P05 × H1/H2 × three repeats = 12 episodes.
- Safety pilots: H1, H4, and H5 = 3 episodes.
- Every episode began at raw tick 2048 within ±5 ticks and used the 1024–3072 software goal gate.

## Collection outcome

- Retained episode rows: 61.
- Complete calibration episodes: 45 / 45.
- Complete model-selection episodes: 12 / 12.
- Complete pilot episodes: 3 / 3.
- Maximum input-supply current: 0.205000 A.
- Maximum PWM fraction: 0.433920.
- Maximum temperature: 26.0 °C.
- Minimum voltage: 4.9 V.

### Calibration tracking

| H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |
|---|---:|---:|---:|---:|
| H1 | 9 | 0.074082782 | 0.062909995 | 0.515833055 |
| H2 | 9 | 0.067620773 | 0.059759446 | 0.484705744 |
| H3 | 9 | 0.074019336 | 0.063020453 | 0.516133373 |
| H4 | 9 | 0.097897102 | 0.074357454 | 0.628767737 |
| H5 | 9 | 0.061386336 | 0.056446328 | 0.453738524 |

### Model-selection tracking

| H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |
|---|---:|---:|---:|---:|
| H1 | 6 | 0.117443315 | 0.025787453 | 0.410486887 |
| H2 | 6 | 0.108329881 | 0.025578965 | 0.375200996 |

## Evidence boundary

Present Current remains XC330 input-supply-current telemetry, not output torque. No MuJoCo joint parameters or equivalent gains are identified during this collection step. Model-selection episodes must not be used as calibration data.

The campaign stops after B2.
