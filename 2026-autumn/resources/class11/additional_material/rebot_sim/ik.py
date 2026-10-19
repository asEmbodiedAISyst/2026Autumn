"""Damped least-squares (DLS) inverse kinematics based on MuJoCo Jacobians.

Only the kinematics of the model are used: iterations run on a private ``MjData`` and do not touch
the simulation state. The same solver works for the real arm (load the same MJCF), so simulated and
real teleoperation share identical IK.
"""

from __future__ import annotations

from dataclasses import dataclass

import mujoco
import numpy as np

from .robot import ARM_JOINTS, HOME_QPOS, MOTOR_LIMITS_DEG, MOTOR_NAMES


@dataclass
class IKResult:
    q: np.ndarray
    pos_err: float
    rot_err: float
    success: bool


def _rot_error(R: np.ndarray, R_target: np.ndarray) -> np.ndarray:
    """Orientation error as a rotation vector in the world frame (small-angle approximation)."""
    return 0.5 * (np.cross(R[:, 0], R_target[:, 0]) + np.cross(R[:, 1], R_target[:, 1]) + np.cross(R[:, 2], R_target[:, 2]))


class DiffIK:
    """Position + orientation IK for the 6-DoF arm.

    Args:
        model: MuJoCo model containing the reBot (any scene).
        site: End-effector site name (default ``tcp``).
        damping: DLS damping factor.
        posture_gain: Null-space gain pulling towards ``posture`` to avoid singularities and joint drift.
        posture: Preferred joint configuration (default ``HOME_QPOS``).
    """

    def __init__(
        self,
        model: mujoco.MjModel,
        site: str = "tcp",
        damping: float = 1e-3,
        posture_gain: float = 0.05,
        posture: np.ndarray | None = None,
        rot_weight: float = 0.3,
    ) -> None:
        self.model = model
        self.data = mujoco.MjData(model)
        self.site_id = model.site(site).id
        self.qadr = np.array([model.jnt_qposadr[model.joint(j).id] for j in ARM_JOINTS])
        self.dofadr = np.array([model.jnt_dofadr[model.joint(j).id] for j in ARM_JOINTS])
        # Joint limits = MJCF limits ∩ real-arm soft limits
        lo = model.jnt_range[[model.joint(j).id for j in ARM_JOINTS], 0].copy()
        hi = model.jnt_range[[model.joint(j).id for j in ARM_JOINTS], 1].copy()
        motor_lo = np.radians([MOTOR_LIMITS_DEG[m][0] for m in MOTOR_NAMES[:6]])
        motor_hi = np.radians([MOTOR_LIMITS_DEG[m][1] for m in MOTOR_NAMES[:6]])
        self.lower = np.maximum(lo, motor_lo) + 1e-3
        self.upper = np.minimum(hi, motor_hi) - 1e-3
        self.damping = damping
        self.posture_gain = posture_gain
        self.posture = HOME_QPOS.copy() if posture is None else np.asarray(posture, dtype=float)
        self.rot_weight = rot_weight
        self._jacp = np.zeros((3, model.nv))
        self._jacr = np.zeros((3, model.nv))

    def fk(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Forward kinematics: return the TCP (position, rotation matrix)."""
        self.data.qpos[self.qadr] = q
        mujoco.mj_kinematics(self.model, self.data)
        mujoco.mj_comPos(self.model, self.data)
        return self.data.site_xpos[self.site_id].copy(), self.data.site_xmat[self.site_id].reshape(3, 3).copy()

    def solve(
        self,
        target_pos: np.ndarray,
        target_rot: np.ndarray | None,
        q_init: np.ndarray,
        max_iters: int = 50,
        pos_tol: float = 1e-4,
        rot_tol: float = 1e-3,
        max_step: float = 0.2,
    ) -> IKResult:
        """Solve for joint angles that bring the TCP to the target pose.

        If ``target_rot`` is ``None`` only the position is constrained.
        """
        q = np.clip(np.asarray(q_init, dtype=float).copy(), self.lower, self.upper)
        target_pos = np.asarray(target_pos, dtype=float)
        pos_err = rot_err = np.inf
        for _ in range(max_iters):
            pos, R = self.fk(q)
            e_pos = target_pos - pos
            pos_err = float(np.linalg.norm(e_pos))
            if target_rot is not None:
                e_rot = _rot_error(R, target_rot)
                rot_err = float(np.linalg.norm(e_rot))
            else:
                e_rot, rot_err = np.zeros(3), 0.0
            if pos_err < pos_tol and rot_err < rot_tol:
                break
            mujoco.mj_jacSite(self.model, self.data, self._jacp, self._jacr, self.site_id)
            Jp = self._jacp[:, self.dofadr]
            Jr = self._jacr[:, self.dofadr]
            if target_rot is not None:
                J = np.vstack([Jp, self.rot_weight * Jr])
                e = np.concatenate([e_pos, self.rot_weight * e_rot])
            else:
                J, e = Jp, e_pos
            JJt = J @ J.T + self.damping * np.eye(J.shape[0])
            J_pinv = J.T @ np.linalg.solve(JJt, np.eye(J.shape[0]))
            dq = J_pinv @ e
            # Null-space posture term: pull towards the preferred posture
            null = np.eye(6) - J_pinv @ J
            dq += null @ (self.posture_gain * (self.posture - q))
            n = np.linalg.norm(dq)
            if n > max_step:
                dq *= max_step / n
            q = np.clip(q + dq, self.lower, self.upper)
        success = pos_err < 5e-3 and rot_err < 5e-2
        return IKResult(q=q, pos_err=pos_err, rot_err=rot_err, success=success)
