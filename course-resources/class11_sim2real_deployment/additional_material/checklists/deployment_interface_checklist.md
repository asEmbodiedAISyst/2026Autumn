# Deployment interface checklist (Class 11, rung 1)

Policy checkpoint: ____________________   Robot: sim follower / physical follower / tool on arm   Date: ________

## Features
- [ ] Input feature keys of the policy (`config.json`, `input_features`) == keys the robot provides. List both:
      policy: __________________________________  robot: __________________________________
- [ ] Shapes match (state dimension 7 or 9; images 480x640x3).
- [ ] Output feature `action` dimension == what the driver expects (7 joint command, or 9 tool pose / 6 delta).
- [ ] Camera keys (`front`, `side`, `phone`) map to the right physical cameras. Which is which: ______

## Normalisation
- [ ] `meta/stats.json` of the training set is inside the checkpoint (preprocessor). Mean of `observation.state`: ______
- [ ] The robot's state at the start pose is within mean +- 2 std of the training statistics for every channel.

## Joint order, direction, calibration
- [ ] Order shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_yaw, wrist_roll, gripper.
- [ ] Direction vector [1, 1, -1, -1, -1, 1, 6] applied by the driver, not by the policy.
- [ ] Motor zero written in the folded pose (Gate B of Class 08). Zero-pose reading: ______
- [ ] Gripper ratio measured (motor 0..270 deg -> stroke ______ m) or gripper unused.
- [ ] Camera placement measured against the simulated `front`/`side` (or phone-to-tip transform measured for the tool).

## Limits and safety
- [ ] Soft limits loaded in the driver; `max_relative_target` or speed limit set low for the first rollout: ______
- [ ] Stream-age rule: hold after ______ s without a new observation.
- [ ] E-stop tested before the first policy step.

## Record
- [ ] Every rollout is logged with: seed/layout, outcome, steps, final error, interventions, checkpoint id, chunk n.
