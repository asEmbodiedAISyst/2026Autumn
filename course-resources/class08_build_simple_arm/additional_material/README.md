# Class 08 additional material

Supplementary material of the Class 08 paper "Let's Build a Simple Arm and Turn It On".

## What to do in this class

Inspect the simulation's joint order, limits and reference configuration. Then, optionally, complete the short
commissioning checklist. Setup and run commands are in the sections below; write your answers on a copy of this list and submit
it to your team repository before the next class.

### 1. Inspection checklist (simulation, about 10 minutes)

Open the viewer (`uv run python code/view_arm_scene.py`, macOS `uv run mjpython ...`) and read the joint table
that the script prints.

- [ ] **Joint order.** Write the seven actuator names in the order of the Control sliders:
      1 ______ 2 ______ 3 ______ 4 ______ 5 ______ 6 ______ 7 ______
- [ ] **Limits.** For joint2 (shoulder_lift) and joint3 (elbow_flex), read the model range (radians) from the slider,
      convert it to degrees and compare it with the soft limit in the table. Which one is tighter?
      joint2: ______ to ______ deg, tighter: model / soft limit; joint3: ______ to ______ deg, tighter: model / soft limit
- [ ] **Reference poses.** Press `Z` (zero pose) and `H` (home pose). Describe each pose in one line (where the gripper
      points, where the tool centre point is). Zero: ______ Home: ______
- [ ] **Sign.** Move the joint3 slider to a larger angle. Does the elbow go up or down? ______ The dataset
      convention multiplies this joint by -1 before the motor; why can the model keep the URDF sign? (one sentence)

### 2. Short commissioning checklist (the three gates), optional

Optional in this class. Tick what the simulation can close today; the other items wait for the physical arm.
Vendor references for the physical steps: the official getting-started tutorial
<https://wiki.seeedstudio.com/rebot_b601_rs_getting_started/> (power, CAN, motor IDs, zero position, parameter
template) and the assembly video <https://www.youtube.com/watch?v=Bv60NPO0TRo>.

**Gate A, assembly (power off)**
- [ ] the five boxes of one arm have the same number n: RS-Pn Power Adapter, RS-Sn Structure Kit, RS-Mn Motor Kit,
      RS-Cn Clamp for Mounting, RS-Gn Gripper Kit
- [ ] 7 actuators present: 3 x RS-06 (joints 1-3), 4 x RS-00 (joints 4-6, gripper)
- [ ] thread-locked screws tightened with a low torque (3-6 kgf cm), cables with slack through the full joint range
- [ ] one 120 ohm termination at each end of the CAN bus (about 60 ohm between CAN-H and CAN-L)
- [ ] base fixed to the table; arm folds to the zero pose by hand, gripper closed

- [ ] wiring: USB-to-CAN adapter (DIP switch 120R), splitter board, XT30 power cable, XT30 2+2 cable to motor 1;
      a switch in the 48 V line within reach of the operator

**Gate B, communication (power on, motors off)**
- [ ] 48 V / 12.5 A supply, emergency stop tested
- [ ] CAN bus at 1 Mbit/s; `motorbridge-cli scan` finds motor IDs 1-7
- [ ] Motorbridge Studio: Scan All Joints, Zero All in the folded pose, parameter template written and read back
- [ ] gateway stopped; after a power cycle the folded pose reads 0 +- 2 degrees on every joint

**Gate C, motion (supervised)**
- [ ] drag check: the digital twin follows each joint in the same direction (`real_gripper_drag.py --viewer`)
- [ ] gravity hold: the arm stays where it is left (`real_gripper_drag.py --mode gravity`)
- [ ] joint test: +-10 degrees at 5 degrees/s on joints 1-6, tracking error well below 15 degrees, return to zero
      (`real_gripper_motion_test.py --viewer`)
- [ ] soft limits of the joint table loaded; TCP speed limit 0.05 m/s for the first motion
- [ ] hold test: the arm keeps the home pose, drift below 0.5 degrees in 10 s (simulation: yes, see the hold figure)
- [ ] bounded motion: each joint +-10 degrees from home and back (simulation: `controlled_motion.py --mode joints`)
- [ ] a command outside the limits is rejected or clipped (simulation: the IK clips to the limits)
- [ ] the arm holds its last target when the command stream stops; emergency stop works during motion

## Contents

| Path | Content |
| --- | --- |
| `model/rebot_b601_rs_mjcf/` | The converted MuJoCo model of the arm (the course standard): `rebot_b601_rs.xml` generated from the vendor URDF, the table environment `table_env.xml`, the scene `scene_table.xml` (arm on the table), the meshes, the source URDF and `NOTICE.md` (source commit and license). Only what this class needs; task objects and tools come in later classes. The original mechanical description (URDF, joint table, meshes, CERN-OHL-W-2.0) is not copied; it is at <https://github.com/Seeed-Projects/reBot-DevArm/tree/main/Rebot_Arm_description/RS>. |
| `code/view_arm_scene.py` | Standalone script: opens the arm on the table in the MuJoCo viewer, prints the joint table (IDs, names, limits); keys Z and H move the arm to the zero and home poses. |
| `code/controlled_motion.py` | Controlled-motion example in simulation: joint-by-joint motion (each joint +-10 degrees from the home pose, then the gripper) and a Cartesian motion (the TCP draws the letters ROB 3 cm above the table with inverse kinematics). Prints the tracking errors. |
| `code/real_gripper_drag.py` | Physical arm, Gate C steps 1-2: zero-torque drag and gravity-only drag; a table of the seven motors and, with `--viewer`, the digital twin that follows the measured joint angles. Never commands a motion. `--rezero` writes the folded pose as the motor zero after you type `yes`. |
| `code/real_gripper_motion_test.py` | Physical arm, Gate C step 3: holds the zero pose, moves joints one at a time +-10 degrees at 5 degrees/s, aborts above 15 degrees tracking error, returns to zero in two stages, writes a JSON log to `outputs/real_gripper/`. |
| `results/motion_test_20261010_000129.json` | The joint motion test of the course arm on 10 October 2026 (hold, gravity sweep and fit, joint 2 at +10 degrees: the -10 degree side is below the soft limit and is skipped) |
| `rebot_sim/` | The small package behind the two scripts: joint conventions, the twin (the model of this folder), the arm backend on the Seeed LeRobot plugin. |
| `tools/can/` | `setup_can0.sh` and `can0.service`: optional automatic set-up of `can0` at 1 Mbit/s (systemd). |
| `tests/` | Tests without hardware (`uv run pytest`). |
| `pyproject.toml` | Python dependencies of the scripts (`mujoco`, `numpy`), for `uv`; the group `real` adds the Seeed LeRobot plugin and `motorbridge` (Linux, Python 3.12-3.13). |

## Setup

Supported: Ubuntu 22.04 / 24.04 and macOS 12 or later (Apple silicon or Intel), with a desktop session. No GPU is
needed. Commands are the same on both systems unless a macOS line is given.

1. Download the Class 08 package (`class08_build_simple_arm.zip`) and unzip it.
2. Install `uv` (one time): <https://docs.astral.sh/uv/getting-started/installation/>
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. Create the environment (one time, about one minute). `uv` downloads a Python and installs `mujoco` and `numpy`
   into `.venv` inside this folder:
   ```bash
   cd additional_material
   uv sync
   ```
4. Open the arm on the table in the MuJoCo viewer:
   ```bash
   uv run python code/view_arm_scene.py              # Ubuntu
   uv run mjpython code/view_arm_scene.py            # macOS: the viewer needs mjpython
   ```
   Options: `--pose zero` (start in the calibration pose), `--list` (print the joint table only, no window).
5. Run the controlled-motion example (same rule for macOS: `mjpython`):
   ```bash
   uv run python code/controlled_motion.py                    # both motions, in the viewer
   uv run python code/controlled_motion.py --mode joints      # joint-by-joint only
   uv run python code/controlled_motion.py --mode letters     # the ROB drawing only
   uv run python code/controlled_motion.py --no-viewer        # no window, errors in the terminal
   ```
   The terminal prints the largest tracking error of each joint (about 1 degree during the move) and of the TCP
   (a few millimetres): the position actuators lag behind a moving target. The red dots in the viewer are the
   drawn path.

   Equivalent, if you prefer an activated environment (bash or zsh, Ubuntu and macOS):
   ```bash
   source .venv/bin/activate
   python code/view_arm_scene.py                     # Ubuntu
   mjpython code/view_arm_scene.py                   # macOS
   deactivate                                        # when you are done
   ```
   `uv run` and the activated `.venv` use the same interpreter and packages. `uv run` works in any shell without
   activation; the activated environment is convenient for several commands in a row.

In the viewer, open the "Control" group of the right panel. The sliders are the seven actuators in the order of the
joint table printed in the terminal: six joints in radians, the gripper in metres. Keys: `Z` moves the arm to the
zero (calibration) pose, `H` to the home pose. Left-drag rotates the camera, right-drag pans, the mouse wheel zooms.


## Bring-up of the physical arm (teaching team)

Students do not operate the powered arm. This section is the procedure of the teaching team; the paper gives it in
the section "Commissioning Gates". Vendor references: the getting-started tutorial
<https://wiki.seeedstudio.com/rebot_b601_rs_getting_started/> and the text guide for motor IDs and zero
<https://github.com/Welt-liu/reBot-B601-Agent-Guide>.

**Safety rules.** **One person keeps control of the power switch at all times and can cut the power without
delay. Nobody stays inside the workspace of the arm while the motors are enabled. Read the usage notes at the top
of each script before you run it. Stop a script in the way that its notes give, and hold or fold the arm before
the torque goes off. The power switch is the emergency stop only: after it the arm falls to its mechanical
stops.** Do not plug or unplug a motor cable while the supply is on. The only exception to the workspace rule is
the drag check: the motors give zero torque or only gravity torque, one staff member moves the arm by hand, and a
second person holds the power switch.

### 1. Wiring (power off)

1. Connect motor 1 and motor 2 as in the vendor tutorial; check the chain of cables to motor 7.
2. Connect the USB-to-CAN adapter, the power and signal splitter board, the XT30 power cable and the XT30 2+2
   cable. The other end of the 2+2 cable goes to motor 1. Set the DIP switch of the adapter to 120R.
3. Put a switch in the 48 V line. Use a branded 48 V supply (kit: 48 V, 12.5 A). Mains selector: 230 V for 220 V
   mains, 115 V for 110 V mains.
4. With the supply off, measure about 60 ohm between CAN-H and CAN-L.

### 2. Power on and the CAN bus (motors stay disabled)

Use a Linux computer, not a virtual machine.

```bash
uv sync --group real                              # Seeed plugin + motorbridge (Python 3.12-3.13)
sudo modprobe peak_usb
ip -br link                                       # can0 is listed
sudo ip link set can0 down 2>/dev/null
sudo ip link set can0 type can bitrate 1000000 restart-ms 100
sudo ip link set can0 up
ip -details link show can0                        # UP, ERROR-ACTIVE, bitrate 1000000
uv run motorbridge-cli scan --vendor robstride --channel can0 --start-id 1 --end-id 7   # 7 motor(s) found
sudo tools/can/setup_can0.sh                      # optional: configure can0 automatically at each boot
```

A new RobStride motor answers on ID 127. Then write the IDs with one motor connected at a time (power off before
each change of cable):

```bash
uv run motorbridge-cli id-set --vendor robstride --channel can0 --motor-id 127 --new-motor-id 5
```

`store_parameters failed: response ack timeout` after `id-set` is normal (the motor restarts); scan to confirm.

### 3. Zero and parameters in Motorbridge Studio

```bash
uv run motorbridge-gateway -- --bind 127.0.0.1:9002 --transport socketcan --channel can0
```

1. Open <https://motorbridge.github.io/motorbridge-studio/> and click Connect (`ws://127.0.0.1:9002`).
2. Arm Model: `rebot-arm-robstride`. Click Scan All Joints: joints 1-7 must be online.
3. Fold the arm by hand to the zero pose (all joints folded, gripper closed).
4. Click Zero All and confirm twice. Studio allows it only when the joints are near zero; use the force option only
   when the arm is truly in the mechanical zero pose.
5. Click Read Params (keep the values as a record), then Write Default Params, with the arm
   supported and nobody near it. The step passes when the read-back matches.
6. Stop the gateway (Ctrl-C). **The gateway holds the CAN bus; no other program can use the bus while it runs.**
7. Switch the supply off and on. The folded pose must read 0 +- 2 degrees in the next step. Some firmware does not
   keep the zero through a power cycle; then write it again.

### 4. Drag check with the digital twin, gravity hold, joint test

```bash
uv run python code/real_gripper_drag.py --can-port can0 --viewer                  # zero torque: move each joint by hand
uv run python code/real_gripper_drag.py --can-port can0 --mode gravity --viewer   # gravity only: support the arm at start
uv run python code/real_gripper_motion_test.py --can-port can0 --viewer           # +-10 deg per joint, then return to zero
uv run python code/real_gripper_motion_test.py --can-port can0 --joints 2 --viewer  # one joint only
```

- Drag check: the twin must turn the same joint in the same direction, the folded pose reads about 0 degrees,
  every state is `OK`. A joint that turns the wrong way stops the bring-up. If the folded pose does not read zero:
  `real_gripper_drag.py --can-port can0 --rezero` (type `yes`). Ctrl-C ends the zero-torque mode at once.
- Gravity hold: the arm stays where you leave it. The first Ctrl-C keeps the compensation: fold the arm, then press
  Enter. A second Ctrl-C disables the torque at once. If the arm drifts, correct the gravity model with
  `--gravity-joint-scale`, `--gravity-joint-offset` or `--gravity-joint-fit` (a sweep:
  `real_gripper_motion_test.py --joints 2 --gravity-sweep 0,15,30,45,60,75 --gravity-sweep-elbow 60`).
- Joint test: hold error below 3 degrees, worst tracking error well below 15 degrees (2-5 degrees is normal),
  smooth torque, no temperature rise. At the end the arm returns to zero in two stages (joints 1, 4, 5, 6, then
  2, 3) and the torque goes off. A tracking error above 15 degrees disables the torque at once: the arm can fall.
  Ctrl-C holds the last target until Enter, then disables the torque: support the arm first. The log is written
  to `outputs/real_gripper/motion_test_<time>.json`.

Result on the course arm, 10 October 2026: folded pose within 0.6 degrees of zero; joint 2 (+-10 degrees at
5 degrees/s): worst tracking error 1.9 degrees, peak torque 1.9 N m, 27 C.

After these steps the arm is ready for Class 09 (phone teleoperation). Stop `motorbridge-gateway` before any
course script runs.
