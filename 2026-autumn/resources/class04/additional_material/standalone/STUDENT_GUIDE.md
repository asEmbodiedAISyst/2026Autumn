# Class 04 student guide — full Sim2Real identification experiment

## Run it

```bash
uv sync
uv run pytest
uv run python simulation_only/b0_identification.py
```

This is simulation only. It does **not** command a motor or collect new hardware data. Instead, it uses all of the actual V5 B0/H2 physical results embedded in this project:

- P01 slow triangle, P02 multisine, P03 smooth levels, P04 chirp, and P05 wide sine;
- repeats R01, R02, and R03 for each profile — 15 experiments total.

## What the command does

1. Runs the baseline MuJoCo model against every recorded V5 command.
2. Fits effective damping and armature with R01/R02 from all five profiles (10 experiments).
3. Re-runs all experiments using the fitted model.
4. Evaluates R03 from all five profiles as independently held-out validation (5 experiments).
5. Plays a focused MuJoCo replay of the held-out P04 chirp R03 test.
6. Opens a full layout after the replay and saves it for analysis.

The layout includes per-episode before/after RMSE, mean RMSE by profile, a held-out trace, and a compact report card.

Color key: cyan = physical V5 measurement, gray dashed = baseline before identification, orange = model after identification, red = post-identification residual.

## Saved analysis

- `outputs/b0_full_h2_before_after_summary.png`
- `outputs/b0_full_h2_episode_metrics.csv`
- `outputs/b0_full_h2_replays.csv`
- `outputs/b0_identification_report.json`

## Useful options

```bash
# Faster graphical replay
uv run python simulation_only/b0_identification.py --playback-speed 1.5

# Save all figures without opening graphical windows
uv run python simulation_only/b0_identification.py --no-viewer --save-only --playback-speed 100
```
