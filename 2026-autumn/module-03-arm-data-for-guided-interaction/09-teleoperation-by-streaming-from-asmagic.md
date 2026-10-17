---
description: 06 November 2026 · 09:00–10:50 · L12
---

# 09 Teleoperation by Streaming from asMagic

#### Central question

What must align for a teleoperated demonstration to become usable robot data?

#### Lecture — 50 minutes

1. Teleoperation command path and robot response path.
2. Mapping, units, bounds, calibration and coordinate frames.
3. Original asMagic camera/device-pose/IMU/joystick streams and Python reception.
4. Simulation action/state logging alongside phone observations; the phone alone does not replace these records.
5. Timestamps, rate mismatch, missing data and reproducible recording schema.

#### Break — 10 minutes

#### Demonstration — 35 minutes

Drive the reBot RS simulation through a verified original asMagic interface. Inspect commands, actions, robot state and phone observations under a common episode identity. Show one deliberate mapping/timing fault. Use a recorded fallback if live streaming is unavailable.

#### Student activity — 15 minutes

Try the simulation or inspect a replay. Check joint/action order, image keys and timestamps. Define a simple repeatable task and reset procedure.
