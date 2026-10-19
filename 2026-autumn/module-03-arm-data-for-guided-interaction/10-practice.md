# Class 10 — Practice

On this page you collect Push Cube demonstrations in simulation: you teleoperate the simulated arm with the iPhone
and record what it does. Then you look at what you collected. After class you can also collect with the iPhone in
your hand. The class page [Class 10](10-collect-data-for-reinforcement-learning.md) explains the task, the tool, the episode frame and the dataset.

---

## Set up

The code is the pusher package of the course, `rebot_pusher`, for the pusher tool of the end of
[Class 09 — Practice](09-practice.md#the-pusher-tool). Class 11 uses the same package:
[`2026-autumn/resources/class10/practical/additional_material/rebot_pusher/`](https://github.com/asEmbodiedAISyst/2026Autumn/tree/main/2026-autumn/resources/class10/practical/additional_material/rebot_pusher).

You need Ubuntu 22.04 or 24.04 with a desktop session, or macOS 12 or later (Apple silicon or Intel).

<details>

<summary>Install uv (once)</summary>

`uv` installs Python and the packages of each class folder. Install it once, following the
[uv installation page](https://docs.astral.sh/uv/getting-started/installation/) or with this command, the same on
Linux and macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

If `curl` is not found, as on a fresh Ubuntu, install it with `sudo apt install curl`, or use `wget` instead:

```bash
wget -qO- https://astral.sh/uv/install.sh | sh
```

Open a new terminal afterwards, so that the `uv` command is found. Check it with `uv --version`.

</details>

Get the code and make the environment:

```bash
git clone https://github.com/asEmbodiedAISyst/2026Autumn.git rob7103
cd rob7103
cd 2026-autumn/resources/class10/practical/additional_material/rebot_pusher
uv sync
```

{% hint style="info" %}
If you cloned the repository in an earlier class, run `git pull` in the `rob7103` folder instead of `git clone`.
{% endhint %}

`uv sync` installs the declared MuJoCo, LeRobot and PyTorch dependencies into the package-local `.venv`. Download and setup time depend on the platform.

**macOS:** the MuJoCo window must run under `mjpython`. `scripts/teleop_real.py` opens the window, so it runs
with `uv run mjpython`; the other commands keep `uv run python`.

| Script | What it does |
| --- | --- |
| [`scripts/teleop_real.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/2026-autumn/resources/class10/practical/additional_material/rebot_pusher/scripts/teleop_real.py) | Teleoperation with the iPhone; `--robot sim --record` records the simulated arm |
| [`scripts/check_handheld_dataset.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/2026-autumn/resources/class10/practical/additional_material/rebot_pusher/scripts/check_handheld_dataset.py) | Checks observed poses with simulated-arm inverse kinematics; reports reachability, speed, tilt and yaw |
| [`rebot_sim/teleop/fake_phone.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/2026-autumn/resources/class10/practical/additional_material/rebot_pusher/rebot_sim/teleop/fake_phone.py) | Phone simulator, for a test without an iPhone |
| [`scripts/record_handheld.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/2026-autumn/resources/class10/practical/additional_material/rebot_pusher/scripts/record_handheld.py) | Optional: records demonstrations with the iPhone in your hand, phone pose and image, to a LeRobot dataset |
| [`DATA_FORMAT.md`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/2026-autumn/resources/class10/practical/additional_material/rebot_pusher/DATA_FORMAT.md) | The features, the episode frame and the height reference of the datasets |

---

## Collect data in simulation

{% stepper %}
{% step %}
### Connect the phone

{% hint style="warning" %}
**The computer and the iPhone must be on the same local network**, for example both on the campus Wi-Fi. The
script reads the stream from the IP address of the phone. A complex network, with many devices or several access
points, can delay the stream, and the arm then moves in jerks.
{% endhint %}

Open asMagic, open **Data Streaming**, switch **AR Data** on and read the IP address of the phone. The app and its
pages are shown in [Class 09 — Practice](09-practice.md#start-with-the-iphone).

**No iPhone?** Start the phone simulator in a second terminal and use `--phone-ip 127.0.0.1` below:

```bash
uv run python -m rebot_sim.teleop.fake_phone --pattern circle --hold tool --image
```
{% endstep %}

{% step %}
### Start the recorder

The mapping is that of the pusher tool in [Class 09 — Practice](09-practice.md#the-pusher-tool): the tool
moves with the phone as one rigid body. Hold the phone as it sits on the robot tool, in landscape, the main
camera looking at the table in front of you; best, mount it in the handheld print `hardware/hand_tool.stl`.

{% tabs %}
{% tab title="Linux" %}
```bash
uv run python scripts/teleop_real.py --robot sim --phone-ip <phone IP> --record \
    --action-mode episode --fps 30 --z-frame start --start-x 0.33 --start-z 0.12 --no-start-noise \
    --max-speed 0.25 --x-range 0.22,0.56 --y-range=-0.20,0.20 --z-min 0.003 --z-max 0.20 \
    --max-yaw 60 --max-tilt 30 --root datasets/my_sim_teleop --num-episodes 5
```
{% endtab %}

{% tab title="macOS" %}
```bash
uv run mjpython scripts/teleop_real.py --robot sim --phone-ip <phone IP> --record \
    --action-mode episode --fps 30 --z-frame start --start-x 0.33 --start-z 0.12 --no-start-noise \
    --max-speed 0.25 --x-range 0.22,0.56 --y-range=-0.20,0.20 --z-min 0.003 --z-max 0.20 \
    --max-yaw 60 --max-tilt 30 --root datasets/my_sim_teleop --num-episodes 5
```
{% endtab %}
{% endtabs %}

These options select the lecture's simulation-controller bounds and the fixed nominal start used by the later pose diagnostic: x 0.22–0.56 m, y ±0.20 m, z 0.003–0.20 m, 0.25 m/s, yaw ±60° and tilt 30°. Angular speed remains the controller default, 2 rad/s. `--robot sim` by itself does not select these bounds: the teleoperation defaults are 0.15 m/s, x 0.10–0.65 m, y ±0.45 m, z up to 0.30 m and yaw ±80°. Keep the exact command, source revision, start/frame convention and any changed settings in the dataset contract. These classroom options describe simulation; they are not a physical commissioning instruction.

The keys work in the MuJoCo window and in the terminal:

| Key | Action |
| --- | --- |
| Space | engage or pause; while paused the arm holds and you can move the phone freely |
| Right arrow or `r` | end the episode and save it |
| Left arrow or `d` | end the episode and discard it |
| `q` | quit |
{% endstep %}

{% step %}
### Push and save

Press Space, push the cube into the green target, and press the Right arrow to save:

```
[episode 1] end: save, saved (91 frames)
```

The arm then goes back to a new start pose with a new layout of the cube and the target. Record five episodes.
For this successful-demonstration collection, a failed push is discarded with the Left arrow. Record its rejection reason separately; discarded data do not remove failures from a later policy-evaluation denominator.
{% endstep %}
{% endstepper %}

---

## Inspect what you collected

{% stepper %}
{% step %}
### Open the files of your dataset

Open `datasets/my_sim_teleop/meta/info.json`. Find the three features and their shapes:

| Feature | Shape | Content |
| --- | --- | --- |
| `observation.images.phone` | 480 × 640 × 3 | the image of the phone on the robot tool |
| `observation.state` | 9 | the measured tip pose: position and orientation |
| `action` | 9 | accepted tool-pose target for this transition, after controller limits; not the next measured pose |

Find also the names of the state, the fps (30) and `robot_type` (`rebot_pusher_tool_sim`). Then open
`meta/stats.json`: these are the numbers that normalise the data for training. `DATA_FORMAT.md` gives the frame
of each episode and the units.
{% endstep %}

{% step %}
### Check the pose sequence on the simulated arm

```bash
uv run python scripts/check_handheld_dataset.py --root datasets/my_sim_teleop
```

The source checker decodes the **observed pose sequence**, solves inverse kinematics and estimates speed/tilt/yaw. It does not execute the logged actions through dynamics or reconstruct cube contact. It also does not test workspace-box membership, angular speed or the semantic correctness of `action`. Its terminal table has the following form; values depend on the recorded episode:

```
  ep frames  reach  peak speed  P95 speed  max tilt      yaw range
   0     91   100%    0.10 m/s   0.09 m/s     0.2 deg     -1 ~    0 deg
```

A `!` means this source diagnostic found reachability below 98%, peak speed above 105% of its 0.25 m/s bound (0.2625 m/s), tilt above 30°, or yaw outside ±60°. These tolerances differ from requiring every pose to pass. An accepted controller target does not guarantee that the measured state sequence passes every diagnostic.

**Frame assumption:** this unchanged checker creates a fixed `EpisodeFrame(TOOL_START_POS, TCP_DOWN_ROT)`. It does not read the dataset's `z_frame` or recover each original start pose. The collection command above explicitly uses `start`, the nominal (0.33, 0, 0.12) m start and `--no-start-noise`, so its episode-frame definition matches that diagnostic assumption. If you omit those settings, random start position/yaw or a changed start height changes the reconstructed placement. Do not pass table-anchored or differently initialised data to it and interpret the result as a faithful physical replay. A correct frame-aware checker or explicit, recorded conversion is required before extending this diagnostic to those records.
{% endstep %}

{% step %}
### Audit a pilot with faults

The class folder has a pilot of ten simulated handheld episodes. Five have a deliberately injected change; that count is not an acceptance target. The audit script is in
`additional_material/code/`. Run it from the package folder, with the environment of the package:

```bash
uv run python ../code/audit_dataset.py ../data/pilot_push_cube_handheld
```

Expected output (shortened):

```
dataset pilot_push_cube_handheld: 10 episodes, 638 frames, nominal 30Hz
ep04: 45frames; dt_ok=True; 0.250m/s; inside15mm=False; last recorded frame outside 15mm goal radius
ep06: 66frames; dt_ok=True; 0.600m/s; inside15mm=True; command speed exceeds declared limit
Visibility and reachability are NOT assessed; geometric success alone does not accept a demonstration.
```

The numeric script flags the truncated final recorded state and excessive command speed. It does not assess visibility, orientation or reachability and does not find every unacceptable demonstration. Compare the recorded source reachability metrics and inspect the images as separate evidence.

After writing your decision, read [the acceptance interpretation](../resources/class10/practical/additional_material/data/pilot_push_cube_handheld/ACCEPTANCE.md), alongside `../data/pilot_push_cube_handheld/audit_reference.json` from the current working directory. The JSON preserves injected-fault labels, source outcomes and metrics; it does not contain a complete accept/reject verdict. Episode 3 has no injected fault but reachability 0.903, below 0.98. Six episodes already have a recorded gate failure under this interpretation; four are eligible for image/remaining-contract review, not automatically accepted. Do not force the rejection count to five.
{% endstep %}
{% endstepper %}

---

## Student activity

For the core classroom response, inspect one supplied or newly recorded episode, make one accept/reject decision and complete its short contract. The complete five-episode collection and ten-episode fault audit below are the extended practice; finish them after class if needed.

* [ ] **Collect:** record five teleoperated episodes of Push Cube in simulation.
* [ ] **Inspect:** write the features, their shapes, the fps and `robot_type` of your dataset.
* [ ] **Check:** run the pose-sequence diagnostic. Report its assumed frame and reach fraction; does 100% IK success establish that the cube reached its target?
* [ ] **Contract:** write a `README.md` for your dataset: task, scene, operator, date, height reference, rejects.
  Which items of the data contract of the class page does `info.json` not have?
* [ ] **Audit:** accept or reject each of the ten pilot episodes, with one reason each. Then compare with
  the acceptance interpretation and `audit_reference.json`; distinguish an injected fault from a gate failure and state any review still needed.

---

## Optional physical handheld collection

The same task can be recorded without the arm: you hold the tool with the phone and push a real cube.

{% hint style="info" %}
**Photo to be added:** the handheld print with the iPhone mounted on it.
{% endhint %}

Print the handheld tool `hardware/hand_tool.stl`, the 40 mm cube `hardware/cube_40mm.stl` and the goal sheet
`hardware/goal_squares_a4.pdf` at 100 %. Network and app are as in the simulation route.

{% stepper %}
{% step %}
### Start the recorder

```bash
uv run python scripts/record_handheld.py --phone-ip <phone IP> --root datasets/my_handheld --num-episodes 5
```

The recorder prints a placement for the next episode, measured from the base mark on the table:

```
Suggested placement (from the base mark, x forward, y left, cm): cube (41, -7) turned 12 deg; goal (46, -7)
```

Put the cube and the goal there.
{% endstep %}

{% step %}
### Calibrate the keyboard session, then start each episode

The command above uses keyboard mode, without `--gesture`. At the initial calibration prompt, rest the rod tip on the table for one second, or press Enter while the tip is on the table to accept its current height. Wait for “Table height calibrated”. This sets the session's table-height reference.

Lift the tool to approximately 12 cm, the arm's nominal start height, and keep it still. Press **Enter to start recording**, then push. After saving or discarding an episode, place the next cube/goal, return to the start pose and press Enter to start again. A touch between keyboard episodes does not invoke per-episode table sampling. If the ARKit reference drifts, stop and calibrate a new, separately identified recording session; keep both session IDs in the contract.
{% endstep %}

{% step %}
### Push the cube

Push the cube into the goal in one smooth motion. The status line shows what the recorder sees:

```
frame   45 | phone   56 Hz | displacement [-3.9 -10.7  12. ] cm | tilt  0.0 deg yaw   0.0 deg | robot can reach | jumps 0
```

**Look at:** `robot can reach` reports the online IK check for the mapped pose. It does not check dynamic tracking, collision/contact or camera visibility. Keep the measured motion within the intended 0.25 m/s, 30° tilt and ±60° yaw contract and record the workspace/frame convention. This recorder does not clip or reject every speed/orientation/workspace violation; it writes the next measured pose as `action`, rather than a controller-limited command.
{% endstep %}

{% step %}
### Save or discard

Press Enter to save the episode, or `d` and Enter to discard it. After each episode the recorder prints the start
height above the table:

```
[episode] saved; saved 1/5
start height 12 cm
```

The recorder does not save an episode with an ARKit jump above 3 cm between two frames, or with more than 2 % of
poses that the arm cannot reach. It warns when the start height is more than 2.5 cm from 12 cm.
{% endstep %}

{% step %}
### Inspect the record and establish a frame-aware check

Inspect the images, feature names, units and the dataset card. Record that this handheld route uses table-anchored height by default. The earlier `check_handheld_dataset.py` command assumes a fixed start-anchored frame and cannot recover this convention from metadata. Do not interpret its raw output on this dataset as a matched reachability or replay result. The teaching team must supply a frame-aware check or a documented conversion with a validation record before comparing it with the simulated collection.

The recorder itself also performs its declared online checks. Distinguish those acquisition checks from a later, independently configured audit.
{% endstep %}
{% endstepper %}

### Optional gesture mode

For gesture input, add `--gesture --voice` to the optional handheld command. Complete the same initial session calibration. Before **every** episode, rest the tip on the table for about 0.5 s, lift to the approximately 12 cm start pose, hold still for about 0.5 s, then move to start. This mode searches the last 30 s of still samples for the table touch; the touch must be at least 5 cm below the start. If it reports no touch, it keeps the previous height. Discard or explicitly flag such an episode for reference review. Voice announces events and placement; verify this optional interface before relying on operation without a keyboard or screen.

| Gesture | Event |
| --- | --- |
| Rest the rod tip on the table, then lift the tool | per-episode table sample in gesture mode; a missing valid touch leaves the previous reference in use |
| Rest the tool at the start pose, then move | the episode starts |
| Lift the tip 8 cm and hold still for 0.7 s | the episode is saved |
| Shake or twist the tool fast | the episode is discarded |
