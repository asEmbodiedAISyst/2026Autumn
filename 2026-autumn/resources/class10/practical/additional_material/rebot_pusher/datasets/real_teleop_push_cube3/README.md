# real_teleop_push_cube3

Phone teleoperation of the physical reBot Arm B601-RS with the pusher tool, Push Cube, 10 October 2026
(third session). LeRobot v3 dataset; this README is the part of the data contract that LeRobot does
not read.

## Files

| File | Content |
| --- | --- |
| `README.md` | this dataset card |
| `meta/info.json` | features, shapes, names, fps, `robot_type`, file paths |
| `meta/stats.json` | min, max, mean, std and quantiles of every feature |
| `meta/tasks.parquet` | the task string |
| `meta/episodes/chunk-000/file-000.parquet` | one row per episode: length, first and last frame index, video file |
| `data/chunk-000/file-000.parquet` | one row per frame: state, action, timestamp, indices |
| `videos/observation.images.phone/chunk-000/file-000.mp4` | the phone images of all episodes (AV1) |

## Contract

| Item | Value |
| --- | --- |
| Episodes, frames | 3, 1732 |
| Rate | 30 fps |
| `robot_type` | `rebot_pusher_tool_real` |
| Task | `Push the black cube into the green target area.` |
| `observation.images.phone` | 480 x 640 x 3, the phone on the robot print of the tool |
| `observation.state` | 9 values, `x, y, z, r11, r21, r31, r12, r22, r32`: measured rod-tip pose at this frame |
| `action` | 9 values, the same names: rod-tip pose to reach at the next frame (after the software limits) |
| Units | m for `x, y, z`; the rotation columns have no unit |
| Frame | episode frame: x, y origin and heading = rod tip at the first frame, z up (`../../DATA_FORMAT.md`) |
| Height reference (`z_frame`) | `start`: z = 0 at the rod tip of the first frame. Do not merge with `table` data |
| Scene | white sheet on the desk, goal outline drawn by hand, black 40 mm printed cube |
| Operator, input | course lead; a second iPhone in the handheld print as the controller (`scripts/teleop_real.py`) |
| Speed limit | `--max-speed` of the run (default 0.15 m/s); the value of the run is not recorded |
| Episode lengths (frames) | 0: 674 (22.5 s), 1: 411 (13.7 s), 2: 647 (21.6 s) |
| Splits | all episodes are training data (`"train": "0:3"`); no held-out episodes |
| Rejected episodes | none written |
| Audit | `scripts/check_handheld_dataset.py --root datasets/real_teleop_push_cube3`; per-episode statistics in `real_episode_stats.csv` of the Class 10 folder |
| Software | LeRobot 0.6.1, codebase v3.0 |

## Known issues

* The scene is not the scene of the handheld dataset (course table, printed green goal). A merge with it teaches
  two scenes.
* The 95th-percentile tip speed of some episodes is above the 0.25 m/s tool limit; the arm clips these moments.
