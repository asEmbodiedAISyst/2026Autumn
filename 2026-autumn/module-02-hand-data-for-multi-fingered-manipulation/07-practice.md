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

- explain how delayed visual observations alter a feedback loop;
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
  "iphone_required_for_live_run": true,
  "motor_interface_included": false
}
```

Do not continue until the three verification commands complete successfully.

## 2. Observe a delayed visual-feedback loop

Generate the exact synthetic pose-recovery result:

```bash
uv run python visual_feedback/simulation_only/demo.py
```

The script projects a known cube pose into image coordinates and recovers it from the correspondences. A near-zero translation, rotation and reprojection error confirms that the packaged geometry and coordinate conventions agree. It does not constitute a physical camera calibration.

Run the feedback-loop baseline:

```bash
uv run python visual_feedback/simulation_only/activity.py \
  --latency-ms 0 --drop-every 0
```

Then introduce 150 ms of observation latency and drop every fifth packet:

```bash
uv run python visual_feedback/simulation_only/activity.py \
  --latency-ms 150 --drop-every 5
```

Record the reported delay steps, dropped packets and final absolute yaw error for both conditions.

The controller acts on an estimate of the cube state rather than the state itself. With a fresh estimate, the correction is aligned with the current yaw error. Latency changes the feedback loop because the same correction is computed from an earlier state. Packet loss reduces the update rate and forces the controller to hold an older observation. A held observation may prevent discontinuous commands, but it does not become fresh merely because it is reused.

## 3. Configure asMagic on the iPhone

1. Connect the iPhone and computer to the same Wi-Fi network.
2. Open asMagic.
3. Open **Panel → Tools → Data Streaming**.
4. Enable **AR Data** and set the port to `8000`.
5. Copy the IP address shown in the app.
6. Keep the iPhone unlocked and asMagic in the foreground.

The IP address belongs to the iPhone. It can change when the phone reconnects to Wi-Fi, so use the value currently displayed by asMagic.

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

- confirm that AR Data is enabled on port `8000`;
- re-enter the current IP shown by asMagic;
- confirm that both devices are on the same Wi-Fi network;
- keep the iPhone unlocked and the app in the foreground; and
- temporarily disable a computer firewall that blocks local port `8000`, if permitted by the lab policy.

### The image arrives but the simulation holds its pose

The overlay reports **HAND NOT FOUND — SIMULATION HOLDING** when MediaPipe cannot estimate a complete hand. Improve lighting, move the full hand into view, reduce motion speed and avoid hiding the fingertips behind the palm.

### The MuJoCo window does not open on macOS

Use the `uv run mjpython ...` command rather than `uv run python ...`.

### Motion is reversed

Stop the program and add `--mirror`. Do not change the robot joint order.

## Submission

Submit:

1. the output from `--check`;
2. the baseline and delayed visual-feedback results;
3. one screenshot containing the landmark overlay and simulated LEAP Hand;
4. a comparison of the two smoothing values; and
5. one observed embodiment or occlusion limitation.

Your conclusion must state that the iPhone supplied visual observations and that all LEAP Hand motion occurred in MuJoCo simulation.

Return to the [Class 07 lesson](07-rotating-a-cube-with-visual-feedback.md).
