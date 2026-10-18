"""Real reBot B601-RS with the pusher tool (rod + iPhone) instead of the gripper.

The real setup reuses everything of the simulated tool pipeline (action/observation format, software limits,
IK on the same MuJoCo model, dataset format); only the backends change:

* :mod:`.arm` -- joint-space arm: the real follower (Seeed ``lerobot-robot-seeed-b601`` plugin, 6 RobStride
  motors over CAN, no gripper motor) or the MuJoCo arm (``SimArm``, for testing without hardware);
* :mod:`.camera` -- policy camera: the robot-mounted iPhone streaming through asMagic, or the simulated phone;
* :mod:`.env` -- :class:`RealToolPushEnv`, the counterpart of :class:`rebot_sim.tool_env.ToolPushEnv`;
* :mod:`.gripper_arm` -- the *stock* arm with the gripper (all 7 motors) for first power-on checks
  (``scripts/real_gripper_drag.py`` / ``real_gripper_motion_test.py``); independent of the pusher pipeline.
"""
