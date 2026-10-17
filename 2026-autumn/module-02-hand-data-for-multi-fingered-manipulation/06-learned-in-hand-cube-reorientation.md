---
description: 30 October 2026 · 09:00–10:50 · L12
---

# 06 Learned In-Hand Cube Reorientation

#### Central question

How does a learned controller rotate a cube through finger contacts while maintaining a grasp, and what evidence supports its performance?

#### Learning objectives

* Distinguish a full orientation target from a face-up target.
* Connect joint targets, actuator torque, and contact wrench to object motion.
* Explain the policy’s joint and cube-pose observations, 57-input/16-output interface and 20 Hz update.
* Run a supplied policy in native MuJoCo and interpret its trace.
* Compare reference and M/B/Z/U/A/I cubes under matched physics and conditions.

#### Lecture — 50 minutes

1. Begin with the grasped cube and separate goal cube; ask whether matching the upward letter is sufficient.
2. Explain full orientation error and the 0.1 rad success threshold (approximately 5.73 degrees).
3. Apply Featherstone’s angular-first spatial dynamics language to the contact wrench; work through a 1 N force at a perpendicular 35 mm lever arm.
4. Trace observations → policy → joint targets → actuator response → contacts → next observation. Cube pose is explicitly observed; this is not a proprioception-only policy.
5. Distinguish native MuJoCo playback from MuJoCo Playground’s task/training pipeline. ONNX inference does not train the controller.
6. Predict the effect of visual-only labels and define a controlled comparison. Introduce first-goal success, goal events, stalls, and drops as distinct quantities.

#### Break — 10 minutes

#### Instructor/TA demonstration — 35 minutes

Show the prepared animation and identify physical and target cubes. Run or replay the upstream-policy native implementation; inspect summary and trace records, including the goal evaluated before a target update. Demonstrate the matched reference/lettered comparison and explain failures without changing the experiment conditions. Use the selected seed 9204 with ideal observations for the prepared example; it records events at steps 356 and 761. Identify it as a selected demonstration, not a reliability estimate. Have the verified recording available if live rendering fails.

#### Student activity — 15 minutes

Use an isolated environment, verify the supplied package, and run matched reference/lettered 200-step episodes with the same policy, seed 9204 and observation-noise setting. Compare saved channels and write a short explanation of the controlled intervention. The first event in the longer selected episode is at 17.80 seconds, beyond this ten-second exercise; successful task completion is the comparison and interpretation, not a required goal event.
