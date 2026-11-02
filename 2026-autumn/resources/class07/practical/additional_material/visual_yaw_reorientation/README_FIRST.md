# Visual-yaw LEAP deployment bundle

This is the transferable package for the MBZUAI 58 mm ArUco cube and flat
right-LEAP visual yaw policy.  It deliberately excludes `.venv`, training
logs, and unrelated checkpoints.  Use the Python environment already prepared
on the destination workstation.

## Contents

- `checkpoints/visual_yaw_model_4900/model_4900.pt`: selected inference policy.
- `project/`: MuJoCo task, model assets, policy server, viewer, and pose bridge.
- `hand_tracking/`: iPhone/asMagic cube tracking and policy-pose producer.
- `camera/aruco_cube/`: six-face marker geometry and printable marker assets.
- `hardware_runtime/`: guarded Dynamixel client and H1 gain profile.
- `media/`: simulation and iPhone recordings for reference.

## First: simulation only

From the bundle root, run with the destination machine's working project
Python environment:

```bash
PYTHON_BIN=/path/to/working/python
$PYTHON_BIN project/scripts/play_reorient.py \
  --task Mjlab-Leap-Right-HandCube-MBZUAI-Visual-Yaw \
  --checkpoint-file checkpoints/visual_yaw_model_4900/model_4900.pt \
  --initial-goal current \
  --goal-step-deg 90 \
  --device cuda:0
```

In the viewer, use **F8** for +90 degrees yaw, **F7** for -90 degrees yaw,
and **F6** to reset the target to the current cube pose.  `M` is a native
MuJoCo center-of-mass display key, not a policy control.

## Camera-to-policy shadow

The iPhone cube tracker requires a measured `T_palm_camera` calibration file.
Do not edit an example calibration to bypass its `calibrated` flag.

```bash
cd hand_tracking
$PYTHON_BIN cube_following_teleop.py \
  --mode policy-shadow \
  --track-ip TRACK_IP --monitor-ip MONITOR_IP \
  --camera-to-palm /absolute/path/to/measured_camera_to_palm.json \
  --policy-pose-output /tmp/leap_cube_pose.json \
  --follow-axes yaw-snap
```

Then start `project/scripts/play_reorient.py` with
`--pose-input-file /tmp/leap_cube_pose.json`.  This remains simulation only.

## Hardware safety order

1. Verify the camera packet and target direction in MuJoCo.
2. Start `project/scripts/serve_policy.py` with `model_4900.pt`.
3. Run `hardware_runtime/runtime_support/deploy_direct.py --shadow`.
4. Review limits, encoder order, target direction, and stale-pose behavior.
5. Use a short, supervised physical trial only after all shadow checks pass.

The physical hand must have a reachable independent torque/power cutoff.
