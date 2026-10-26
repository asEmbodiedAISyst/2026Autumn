# Class 04 standalone — full Sim2Real identification experiment

This folder is standalone: B0 MJCFs/meshes, all 15 recorded V5 B0/H2 episodes, simulation-only system identification, a focused MuJoCo replay, and saved before/after analysis are included.

- [Student guide](STUDENT_GUIDE.md) — full simulation-only experiment.
- [Embedded V5 record note](data/V5_H2_RECORDS.md) — data provenance and splits.

## Run the full experiment

```bash
uv sync
uv run pytest
uv run python simulation_only/b0_identification.py
```

The command reads the embedded V5 measurement records, runs MuJoCo for all 15 experiments, performs system identification, shows the representative MuJoCo replay, then opens the complete before/after analysis layout.

For an immediate animated MuJoCo preview without identification:

```bash
uv run python simulation_only/b0_identification.py --preview-viewer
```

Saved files in `outputs/`:

- `b0_full_h2_before_after_summary.png` — full analysis layout;
- `b0_full_h2_episode_metrics.csv` — before/after RMSE for every episode;
- `b0_full_h2_replays.csv` — recorded, baseline, and identified positions for every sample;
- `b0_identification_report.json` — fitted parameters and aggregate validation result.

For non-graphical analysis:

```bash
uv run python simulation_only/b0_identification.py --no-viewer --save-only --playback-speed 100
```
