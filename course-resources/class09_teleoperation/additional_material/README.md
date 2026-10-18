# Class 09 additional material

Supplementary material of the Class 09 paper "Teleoperation of the reBot Arm with a Phone".

## What to do in this class

Teleoperate the simulated arm with the asMagic app on an iPhone (or with the phone simulator), record one
episode with the keyboard, inspect the recorded files and define one repeatable task.

### 1. Teleoperation and recording checklist (about 15 minutes)

- [ ] **Run.** Follow the four steps of "Teleoperate the simulated arm" below. Press Space; the gripper follows
      the phone. Move the phone along its camera direction, toward its top and toward its right: along which
      gripper direction does the gripper move each time? ______ / ______ / ______
- [ ] **Record.** Press the Right arrow, push the black cube about 10 cm, press the Right arrow again. Write the
      path that the log reports: ______
- [ ] **Inspect.** Open `meta.json` and `frames.csv` of that episode. Write the channel names in order, the
      mean timestamp step, the largest timestamp step and the number of frames: ______ / ______ / ______ / ______
- [ ] **Holds.** How many frames have `phone_age` above 0.25 s (stream lost) and how many have `blocked` = 1
      (reach limit)? ______ / ______
- [ ] **Sign.** In `frames.csv`, compare `state.elbow_flex` with `action.elbow_flex` on one row. Why do they have
      opposite signs, and what multiplies the action before the motor? (one sentence)
- [ ] **Phone alone.** Name two channels of the episode that the phone stream does not contain: ______, ______
- [ ] **Task.** Fill the task template at the end of this file for the task you recorded.

### 2. Task definition template

| Field | Your entry |
| --- | --- |
| Task name and one-sentence task string | |
| Objects (size, mass, colour) | black cube, 40 mm, 50 g / other: |
| Initial conditions (ranges in m, yaw in deg) | |
| Initial robot pose | home pose: TCP (0.25, 0, 0.10) m, gripper closed / other: |
| Success criterion (number and unit) | e.g. cube centre within 1.5 cm of a marked point |
| Time limit (s) | |
| Reset procedure (who moves what, in which order) | |
| Reject rule (when an episode is discarded) | |
| Control mode | position and orientation (default) / `--no-rotation` |
| Cameras recorded | front, side |

## Contents

| Path | Content |
| --- | --- |
| `code/teleop_rebot_rs_sim.py` | Teleoperation of the simulated arm with the asMagic app; keys for start/pause, recording and the gripper |
| `code/teleop_rebot_rs_real.py` | The same for the physical arm on the CAN bus (verified on the arm on 9 Oct 2026). **Read the safety rules below before you run it** |
| `code/teleop_common.py` | Shared parts: conventions, phone receiver and mapping, inverse kinematics, recorder, keys |
| `code/teleop_rebot_rs_pusher_sim.py` | The simulated teleoperation with another end effector: the pusher tool (rod + phone) of Classes 10 and 11 instead of the gripper |
| `code/fake_phone.py` | Publishes phone poses with the asMagic protocol, to use the scripts without an iPhone |
| `model/rebot_b601_rs_mjcf/` | The Class 08 model (arm, table, cameras) plus `scene_cube.xml` with one black 40 mm cube; the arm with the pusher tool (`rebot_b601_rs_pusher.xml`, `tool_pusher.xml`, `meshes/tool/robot_tool.stl`) and its scene `scene_pusher_cube.xml` with the cube and a green target; source and license in `NOTICE.md` |
| `leader_arm_teleop.md` | Optional guide: joint-space teleoperation with the reBot Arm 102 leader arm (vendor LeRobot pipeline) |
| `pyproject.toml` | Python dependencies (`mujoco`, `numpy`, `pillow`, `asmagic`, `sharklog`); the optional extra `real` adds the motor SDK `motorbridge` |

## Teleoperate the simulated arm

### Step 1: download the code and set up the environment

Supported: Ubuntu 22.04 / 24.04 and macOS 12 or later, with a desktop session. No GPU is needed. The setup is the
same as in Class 08; only the code of this class is needed.

1. Download the Class 09 package (`class09_teleoperation.zip`) and unzip it.
2. Install `uv` (one time): <https://docs.astral.sh/uv/getting-started/installation/>
3. Create the environment (one time, a few minutes; `asmagic` installs OpenCV):
   ```bash
   cd additional_material
   uv sync
   ```
   Equivalent after `source .venv/bin/activate`: run `python ...` (macOS `mjpython ...`) instead of `uv run python ...`.

### Step 2: install the asMagic app

Install asMagic from the App Store on an iPhone: <https://apps.apple.com/us/app/asmagic/id6661033548>.
Documentation: <https://doc.ancoraspring.com/asmagic>. Put the phone and the computer on the same Wi-Fi network.

### Step 3: run `teleop_rebot_rs_sim.py`

Open the app and open **Data Streaming** (Tools): the page shows the IP of the phone (here 10.127.120.185). Start
the script with that IP; it opens the viewer and waits for the stream.

```bash
uv run python code/teleop_rebot_rs_sim.py --phone-ip 10.127.120.185                       # Ubuntu
uv run mjpython code/teleop_rebot_rs_sim.py --phone-ip 10.127.120.185                     # macOS
uv run python code/teleop_rebot_rs_sim.py --phone-ip 10.127.120.185 --out recordings/cube  # choose the output folder
```

**Mapping: the phone is the gripper.** Hold the phone with the camera toward the table. A motion along the camera
direction moves the gripper along the direction it points at (down, toward the table); a motion toward the top of
the phone moves it along the open/close direction of the fingers; a motion toward the right side of the phone
moves it sideways; a rotation of the phone rotates the gripper the same way. One constant matrix does this,
`ee_tf_iphone` in `teleop_common.py` (the iPhone frame expressed in the end-effector frame; `a_tf_b` is the pose
of frame b in frame a). Press Space at a comfortable pose: at that moment the phone pose and the gripper pose
become the references, and only the motion since then counts.

Options: `--scene table` (no cube), `--scale 0.5` for half the motion, `--no-rotation` to keep the gripper
orientation (only the position follows), `--debug` for a status line every 5 s.

### Step 4: start the AR data stream

On the Data Streaming page switch **AR Data** on (port 8000). The log of the script reports `phone stream received`.
Keep the page open while you teleoperate: the pose is tracked by the camera, so point the phone at the
room, not at the ceiling.

| iPhone home screen | asMagic home page | Data Streaming page |
| --- | --- | --- |
| ![iPhone home screen](../figures/app_iphone_home.png) | ![asMagic home page](../figures/app_home.png) | ![Data Streaming page](../figures/app_data_streaming.png) |

Keys, with the viewer window focused:

| Key | Action |
| --- | --- |
| Space | start the teleoperation; press again to pause (the arm holds). At every start the current phone pose and the current gripper pose become the references |
| Right arrow | start recording; press again to stop and save the episode |
| Left arrow | discard the recording in progress |
| Enter | open / close the gripper |

Expected behaviour:

1. The viewer opens with the arm in its home pose above the table and the black cube in front of it. The terminal
   logs `waiting for the phone stream`, then `phone stream received` when the app is streaming.
2. Press Space: the log says `teleop started at TCP (0.250, 0.000, 0.100) m`. Move the phone slowly: the gripper
   follows it, at most 0.25 m/s and 90 degrees/s, inside the box x 0.12 to 0.42 m, y -0.25 to 0.25 m, z 0.03 to
   0.30 m. With the gripper pointing straight down it cannot rise above about 0.12 m (wrist limit): the arm then
   stops at the limit and follows again when the phone comes back; tilt the phone to tilt the gripper and reach
   higher. The fingertips are 15 mm below the TCP, so z = 0.03 m puts them 15 mm above the table.
3. Press the Right arrow: `recording started (episode_000)`. Push the cube. Press the Right arrow again:
   `recording stopped: recordings/sim/episode_000 saved (N frames)`. Left arrow instead: `recording discarded`.
4. If the stream stops (Wi-Fi, app in the background) the log warns `phone stream lost` and the arm holds its last
   target; it continues when the stream is back. Press Space to pause whenever the mapping feels wrong, move the
   phone to a comfortable position and press Space again.
5. Close the window to quit; a recording in progress is saved.

Without an iPhone, publish a test motion with `uv run python code/fake_phone.py` in a second terminal and use
`--phone-ip 127.0.0.1`: after Space the gripper draws a horizontal circle of radius 8 cm (`--pattern line` moves it
along the approach direction, `--pattern tilt` rocks it about the finger axis).

## Another end effector: the pusher tool

`teleop_rebot_rs_pusher_sim.py` is the same teleoperation with the pusher tool of Classes 10 and 11: a printed rod
with the iPhone on it. The phone sits on the tool, so the tool moves with the phone as one rigid body: a rotation
of the phone swings the rod tip about the phone. The mapping is the same `PhoneMapper` with the position of the
phone in the rod-tip frame added (`ee_p_iphone`, about 16 cm behind the tip); the script reads both from the
`phone` camera and the `tcp` site of the model.

```bash
uv run python code/teleop_rebot_rs_pusher_sim.py --phone-ip 10.127.120.185      # Ubuntu
uv run mjpython code/teleop_rebot_rs_pusher_sim.py --phone-ip 10.127.120.185    # macOS
```

Hold the phone in landscape, the back camera looking forward and down at the table, press Space and push the cube
into the green square. The keys are those of the gripper script without Enter. The episodes go to
`recordings/pusher/`, with six joints and three images per frame (`front`, `side`, `phone`).

Another end effector needs three changes: its model (a body under `link6` with a `tcp` site), its start pose
and its `ee_tf_iphone`, the pose of the phone in the end-effector frame.

## Teleoperate the physical arm

`teleop_rebot_rs_real.py` has the same keys and recording as the simulation script and drives the seven
RobStride motors of the physical reBot Arm B601-RS over the CAN bus (SocketCAN adapter, `can0`) with the
`motorbridge` SDK. Keys are read from the terminal (letters `r`, `d`, `g` are aliases of Right, Left, Enter; `q`
quits).

Before the first run, complete the Class 08 bring-up of the arm: wiring, `can0`, the motor zero and the parameter
template in Motorbridge Studio, the drag check and the joint motion test. Stop `motorbridge-gateway` before you
start this script: the gateway holds the CAN bus.

Another input device is a leader arm (reBot Arm 102) with the vendor LeRobot pipeline. It is not part of this
class; if you want to try it, follow `leader_arm_teleop.md`.

**Safety rules for the physical arm.** **One person must keep control of the power switch at all times and must
be able to cut the power without delay. Nobody stays inside the workspace of the arm while the motors are enabled;
operate the phone from outside the reach of the arm. Read the usage notes at the top of the script before you run
it. To stop normally, press `q` (or Ctrl-C): the arm returns to its zero pose, wrist first, and the motors are
disabled; wait until the log reports that the motors are disabled before you touch the arm. Use the power switch
only for an emergency stop; after an emergency stop the arm falls to its mechanical stops.**

```bash
uv sync --extra real                                                  # motor SDK, one time
sudo ip link set can0 up type can bitrate 1000000                     # SocketCAN adapter, once per boot
uv run python code/teleop_rebot_rs_real.py --phone-ip 10.127.120.185 --can can0 --set-zero   # only if the Class 08 zero is missing
uv run python code/teleop_rebot_rs_real.py --phone-ip 10.127.120.185 --can can0
uv run python code/teleop_rebot_rs_real.py --phone-ip 10.127.120.185 --can can0 --camera front=0 --camera side=2
```

Sequence: the motors switch to impedance (MIT) mode with gains 20 % below those of the vendor LeRobot driver; the arm moves in
6 s from its zero pose to the home pose (shoulder and elbow first, then the wrist); then the keys work as in the
simulation. On `q` or Ctrl-C the arm returns to the zero pose (wrist first) and the motors are disabled. Joint
targets are clipped to the soft limits and to 2 degrees per control period, then a first-order filter with a time
constant of 0.1 s (`--filter-tau`, 0 switches it off) smooths them before the motors; the motor temperatures are reported
over 115 °C and stop the script over 125 °C.

## Recording format

One folder per saved episode, `episode_000/`:

| File | Content |
| --- | --- |
| `meta.json` | fps (30), number of frames, scene, input device, robot type, channel names and units, direction vector |
| `frames.csv` | one row per frame: `frame_index`, `timestamp` (s since the start of the recording, wall clock), `state.<joint>` (7, motor angles in degrees), `action.<joint>` (7, command space in degrees), `phone_age` (s since the latest phone sample), `blocked` (1 when the arm was at its reach limit) |
| `front/000000.jpg`, `side/000000.jpg` | the two camera images of each frame, 640x480 (simulation: the two fixed cameras; physical arm: the `--camera` devices) |

The joint order is shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_yaw, wrist_roll, gripper, and
`motor target = action x [1, 1, -1, -1, -1, 1, 6]`, as in the LeRobot driver of the physical arm. The state is the
observation before the action of the same frame is applied.
