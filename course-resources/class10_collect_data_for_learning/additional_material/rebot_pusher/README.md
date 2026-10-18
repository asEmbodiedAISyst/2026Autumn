# reBot Arm with the pusher tool: collect, train, deploy

One printed tool, a 10 x 10 mm rod with an iPhone mount, is made twice: one with a handle for a person, one with
a flange for the reBot Arm B601-RS (the gripper and its motor are removed). The rod, the phone and the camera
have the same position relative to the rod tip in both prints. A person records demonstrations with the
handheld tool and the asMagic app; the same data format is recorded when the phone teleoperates the physical
arm; one policy is trained on both and runs on the arm. The method follows UMI (Chi et al., RSS 2024). A second
controller needs no data: Claude looks at the phone image and calls checked motion tools (`agent_control.py`).

| Handheld print and robot print (simulation) | The physical arm with the tool and the phone |
| --- | --- |
| ![tool](figures/ip17_handheld_vs_robot.png) | ![arm](figures/photo_arm_pusher_tool.jpg) |

Zero pose (left) and episode start pose (right) of the arm: ![poses](figures/real_zero_and_start.png)

## Status (15 October 2026)

| Item | State |
| --- | --- |
| Phone teleoperation of the physical arm with the tool (`teleop_real.py`) | verified by the course lead, 10 October 2026; Push Cube completed |
| Teleoperation dataset, physical arm | 11 episodes in `datasets/` (10 October 2026) |
| Handheld dataset, physical table | 150 episodes (13 October 2026), 717 MB, not in the package (see `datasets/README.md`) |
| Policies trained on physical data | ACT, Diffusion Policy, SmolVLA: 1 s open-loop error 29-35 mm against 51 mm for holding still |
| First rollouts of a learned policy on the arm (`rollout_real.py`) | 0 of 10 (14 October 2026): the start height of the data did not match the arm; corrections in section 6 |
| Agent controller (`agent_control.py`) | simulation: 5/5 with Sonnet 5.5 and Opus 5.5, 4/5 with Haiku 5.5; physical arm: Push Cube completed by the course lead; trial count, logs and videos to be added |

## Contents

| Path | Content |
| --- | --- |
| `scripts/generate_tool_demos.py` | Simulated demonstrations by the scripted expert (Push Cube or Push-T, handheld or robot tool), written as a LeRobot dataset; `--seed 20000 --num-episodes 300` gives the 300 Push Cube episodes of the course |
| `scripts/record_handheld.py` | Handheld recording without the robot: phone pose and image from asMagic to a LeRobot dataset in the robot format; table touch for the height reference; keyboard or hands-free (gesture and voice) control |
| `scripts/teleop_real.py` | Teleoperation of the physical arm with a second phone; records the same dataset format; `--robot sim` runs the same code on the simulated arm |
| `scripts/rollout_real.py` | Runs a trained policy on the physical arm (or `--robot sim`) |
| `scripts/agent_control.py` | Claude as the high-level controller: phone image with a table grid, tools `move`, `locate`, `push`, `done`; simulation or physical arm |
| `scripts/real_check.py` | First check of the arm with the tool: torque off, joint angles and rod-tip position against a ruler, wrist-roll re-zero |
| `scripts/asmagic_probe.py` | Prints the pose format, the axis directions and the camera field of view of a phone; `--scan` finds the phone on a network |
| `scripts/check_handheld_dataset.py` | Replays a handheld dataset on the simulated arm: reachable fraction, speed, tilt, yaw; optional video |
| `scripts/eval_offline.py` | Open-loop evaluation of a policy on held-out episodes (1, 10, 30 frames ahead against a hold-still baseline) |
| `scripts/eval_policy.py` | Closed-loop evaluation in simulation (handheld or robot embodiment) |
| `tools/anchor_z_to_table.py` | Converts a dataset with start-anchored height to table-anchored height |
| `tools/can/` | Optional automatic set-up of `can0` at 1 Mbit/s (systemd) |
| `rebot_sim/` | The package behind the scripts: conventions, IK, MuJoCo scenes, tool limits, phone mapping, gestures, voice, dataset writer, arm and camera backends, fake phone |
| `model/rebot_b601_rs_mjcf/` | MuJoCo model of the arm with the pusher tool, the handheld tool alone, table (photo of the course table), cube and T scenes; source and licence in `NOTICE.md` |
| `hardware/` | `hand_tool.stl`, `robot_tool.stl` (the two prints), `cube_40mm.stl`, `t_block.stl`, goal templates `goal_square.svg`, `goal_t.svg`, A4 goal sheets `goal_sheet_a4.pdf`, `goal_squares_a4.pdf` (print at 100 %), print project of the cube and the T block `cube+t_block.3mf` |
| `datasets/` | The 11 teleoperated Push Cube episodes; `datasets/README.md` describes all physical datasets |
| `videos/teleop_real_pusher_tool.mp4` | Phone teleoperation of the physical arm with the tool, 18 s, 10 October 2026 (no audio) |
| `figures/` | Simulation views of the tool, the zero and start poses of the arm, the photo of the physical arm with the tool |
| `DATA_FORMAT.md` | The dataset features, the episode frame, the height reference (`z_frame`) and the tool conventions |
| `tests/` | Tests without hardware (`uv run pytest`) |

## 1. Setup

Ubuntu 22.04 or 24.04 with Python 3.12 (uv installs it). The physical arm needs Linux (SocketCAN); macOS can run
the handheld recording, the training and the simulation.

```bash
uv sync                  # simulation, dataset recording, training, evaluation (installs LeRobot and torch)
uv sync --group real     # plus the arm driver (lerobot-robot-seeed-b601, motorbridge)
uv run pytest            # checks the package without hardware
```

`uv sync` without `--group real` removes the arm driver again; use `uv sync --group real` on the computer of the
arm.

Test the whole chain without a phone and without the arm:

```bash
uv run python -m rebot_sim.teleop.fake_phone --pattern circle --hold tool --image     # terminal 1
uv run python scripts/record_handheld.py --phone-ip 127.0.0.1 --root /tmp/handheld_test --auto 2
uv run python scripts/teleop_real.py --robot sim --phone-ip 127.0.0.1 --auto-engage --record --root /tmp/teleop_test --num-episodes 1
```

## 2. Hardware

- **Prints.** `hardware/hand_tool.stl` (handheld, with a 97 mm handle behind the flange) and
  `hardware/robot_tool.stl` (robot, four M3 screws on the output face of motor 6). Rod and phone plate are the
  same in both. Print with the rod parallel to the layers, 40 % infill or more; a rounded rod tip pushes the cube
  more evenly.
- **Phone.** An iPhone with asMagic, in a case with a MagSafe ring, in landscape on the plate: the phone centre
  on the ring groove, the main camera in the vertical plane of the rod. Mount it the same way every time; a mark
  on the plate helps. Power the phone during long sessions and fix the cable to the arm.
- **Robot mounting direction.** With all joints at zero (folded pose) the rod points forward and down and the
  phone is above it (figure above, left). After mounting, the wrist-roll zero is usually different from the
  gripper version: see `real_check.py --rezero 6`.
- **Objects.** `cube_40mm.stl` (40 mm, matte black, hollow, about 15 g) and `t_block.stl` (about 28 g). Print the
  goal sheets on paper at 100 % (check the 100 mm scale bar) and cut along the green edge; no white border. The
  simulation uses the same sizes, masses and the measured green.
- **Table.** The arm base stands directly on the table (z = 0 of the model; the rod tip goes down to 3 mm above
  the table) and is clamped. Hard, flat, light, matte surface with a fine texture (ARKit tracking); even light;
  no objects in the workspace box (x 0.10 to 0.65 m in front of the base, y plus or minus 0.45 m).
- **Marks on the table.** Base mark (where the base centre is or will be, with the forward direction), start
  mark 33 cm in front of it, workspace rectangle x 30 to 48 cm, y plus or minus 12 cm for the objects.
- **Network.** Phone and computer on the same 5 GHz Wi-Fi; the computer on a cable to the router when possible.
  A campus network often blocks traffic between devices: then let the computer open a hotspot
  (`nmcli dev wifi hotspot ...`) and connect the phone to it. `asmagic_probe.py --scan 10.42.0.0/24` finds the
  phone. Open the asMagic app, Data Streaming, switch AR Data on; the page shows the IP.

## 3. Route A: handheld collection (no robot)

```bash
uv run python scripts/asmagic_probe.py --phone-ip <phone IP>         # first use: pose format, axes, field of view
uv run python scripts/record_handheld.py --phone-ip <phone IP> \
    --repo-id local/handheld_push_cube --root datasets/handheld_push_cube --num-episodes 150
uv run python scripts/record_handheld.py --phone-ip <phone IP> \
    --repo-id local/handheld_push_cube --root datasets/handheld_push_cube --num-episodes 150 --gesture --voice
```

**Height reference.** The default is `--z-frame table`: the height in the data is the height above the table
(`DATA_FORMAT.md`). At the start of a session, rest the rod tip on the table for 1 s (or press Enter). In gesture
mode, also touch the table before every episode: the ARKit position drifts by some centimetres within minutes.

For every episode (keyboard mode):

1. Place the cube and the goal as the script suggests (the distribution of the simulated task). The goal lies 5
   to 10 cm from the cube, in front of it (push direction within plus or minus 70 degrees of "away from the
   base").
2. Hold the rod tip above the start mark, **12 cm high** (a stack of three cubes is a good height mark), rod tilted
   about 30 degrees forward, camera toward the push direction. Press Enter.
3. Turn toward the push direction so that cube and goal are in the image, move behind the cube, push along the
   cube-to-goal line, lift the rod when the cube is on the goal, stop. Press Enter: the episode is saved. Type
   `d` and Enter to discard it, `q` and Enter to quit. Add `--resume` to continue a dataset later.

Hands-free (`--gesture --voice`): touch the table with the tip and rest for half a second; lift to the start pose
and rest; start to move: the episode starts. To save, lift the tip 8 cm above the start height and hold still for
0.7 s. To discard, shake or twist the tool fast. The voice (English, `spd-say`) says the events and the next cube
and goal positions. The keyboard keeps working. You can run the recorder in an `ssh` session from a laptop.

Rules: smooth motion, speed below 0.25 m/s, rod tilt below 30 degrees, yaw within plus or minus 60 degrees; the
hand and the arm of the person stay out of the image. The script discards an episode with an ARKit jump (more
than 3 cm between two frames) or with more than 2 % of poses out of reach of the arm. After each episode it prints
the start height and warns when it is more than 2.5 cm from 12 cm. One episode takes about 7 s (3 to 16 s) plus the layout;
150 episodes take about one hour. Different people and light conditions improve generalisation.

Check the dataset: every episode replayed kinematically on the simulated arm with the same tool.

```bash
uv run python scripts/check_handheld_dataset.py --root datasets/handheld_push_cube
uv run python scripts/check_handheld_dataset.py --root datasets/handheld_push_cube --video 0 --out outputs/check_ep0.mp4
```

Pivot check of the phone mount (once): start an episode, keep the rod tip on one point of the table and rotate
the tool about it; the displacement in the status line must stay within plus or minus 1 cm. A larger change
means that the phone is not mounted as in the model.

## 4. Route B: teleoperation of the physical arm

Two phones: the controller phone in the handheld print (operator), the camera phone on the robot print. The arm
must have passed the bring-up of Class 08 (wiring, CAN, motor IDs, zero and parameters in Motorbridge Studio,
drag check, joint test). Stop `motorbridge-gateway` before a script of this package runs: it holds the CAN bus.

**Safety rules.** **One person keeps control of the power switch at all times and can cut the power without
delay. Nobody stays inside the workspace of the arm while the motors are enabled; the operator stands outside
the reach of the arm. Read the usage notes at the top of the script before you run it. To stop normally, press
`q` (or close the window or Ctrl-C): the arm returns to its folded zero pose in two stages and the motors are
disabled. The power switch is the emergency stop only; after it the arm falls.**

```bash
sudo ip link set can0 down 2>/dev/null
sudo ip link set can0 type can bitrate 1000000 restart-ms 100
sudo ip link set can0 up
ip -details link show can0                                            # must show UP and ERROR-ACTIVE
sudo tools/can/setup_can0.sh                                          # optional: do the above at every boot
uv run python scripts/real_check.py --can-port can0 --viewer          # torque off: move the arm by hand
uv run python scripts/real_check.py --can-port can0 --rezero 6        # only when the wrist-roll zero changed with the tool
uv run python scripts/teleop_real.py --robot real --can-port can0 --phone-ip <controller IP> --no-camera --max-speed 0.10
uv run python scripts/teleop_real.py --robot real --can-port can0 --phone-ip <controller IP> --camera-ip <robot phone IP> \
    --max-speed 0.20 --z-frame table --record --repo-id local/teleop_push_cube --root datasets/teleop_push_cube --num-episodes 50
```

- `real_check.py`: the zero of the motors comes from Motorbridge Studio; the script only writes the marker file
  of the plugin (do not run `lerobot-calibrate`, it expects seven motors). With torque off, move each joint by
  hand: the twin in the window must follow in the same direction; the rod tip on the table must read a height
  near 0 and 30 cm in front of the base must read x about 30 cm. If not, check the zero and the mounting
  direction before any powered motion.
- Start of a run: after the confirmation the arm moves at 20 degrees per second to the start pose (shoulder and
  elbow first, then base and wrist). The terminal waits up to 10 s for the controller phone.
- Keys (window or terminal): Space engages and disengages (the motion of the hand tool becomes the motion of the
  robot tool; disengaged, the arm holds and the phone can be moved), Right or `r` saves the episode, Left or `d`
  discards it, `q` quits. At engage, position and yaw are aligned to the current arm pose and the orientation
  blends over 1 s (`--orientation absolute`, the tilt of the robot tool equals the tilt of the hand tool: use it
  for recording; `--orientation relative` makes the pose at Space the neutral pose: use it to learn the control).
- **Height reference.** `teleop_real.py` records with `--z-frame start` by default. Use `--z-frame table` when the
  data will be merged with handheld data (table frame by default). The 11 episodes in `datasets/` are in the
  start frame.
- Limits and smoothness: `--max-speed` (start at 0.10 m/s, data at 0.20 to 0.25), `--x-range`, `--y-range`,
  `--z-min`, `--z-max`, `--max-tilt`, `--max-yaw`; `--kp-scale 0.8` (MIT gains 40/120/120/40/40/40),
  `--filter-tau 0.1` (first-order filter on the joint targets), `--max-step-deg 3` (90 degrees per second),
  `--stream-hz 150`: a background thread sends the motor commands at 150 Hz, interpolates between two 30 Hz
  targets and gives the slope as a velocity feedforward (no knocking sound, less lag; with it,
  `--filter-tau 0.05 --kp-scale 1.0` is safe). The gravity feedforward uses the MuJoCo model of the arm with the
  tool.
- Faults: a joint more than 20 degrees behind its target slows the advance of the target in proportion and stops
  it at 40 degrees (status shows the speed factor); a joint more than 10 degrees behind that moves less than
  1 degree in 1 s is a collision: torque off and stop; a joint target that jumps more than 25 degrees is refused
  and stops the run. IK failures hold the previous pose (status `IK FAIL`).
- Recording: one episode = arm at the start pose, objects placed, Space, push, Right. Frames with an image older
  than 0.2 s count as missing; an episode with more than 5 % missing frames is discarded. The status line shows
  the tracking error (joint, rotation, position) and the image age (50 to 150 ms over Wi-Fi).
  `--log-mapping outputs/mapping.csv` logs the phone pose, the mapped tip pose, the command and the measured pose
  of every frame.

## 5. Train

Handheld and teleoperation datasets have the same features and the same `robot_type` (`rebot_pusher_tool_real`).
Before a merge, check that they have the same height reference and the same scene (`DATA_FORMAT.md`). LeRobot
trains on one dataset; merge with:

```bash
uv run lerobot-edit-dataset --operation.type merge \
    --operation.repo_ids "['local/handheld_push_cube','local/teleop_push_cube']" \
    --operation.roots "['datasets/handheld_push_cube','datasets/teleop_push_cube']" \
    --new_repo_id local/mixed_push_cube --new_root datasets/mixed_push_cube
```

Convert an older dataset with start-anchored height: `uv run python tools/anchor_z_to_table.py datasets/<name>`
(writes `datasets/<name>_tablez`). Keep the last 20 episodes out for the offline evaluation.

```bash
# ACT, Push Cube (about 1 h for 60k steps on an RTX 5090)
uv run lerobot-train --dataset.repo_id=local/handheld_push_cube --dataset.root=datasets/handheld_push_cube \
    --dataset.episodes="[$(seq -s, 0 129)]" --dataset.image_transforms.enable=true \
    --policy.type=act --output_dir=outputs/train/act_push_cube --job_name=act_push_cube \
    --policy.device=cuda --wandb.enable=false --policy.push_to_hub=false \
    --steps=60000 --batch_size=16 --save_freq=20000
# Diffusion Policy (multimodal demonstrations, e.g. Push-T; about 2.5 h for 60k steps)
uv run lerobot-train --dataset.repo_id=local/handheld_push_t --dataset.root=datasets/handheld_push_t \
    --policy.type=diffusion --output_dir=outputs/train/dp_push_t --job_name=dp_push_t \
    --policy.device=cuda --wandb.enable=false --policy.push_to_hub=false --steps=60000 --batch_size=32
```

`image_transforms` adds random brightness and contrast, which helps with real images. SmolVLA is installed too
(`--policy.type=smolvla`; map the phone camera to `camera1` with `--rename_map` and set
`--policy.empty_cameras=2`). In the simulation study of the course (300 handheld Push Cube episodes, ACT 60k
steps) the policy trained on handheld data reached 60 to 70 % on the simulated arm, the same as a policy trained
on arm data. With the 150 physical handheld episodes (130 for training), ACT, Diffusion Policy and SmolVLA reach a
1 s open-loop error of 29 to 35 mm against 51 mm for holding still; a policy trained on simulated data only gives
74 mm.

## 6. Evaluate and deploy a policy

```bash
# open loop on held-out episodes: predicted pose 1 / 10 / 30 frames ahead against the human pose and a hold-still baseline
uv run python scripts/eval_offline.py --policy-path outputs/train/act_push_cube/checkpoints/last/pretrained_model \
    --root datasets/handheld_push_cube --episodes 130-149
# closed loop in simulation (only for policies trained on simulated images)
uv run python scripts/eval_policy.py --policy-path <checkpoint>/pretrained_model --embodiment pusher --episodes 50
# physical arm, data in the table frame: Space starts and pauses, Right = success, Left = failure
uv run python scripts/rollout_real.py --robot real --can-port can0 --camera-ip <robot phone IP> \
    --policy-path outputs/train/act_push_cube/checkpoints/last/pretrained_model \
    --z-frame table --temporal-ensemble 0.01 --max-speed 0.10 --episodes 10 --video-dir outputs/real_rollouts
```

- The 1-frame error of the offline evaluation has no meaning (the hand moves a few millimetres per frame); at 10
  and 30 frames the policy error must be clearly below the hold-still baseline. A policy trained on real images
  cannot be judged in the MuJoCo renderer: the images differ.
- **The start height must match the data.** The policy outputs motion relative to the start pose. For data in the
  start frame, give the start height that makes the pushes of the data reach the table: `--start-z 0.085` for the
  first physical handheld dataset (its episodes go down 8.5 cm on average from the start pose; the start height
  above the table has a median of 9.4 cm, not 12 cm). For data in the table frame use `--z-frame table`.
- `--temporal-ensemble 0.01` (ACT only) runs the policy at every step and averages the overlapping action chunks:
  no jerk at each new chunk. Diffusion Policy: `--n-action-steps 16` to `32`. SmolVLA: no ensemble (chunk of 50,
  about 150 ms per inference).
- `--video-dir` saves the phone image and the state of every rollout (mp4 and npz) for comparison with the data.
- When the image is older than 0.3 s the arm stops. The physical rollout is the final evidence; the safety rules
  of section 4 apply, start with `--max-speed 0.10`.
- Look for: does the policy move toward the cube at once (it sees the cube); does the tip scrape the table (adjust
  `--z-min`); does it come back after a push past the goal; standing still usually means that the image differs
  too much from the data (light, goal sheet, table).
- First physical result (14 October 2026, before `--start-z` and `--z-frame table`): ACT trained on 130 physical
  episodes moved to the cube and pushed it, always off its line: 0 of 10. ACT with physical and simulated data
  sometimes moved away from the cube.

## 7. Claude as the controller (`agent_control.py`)

The model looks at the phone image and decides the next motion; the executor of `rollout_real.py` (software
limits, IK, speed limits) carries it out. One API call per step. The model receives the phone image (reduced to
512 x 384) with a 5 cm table grid projected from the known camera pose (yellow lines: constant x, cyan: constant
y, numbers every 10 cm; red circle: the rod tip on the table; red arrow: forward), the rod-tip position and the
results so far. It must call one tool:

- `move`: up to three relative moves of the rod tip (dx forward, dy left, dz up, in cm; optional yaw). Each target
  is checked (workspace box, IK, length at most 15 cm); a target that fails is rejected with the reason, not
  clipped, and the moves after it do not run;
- `locate`: a pixel to table coordinates (the model does the perception, the script the geometry);
- `push` (`--mode push`): the model marks the cube and the goal centre; the script approaches from behind the
  cube, lowers the tip and pushes along the line (at most 6 cm per call), then lifts the tip;
- `done`: the episode ends; in simulation the simulator checks the claim.

```bash
uv run python scripts/agent_control.py --robot sim --episodes 5 --model claude-sonnet-5-5 --mode push --log-dir outputs/agent/sonnet_push
uv run python scripts/agent_control.py --robot sim --episodes 5 --model claude-opus-5-5 --log-dir outputs/agent/opus_step
uv run python scripts/agent_control.py --robot real --can-port can0 --camera-ip <robot phone IP> \
    --model claude-opus-5-5 --mode push --max-speed 0.10 --episodes 3 --log-dir outputs/agent/real
```

Options: `--model`, `--mode step|push` (default step), `--effort low|medium|high`, `--episodes 5`,
`--max-calls 25`, `--seed 0`, `--log-dir` (the grid image of every step and the conversation of every episode),
`--video` (phone view and third-person view per episode), `--push-height 0.008` (never below `--z-min`), `--auto`
(physical arm: start without Space), plus the robot options of `teleop_real.py`. On the physical arm Space starts
the episode and pauses the arm mid-motion; Right ends it as a success, Left as a failure. The terminal prints the
number of calls and the cost at API list prices.

Simulated results (Push Cube, the random layouts of the policy evaluation, seeds 0 to 4, 15 October 2026):

| Model | Mode | Success | Mean calls | Mean time | Cost of 5 episodes |
| --- | --- | --- | --- | --- | --- |
| Sonnet 5.5 | push | 5/5 | 2.2 | 6 s | $0.04 |
| Sonnet 5.5 | step | 5/5 (1) | 5.4 | 20 s | $0.17 |
| Opus 5.5 | step | 5/5 | 5.2 | 23 s | $0.30 |
| Haiku 5.5 | step | 4/5 | 9.4 | 35 s | $0.03 |

(1) One episode ended with the model's own `done` claim, before the simulator checked claims. That layout was run
again with the check: success in 4 calls.

**API key.** The script reads the key from the environment variable `ANTHROPIC_API_KEY` (or `CLAUDE_API_KEY`),
or from a file `.claude.env` in this folder (`ANTHROPIC_API_KEY=...`). `.claude.env` and `*.env` are ignored by
git. **Never put a key in a script, a notebook, a commit, a zip, a screenshot or a log that you share.** The
course does not provide a key; each user needs an Anthropic account.

Each step takes 2 to 5 s and needs the network: the agent cannot run at 30 Hz like a policy. Its success on the
physical arm depends on how well the model locates the cube and the goal in the real image; record every
episode (count, conditions, outcome, interventions) as for a learned policy.
