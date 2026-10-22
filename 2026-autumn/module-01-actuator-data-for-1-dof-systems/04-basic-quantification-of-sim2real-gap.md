---
description: 27 October 2026 · 09:00–10:20 · CR6 | Mohamed HALWANI & SONG Chaoyang
---

# 04 Basic Quantification of the Sim2Real Gap

## Central question

> How can measured actuator motion be used to quantify the Sim2Real gap and evaluate whether a frozen MuJoCo model predicts held-out physical motion?

Class 03 established a mechanically meaningful digital representation of the XC330 fixture through its geometry, rigid bodies, joints, mass properties, inputs, and measurable outputs. This class extends that foundation from digitization to validation by replaying recorded controller references in MuJoCo, comparing predicted and measured joint motion, fitting effective model parameters, and evaluating the frozen model on experiments excluded from fitting.

By the end of this class, you should be able to:

- identify the recorded replay input, measured physical output, and simulated prediction;
- distinguish calibration, model selection, and held-out validation data;
- explain how armature, damping, and friction loss affect a one-degree-of-freedom replay model;
- calculate and interpret position root-mean-square error;
- state a model-use claim whose scope matches the available evidence.

[Lecture](#from-a-digitized-fixture-to-a-measured-prediction-claim) · [Instructor and TA demonstration](#instructor-and-ta-demonstration) · [Student activity](#student-activity)

## From a digitized fixture to a measured prediction claim

A simulation is useful relative to a declared mechanism, input, operating condition, and error measure. This class evaluates a one-degree-of-freedom XC330 fixture by replaying the recorded controller reference in MuJoCo and comparing the simulated output angle with the measured hardware angle.

The evaluation tests whether a frozen simulation model improves position prediction for fixture, controller, and motion combinations excluded from parameter fitting.

![Figure 1. Notation key for the fixture configurations, controller conditions, episode identifiers, and trace names.](../resources/class04/figures/source/experiment_language.png)

Figure 1 is the shared vocabulary for the record:

- **M0** has no external fixture.
- **B0**, **B1**, and **B2** are balanced 110 g external fixtures. The equal payload assemblies are placed symmetrically, so their ideal static gravity moments cancel while their rotational inertia changes.
- **G1** carries the same 110 g external mass asymmetrically. Its static gravity moment does not cancel.
- **H1** and **H2** name the two XC330 controller settings. They are different hardware conditions, not labels for simulation quality.
- An episode identifier, such as `B0__H2__P04_chirp__R03`, states the fixture, controller, motion profile, and repetition.
- The recorded inner reference, hardware position, synthetic baseline, and hardware-fitted replay remain separate signals. Their names are not interchangeable.

## 1. The experiment in one view

The physical system is a ROBOTIS XC330-M288-T with one revolute output joint. The loaded cases contain a 22 g link and two 44 g pin-and-payload assemblies:

```math
m_{ext}=0.022+2(0.044)=0.110\ \mathrm{kg}.
```

The payload-centre positions are measured from the XC330 output axis.

| Fixture | Payload-centre positions | Static gravity moment at the reference pose | Primary mechanical change |
|---|---:|---|---|
| M0 | none | none from external fixture | unloaded reference |
| B0 |-60 mm, +60 mm | ideally cancels | balanced inertia |
| B1 |-80 mm, +80 mm | ideally cancels | larger balanced inertia |
| B2 |-100 mm, +100 mm | ideally cancels | largest balanced inertia |
| G1 | +60 mm, +100 mm | remains | asymmetric gravity load |

Two controller conditions are retained:

| Condition | XC330 raw P/I/D registers | Replay `K_p` | Replay `K_v` | Meaning |
|---|---:|---:|---:|---|
| H1 | 600 / 0 / 150 | 1.579836 N m/rad | 0.202115 N m s/rad | Lower declared position stiffness |
| H2 | 800 / 0 / 150 | 2.106448 N m/rad | 0.202115 N m s/rad | Higher declared position stiffness; same replay velocity damping |

The experiment runner, the embedded XC330 controller, and the MuJoCo replay have distinct roles:

1. The **experiment runner** defines an episode, writes commands, and preserves timestamps.
2. The **XC330 controller** converts requested motion into internal position and velocity references, then drives the physical actuator.
3. The **MuJoCo replay** receives the recorded inner references and predicts the joint motion with an explicit, transparent controller approximation.

The recorded inner reference is therefore the common replay input. An external command records episode context, but it is not substituted for the inner controller reference.

### Controller records

The hardware controller and MuJoCo replay are documented separately:

| Need | Hardware controller record | MuJoCo replay record |
| --- | --- | --- |
| Exact settings | `../resources/class04/additional_material/data/controller_conditions.json` and each episode's `control_table_before.json` / `control_table_after.json` | The same declared H1/H2 values are checked in the generated MJCF and replay program |
| What ran the experiment | `../resources/class04/additional_material/demonstration/hardware_runner/` writes gains, enables torque, sends goals, and logs telemetry | `../resources/class04/additional_material/code/full_fit_and_replay.py` replays the one-axis records; Class 05's `run_sim2real_16.py` applies the same idea to 16 axes |
| Evidence of the actual reference | `Position Trajectory` and `Velocity Trajectory` telemetry columns | Those recorded references become `q_r` and `qdot_r` in the explicit PD law |

Raw XC330 P/I/D register numbers are not automatically physical SI gains. The `K_p` and `K_v` values above are fixed engineering mappings chosen for the replay; they are not fitted alongside the mechanical parameters.

## 2. Matched hardware motion

The asMagic recording documents physical motion for the held-out B1/H2 composite episode `B1__H2__P06_heldout_composite__R01`. It provides fixture context for the motor-side record and is not used as a joint-angle measurement.

![Figure 2. Physical B1/H2 composite motion recorded by asMagic.](../resources/class04/figures/source/asmagic_b1_h2_p06_motion_grid.png)

The video, before-motion photograph, command record, telemetry record, and replay trace share the same episode identifier. This maintains the connection between visible hardware motion and the numerical comparison without treating video frames as calibrated motion capture.

The motion profiles have distinct decision roles.

### Seven trajectories, three roles

![The seven commanded position profiles, coloured by their role.](../resources/class04/figures/source/rs06/rs06_profiles.png)

*Figure 3. The seven commanded position profiles, coloured by their role.*

| Profile group | Profiles | Decision role |
|---|---|---|
| Calibration | P01 slow triangle, P02 multisine, P03 smooth levels | fit bounded parameter candidates |
| Model selection | P04 chirp, P05 wide sine | select one successful candidate |
| Held-out validation | P06 composite, P07 sine-hold | test the frozen candidate |

The data are opened in that order. Calibration establishes candidate parameters; model selection chooses among candidates; held-out evaluation reports the final score without changing the selected model.

### Fixture and model records

The B1 and G1 hardware fixtures, their MuJoCo representations, and the B1/H2 held-out replay document the declared geometry, loading conditions, and position comparison.

![Figure 4. B1 and G1 hardware fixtures, corresponding MuJoCo models, and the B1/H2 held-out position replay.](../resources/class04/figures/source/physical_and_simulation_configurations.png)

## 3. What is compared

For every active sample, the paired archive contains six signal roles:

| Signal | Meaning | Role in the comparison |
|---|---|---|
| External position command | Goal sent by the experiment runner | episode context only |
| Recorded inner position reference | Position reference logged from the XC330 control path | replay input |
| Recorded inner velocity reference | Velocity reference logged from the XC330 control path | replay input |
| Hardware position | Measured XC330 output position | comparison target |
| Synthetic-baseline position | MuJoCo output using the synthetic parameter set | reference baseline |
| Hardware-fitted position | MuJoCo output using the frozen hardware fit | candidate prediction |

MuJoCo advances the rigid-body model at 2 ms. Its replay controller is:

$$
\tau = \operatorname{clip}\!\left[
K_p(q_r - q) + K_v(\dot{q}_r - \dot{q}),
\,-0.1551,\,0.1551
\right]\,\mathrm{N\,m}.
$$

Here, $q_r$ and $\dot{q}_r$ are the recorded inner references; $q$ and $\dot{q}$ are the simulated joint state. H1 and H2 receive separate declared gains. The equation is a replay approximation, not a claim to reproduce hidden XC330 firmware.

At each 2 ms MuJoCo step, the replay reads the simulated `q` and `qdot`, interpolates/holds the logged hardware reference, computes the displayed PD torque, clips it to ±0.1551 N m, and writes that torque to the MuJoCo actuator. The hardware had already run once; no simulation state is sent back to the real XC330.

The magnitude 0.1551 N m is an engineering estimate derived from the [recorded XC330 current limit](../resources/class04/additional_material/demonstration/hardware_runner/experiment_config.json) and the manufacturer's nominal 5 V stall torque/current ratio. The configured register value is 300, with a resolution of 1 mA, so the declared limit is 0.300 A. ROBOTIS specifies 0.93 N m at 1.80 A, giving approximately 0.517 N m/A. Therefore,

$$
\tau_{\max}^{\mathrm{assumed}}
=(0.300\ \mathrm{A})(0.517\ \mathrm{N\,m/A})
=0.1551\ \mathrm{N\,m}.
$$

The symmetric interval allows the replay to apply this estimated effort in either rotational direction. It is **not an independently measured output-torque limit**. The [XC330-M288-T documentation](https://emanual.robotis.com/docs/en/dxl/x/xc330-m288/) states that the XC330 measures input-supply current rather than motor phase current, and a nominal stall ratio need not describe torque during dynamic motion. The replay therefore treats ±0.1551 N m as an assumed model limit; validating it requires an independent current-to-output-torque calibration.

## 4. Fitting a bounded effective model

The fitted joint terms are effective prediction parameters:

| Parameter | Symbol | Fitting interval | Meaning in this replay model |
|---|---|---:|---|
| Armature | (J_a) | 0.0002-0.010 kg m^2 | additional reflected rotational inertia |
| Damping | (b) | 0.003-0.150 N m s/rad | velocity-dependent loss |
| Friction loss | (\tau_f) | 0.002-0.050 N m | constant joint-loss term |

Four bounded starts are fitted independently for H1 and H2 on the calibration profiles. The selected candidate is the successful candidate with the lowest mean episode RMSE on the model-selection profiles. That choice is frozen before P06 and P07 are opened.

| Set | Armature (kg m^2) | Damping (N m s/rad) | Friction loss (N m) |
|---|---:|---:|---:|
| Synthetic baseline | 0.001003 | 0.014963 | 0.010095 |
| H1 selected | 0.006051 | 0.046289 | 0.003542 |
| H2 selected | 0.004779 | 0.047630 | 0.002773 |

Neither selected H1 nor H2 parameter reaches an upper fitting bound. The terms still remain effective closed-loop parameters, because the position record alone cannot uniquely separate inertia and damping from timing, effort scaling, compliance, or reference interpolation.

![Figure 5. Selected parameter values normalized to the widened fitting intervals. Neither controller fit reaches an upper limit.](../resources/class04/figures/source/parameter_bounds.png)

## 5. Held-out error

For an episode (e) with (N_e) active samples, the position score is:

```math
\mathrm{RMSE}_e =
\sqrt{\frac{1}{N_e}\sum_{k=1}^{N_e}
\left(q^{\mathrm{sim}}_{e,k}-q^{\mathrm{hw}}_{e,k}\right)^2}.
```

The final aggregate is the arithmetic mean of episode RMSE values. Equal episode weighting prevents longer episodes from dominating the reported score.

The held-out conditions are B1 and G1, which have equal external mass and different gravity loading.

![Figure 6. Held-out fixture callouts. B1 is balanced; G1 has the same external mass but an asymmetric gravity load.](../resources/class04/figures/source/heldout_fixture_callouts.png)

| Fixture | Controller | Episodes | Baseline mean RMSE (rad) | Fitted mean RMSE (rad) |
|---|---|---:|---:|---:|
| B1 | H1 | 5 | 0.014615 | 0.003420 |
| B1 | H2 | 5 | 0.010184 | 0.002769 |
| G1 | H1 | 10 | 0.028558 | 0.022842 |
| G1 | H2 | 10 | 0.020983 | 0.018506 |
| All | H1/H2 | 30 | 0.020647 | 0.014814 |

Across all 30 held-out episodes, the frozen hardware-fitted replay reduces the mean episode position RMSE by **28.3%** relative to the synthetic baseline.

The asymmetric G1 condition remains harder to predict than B1, especially under H1.

![Figure 7. Held-out mean episode position RMSE for the synthetic baseline and frozen hardware fit.](../resources/class04/figures/source/heldout_error_overview.png)

The largest fitted held-out error occurs in `G1__H1__P07_heldout_sine_hold__R01`: fitted RMSE is 0.026859 rad and baseline RMSE is 0.029262 rad. The fitted replay improves the trace but leaves a directional residual bias of about -0.0171 rad. This observation is evidence of remaining mismatch, not a unique identification of its cause.

## 6. Held-out B1/H2 composite episode

The B1/H2 composite episode did not influence parameter fitting or candidate selection. Its hardware-fitted replay has an RMSE of 0.002743 rad, compared with 0.010119 rad for the synthetic baseline.

![Figure 8. Recorded inner reference, measured position, and frozen hardware-fitted replay for the held-out B1/H2 composite episode.](../resources/class04/figures/source/good_heldout_episode.png)

The signal definitions are:

- **Recorded inner reference** (purple dashed): the motion reference taken from the hardware control record and supplied to the replay.
- **Hardware position** (black): the measured output angle of the physical XC330 fixture.
- **Hardware-fitted replay** (green): the MuJoCo output predicted using the frozen H2 effective parameters.


## 7. What the model does and does not establish

The results support a bounded claim: for the declared one-actuator fixture, H1/H2 controller conditions, recorded inner references, and held-out B1/G1 profiles, the frozen replay model improves position prediction over the synthetic baseline.

Several mechanisms can produce similar residuals:

- fixed effort scaling may be imperfect because output torque was not measured;
- host-side timestamps include software and USB timing, while command-to-actuation delay was not independently measured;
- the logged inner references are slower than the hidden embedded control loop;
- the rigid model excludes shaft compliance, printed-part flex, backlash, joint play, cable forces, base motion, temperature effects, stiction, Stribeck behavior, and direction-dependent friction.

Consequently, the fitted terms are not isolated motor constants. The study does not establish torque accuracy, thermal behavior, contact performance, or transfer to a multi-joint mechanism.

## 8. RS06 actuator measurement

An analogous measurement record for the RobStride RS06 actuator is available on the following page:

[RS06 hardware identification companion](04-rs06-hardware-identification.md)

## 9. Supporting evidence

The supporting record contains the episode index, paired hardware/simulation samples, parameter records, frozen-selection record, optimizer candidates, raw motor-side campaigns, and a compact held-out trace.

The complete supporting package is available in the [Class 04 practical resources](../resources/class04/README.md). It includes the [episode index](../resources/class04/additional_material/data/EPISODES_USED.csv), [paired hardware/simulation samples](../resources/class04/additional_material/data/paired_simulation_hardware_samples.csv.gz), [fitted parameters](../resources/class04/additional_material/data/fitted_parameters.csv), [frozen-selection record](../resources/class04/additional_material/data/FROZEN_SELECTION_BEFORE_HELD_OUT.json), [optimizer candidates](../resources/class04/additional_material/data/optimizer_candidates.csv), [compact held-out trace](../resources/class04/additional_material/data/minimal_heldout_episode_B1_H2_P06_R01.csv.gz), [fit and replay code](../resources/class04/additional_material/code/full_fit_and_replay.py), generated models, raw motor-side records, and matched demonstration media.

## Instructor and TA demonstration

### Prepare the Ubuntu workspace

Install Git, `curl`, and the desktop libraries used by MuJoCo:

```bash
sudo apt update
sudo apt install -y git curl libgl1 libglfw3
```

Install `uv` when it is not already available:

```bash
uv --version || (curl -LsSf https://astral.sh/uv/install.sh | sh)
source "$HOME/.local/bin/env"
uv --version
```

Clone only the Class 04 lesson and resources, then enter the standalone activity directory:

```bash
git clone --depth 1 --filter=blob:none --no-checkout \
  https://github.com/asEmbodiedAISyst/2026Autumn.git \
  rob7103-class04
cd rob7103-class04
git sparse-checkout init --no-cone
git sparse-checkout set \
  /2026-autumn/module-01-actuator-data-for-1-dof-systems/04-basic-quantification-of-sim2real-gap.md \
  /2026-autumn/resources/class04/
git checkout main
cd 2026-autumn/resources/class04/additional_material/standalone
```

The normal Class 04 command is deliberately complete but simulation-only: it uses embedded V5 physical records and never opens a serial port.

```bash
uv sync
uv run pytest
uv run python simulation_only/b0_identification.py
```

### Experiment design

The local data set has all 15 V5 B0/H2 episodes: P01–P05 and R01–R03. The script calibrates on R01/R02 across every profile and validates on all R03 episodes. Each baseline and identified response is generated in MuJoCo; the physical curves are the copied V5 measurements.

After the representative held-out MuJoCo replay, leave the analysis layout open for discussion. It contains:

- before/after RMSE for every V5 episode;
- profile-level average before/after RMSE;
- a detailed P04 chirp R03 trace; and
- fitted values plus held-out aggregate error.

All visual and numerical results are saved in `outputs/` for later analysis. Use `b0_full_h2_episode_metrics.csv` for a compact table and `b0_full_h2_replays.csv` for complete sampled traces.

### Physical reference

No physical collection is needed for Class 04. If a physical station demonstration is desired, this standalone folder also includes the guarded selected H2 physical runner:

```bash
uv run python simulation_and_hardware/live_b0_collection.py --protocol h2_calibration --enable-motion
```

That opt-in command remains limited to the separately selected P01 + P02 + P03, one repeat, and keeps the MuJoCo twin open while the motor moves. It is not part of the Class 04 identification dataset collection.

## Student activity

Continue in the standalone activity directory prepared above.

### Run it

```bash
uv sync
uv run pytest
uv run python simulation_only/b0_identification.py
```

This is simulation only. It does **not** command a motor or collect new hardware data. Instead, it uses all of the actual V5 B0/H2 physical results embedded in this project:

- P01 slow triangle, P02 multisine, P03 smooth levels, P04 chirp, and P05 wide sine;
- repeats R01, R02, and R03 for each profile — 15 experiments total.

### What the command does

1. Runs the baseline MuJoCo model against every recorded V5 command.
2. Fits effective damping and armature with R01/R02 from all five profiles (10 experiments).
3. Re-runs all experiments using the fitted model.
4. Evaluates R03 from all five profiles as independently held-out validation (5 experiments).
5. Plays a focused MuJoCo replay of the held-out P04 chirp R03 test.
6. Opens a full layout after the replay and saves it for analysis.

The layout includes per-episode before/after RMSE, mean RMSE by profile, a held-out trace, and a compact report card.

Color key: cyan = physical V5 measurement, gray dashed = baseline before identification, orange = model after identification, red = post-identification residual.

### Saved analysis

- `outputs/b0_full_h2_before_after_summary.png`
- `outputs/b0_full_h2_episode_metrics.csv`
- `outputs/b0_full_h2_replays.csv`
- `outputs/b0_identification_report.json`

### Useful options

```bash
# Faster graphical replay
uv run python simulation_only/b0_identification.py --playback-speed 1.5

# Save all figures without opening graphical windows
uv run python simulation_only/b0_identification.py --no-viewer --save-only --playback-speed 100
```
