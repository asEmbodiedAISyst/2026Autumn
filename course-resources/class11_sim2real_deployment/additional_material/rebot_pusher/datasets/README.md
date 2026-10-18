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

`robot_type` is `rebot_pusher_tool_real`. Episode durations 9 to 28 s. Check them with
`uv run python scripts/check_handheld_dataset.py --root datasets/real_teleop_push_cube` and view them with
`lerobot-dataset-viz`.

## Not in this folder (course workstation, ask the teaching team)

| Dataset | Source | Episodes | Frames | Size | Height reference | Scene |
| --- | --- | --- | --- | --- | --- | --- |
| `real_push_cube_all` | `record_handheld.py` (older version, keyboard and gesture modes), three sessions merged on 13 October 2026 | 150 | 32 539 | 717 MB | start | course table (light oak), printed green goal |
| `real_push_cube_all_tablez` | the same, converted with `tools/anchor_z_to_table.py` | 150 | 32 539 | the same videos | table | the same |

Audit of the handheld set: all 150 episodes are reachable by the arm; 13 have a short speed or tilt excess; the
start height above the table has a median of 9.4 cm (instruction: 12 cm), so a policy trained on the start-frame
version must run with `--start-z 0.085` (the mean depth of the episodes below their start pose) or be trained on the
table-frame version. Per-episode statistics of all
161 physical episodes are in `../../data/results/real_episode_stats.csv` of the Class 10 package.

Policies trained on these data (course workstation): `act_real_cube`, `act_real_plus_sim_cube`,
`act_real_cube_tablez`, `act_real_plus_sim_cube_tablez`, `dp_real_plus_sim_cube`,
`smolvla_real_plus_sim_cube_tablez` (about 2 GB each with all checkpoints).

New datasets go into this folder, one folder per dataset. Folders other than the three above are ignored by git;
release them as a separate archive.
