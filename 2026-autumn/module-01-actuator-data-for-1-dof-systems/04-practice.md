---
description: Class 04 practice · full B0 Sim2Real identification with embedded V5 hardware records
---

# Class 04 — Practice: quantify the B0 Sim2Real gap

This practice uses the complete recorded V5 B0/H2 experiment. The physical XC330 has already completed the fifteen recorded episodes. MuJoCo replays the same recorded input, first with the baseline model and then with an identified effective model. The comparison quantifies the gap between the measured B0 motion and each simulated prediction.

## The experiment at a glance

| Stage | Episodes | Purpose |
| --- | --- | --- |
| Calibration | P01–P05, R01–R02 | choose effective damping and armature from 10 recorded B0/H2 episodes |
| Validation | P01–P05, R03 | evaluate the frozen model on 5 B0/H2 episodes excluded from fitting |
| Visual replay | P04 chirp, R03 | follow one held-out episode frame by frame in MuJoCo and in the live comparison dashboard |

![The recorded data split for the B0 identification experiment](../resources/class04/figures/source/data-split.png)

*Figure 1. Repeats R01 and R02 calibrate the effective replay parameters; R03 remains separate until validation.*

## 1. Install Git and uv on Ubuntu

Open an Ubuntu terminal and install Git and `curl`:

```bash
sudo apt update
sudo apt install -y git curl
git --version
```

Check whether `uv` is available:

```bash
uv --version
```

If the command is not found, install `uv` and load it into the current terminal:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv --version
```

## 2. Clone the Class 04 practice files

Use a sparse checkout so the working copy contains the Class 04 lesson, practice page, figures, records, models, and standalone activity:

```bash
git clone --depth 1 --filter=blob:none --no-checkout \
  https://github.com/asEmbodiedAISyst/2026Autumn.git \
  rob7103-class04

cd rob7103-class04
git sparse-checkout init --no-cone
git sparse-checkout set \
  '/2026-autumn/module-01-actuator-data-for-1-dof-systems/04-basic-quantification-of-sim2real-gap.md' \
  '/2026-autumn/module-01-actuator-data-for-1-dof-systems/04-practice.md' \
  '/2026-autumn/resources/class04/'
git checkout main
```

Enter the standalone experiment directory and create its locked Python environment:

```bash
cd 2026-autumn/resources/class04/additional_material/standalone
uv sync
uv run pytest
```

Keep the terminal in this directory for every remaining command. The supplied environment contains the B0 MJCF, mesh assets, all fifteen V5 records, replay code, and analysis tools.

## 3. Identify the B0 record and the two model conditions

The B0 fixture contains a 22 g link and two 44 g pin–payload assemblies:

```math
m_{ext}=0.022+2(0.044)=0.110\ \mathrm{kg}.
```

The `data/v5_h2_full/` directory contains five motion profiles, each recorded three times under the H2 controller condition. The baseline model uses its supplied parameters. The identification stage searches bounded effective damping and armature values using only R01 and R02. R03 is not used until the chosen pair has been fixed.

```bash
find data/v5_h2_full -mindepth 1 -maxdepth 1 -type d | sort
```

The expected result lists fifteen directories: P01–P05, each with R01, R02, and R03.

![B0 physical and simulation records used by the identification exercise](../resources/class04/figures/source/physical_and_simulation_configurations.png)

*Figure 2. Fixture records and model representations establish the B0/B1/G1 loading vocabulary used by the replay archive.*

## 4. Run the complete B0 identification experiment

Run the full calculation and paced visual replay:

```bash
uv run python simulation_only/b0_identification.py --playback-speed 0.5
```

The terminal reports four phases:

1. loading the fifteen measured V5 B0/H2 episodes;
2. choosing effective damping and armature from R01/R02;
3. replaying the baseline and identified MuJoCo models for all fifteen episodes; and
4. opening the held-out P04 chirp R03 replay.

The final phase opens a MuJoCo scene and a live comparison dashboard. The white cursor advances through the physical record and the corresponding simulated frame. The dashboard displays elapsed replay time, frame number, and the instantaneous position residual. Playback is half speed by default. When the replay reaches its final frame, the MuJoCo scene and dashboard remain open so the final pose, trace, and residual can be examined before closing the MuJoCo viewer.

The analysis layout opens after the replay dashboard is closed. It remains open until it is closed and is also saved in `outputs/`.

## 5. Read the live comparison while the model moves

During the P04 chirp R03 replay, identify the four traces:

| Trace | Meaning |
| --- | --- |
| Cyan | measured V5 hardware position |
| Gray dashed | baseline MuJoCo prediction before identification |
| Orange | MuJoCo prediction after identification |
| Red | post-identification residual: simulated position minus measured position |

The vertical white cursor is the current replay time. It connects the pose in the MuJoCo window to the corresponding sample in the three traces. A small red residual near the cursor indicates closer agreement at that moment; it does not replace the episode-level RMSE calculation.

![Before-and-after B0 identification results](../resources/class04/figures/source/b0_full_h2_before_after_summary.png)

*Figure 3. The saved summary reports episode RMSE before and after identification, profile means, the held-out P04 chirp trace, and the frozen effective parameters.*

## 6. Compare the full B0 results

After the run, inspect the saved files without changing directory:

```bash
ls outputs
```

The main files are:

| File | Contents |
| --- | --- |
| `outputs/b0_full_h2_episode_metrics.csv` | one baseline and identified RMSE pair for each of the 15 episodes |
| `outputs/b0_full_h2_replays.csv` | time-aligned hardware, baseline, and identified positions for every replay sample |
| `outputs/b0_identification_replay.csv` | the held-out P04 chirp R03 trace used in the live replay |
| `outputs/b0_identification_gap.png` | the saved live comparison dashboard |
| `outputs/b0_full_h2_before_after_summary.png` | the complete before-and-after analysis layout |
| `outputs/b0_identification_report.json` | selected parameters and aggregate validation RMSE |

Read the validation rows from the episode table:

```bash
uv run python -c "import pandas as pd; d=pd.read_csv('outputs/b0_full_h2_episode_metrics.csv'); print(d.loc[d.split.eq('validation'), ['episode','before_rmse_rad','after_rmse_rad']].to_string(index=False)); print(); print(d.loc[d.split.eq('validation'), ['before_rmse_rad','after_rmse_rad']].mean())"
```

Each validation row is an R03 episode. For each episode, compare the baseline RMSE with the frozen identified-model RMSE. Then compare their mean values. This is the B0 Sim2Real gap before and after the effective parameter fit.

The result is limited to the declared B0 fixture, H2 controller condition, logged reference, five profiles, and recorded timing. The fitted damping and armature are effective replay parameters, not independently identified motor constants.

## 7. Inspect one held-out trace in detail

Open the representative trace with the saved dashboard or inspect its numerical samples:

```bash
uv run python -c "import pandas as pd; d=pd.read_csv('outputs/b0_identification_replay.csv'); print(d[['time_s','hardware_position_rad','before_identification_rad','after_identification_rad']].head(10).to_string(index=False))"
```

For a selected time interval, distinguish these questions:

1. Does the orange prediction follow the cyan hardware trace more closely than the gray baseline?
2. Does the red residual remain centered near zero, or does it preserve a directional bias?
3. Does a local improvement change the result for every held-out episode?

The complete validation table, rather than a single visually successful segment, supports the final comparison.

## 8. Run without graphical windows

To reproduce the full calculation and save all figures without opening MuJoCo or plot windows:

```bash
uv run python simulation_only/b0_identification.py --no-viewer --save-only --playback-speed 100
```

This command performs the same 15-episode baseline, fitting, and validation calculation. It writes the same tables and figures to `outputs/`.

## 9. Return to the course lesson

The [Class 04 lesson](04-basic-quantification-of-sim2real-gap.md) defines the signal roles, replay equation, effective parameters, RMSE calculation, and scope of the resulting Sim2Real claim.
