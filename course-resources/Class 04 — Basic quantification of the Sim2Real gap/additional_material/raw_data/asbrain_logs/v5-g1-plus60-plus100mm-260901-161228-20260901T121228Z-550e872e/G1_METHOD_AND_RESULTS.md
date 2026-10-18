# V5 G1 +60/+100 mm hardware collection: method and results

Run: `v5-g1-plus60-plus100mm-260901-161228-20260901T121228Z-550e872e`

## Corrected physical fixture

G1 used two complete **44 g payload assemblies, each including its pin**, on the positive side at **+60 mm and +100 mm**, plus the **22 g link**. Total external moving mass is **110 g**. The user-corrected +60 mm location supersedes the PDF's preliminary +50 mm location, so the PDF inertia and gravity moment are not reused. The two payloads contribute `0.0005984 kg·m²` point inertia and `0.00704 kg·m` first moment; complete link inertia/gravity terms still require link geometry.

## Tick-to-tick zero procedure

Torque-off gravity rest was never treated as experiment zero. After each frozen active segment, a non-active four-second recovery commanded raw tick **1024** (−90°), held it there, and only then disabled torque. With torque off, the heavier unbalanced fixture may settle slightly below 1024 inside the separately declared passive envelope 950–3072. The torque-off DYNAMIXEL goal latch was kept equal to that passive present position to prevent a torque-enable jump; this disabled-torque latch was not an energized motion command. The first energized pickup goal was clamped to 1024, and no energized commanded goal was allowed outside 1024–3072. The temporary passive measured-position allowance remained active through boundary chatter until the encoder reached raw 1029 (a five-tick entry hysteresis), after which the strict 1024–3072 measured-position gate latched permanently. Before every pilot and held-out episode, ID5 then moved slowly toward zero. During setup only, a bounded and logged integral goal bias compensated steady gravity error until the **measured encoder** reached raw tick **2048 ±5**. Torque stayed enabled and the first experimental command was exactly raw tick **2048**, with no setup bias. Every successful zero-acquisition time series is stored as `zeroing_events.parquet` beside its episode data.

## Episode design

- Safety pilots: H1 and H2 = 2 episodes.
- Untouched held out: P06–P07 × H1/H2 × five repeats = 20 episodes.
- P06/P07 were not used for fitting, bounds, timing/filter choices, or model selection.

## Collection outcome

- Complete held-out episodes: 20 / 20.
- Complete pilot episodes: 2 / 2.
- Maximum experiment-start encoder error: 2 ticks relative to 2048.
- Maximum input-supply current: 0.239000 A.
- Maximum PWM fraction: 0.444090.
- Maximum temperature: 26.0 °C.
- Minimum voltage: 4.9 V.

### Frozen held-out hardware tracking

These statistics describe hardware command tracking only. No candidate MuJoCo model was evaluated.

| Profile | H | Episodes | Mean RMSE (rad) | RMSE SD (rad) | Peak error (rad) |
|---|---|---:|---:|---:|---:|
| P06_heldout_composite | H1 | 5 | 0.079660146 | 0.000144886 | 0.195842015 |
| P06_heldout_composite | H2 | 5 | 0.069753111 | 0.000117699 | 0.180357486 |
| P07_heldout_sine_hold | H1 | 5 | 0.096470201 | 0.000166267 | 0.400085979 |
| P07_heldout_sine_hold | H2 | 5 | 0.084953617 | 0.000198023 | 0.364690509 |

## Evidence boundary

Present Current remains XC330 input-supply-current telemetry, not measured output torque. No MuJoCo joint parameters or equivalent gains are identified during collection. G1 P06/P07 remain untouched held-out evidence.
