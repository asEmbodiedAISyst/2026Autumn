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
`"motor_interface_included": false`. It must also report `asmagic 1.0.1` and
an available PyAV HEVC decoder.

## Connect the iPhone

1. Connect the iPhone and computer to the same Wi-Fi network.
2. Open asMagic on the iPhone.
3. Hold or mount the iPhone in landscape orientation.
4. Open **Stream / Data Streaming**.
5. Enable **AR Data** on port 8000.
6. Keep the app foregrounded and copy the IP displayed on that page.

Verify one decoded frame before launching MediaPipe and MuJoCo:

```bash
uv run python simulation/iphone_leap_sim.py \
  --iphone-ip 10.127.120.185 \
  --port 8000 \
  --check-stream \
  --stream-timeout-s 10
```

Continue only when the JSON output reports `"status": "pass"` and
`"mode": "iphone_stream_check"`. The current app sends HEVC color frames;
`asmagic 1.0.1` and PyAV preserve the video history needed to decode them.

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

## Goal-conditioned cube reorientation in MuJoCo

Run the simulation with a known target yaw angle (e.g. 90° in the palm frame):

```bash
./run_cube_reorient_simulation.sh 90
```

The interactive viewer displays the manipulated cube in the LEAP Hand and a separate nonphysical goal cube showing the target orientation. Use **F8** to step target yaw by +90°, **F7** for -90°, **F6** to reset to the current cube orientation, and **F9** for a random target.

