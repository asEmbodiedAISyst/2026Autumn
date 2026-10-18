"""asMagic phone-pose teleoperation.

The asMagic app (iPhone, ARKit) publishes AR data via ZeroMQ PUB on ``tcp://<phone IP>:8000``, with
``local_pose = [tx, ty, tz, qx, qy, qz, qw]`` (meters, quaternion xyzw) in the ARKit world frame:
x right, y up, z towards the user (the camera looks along -z), gravity aligned.

This module provides:

* :class:`AsmagicPoseReader`: background thread that keeps the latest pose (never blocks the sim loop);
* :class:`PhoneMapper`: maps the phone's motion relative to the "engage" moment onto a TCP target.
  The heading is aligned to the phone's orientation at engage time, so "phone forward = arm forward"
  regardless of where the operator stands.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass

import numpy as np

from ..pose import matrix_to_rotvec, rotvec_to_matrix

log = logging.getLogger(__name__)

# ARKit (x right, y up, z back) -> robot base frame (x forward, y left, z up), operator facing ARKit -z
ARKIT_TO_ROBOT = np.array([[0.0, 0.0, -1.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])


@dataclass
class PhonePose:
    pos: np.ndarray  # (3,) ARKit world frame, m
    rot: np.ndarray  # (3, 3) ARKit world frame
    stamp: float  # phone-side timestamp (s)
    recv_time: float  # PC receive time (time.monotonic)


def quat_xyzw_to_matrix(q: np.ndarray) -> np.ndarray:
    """Quaternion (x, y, z, w) -> rotation matrix.

    scipy is deliberately not used in the receiver thread: scipy probes the ``torch`` module and raises
    if the main thread is importing torch at the same moment.
    """
    x, y, z, w = np.asarray(q, dtype=float) / np.linalg.norm(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def parse_pose(pose: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Parse an asMagic ``local_pose``. Supports 7 values (t + xyzw) and 16 values (4x4 matrix)."""
    pose = np.asarray(pose, dtype=float).ravel()
    if pose.size == 7:
        if not np.isfinite(pose).all() or np.linalg.norm(pose[3:7]) < 1e-6:
            raise ValueError("invalid quaternion")
        return pose[:3].copy(), quat_xyzw_to_matrix(pose[3:7])
    if pose.size == 16:
        T = pose.reshape(4, 4)
        if not np.allclose(T[3], [0, 0, 0, 1], atol=1e-4):
            T = T.T  # column-major
        return T[:3, 3].copy(), T[:3, :3].copy()
    raise ValueError(f"cannot parse a pose of length {pose.size}")


class AsmagicPoseReader:
    """Subscribe to the asMagic AR stream in a background thread; the latest pose is always available."""

    def __init__(self, ip: str, port: int = 8000, use_global_pose: bool = False) -> None:
        from asmagic import ARDataSubscriber  # lazy import so the rest works without asmagic

        self.address = f"tcp://{ip}:{port}"
        self._sub = ARDataSubscriber(ip, port=port)
        self._use_global = use_global_pose
        self._latest: PhonePose | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._count = 0
        self._errors = 0
        self._rate = 0.0
        self._thread = threading.Thread(target=self._run, name="asmagic-reader", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            self._loop()
        finally:
            # ZeroMQ sockets are not thread-safe: close it only in the receiver thread
            self._sub.close()

    def _loop(self) -> None:
        t0, n0 = time.monotonic(), 0
        while not self._stop.is_set():
            try:
                frame = self._sub.get(timeout=100)
                if frame is None:
                    continue
                raw = frame.global_pose if self._use_global else frame.local_pose
                if raw is None or len(raw) not in (7, 16):
                    continue
                pos, rot = parse_pose(raw)
            except Exception as e:  # one bad frame must not kill the receiver thread
                self._errors += 1
                if self._errors <= 3:
                    log.warning("asMagic frame could not be parsed: %r", e)
                continue
            now = time.monotonic()
            with self._lock:
                self._latest = PhonePose(pos, rot, float(frame.timestamp), now)
                self._count += 1
            if now - t0 >= 1.0:
                self._rate = (self._count - n0) / (now - t0)
                t0, n0 = now, self._count

    def latest(self, max_age: float = 0.25) -> PhonePose | None:
        """Latest pose, or None if not updated for ``max_age`` seconds (stream considered lost)."""
        with self._lock:
            p = self._latest
        if p is None or time.monotonic() - p.recv_time > max_age:
            return None
        return p

    @property
    def rate_hz(self) -> float:
        return self._rate

    @property
    def frame_count(self) -> int:
        return self._count

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)


def _yaw_of(v: np.ndarray) -> float | None:
    h = math.hypot(v[0], v[1])
    if h < 0.3:
        return None
    return math.atan2(v[1], v[0])


def rot_z(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


class PhoneMapper:
    """Phone pose -> TCP target (clutched relative mapping).

    Args:
        scale: Translation scale (phone moves 1 m -> arm moves ``scale`` m).
        operator_yaw_deg: Yaw of the operator's facing direction in the robot base frame. 0 = standing
            behind the arm facing the same way; 180 = standing across the table facing the arm.
        align_heading: Align the heading to the phone's orientation at engage time (recommended).
        smoothing: First-order low-pass coefficient for position (0-1); larger is smoother but laggier.
    """

    def __init__(
        self,
        scale: float = 1.0,
        operator_yaw_deg: float = 0.0,
        align_heading: bool = True,
        smoothing: float = 0.3,
    ) -> None:
        self.scale = scale
        self.operator_yaw = math.radians(operator_yaw_deg)
        self.align_heading = align_heading
        self.smoothing = smoothing
        self.engaged = False
        self._M = ARKIT_TO_ROBOT.copy()
        self._phone0: PhonePose | None = None
        self._robot_pos0 = np.zeros(3)
        self._robot_rot0 = np.eye(3)
        self._filt: np.ndarray | None = None

    def engage(self, phone: PhonePose, robot_pos: np.ndarray, robot_rot: np.ndarray) -> None:
        """Record phone and robot poses at engage time; afterwards output motion relative to them."""
        M = ARKIT_TO_ROBOT
        if self.align_heading:
            fwd = M @ phone.rot @ np.array([0.0, 0.0, -1.0])  # direction of the phone's back camera
            yaw = _yaw_of(fwd)
            if yaw is None:  # phone lying flat: use the phone's top edge direction
                yaw = _yaw_of(M @ phone.rot @ np.array([0.0, 1.0, 0.0]))
            if yaw is None:
                yaw = 0.0
            M = rot_z(self.operator_yaw - yaw) @ M
        else:
            M = rot_z(self.operator_yaw) @ M
        self._M = M
        self._phone0 = phone
        self._robot_pos0 = np.asarray(robot_pos, dtype=float).copy()
        self._robot_rot0 = np.asarray(robot_rot, dtype=float).copy()
        self._filt = None
        self.engaged = True

    def disengage(self) -> None:
        self.engaged = False
        self._phone0 = None

    def map(self, phone: PhonePose) -> tuple[np.ndarray, np.ndarray]:
        """Return (TCP target position, TCP target rotation). Requires :meth:`engage` first."""
        assert self._phone0 is not None, "engage() must be called first"
        dp = self.scale * (self._M @ (phone.pos - self._phone0.pos))
        pos = self._robot_pos0 + dp
        if self._filt is None:
            self._filt = pos
        else:
            a = self.smoothing
            self._filt = a * self._filt + (1 - a) * pos
        dR = phone.rot @ self._phone0.rot.T  # rotation increment in the ARKit world frame
        dR_robot = self._M @ dR @ self._M.T
        return self._filt.copy(), dR_robot @ self._robot_rot0


class RigidPhoneMapper:
    """Phone camera pose -> TCP pose of the rigid tool the phone is mounted on (rod + phone).

    Unlike :class:`PhoneMapper`, the tool pose follows the phone with the full rigid transform
    (rotating the phone swings the rod tip, exactly as with the real 3D-printed part). At engage time only
    a yaw rotation and a translation are estimated to line up the phone's ARKit frame with the scene, so the
    tool tilt (gravity direction) always matches the real phone.

    Orientation modes (``orientation``):

    * ``"absolute"`` (default): only heading and position are aligned at engage; the tool tilt is the real
      phone's tilt with respect to gravity. The robot tool therefore snaps to the hand tool's tilt at engage
      (blended over ``blend_s`` seconds), and a few degrees of mounting difference between the two prints
      show up as a constant tilt offset;
    * ``"relative"``: the whole rotation is aligned at engage, i.e. the way the hand tool is held when Space
      is pressed counts as the robot tool's current orientation; afterwards rotations are followed relative
      to that. No snap, no constant offset, but the robot phone's view no longer equals the hand phone's.

    Args:
        R_cam_tcp, p_cam_tcp: TCP pose expressed in the phone camera frame (camera axes as in MuJoCo/ARKit:
            x right, y up, looking along -z). Take them from the tool CAD, or use :meth:`from_model`.
        smoothing: First-order low-pass coefficient for position (0-1).
        orientation: see above.
        blend_s: seconds over which the orientation blends from the robot's pose at engage to the mapped
            pose (0 = immediate).
    """

    def __init__(self, R_cam_tcp: np.ndarray, p_cam_tcp: np.ndarray, smoothing: float = 0.0,
                 orientation: str = "absolute", blend_s: float = 0.0) -> None:
        if orientation not in ("absolute", "relative"):
            raise ValueError("orientation must be 'absolute' or 'relative'")
        self.R_cam_tcp = np.asarray(R_cam_tcp, dtype=float)
        self.p_cam_tcp = np.asarray(p_cam_tcp, dtype=float)
        self.smoothing = smoothing
        self.orientation = orientation
        self.blend_s = blend_s
        self.engaged = False
        self._A = np.eye(3)  # yaw alignment for the position (and the rotation in absolute mode)
        self._A_rot = np.eye(3)  # full rotation alignment (relative mode)
        self._t = np.zeros(3)
        self._filt: np.ndarray | None = None
        self._R0 = np.eye(3)  # robot TCP rotation at engage (blend start)
        self._t_engage = 0.0

    @classmethod
    def from_model(cls, model, camera: str = "phone", site: str = "tcp", smoothing: float = 0.0,
                   orientation: str = "absolute", blend_s: float = 0.0) -> RigidPhoneMapper:
        """Read the camera -> TCP transform from a MuJoCo model containing the tool."""
        import mujoco

        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)  # camera poses are only computed by mj_camlight (part of mj_forward)
        R_cam = data.cam(camera).xmat.reshape(3, 3)
        R_tcp = data.site(site).xmat.reshape(3, 3)
        p = R_cam.T @ (data.site(site).xpos - data.cam(camera).xpos)
        return cls(R_cam.T @ R_tcp, p, smoothing, orientation, blend_s)

    def _raw_tcp(self, phone: PhonePose) -> tuple[np.ndarray, np.ndarray]:
        R_cam = ARKIT_TO_ROBOT @ phone.rot  # phone camera in a z-up frame (heading still arbitrary)
        p_cam = ARKIT_TO_ROBOT @ phone.pos
        return p_cam + R_cam @ self.p_cam_tcp, R_cam @ self.R_cam_tcp

    def engage(self, phone: PhonePose, tcp_pos: np.ndarray, tcp_rot: np.ndarray) -> None:
        """Align heading and position so that the current phone pose maps onto the current TCP pose."""
        from ..pose import rot_z, yaw_of

        p_raw, R_raw = self._raw_tcp(phone)
        tcp_rot = np.asarray(tcp_rot, dtype=float)
        self._A = rot_z(yaw_of(tcp_rot) - yaw_of(R_raw))
        self._A_rot = tcp_rot @ R_raw.T  # relative mode: the current hand orientation = the current tool orientation
        self._t = np.asarray(tcp_pos, dtype=float) - self._A @ p_raw
        self._filt = None
        self._R0 = tcp_rot.copy()
        self._t_engage = time.monotonic()
        self.engaged = True

    def disengage(self) -> None:
        self.engaged = False

    def map(self, phone: PhonePose) -> tuple[np.ndarray, np.ndarray]:
        """Return (TCP position, TCP rotation) in the scene frame. Requires :meth:`engage` first."""
        p_raw, R_raw = self._raw_tcp(phone)
        pos = self._A @ p_raw + self._t
        if self._filt is None or self.smoothing <= 0:
            self._filt = pos
        else:
            self._filt = self.smoothing * self._filt + (1 - self.smoothing) * pos
        rot = (self._A_rot if self.orientation == "relative" else self._A) @ R_raw
        if self.blend_s > 0:
            a = min(1.0, (time.monotonic() - self._t_engage) / self.blend_s)
            if a < 1.0:  # geodesic blend from the robot's orientation at engage towards the mapped one
                rot = rotvec_to_matrix(a * matrix_to_rotvec(rot @ self._R0.T)) @ self._R0
        return self._filt.copy(), rot


@dataclass
class PhoneFrame:
    """One asMagic AR frame: phone camera pose (ARKit world) + color image (RGB, decoded)."""

    pos: np.ndarray
    rot: np.ndarray
    image: np.ndarray | None  # (H, W, 3) uint8, None if the frame carried no image
    stamp: float
    recv_time: float
    seq: int


class AsmagicFrameReader:
    """Like :class:`AsmagicPoseReader`, but keeps the latest pose *and* the color image of the same frame.

    Used to record real handheld demonstrations (the phone on the printed tool is the policy camera).
    """

    def __init__(self, ip: str, port: int = 8000) -> None:
        from asmagic import ARDataSubscriber

        self.address = f"tcp://{ip}:{port}"
        self._sub = ARDataSubscriber(ip, port=port)
        self._latest: PhoneFrame | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._count = 0
        self._errors = 0
        self._rate = 0.0
        self._thread = threading.Thread(target=self._run, name="asmagic-frames", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            t0, n0 = time.monotonic(), 0
            while not self._stop.is_set():
                try:
                    frame = self._sub.get(timeout=100)
                    if frame is None or frame.local_pose is None or len(frame.local_pose) not in (7, 16):
                        continue
                    pos, rot = parse_pose(frame.local_pose)
                    image = frame.color_array if frame.has_color_image else None
                except Exception as e:  # one bad frame must not kill the receiver thread
                    self._errors += 1
                    if self._errors <= 3:
                        log.warning("asMagic frame could not be parsed: %r", e)
                    continue
                now = time.monotonic()
                with self._lock:
                    self._count += 1
                    self._latest = PhoneFrame(pos, rot, image, float(frame.timestamp), now, self._count)
                if now - t0 >= 1.0:
                    self._rate = (self._count - n0) / (now - t0)
                    t0, n0 = now, self._count
        finally:
            self._sub.close()  # ZeroMQ sockets are not thread-safe: close it only in the receiver thread

    def latest(self, max_age: float = 0.25) -> PhoneFrame | None:
        with self._lock:
            f = self._latest
        if f is None or time.monotonic() - f.recv_time > max_age:
            return None
        return f

    @property
    def rate_hz(self) -> float:
        return self._rate

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
