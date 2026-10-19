# V5 B1 ±80 mm hardware collection: method and results

Run: `v5-b1-80mm-260901-183102-20260901T143102Z-00cf0746`

## Physical fixture

B1 was physically configured with equal payload centers at **−80 mm and +80 mm**. For this recollection, each complete payload is **44 g including its pin**, and the link is **22 g**, giving **110 g total external moving mass**. The PDF's `0.00075 kg·m²` value remains a preliminary design value and is not reused; link rotational inertia still requires link geometry.

## Episode design

- Calibration: P01–P03 × H1/H2 × three repeats = 18 episodes.
- Untouched held out: P06 × H1/H2 × five repeats = 10 episodes.
- Safety pilots: H1 and H2 = 2 episodes.
- P06 remains frozen and must not influence fitting, bounds, timing/filter choices, or model selection.
- Every episode began at raw tick 2048 within ±5 ticks and used the 1024–3072 software goal gate.

## Collection outcome

- Retained episode rows: 30.
- Complete calibration episodes: 18 / 18.
- Complete model-selection episodes: 0 / 0.
- Complete held-out episodes: 10 / 10.
- Complete pilot episodes: 2 / 2.
- Maximum input-supply current: 0.194000 A.
- Maximum PWM fraction: 0.431660.
- Maximum temperature: 25.0 °C.
- Minimum voltage: 4.9 V.

### Calibration tracking

| H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |
|---|---:|---:|---:|---:|
| H1 | 9 | 0.073361926 | 0.062641946 | 0.512675088 |
| H2 | 9 | 0.067258658 | 0.059644838 | 0.482882449 |

### Frozen held-out tracking

| H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |
|---|---:|---:|---:|---:|
| H1 | 5 | 0.066641566 | 0.000417932 | 0.176145880 |
| H2 | 5 | 0.060471906 | 0.000288512 | 0.164815091 |

## Evidence boundary

Present Current remains XC330 input-supply-current telemetry, not output torque. No MuJoCo joint parameters or equivalent gains are identified during this collection step. Held-out P06 episodes must not be used as calibration or model-selection data.

The campaign stops after B1.
