"""Software limits for the pusher-tool TCP target: workspace box, linear/angular speed, tilt and yaw.

Used identically for the handheld tool (simulated human) and the robot-mounted tool, so human
demonstrations never contain motions that the robot executor would clip differently.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..pose import limit_tilt, matrix_to_rotvec, rot_z, rotvec_to_matrix, yaw_of


@dataclass
class ToolLimits:
    x: tuple[float, float] = (0.12, 0.42)
    y: tuple[float, float] = (-0.25, 0.25)
    z: tuple[float, float] = (0.003, 0.30)  # TCP = rod tip; 3 mm above the table at the lowest
    max_speed: float = 0.25  # m/s
    max_ang_speed: float = 2.0  # rad/s
    max_tilt_deg: float = 30.0  # rod tilt from straight down
    max_yaw_deg: float = 80.0  # heading of the tool x axis (camera direction) relative to +x; wrist limits


class ToolController:
    """Holds the commanded TCP pose and applies :class:`ToolLimits` to new targets."""

    def __init__(self, fps: int = 30, limits: ToolLimits | None = None) -> None:
        self.limits = limits or ToolLimits()
        self.dt = 1.0 / fps
        self.target_pos = np.zeros(3)
        self.target_rot = np.eye(3)

    def reset(self, pos: np.ndarray, rot: np.ndarray) -> None:
        self.target_pos = np.asarray(pos, dtype=float).copy()
        self.target_rot = np.asarray(rot, dtype=float).copy()

    def command(self, pos: np.ndarray, rot: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Move the commanded pose towards ``(pos, rot)`` within the limits and return the new commanded pose."""
        lim = self.limits
        desired = np.array([np.clip(pos[0], *lim.x), np.clip(pos[1], *lim.y), np.clip(pos[2], *lim.z)])
        step = desired - self.target_pos
        n = np.linalg.norm(step)
        if n > lim.max_speed * self.dt:
            step *= lim.max_speed * self.dt / n
        self.target_pos = self.target_pos + step

        if rot is not None:
            rot = limit_tilt(np.asarray(rot, dtype=float), np.radians(lim.max_tilt_deg))
            yaw, max_yaw = yaw_of(rot), np.radians(lim.max_yaw_deg)
            if abs(yaw) > max_yaw:
                rot = rot_z(np.clip(yaw, -max_yaw, max_yaw) - yaw) @ rot
            dr = matrix_to_rotvec(rot @ self.target_rot.T)  # rotation increment in the world frame
            a = np.linalg.norm(dr)
            if a > lim.max_ang_speed * self.dt:
                dr *= lim.max_ang_speed * self.dt / a
            self.target_rot = rotvec_to_matrix(dr) @ self.target_rot
        return self.target_pos.copy(), self.target_rot.copy()
