# Datasets

All datasets are LeRobot v3 datasets in the pusher-tool format (`../DATA_FORMAT.md`), Push Cube, 30 fps, one
phone image (480 x 640), 9-D state and action.

Each dataset folder has seven files: `README.md` (the dataset card: source, scene, height reference, splits,
known issues) and the six LeRobot files under `meta/`, `data/` and `videos/`. Write the card for every new dataset.

## In this folder

| Folder | Source | Episodes | Frames | Height reference | Scene |
| --- | --- | --- | --- | --- | --- |
| `real_teleop_push_cube/` | `teleop_real.py`, phone teleoperation of the physical arm, 10 October 2026 | 5 | 2 147 | start | white sheet, goal outline drawn by hand |
| `real_teleop_push_cube2/` | the same, second session | 3 | 1 198 | start | the same |
| `real_teleop_push_cube3/` | the same, third session | 3 | 1 732 | start | the same |

`robot_type` is `rebot_pusher_tool_real`. Episode durations are 9 to 28 s. These are source dataset records, not a guarantee of a successful dynamic replay. Follow the [current practice](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/2026-autumn/module-03-arm-data-for-guided-interaction/10-practice.md) for the frame assumptions and diagnostic procedure.

## Not in this folder (course workstation, ask the teaching team)

| Dataset | Source | Episodes | Frames | Size | Height reference | Scene |
| --- | --- | --- | --- | --- | --- | --- |
| `real_push_cube_all` | `record_handheld.py` (older version, keyboard and gesture modes), three sessions merged on 13 October 2026 | 150 | 32 539 | 717 MB | start | course table (light oak), printed green goal |
| `real_push_cube_all_tablez` | the same, converted with `tools/anchor_z_to_table.py` | 150 | 32 539 | the same videos | table | the same |

The source reports an audit of all 150 handheld episodes, with 13 short speed or tilt excesses and a median start height of 9.4 cm. Those reported values belong to the source setup; the current fixed-start-frame checker cannot establish a matched table-frame replay from metadata alone. The original 0.085 m start-height compensation was a run-specific setting, not a universal deployment instruction. Use the current practice's explicit frame, reset and tool contract before comparing results. Per-episode statistics of 161 physical episodes are retained in the Class 10 package's `additional_material/data/results/real_episode_stats.csv`.

Policies trained on these data (course workstation): `act_real_cube`, `act_real_plus_sim_cube`,
`act_real_cube_tablez`, `act_real_plus_sim_cube_tablez`, `dp_real_plus_sim_cube`,
`smolvla_real_plus_sim_cube_tablez` (about 2 GB each with all checkpoints).

New datasets go into this folder, one folder per dataset. Folders other than the three above are ignored by git;
release them as a separate archive.
