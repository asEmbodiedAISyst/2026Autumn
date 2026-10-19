# V5 M0 motor-only hardware collection: method and results

Run: `v5-m0-no-payload-260901-200740-20260901T160740Z-eafcec4d`

## Physical fixture

M0 was physically configured as **motor-only** with no external horn, link, pin, or payload: **0 g external moving mass**, no payload centers, and exactly zero external-load gravity moment. No external payload inertia is applicable.

## Episode design

- Total retained M0 motion-and-media sessions: 20.
- Calibration: P01–P03 × H1/H2 × three repeats = 18 episodes.
- Safety pilots: H1 and H2 = 2 episodes.
- Model-selection and held-out profiles are excluded from M0 by design.
- Every episode began at raw tick 2048 within ±5 ticks and used the 1024–3072 software goal gate.

## Collection outcome

- Retained episode rows: 21.
- Complete calibration episodes: 18 / 18.
- Complete model-selection episodes: 0 / 0.
- Complete held-out episodes: 0 / 0.
- Complete pilot episodes: 2 / 2.
- Maximum input-supply current: 0.184000 A.
- Maximum PWM fraction: 0.446350.
- Maximum temperature: 24.0 °C.
- Minimum voltage: 4.9 V.

### Calibration tracking

| H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |
|---|---:|---:|---:|---:|
| H1 | 9 | 0.074276128 | 0.062396799 | 0.514455747 |
| H2 | 9 | 0.067888895 | 0.059573564 | 0.485066058 |

### Excluded secondary profiles

M0 contains no P04/P05 model-selection or P06 held-out episodes by design.

## Evidence boundary

Present Current remains XC330 input-supply-current telemetry, not output torque. No MuJoCo joint parameters or equivalent gains are identified during this collection step. No P04/P05 model-selection or P06 held-out episodes are collected for M0.

The campaign stops after M0.
