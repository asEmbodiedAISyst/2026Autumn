# Simulation data dictionary

`data/simulation_dataset.npz` contains all 38 deterministic episodes concatenated in episode-list order. `episode_offsets[i]:episode_offsets[i+1]` selects `episode_id[i]`; no pickle objects are required to read the archive.

Core fields:

| Field | Meaning |
|---|---|
| `time_s`, `t_command_s`, `t_state_s` | Ideal 100 Hz simulation/archive clock; equal because declared delay is zero |
| `position_cmd_rad` | Continuous requested profile before encoder quantization |
| `position_applied_rad` | Requested position rounded to `2*pi/4096`; exact actuator input |
| `source_*_true_*` | Continuous MuJoCo state from the disclosed Source plant |
| `source_*_meas_*` | Source position/velocity quantized to declared measurement resolution |
| `nominal_*` | Same channels from the deliberately mismatched Nominal plant |
| `*_actuator_torque_Nm` | MuJoCo `qfrc_actuator`; simulator-only context, not measured hardware torque |
| `*_bias_torque_Nm` | MuJoCo bias force, including gravity/Coriolis terms |
| `*_passive_torque_Nm` | MuJoCo passive joint force from damping/friction terms |
| `*_constraint_torque_Nm` | MuJoCo constraint contribution |
| `*_tracking_error_rad` | Quantized measured position minus applied command |
| `*_saturated` | 1 when actuator force reaches the declared +/-0.5 N*m limit, otherwise 0 |
| `nominal_minus_source_position_meas_rad` | Primary disclosed plant-gap diagnostic |
| `valid` | 1 for a retained finite sample |

`source` means a disclosed synthetic plant, not physical ground truth and not an identified XC330. Source and Nominal differ only in armature, damping, and friction loss. C1/C2 are fixed MuJoCo controller conditions; they are not DYNAMIXEL H-register values.

Archive index:

- `data/episode_list.csv` gives the configuration, profile, controller, R01 instance, intended split, and completion state for every episode. Its `dataset_archive` column points to the NPZ above.
- The NPZ metadata arrays are `episode_id`, `split`, `fixture_id`, `profile_id`, `controller_id`, `repetition`, and `episode_offsets`.
- The fitting runner uses only calibration records for parameter estimation, model-selection records to choose a completed primary start, and held-out records for the final untouched evaluation.

Do not use simulator-true state or simulator effort as if hardware directly measured them. The primary cross-domain boundary is applied position command to measured position/velocity.
