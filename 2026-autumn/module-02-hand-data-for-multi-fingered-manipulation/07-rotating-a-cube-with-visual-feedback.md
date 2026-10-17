---
description: 03 November 2026 · 09:00–10:20 · CR6
---

# 07 Rotating a Cube with Visual Feedback

#### Central question

How does visual observation change the robot's feedback loop?

#### Lecture — 40 minutes

1. Explain OpenAI's object-reorientation example, distinguishing it from Rubik's Cube solving.
2. Replace the preceding task’s simulated cube-pose feedback with an estimated visual measurement: frames, uncertainty, latency, dropout and occlusion. The Class06 actor already receives cube pose.
3. Separate device AR pose, observed marker pose and object pose in the hand frame.
4. Formulate the visual-feedback learning problem in simulation.
5. Brief retargeting introduction: correspondence, joint order and embodiment differences between a human hand and LEAP.

#### Break — 5 minutes

#### Instructor/TA demonstration — 25 minutes

Show original asMagic → Python → MuJoCo observations. Compare prepared visual and proprioceptive examples when available. Human-hand retargeting is a short preview only after its finger-observation interface and mapping have been verified; joystick control is not hand retargeting.

#### Student activity — 10 minutes

Use the assigned iPhone to inspect viewpoint/occlusion effects or try a verified simulation interface. No hardware hand control is required.
