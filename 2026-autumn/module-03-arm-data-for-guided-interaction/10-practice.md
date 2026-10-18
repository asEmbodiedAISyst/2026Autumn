# Class 10 — Practice

On this page you collect Push Cube demonstrations in simulation: you teleoperate the simulated arm with the iPhone
and record what it does. Then you look at what you collected. After class you can also collect with the iPhone in
your hand. The class page [Class 10](10-collect-data-for-reinforcement-learning.md) explains the task, the tool, the episode frame and the dataset.

---

## Set up

The code is the pusher package of the course, `rebot_pusher`, for the pusher tool of the end of
[Class 09 — Practice](09-practice.md#the-pusher-tool). Class 11 uses the same package:
[`course-resources/class10_collect_data_for_learning/additional_material/rebot_pusher/`](https://github.com/asEmbodiedAISyst/2026Autumn/tree/main/course-resources/class10_collect_data_for_learning/additional_material/rebot_pusher).

You need Ubuntu 22.04 or 24.04 with a desktop session, or macOS 12 or later (Apple silicon or Intel).

The setup below installs `uv` in a course-local `.course-tools` environment and class dependencies in a package-local `.venv`. It does not change a system Python installation. If `uv` is already available, the three `.course-tools` bootstrap lines may be skipped.



Get the code and make the environment:

```bash
git clone https://github.com/asEmbodiedAISyst/2026Autumn.git rob7103
cd rob7103
python3 -m venv .course-tools
.course-tools/bin/python -m pip install uv
export PATH="$PWD/.course-tools/bin:$PATH"
cd course-resources/class10_collect_data_for_learning/additional_material/rebot_pusher
uv sync
```

If you already have the course checkout, update it with `git pull --ff-only` before opening the class package.

`uv sync` installs the declared MuJoCo, LeRobot and PyTorch dependencies into the package-local `.venv`. Download and setup time depend on the platform.

**macOS:** the MuJoCo window must run under `mjpython`. `scripts/teleop_real.py` opens the window, so it runs
with `uv run mjpython`; the other commands keep `uv run python`.

| Script | What it does |
| --- | --- |
| [`scripts/teleop_real.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/course-resources/class10_collect_data_for_learning/additional_material/rebot_pusher/scripts/teleop_real.py) | Teleoperation with the iPhone; `--robot sim --record` records the simulated arm |
| [`scripts/check_handheld_dataset.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/course-resources/class10_collect_data_for_learning/additional_material/rebot_pusher/scripts/check_handheld_dataset.py) | Replays a dataset on the simulated arm: reach, speed, tilt and yaw of every episode |
| [`rebot_sim/teleop/fake_phone.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/course-resources/class10_collect_data_for_learning/additional_material/rebot_pusher/rebot_sim/teleop/fake_phone.py) | Phone simulator, for a test without an iPhone |
| [`scripts/record_handheld.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/course-resources/class10_collect_data_for_learning/additional_material/rebot_pusher/scripts/record_handheld.py) | Optional: records demonstrations with the iPhone in your hand, phone pose and image, to a LeRobot dataset |
| [`DATA_FORMAT.md`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/course-resources/class10_collect_data_for_learning/additional_material/rebot_pusher/DATA_FORMAT.md) | The features, the episode frame and the height reference of the datasets |

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
uv run python scripts/teleop_real.py --robot sim --phone-ip <phone IP> --record --root datasets/my_sim_teleop --num-episodes 5
```
{% endtab %}

{% tab title="macOS" %}
```bash
uv run mjpython scripts/teleop_real.py --robot sim --phone-ip <phone IP> --record --root datasets/my_sim_teleop --num-episodes 5
```
{% endtab %}
{% endtabs %}

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
A failed push is discarded with the Left arrow.
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
| `action` | 9 | the tip pose to reach at the next frame |

Find also the names of the state, the fps (30) and `robot_type` (`rebot_pusher_tool_sim`). Then open
`meta/stats.json`: these are the numbers that normalise the data for training. `DATA_FORMAT.md` gives the frame
of each episode and the units.
{% endstep %}

{% step %}
### Replay on the simulated arm

```bash
uv run python scripts/check_handheld_dataset.py --root datasets/my_sim_teleop
```

The script replays each episode on the simulated arm with the same tool:

```
  ep frames  reach  peak speed  P95 speed  max tilt      yaw range
   0     91   100%    0.10 m/s   0.09 m/s     0.2 deg     -1 ~    0 deg
```

A `!` marks an episode with unreachable frames or with a motion outside the limits (0.25 m/s, tilt 30°, yaw
±60°). Data recorded through the simulated arm always stay inside these limits; data recorded by hand, in the optional handheld route,
may not.
{% endstep %}

{% step %}
### Audit a pilot with faults

The class folder has a pilot of ten handheld episodes, five of them with a fault. The audit script is in
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

The script reads only numbers and finds two faults. The other three need the images and the reachability check.
The answers are in `additional_material/data/pilot_push_cube_handheld/audit_reference.json`. Open it only after
you wrote your own.
{% endstep %}
{% endstepper %}

---

## Student activity

* [ ] **Collect:** record five teleoperated episodes of Push Cube in simulation.
* [ ] **Inspect:** write the features, their shapes, the fps and `robot_type` of your dataset.
* [ ] **Check:** replay your episodes. Do all of them reach 100 %?
* [ ] **Contract:** write a `README.md` for your dataset: task, scene, operator, date, height reference, rejects.
  Which items of the data contract of the class page does `info.json` not have?
* [ ] **Audit:** accept or reject each of the ten pilot episodes, with one reason each. Then compare with
  `audit_reference.json`.

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
### Touch the table, then start

Hold the tool with the phone mounted, as the robot would hold it. Rest the rod tip on the table for one second,
lift the tool to approximately 12 cm, the start height of the arm, and keep it still. The touch sets the zero of
the height axis for this episode.
{% endstep %}

{% step %}
### Push the cube

Push the cube into the goal in one smooth motion. The status line shows what the recorder sees:

```
frame   45 | phone   56 Hz | displacement [-3.9 -10.7  12. ] cm | tilt  0.0 deg yaw   0.0 deg | robot can reach | jumps 0
```

**Look at:** `robot can reach` tells you if the arm could follow your motion at this moment. Keep the tilt
below 30° and the yaw within ±60°: these are the limits of the arm.
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
### Check it with the same audit

```bash
uv run python scripts/check_handheld_dataset.py --root datasets/my_handheld
```

Compare with your simulated data: which one has the robot's own limits in it?
{% endstep %}
{% endstepper %}

With `--gesture --voice` you need no keyboard and no screen. A voice says each event and the next placement.

| Gesture | Event |
| --- | --- |
| Rest the rod tip on the table, then lift the tool | the table touch: the zero of the height axis for this episode |
| Rest the tool at the start pose, then move | the episode starts |
| Lift the tip 8 cm and hold still for 0.7 s | the episode is saved |
| Shake or twist the tool fast | the episode is discarded |
