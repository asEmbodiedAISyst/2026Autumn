# Data format of the pusher-tool datasets

All datasets of this package are LeRobot v3 datasets at 30 fps with the features below. `record_handheld.py`
(person with the handheld tool) and `teleop_real.py` (phone teleoperation of the arm) write the same features
and, on the physical arm, the same `robot_type`. A policy can be trained on one of them or on both, if the two
datasets use the same height convention (see "Height reference") and the same scene.

| Feature | Shape | Names | Content |
| --- | --- | --- | --- |
| `observation.images.phone` | 480 x 640 x 3, video | | Colour image of the phone on the tool |
| `observation.state` | 9, float32 | `x, y, z, r11, r21, r31, r12, r22, r32` | Measured rod-tip pose at this frame, in the episode frame |
| `action` | 9, float32 | the same | Rod-tip pose to reach at the next frame, in the episode frame |
| `task` | string | | `Push the black cube into the green target area.` (or the Push-T string) |

`robot_type`: `rebot_pusher_tool_real` (handheld with a real phone, and the physical arm), `rebot_pusher_tool_sim`
(`teleop_real.py --robot sim`), `rebot_pusher_tool_handheld` and `rebot_pusher_tool_robot` (simulated
demonstrations). Datasets recorded before 10 October 2026 with the handheld recorder have
`rebot_pusher_tool_handheld_real`; change it to `rebot_pusher_tool_real` in `meta/info.json` before a merge
(`lerobot-edit-dataset --operation.type merge` needs the same fps, features and `robot_type`).

## Pose encoding

A pose is a position (3) and a rotation matrix; the dataset stores the position and the first two columns of
the matrix (`r11 r21 r31` = column 1, `r12 r22 r32` = column 2; the third column is their cross product). This
6-D rotation representation is continuous and the network output is made orthonormal by Gram-Schmidt.

## Episode frame

Every episode has its own frame: x and y origin = rod-tip position at the first frame, x axis = heading (yaw) of
the tool at the first frame, z = up (gravity); the z origin is given by the height reference below. The person and the robot each define it from their own start pose, so a
handheld episode and a robot episode of the same motion give the same numbers without a calibration between
the phone frame and the robot base. The only absolute reference is gravity, which ARKit and the robot base
share. The action is an absolute target in this frame (no accumulation of tracking lag, unlike per-step deltas).

## Height reference (`z_frame`)

Two conventions exist. They must not be mixed in one training set.

| `z_frame` | z = 0 at | Written by | Run the policy with |
| --- | --- | --- | --- |
| `start` | the rod-tip height at the first frame of the episode | `teleop_real.py` (default), older handheld data | `rollout_real.py` default; add `--start-z <mean start height of the data>` |
| `table` | the table | `record_handheld.py` (default), `tools/anchor_z_to_table.py` | `rollout_real.py --z-frame table` |

Why: the arm starts every episode 12 cm above the table. With `start`, a demonstration that started 9 cm high
makes the arm push 3 cm above the table. The first 150 physical handheld episodes had a median start height of
9.4 cm, and the first physical rollouts failed for this reason. With `table`, the height of the push does not
depend on the start height.

- `record_handheld.py` asks for one touch of the table at the start of a session (rod tip still on the table for
  1 s, or Enter). In gesture mode, each episode also needs a touch of the table before its start, because the
  ARKit position drifts by some centimetres within minutes. If the tip goes more than 5 mm below the table, the
  table height is lowered.
- `teleop_real.py --z-frame table` records in the table frame on the arm (the arm knows the table from its model).
- `tools/anchor_z_to_table.py <dataset>` converts a `start` dataset: it estimates the table from the lowest point
  of each episode (minus the push height, 8 mm), writes `<dataset>_tablez` with `z_frame = table` in
  `meta/info.json` and the offsets in `meta/table_offsets.json`.
- The recorders do not write `z_frame` into `meta/info.json`. Write the convention into the dataset contract and,
  for a handheld dataset, add `"z_frame": "table"` to `meta/info.json` by hand (LeRobot ignores the field).

## Tool frame and transforms

- Tool frame (`tcp` site of the model): origin at the rod tip; z along the rod toward the tip; x "forward", the
  direction the camera looks at when projected on the table. At the start pose the rod is tilted 30 degrees
  forward: the tool frame of that pose is `TCP_DOWN_ROT` (x forward, y right, z down).
- Phone frame of asMagic: x along the long side toward the top of the phone, y toward the left edge, z out of
  the screen (the camera looks along -z); gravity aligned. On the tool the phone is in landscape with its top to
  the right, so this is also "x right, y up" in the image.
- Camera to rod tip (both prints): `RigidPhoneMapper.from_model` in `rebot_sim/teleop/phone.py` reads it from the
  `phone` camera and the `tcp` site of `model/rebot_b601_rs_mjcf/tool_handheld.xml`. The tip is 162 mm from the
  camera, almost on its optical axis. The camera has a vertical field of view of 54.4 degrees (measured from the
  asMagic intrinsics of an iPhone 17 Pro).
- Robot: joint angles are read from the motors; the tool pose comes from the forward kinematics of the model.

## Software limits (the same for the person and the arm)

Workspace box of the rod tip x 0.22 to 0.56 m, y plus or minus 0.20 m, z 0.003 to 0.20 m (teleoperation of the
physical arm uses a wider box, see the script options); speed 0.25 m/s; angular speed 2 rad/s; rod tilt 30
degrees; yaw plus or minus 60 degrees. A dataset stores the action after these limits, so a demonstration never
contains a motion that the arm would clip. Handheld episodes are also checked for reachability with the IK of
the arm while they are recorded (an episode with more than 2 % unreachable frames is not saved) and afterwards
with `check_handheld_dataset.py`.

## Episode start pose and task

Rod tip at (0.33, 0, 0.12) m from the base (plus a small random offset on the arm), rod tilted 30 degrees forward,
camera toward the push direction. Push Cube: cube and goal in x 0.30 to 0.48 m, y plus or minus 0.12 m; goal 5 to
10 cm from the cube within plus or minus 70 degrees of +x; success when the cube centre is within 15 mm of the
goal centre (judged by the operator on the physical arm). Push-T: goal T at (0.40, 0); success at 90 % overlap.
