# Data format of the pusher-tool datasets

The selected `episode`-mode datasets use LeRobot v3 at nominal 30 fps with the features below. `record_handheld.py` (physical handheld tool), `teleop_real.py` (phone teleoperation of the arm) and `generate_tool_demos.py` (scripted simulation) share feature names/shapes, but their action labels have different meanings. Identify the recorder, source revision, fps, frame/height convention, limits, scene and timing rule in the dataset contract. Equal features, `robot_type` or height convention alone do not make the routes interchangeable for training or merging. The optional `delta` mode has a different schema and is outside this nine-component contract.

| Feature | Shape | Names | Content |
| --- | --- | --- | --- |
| `observation.images.phone` | 480 x 640 x 3, video | | Colour image of the phone on the tool |
| `observation.state` | 9, float32 | `x, y, z, r11, r21, r31, r12, r22, r32` | Measured rod-tip pose at this frame, in the episode frame |
| `action` | 9, float32 | the same | Route-specific label in the episode frame: next measured pose for physical handheld recording; accepted controller target for teleoperation/scripted simulation (below) |
| `task` | string | | `Push the black cube into the green target area.` (or the Push-T string) |

`robot_type`: `rebot_pusher_tool_real` (handheld with a real phone, and the physical arm), `rebot_pusher_tool_sim`
(`teleop_real.py --robot sim`), `rebot_pusher_tool_handheld` and `rebot_pusher_tool_robot` (simulated
demonstrations). Datasets recorded before 10 October 2026 with the handheld recorder have
`rebot_pusher_tool_handheld_real`. A merge tool may require equal fps, features and `robot_type`, but changing this label does not reconcile action/frame/timing semantics. Preserve the original metadata and document any separately versioned metadata migration before merging; verify the scientific contract as well as the tool's structural requirements.

## Pose encoding

A pose is a position (3) and a rotation matrix; the dataset stores the position and the first two columns of
the matrix (`r11 r21 r31` = column 1, `r12 r22 r32` = column 2; the third column is their cross product). This
6-D rotation representation is continuous and the network output is made orthonormal by Gram-Schmidt.

## Episode frame

Every episode has its own frame: x and y origin = rod-tip position at the first frame, x axis = heading (yaw) of
the tool at the first frame, z = up (gravity); the z origin is given by the height reference below. The person and the robot each define it from their own start pose, so a
handheld episode and a robot episode of the same motion give the same numbers without a calibration between
the phone frame and the robot base. The only absolute reference is gravity, which ARKit and the robot base
share. The action is encoded as an absolute pose in this frame, rather than a per-step delta. Whether that pose is a measured successor or a commanded target depends on the recorder; the representation alone does not establish the label's timing or executor semantics.

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

- `record_handheld.py` asks for a session table calibration (tip still for 1 s, or Enter accepting the current height). In default keyboard mode, lift to the start pose and press Enter again to start each episode; it does not resample table touches while waiting between episodes. In `--gesture` mode, each episode searches a 30-second still-sample history for a touch at least 5 cm below its start. If none is found, it warns and retains the previous reference. After a saved episode that goes more than 5 mm below the calibrated table, the estimate is lowered; this does not correct every drift direction. Record calibration mode, session identity and warnings.
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

## Action labels and limits by collection route

| Route | What `action` stores | Limits and checks |
| --- | --- | --- |
| `generate_tool_demos.py`, simulation | `info["applied_action"]`: controller-limited target, paired with the pre-transition observation/state; embodiment-specific IK status/handling is separate | `default_tool_limits()`: workspace x 0.22–0.56 m, y ±0.20 m, z 0.003–0.20 m; linear speed 0.25 m/s, angular speed 2 rad/s, tilt 30°, yaw ±60° |
| `teleop_real.py`, simulated or physical arm | `info["applied_action"]`: accepted target after controller limits/IK handling, not the next measured tip pose | CLI settings override defaults even with `--robot sim`: source defaults are x 0.10–0.65 m, y ±0.45 m, z 0.003–0.30 m, 0.15 m/s, yaw ±80°, tilt 30°; angular speed remains 2 rad/s |
| `record_handheld.py`, physical handheld | the next measured tip pose, paired with the preceding measured state/image | No workspace/speed/tilt/yaw clipping. The source defaults reject a saved attempt with fewer than 10 transitions, any >3 cm inter-sample jump, or an online unreachable count above 2% of its transition-count denominator. A retained episode is not thereby a complete demonstration-acceptance pass. |

The current [Class 10 practice collection command](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/2026-autumn/module-03-arm-data-for-guided-interaction/10-practice.md#start-the-recorder) explicitly selects the simulation-controller limits, `episode` mode, nominal start pose, `--no-start-noise` and `z_frame=start`. Store the actual command/configuration with every new dataset. Other settings are separate declared routes, not automatically the same contract. `ToolPushEnv` records this target before its pusher IK result. Controller-target limits do not guarantee successful IK, identical measured motion, successful contact or valid physical deployment.

The later `check_handheld_dataset.py` reads **observed states**, not `action`. It decodes them with a fixed `EpisodeFrame(TOOL_START_POS, TCP_DOWN_ROT)` and tests IK reach fraction ≥0.98, estimated peak linear speed ≤0.2625 m/s (105% of 0.25), tilt ≤30° and yaw within ±60°. It does not read `z_frame`, recover an episode's original start pose, test workspace membership/angular speed, execute logged actions through dynamics or assess visibility/contact/outcome. Default physical handheld data are table anchored, so this unchanged start-anchored checker is not a matched checker for them. Require a frame-aware checker or a documented conversion with validation before interpreting its output on such data. The online handheld IK check uses its selected height convention; it is a different acquisition check, not an independent full replay.

## Episode start pose and task

Rod tip at (0.33, 0, 0.12) m from the base (plus a small random offset on the arm), rod tilted 30 degrees forward,
camera toward the push direction. Push Cube: cube and goal in x 0.30 to 0.48 m, y plus or minus 0.12 m; goal 5 to
10 cm from the cube within plus or minus 70 degrees of +x; success when the cube centre is within 15 mm of the
goal centre (judged by the operator on the physical arm). Push-T: goal T at (0.40, 0); success at 90 % overlap.
