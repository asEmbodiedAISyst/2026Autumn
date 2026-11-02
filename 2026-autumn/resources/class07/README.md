# Class 07 resources

[Lecture](../../module-02-hand-data-for-multi-fingered-manipulation/07-rotating-a-cube-with-visual-feedback.md) · [Simulation practice](../../module-02-hand-data-for-multi-fingered-manipulation/07-practice.md)

This directory contains the figures and runnable resources for the cube
visual-feedback and human-hand-retargeting tasks.

## Resource map

```text
class07/
├── figures/
│   ├── source-recordings/       # cube and visual-yaw evidence from supplied runs
│   ├── simulation-progress/     # MuJoCo reorientation rollout screenshots
│   ├── hand-retargeting-*.png   # human landmarks and MuJoCo correspondence
│   └── source/                  # asMagic reference
└── practical/
    ├── downloads/
    │   ├── class07-iphone-leap-simulation.zip # student standalone package
    │   └── Class07_iPhone_LEAP_Simulation/    # unpacked package source
    └── additional_material/
        ├── standalone/              # lightweight synthetic pose and timing activity
        ├── visual_yaw_reorientation/ # checkpoint, task, cube tracker and guarded runtime
        └── run_visual_yaw_simulation.sh
```

The package includes the selected checkpoint, six-face ArUco cube geometry,
MuJoCo assets, calibration and tracking utilities, hand-landmarker model,
retargeting source, and LEAP model assets. Python virtual
environments and machine-specific serial/camera settings are intentionally not
included.

The downloadable student package uses only an iPhone running asMagic and a
MuJoCo LEAP Hand. It includes a locked Python environment, all model assets and
a self-check; it contains no motor-command interface. Live LEAP operation is
restricted to authorised instructor supervision and requires a measured
camera-to-palm calibration, verified joint order, torque-disabled shadow pass
and independent power cutoff.
