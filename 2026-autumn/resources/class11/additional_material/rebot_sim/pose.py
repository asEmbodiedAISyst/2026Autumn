"""Relative-pose helpers for the pusher tool (phone + rod rigid body).

Action representation used for tool-based data (human handheld or robot-mounted):

* a pose is ``(p, R)``: TCP position (3,) and rotation matrix (3, 3) in some world frame;
* the action at step ``t`` is the motion from the commanded pose ``T_t`` to ``T_{t+1}`` **expressed in the
  tool frame of** ``T_t``: ``[R_t^T (p_{t+1} - p_t), log(R_t^T R_{t+1})]`` (6 values: m, rad).

Such deltas do not depend on the world frame, so data from the phone's ARKit frame and from the robot base
frame are directly comparable and no calibration between them is needed. The only absolute quantity used
is gravity (both ARKit and the robot base are gravity aligned), see :func:`gravity_in_tool`.
"""

from __future__ import annotations

import numpy as np

WORLD_DOWN = np.array([0.0, 0.0, -1.0])


def _skew(v: np.ndarray) -> np.ndarray:
    return np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])


def rotvec_to_matrix(r: np.ndarray) -> np.ndarray:
    """Rotation vector (axis * angle) -> rotation matrix (Rodrigues)."""
    r = np.asarray(r, dtype=float)
    theta = np.linalg.norm(r)
    if theta < 1e-12:
        return np.eye(3) + _skew(r)
    k = _skew(r / theta)
    return np.eye(3) + np.sin(theta) * k + (1.0 - np.cos(theta)) * (k @ k)


def matrix_to_rotvec(R: np.ndarray) -> np.ndarray:
    """Rotation matrix -> rotation vector (axis * angle), angle in [0, pi]."""
    R = np.asarray(R, dtype=float)
    cos = np.clip((np.trace(R) - 1.0) / 2.0, -1.0, 1.0)
    theta = np.arccos(cos)
    w = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    if theta < 1e-6:
        return 0.5 * w
    if np.pi - theta < 1e-4:  # near 180 deg: use the diagonal for the axis
        axis = np.sqrt(np.clip((np.diag(R) + 1.0) / 2.0, 0.0, None))
        axis *= np.sign(w + (w == 0))
        return theta * axis / np.linalg.norm(axis)
    return theta / (2.0 * np.sin(theta)) * w


def pose_delta(p0: np.ndarray, R0: np.ndarray, p1: np.ndarray, R1: np.ndarray) -> np.ndarray:
    """Motion from pose 0 to pose 1 expressed in the frame of pose 0: [dp (3), drot (3)]."""
    return np.concatenate([R0.T @ (np.asarray(p1) - np.asarray(p0)), matrix_to_rotvec(R0.T @ R1)])


def apply_delta(p0: np.ndarray, R0: np.ndarray, delta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Inverse of :func:`pose_delta`: pose 0 moved by ``delta`` (expressed in the frame of pose 0)."""
    delta = np.asarray(delta, dtype=float)
    return np.asarray(p0) + R0 @ delta[:3], R0 @ rotvec_to_matrix(delta[3:])


def gravity_in_tool(R: np.ndarray) -> np.ndarray:
    """Unit gravity direction expressed in the tool frame (calibration-free proprioception)."""
    return np.asarray(R).T @ WORLD_DOWN


def tilt_angle(R: np.ndarray) -> float:
    """Angle (rad) between the tool z axis (along the rod) and straight down."""
    return float(np.arccos(np.clip(np.asarray(R)[:, 2] @ WORLD_DOWN, -1.0, 1.0)))


def yaw_of(R: np.ndarray) -> float:
    """Heading (rad) of the tool x axis projected on the horizontal plane."""
    x = np.asarray(R)[:, 0]
    return float(np.arctan2(x[1], x[0]))


def rot_z(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def limit_tilt(R: np.ndarray, max_tilt: float) -> np.ndarray:
    """Rotate ``R`` (about a horizontal axis) so that its tilt from straight down is at most ``max_tilt``."""
    tilt = tilt_angle(R)
    if tilt <= max_tilt:
        return R
    z = R[:, 2]
    axis = np.cross(z, WORLD_DOWN)
    n = np.linalg.norm(axis)
    if n < 1e-9:  # pointing straight up: any horizontal axis works
        axis = R[:, 0] - (R[:, 0] @ WORLD_DOWN) * WORLD_DOWN
        n = np.linalg.norm(axis)
    return rotvec_to_matrix(axis / n * (tilt - max_tilt)) @ R


def to_rot6d(R: np.ndarray) -> np.ndarray:
    """Continuous 6-D rotation representation: the first two columns of ``R`` (Zhou et al., CVPR 2019)."""
    R = np.asarray(R)
    return np.concatenate([R[:, 0], R[:, 1]])


def from_rot6d(r: np.ndarray) -> np.ndarray:
    """Inverse of :func:`to_rot6d` (Gram-Schmidt, tolerant to non-orthonormal network outputs)."""
    r = np.asarray(r, dtype=float)
    x = r[:3] / max(np.linalg.norm(r[:3]), 1e-9)
    y = r[3:] - (x @ r[3:]) * x
    y /= max(np.linalg.norm(y), 1e-9)
    return np.column_stack([x, y, np.cross(x, y)])


class EpisodeFrame:
    """Gravity-aligned frame anchored at the tool pose at the start of an episode.

    Origin = TCP position at the start, heading = tool yaw at the start, z = up. Each embodiment (human
    with the handheld tool, robot with the mounted tool) defines it from its own start pose, so poses
    expressed in it are calibration-free, like the per-step deltas, while still giving the policy
    absolute targets (no integration drift, no accumulation of tracking lag).
    """

    def __init__(self, p0: np.ndarray, R0: np.ndarray) -> None:
        self.p0 = np.asarray(p0, dtype=float).copy()
        self.R = rot_z(yaw_of(R0))

    def encode(self, p: np.ndarray, R: np.ndarray) -> np.ndarray:
        """World pose -> 9-D [position in the episode frame (3), rot6d (6)]."""
        return np.concatenate([self.R.T @ (np.asarray(p) - self.p0), to_rot6d(self.R.T @ R)])

    def decode(self, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        v = np.asarray(v, dtype=float)
        return self.p0 + self.R @ v[:3], self.R @ from_rot6d(v[3:9])
