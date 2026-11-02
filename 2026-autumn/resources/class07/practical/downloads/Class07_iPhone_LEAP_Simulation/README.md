# Class 07 iPhone-to-LEAP simulation

This package is simulation-only. The iPhone running asMagic is the only
physical device used. The package contains no motor, serial-bus or Dynamixel
control interface.

## Install

Install `uv`, open a terminal in this folder, and run:

```bash
uv sync --locked
uv run pytest
uv run python simulation/iphone_leap_sim.py --check
```

The final command must report `"status": "pass"`, 16 model actuators, 16
retargeted joints, a loaded MediaPipe model, a finite MuJoCo state and
`"motor_interface_included": false`.

## Connect the iPhone

1. Connect the iPhone and computer to the same Wi-Fi network.
2. Open asMagic on the iPhone.
3. Open **Panel → Tools → Data Streaming**.
4. Enable **AR Data** on port 8000.
5. Keep the app foregrounded and copy the IP displayed on that page.

Run the simulation, replacing the example address:

```bash
uv run python simulation/iphone_leap_sim.py \
  --iphone-ip 10.127.120.185 \
  --port 8000
```

On macOS, use MuJoCo's launcher:

```bash
uv run mjpython simulation/iphone_leap_sim.py \
  --iphone-ip 10.127.120.185 \
  --port 8000
```

The camera window shows the detected human-hand landmarks. The separate MuJoCo
window shows the simulated 16-joint LEAP Hand following the retargeted posture.
No command is sent to a physical hand. Press `Q` or Escape to stop. Add
`--mirror` only when the displayed handedness is reversed.

## Visual-feedback calculation

The package also includes the synthetic pose and timing exercise:

```bash
uv run python visual_feedback/simulation_only/demo.py
uv run python visual_feedback/simulation_only/activity.py \
  --latency-ms 150 --drop-every 5
```
