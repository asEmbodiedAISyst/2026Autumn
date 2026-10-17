"""Constants and unit conversions for the reBot Arm B601-RS.

Three joint representations are involved:

* **MuJoCo / URDF joint angles** (rad): ``joint1..joint6``; the gripper is the stroke of one finger (m).
* **Motor angles** (deg): the real ``lerobot-robot-seeed-b601`` follower returns ``degrees(motor.pos)``
  from ``get_observation()``, and its gravity-compensation code feeds motor angles directly into the
  URDF, so for the arm joints ``motor angle = degrees(URDF joint angle)``.
* **LeRobot actions** (deg): the real ``send_action()`` multiplies the action by ``joint_directions``
  before sending it to the motors, i.e. ``motor target = action * direction``.

To keep simulated datasets identical to real ones, the simulation uses:

* ``observation.state`` = motor angles;
* ``action`` = ``motor target / direction`` (same convention as the real follower).
"""

from __future__ import annotations

import numpy as np

ARM_JOINTS: tuple[str, ...] = ("joint1", "joint2", "joint3", "joint4", "joint5", "joint6")
FINGER_JOINTS: tuple[str, ...] = ("gripper_joint1", "gripper_joint2")
ACTUATORS: tuple[str, ...] = ARM_JOINTS + ("gripper",)

# Motor names used by LeRobot (same order as ARM_JOINTS + gripper)
MOTOR_NAMES: tuple[str, ...] = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_yaw",
    "wrist_roll",
    "gripper",
)

# From lerobot-robot-seeed-b601: SeeedB601RSFollowerConfig.joint_directions
JOINT_DIRECTIONS: dict[str, float] = {
    "shoulder_pan": 1.0,
    "shoulder_lift": 1.0,
    "elbow_flex": -1.0,
    "wrist_flex": -1.0,
    "wrist_yaw": -1.0,
    "wrist_roll": 1.0,
    "gripper": 6.0,
}
DIRECTIONS = np.array([JOINT_DIRECTIONS[m] for m in MOTOR_NAMES])

# From SeeedB601RSFollowerConfig.joint_limits (motor angles, deg)
MOTOR_LIMITS_DEG: dict[str, tuple[float, float]] = {
    "shoulder_pan": (-145.0, 145.0),
    "shoulder_lift": (0.0, 170.0),
    "elbow_flex": (0.0, 200.0),
    "wrist_flex": (-80.0, 90.0),
    "wrist_yaw": (-90.0, 90.0),
    "wrist_roll": (-130.0, 130.0),
    "gripper": (0.0, 270.0),
}

# Gripper: single-finger stroke [0, GRIPPER_STROKE] m maps linearly to motor angle
# [0, GRIPPER_MOTOR_MAX_DEG]. NOTE: this ratio has not been calibrated on the real arm
# (the URDF does not specify the rack-and-pinion); measure the finger travel for a 270 deg
# motor rotation on the real gripper and update these values.
GRIPPER_STROKE = 0.05
GRIPPER_MOTOR_MAX_DEG = 270.0

# Working home pose (rad): gripper pointing down, TCP at (0.25, 0, 0.10) above the table
HOME_QPOS = np.array([0.0, 1.532, 1.197, -1.236, 0.0, 0.0])
# Pusher tool ("ip17" printed part: rod at 30 deg to the flange, held like a pen with the rod tilted 30 deg
# forward): home pose with the TCP frame = TCP_DOWN_ROT and the rod tip at (0.22, 0, 0.10) (rad).
# For the parametric "simple" tool (tools/build_rebot_mjcf.py, TOOL = "simple") use
# [0.0, 1.134, 0.914, -0.828, 0.0, 0.0].
PUSHER_HOME_QPOS = np.array([0.0, 0.349, 0.5, -0.677, 0.0, 0.0])
TOOL_HOME_POS = np.array([0.22, 0.0, 0.10])
# Zero pose of the real arm after calibration: folded, gripper horizontal and pointing forward
ZERO_QPOS = np.zeros(6)

# TCP orientation when pointing down (columns are the TCP axes expressed in the world frame):
# z points down (approach direction), y points to world -y (left-finger opening direction), x to +x.
TCP_DOWN_ROT = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]])


def gripper_m_to_motor_deg(stroke_m: float | np.ndarray) -> float | np.ndarray:
    return np.asarray(stroke_m) / GRIPPER_STROKE * GRIPPER_MOTOR_MAX_DEG


def gripper_motor_deg_to_m(deg: float | np.ndarray) -> float | np.ndarray:
    return np.asarray(deg) / GRIPPER_MOTOR_MAX_DEG * GRIPPER_STROKE


def sim_to_motor_deg(arm_q_rad: np.ndarray, gripper_m: float) -> np.ndarray:
    """MuJoCo joints (6 x rad + gripper m) -> 7 motor angles (deg)."""
    return np.concatenate([np.degrees(arm_q_rad), [gripper_m_to_motor_deg(gripper_m)]])


def motor_deg_to_sim(motor_deg: np.ndarray) -> tuple[np.ndarray, float]:
    """7 motor angles (deg) -> (6 x rad, gripper m)."""
    motor_deg = np.asarray(motor_deg, dtype=float)
    return np.radians(motor_deg[:6]), float(gripper_motor_deg_to_m(motor_deg[6]))


def motor_deg_to_action(motor_deg: np.ndarray) -> np.ndarray:
    """Motor targets -> LeRobot follower action (the real send_action multiplies by direction again)."""
    return np.asarray(motor_deg, dtype=float) / DIRECTIONS


def action_to_motor_deg(action: np.ndarray) -> np.ndarray:
    """LeRobot follower action -> motor targets, clipped to the real arm's soft limits."""
    motor = np.asarray(action, dtype=float) * DIRECTIONS
    lo = np.array([MOTOR_LIMITS_DEG[m][0] for m in MOTOR_NAMES])
    hi = np.array([MOTOR_LIMITS_DEG[m][1] for m in MOTOR_NAMES])
    return np.clip(motor, lo, hi)
