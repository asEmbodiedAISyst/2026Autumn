# Class 04 TA guide — full V5 H2 before/after identification

The normal Class 04 command is deliberately complete but simulation-only: it uses embedded V5 physical records and never opens a serial port.

```bash
uv sync
uv run pytest
uv run python simulation_only/b0_identification.py
```

## Experiment design

The local data set has all 15 V5 B0/H2 episodes: P01–P05 and R01–R03. The script calibrates on R01/R02 across every profile and validates on all R03 episodes. Each baseline and identified response is generated in MuJoCo; the physical curves are the copied V5 measurements.

After the representative held-out MuJoCo replay, leave the analysis layout open for discussion. It contains:

- before/after RMSE for every V5 episode;
- profile-level average before/after RMSE;
- a detailed P04 chirp R03 trace; and
- fitted values plus held-out aggregate error.

All visual and numerical results are saved in `outputs/` for later analysis. Use `b0_full_h2_episode_metrics.csv` for a compact table and `b0_full_h2_replays.csv` for complete sampled traces.

## Physical reference

No physical collection is needed for Class 04. If a physical station demonstration is desired, this standalone folder also includes the guarded selected H2 physical runner:

```bash
uv run python simulation_and_hardware/live_b0_collection.py --protocol h2_calibration --enable-motion
```

That opt-in command remains limited to the separately selected P01 + P02 + P03, one repeat, and keeps the MuJoCo twin open while the motor moves. It is not part of the Class 04 identification dataset collection.
