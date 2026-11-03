---
description: Class 07 practice · visual feedback and iPhone hand retargeting to a simulated LEAP Hand
---

# Class 07 — Practice: visual feedback and simulated hand retargeting

This practice runs entirely in simulation. The only physical device is your own iPhone running asMagic. The iPhone supplies images; it does not command a robot. All retargeted joint commands are applied only to the MuJoCo LEAP Hand model on your computer.

{% hint style="danger" %}
Do not connect a physical LEAP Hand, motor controller or serial interface. The student package contains no Dynamixel or motor-command code.
{% endhint %}

## Learning outcomes

By the end of the practice, you can:

- observe goal-directed cube reorientation in MuJoCo with a known target;
- connect an asMagic iPhone stream by using the IP address displayed in the app;
- map human-hand landmarks to the 16 joints of a simulated LEAP Hand; and
- distinguish image tracking, retargeting and simulated actuation.

## Required equipment and software

- a Linux or macOS computer with Python 3.11, `uv` and a graphical desktop;
- an iPhone with asMagic installed; and
- one Wi-Fi network shared by the computer and iPhone.

No webcam, physical LEAP Hand, Dynamixel interface or external course repository is required.

## 1. Download and verify the standalone package

Download [Class07 iPhone–LEAP Simulation](../resources/class07/practical/downloads/class07-iphone-leap-simulation.zip), extract it, and open a terminal in `Class07_iPhone_LEAP_Simulation`.

Install the locked environment and run the verification:

```bash
uv sync --locked
uv run pytest
uv run python simulation/iphone_leap_sim.py --check
```

The first installation downloads the vision, retargeting and simulation dependencies. The final command should report:

```json
{
  "status": "pass",
  "mode": "simulation_only",
  "model_actuators": 16,
  "retargeted_joints": 16,
  "finite_state": true,
  "hand_landmarker_loaded": true,
  "asmagic_version": "1.0.1",
  "hevc_decoder": "PyAV 18.1.0",
  "iphone_required_for_live_run": true,
  "motor_interface_included": false
}
```

Do not continue until the three verification commands complete successfully.

## 2. Reorient the cube toward a known target in MuJoCo

Run the goal-conditioned in-hand cube reorientation simulation with a known target yaw (for example, +90° in the palm frame):

```bash
./run_cube_reorient_simulation.sh 90
```

The interactive MuJoCo viewer displays two objects:
- the **dynamically simulated 58 mm cube** held in the 16-joint LEAP Hand; and
- a separate detached **non-physical target cube** communicating the requested goal orientation.

The learned visual-yaw policy (`model_4900.pt`) continuously observes the cube error relative to the target and commands finger gait updates to drive the cube into alignment.

### Interactive viewer controls

Use the keyboard and mouse to test different targets during the simulation:

| Key / Input | Action |
| :--- | :--- |
| **`F8`** | Step target yaw by **+90°** |
| **`F7`** | Step target yaw by **-90°** |
| **`F6`** | Reset target to the current cube orientation |
| **`F9`** | Sample a new random target orientation |
| **Mouse** | Double-click the target cube, then **`Ctrl` + Right-drag** to freely rotate it in 3D |
| **`Space`** | Pause / Resume simulation |
| **`Enter`** | Reset rollout |
| **`Esc`** | Exit viewer |

Observe how the finger contact pattern redistributes as the target changes. When the target yaw is reached within the success threshold, the policy settles the fingers to maintain the object orientation without losing contact.

## 3. Configure asMagic on the iPhone

1. Connect the iPhone and computer to the same Wi-Fi network.
2. Open asMagic.
3. Hold or mount the iPhone in landscape orientation.
4. Open **Stream / Data Streaming** in asMagic.
5. Enable **AR Data** and set the port to `8000`.
6. Copy the IP address shown in the app.
7. Keep the iPhone unlocked and asMagic in the foreground.

The IP address belongs to the iPhone. It can change when the phone reconnects to Wi-Fi, so use the value currently displayed by asMagic. The package uses `asmagic 1.0.1` and PyAV to decode the current HEVC stream; the older `asmagic 0.1.4` JPEG-only path produces an empty image window.

Verify that one color frame can be decoded before starting MediaPipe or MuJoCo:

```bash
uv run python simulation/iphone_leap_sim.py \
  --iphone-ip PHONE_IP \
  --port 8000 \
  --check-stream \
  --stream-timeout-s 10
```

The check succeeds only after it prints a JSON report containing:

```json
{
  "status": "pass",
  "mode": "iphone_stream_check",
  "decoded_bgr_shape": [480, 640, 3],
  "asmagic_version": "1.0.1",
  "motor_interface_included": false
}
```

The exact decoded dimensions can vary with the selected stream mode. Do not continue until the status is `pass`.

## 4. Retarget your hand to the simulated LEAP Hand

On Linux, replace `PHONE_IP` with the address displayed by asMagic:

```bash
uv run python simulation/iphone_leap_sim.py \
  --iphone-ip PHONE_IP \
  --port 8000 \
  --alpha 0.25
```

On macOS, launch the same program through MuJoCo:

```bash
uv run mjpython simulation/iphone_leap_sim.py \
  --iphone-ip PHONE_IP \
  --port 8000 \
  --alpha 0.25
```

Two windows should appear:

- the asMagic image window shows the human-hand landmarks and tracking status; and
- the MuJoCo window shows the simulated 16-joint LEAP Hand following the retargeted posture.

Present one right hand to the iPhone with the palm and all fingertips visible. Perform each motion slowly:

1. open the palm;
2. flex and extend the four long fingers;
3. form a thumb–index pinch; and
4. move the thumb across the palm.

Press `Q` or `Esc` in the image window to stop. If left and right appear reversed, stop and rerun the command with `--mirror`.

## 5. Examine smoothing and embodiment mismatch

Repeat the same motions with stronger smoothing:

```bash
uv run python simulation/iphone_leap_sim.py \
  --iphone-ip PHONE_IP \
  --port 8000 \
  --alpha 0.10 \
  --duration 60
```

The filter updates the target according to

$$
q_t^{\mathrm{filtered}}=(1-\alpha)q_{t-1}^{\mathrm{filtered}}+\alpha q_t^{\mathrm{retargeted}}.
$$

A smaller $\alpha$ suppresses frame-to-frame jitter but increases response delay. It cannot recover an occluded fingertip or remove a systematic mismatch between human and robot hand geometry.

Compare `--alpha 0.10` with `--alpha 0.25`. Identify which setting follows fast motion sooner and which produces the steadier simulated posture. Also identify one motion that the simulated LEAP Hand cannot reproduce exactly because its joint axes, link lengths and thumb structure differ from those of your hand.

## Troubleshooting

### The window remains on “Waiting for asMagic AR Data”

- run the `--check-stream` command before starting the simulation;
- confirm that `uv run python -c 'import asmagic; print(asmagic.__version__)'` reports `1.0.1`;
- confirm that AR Data is enabled on port `8000`;
- re-enter the current IP shown by asMagic;
- confirm that both devices are on the same Wi-Fi network;
- keep the iPhone unlocked and the app in the foreground; and
- temporarily disable a computer firewall that blocks local port `8000`, if permitted by the lab policy.

HEVC frames depend on earlier packets and periodic key frames. Keep one receiver running while it waits; repeatedly restarting the program can delay image recovery.

### The image arrives but the simulation holds its pose

The overlay reports **HAND NOT FOUND — SIMULATION HOLDING** when MediaPipe cannot estimate a complete hand. Improve lighting, move the full hand into view, reduce motion speed and avoid hiding the fingertips behind the palm.

### The MuJoCo window does not open on macOS

Use the `uv run mjpython ...` command rather than `uv run python ...`.

### Motion is reversed

Stop the program and add `--mirror`. Do not change the robot joint order.

## Submission

Submit:

1. the output from `--check`;
2. one screenshot of the MuJoCo cube reorientation simulation showing the manipulated cube aligning with the detached target cube;
3. one screenshot containing the landmark overlay and simulated LEAP Hand;
4. a comparison of the two smoothing values; and
5. one observed embodiment or occlusion limitation.

Your conclusion must state that the iPhone supplied visual observations and that all LEAP Hand motion occurred in MuJoCo simulation.

Return to the [Class 07 lesson](07-rotating-a-cube-with-visual-feedback.md).
