"""Physical reBot B601-RS with the stock gripper.

* :mod:`.gripper_arm`: all 7 RobStride motors through the Seeed ``lerobot-robot-seeed-b601`` plugin (motorbridge
  over SocketCAN), for the first power-on checks (``code/real_gripper_drag.py`` and
  ``code/real_gripper_motion_test.py``), and the MuJoCo digital twin that follows the measured angles.

The plugin is an optional dependency: ``uv sync --group real``.
"""
