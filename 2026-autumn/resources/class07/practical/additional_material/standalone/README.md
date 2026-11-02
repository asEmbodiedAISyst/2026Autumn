# Class 07 standalone — visual feedback

This CPU-friendly package isolates the ready parts of the Class 07 visual loop: declared six-face ArUco geometry, synthetic pose recovery, latency/dropout intervention, and a compact replay of the recorded visual-yaw hardware run.

## Setup

```bash
uv sync
uv run pytest
```

## Part A — simulation only

Recover a known cube pose from synthetically projected marker corners:

```bash
uv run python simulation_only/demo.py
```

Student activity: compare a fresh visual-feedback loop with 150 ms latency and periodic packet loss:

```bash
uv run python simulation_only/activity.py --latency-ms 150 --drop-every 5
```

The synthetic test validates a declared coordinate/measurement interface. It is not a physical camera calibration or a marker-detector accuracy claim.

## Part B — simulation and hardware record

Replay the supplied visual-yaw deployment log without commanding the LEAP Hand:

```bash
uv run python simulation_and_hardware/demo.py
uv run python simulation_and_hardware/activity.py --max-pose-age-s 0.15
```

The activity examines pose age, dropout, current, temperature and joint tracking in the saved record. Live torque-enabled deployment remains teaching-team-only and requires the measured camera-to-palm calibration, verified joint order, stale-pose behavior and an independent power cutoff. The larger guarded deployment bundle remains in `additional_material/visual_yaw_reorientation/`; it is deliberately not duplicated here.

## Source map

- ArUco geometry and pose estimator: Class 07 `visual_yaw_reorientation/camera/aruco_cube/`
- Recorded deployment JSONL and preview: Class 07 `visual_yaw_reorientation/project/data/`
- Included marker PNGs: IDs 0–5 for the 58 mm cube

The original asMagic live stream is not required for the simulation activity or replay. The physical log is evidence from an existing run, not authorization to operate hardware.
