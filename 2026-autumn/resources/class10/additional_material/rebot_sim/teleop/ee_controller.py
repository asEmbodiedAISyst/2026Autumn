"""Teleoperation controller: end-effector (TCP) target -> joint targets.

Takes a TCP target pose from any source (phone, mouse, script), applies workspace clipping, a speed
limit and IK, and outputs 6 joint targets. It can be reused unchanged for the real arm (same MJCF + IK).

Modes:

* ``planar``: TCP height fixed at pushing height, gripper pointing down, only x/y controlled (like 2D Push-T);
* ``xyz``: x/y/z controlled, orientation fixed pointing down;
* ``6d``: full pose.
"""

from __future__ import annotations

from dataclasses import dataclass

import mujoco
import numpy as np

from ..ik import DiffIK
from ..robot import HOME_QPOS, TCP_DOWN_ROT

MODES = ("planar", "xyz", "6d")


@dataclass
class Workspace:
    x: tuple[float, float] = (0.12, 0.42)
    y: tuple[float, float] = (-0.25, 0.25)
    z: tuple[float, float] = (0.02, 0.30)

    def clip(self, p: np.ndarray) -> np.ndarray:
        return np.array([np.clip(p[0], *self.x), np.clip(p[1], *self.y), np.clip(p[2], *self.z)])


class EEController:
    def __init__(
        self,
        model: mujoco.MjModel,
        mode: str = "planar",
        fps: int = 30,
        push_height: float = 0.025,
        max_speed: float = 0.25,
        workspace: Workspace | None = None,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.ik = DiffIK(model)
        self.mode = mode
        self.dt = 1.0 / fps
        self.push_height = push_height
        self.max_step = max_speed * self.dt
        self.workspace = workspace or Workspace()
        self.target_pos = np.zeros(3)
        self.target_rot = TCP_DOWN_ROT.copy()
        self.q_cmd = HOME_QPOS.copy()
        self.reset(HOME_QPOS)

    def reset(self, q: np.ndarray) -> None:
        """Use the TCP pose at joint angles ``q`` as the current target."""
        self.q_cmd = np.asarray(q, dtype=float).copy()
        pos, rot = self.ik.fk(self.q_cmd)
        self.target_pos = pos
        self.target_rot = rot if self.mode == "6d" else TCP_DOWN_ROT.copy()

    def _constrain(self, pos: np.ndarray) -> np.ndarray:
        pos = np.asarray(pos, dtype=float).copy()
        if self.mode == "planar":
            pos[2] = self.push_height
        return self.workspace.clip(pos)

    def command(self, pos: np.ndarray, rot: np.ndarray | None = None) -> np.ndarray:
        """Given a desired TCP pose, return the 6-D joint target (rad) for this control period.

        The target moves at most ``max_speed * dt`` per period, so input jumps do not make the arm lunge.
        """
        desired = self._constrain(pos)
        delta = desired - self.target_pos
        n = np.linalg.norm(delta)
        if n > self.max_step:
            delta *= self.max_step / n
        self.target_pos = self.target_pos + delta
        if self.mode == "6d" and rot is not None:
            self.target_rot = np.asarray(rot, dtype=float)
        elif self.mode != "6d":
            self.target_rot = TCP_DOWN_ROT
        res = self.ik.solve(self.target_pos, self.target_rot, self.q_cmd, max_iters=30)
        self.q_cmd = res.q
        return self.q_cmd.copy()

    def hold(self) -> np.ndarray:
        """Hold the current target (call when there is no input)."""
        return self.command(self.target_pos, self.target_rot)
