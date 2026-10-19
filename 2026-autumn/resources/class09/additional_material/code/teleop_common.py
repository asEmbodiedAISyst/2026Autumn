"""Shared parts of the Class 09 teleoperation scripts (``teleop_rebot_rs_sim.py``, ``teleop_rebot_rs_real.py`` and
``teleop_rebot_rs_pusher_sim.py``).

* conventions of the reBot Arm B601-RS (joint names, direction vector, soft limits, home pose);
* ``PhoneReader`` / ``PhoneMapper``: the asMagic AR stream and the clutched "phone as gripper" mapping to a TCP
  pose: the camera direction of the phone is the direction the gripper points at, the top of the phone is the
  open/close direction of the fingers, the right side of the phone is the side of the gripper;
* ``DlsIk`` / ``TcpController``: workspace clip, speed limit and inverse kinematics on the MuJoCo model;
* ``Recorder``: one folder per episode (``meta.json``, ``frames.csv``, camera images);
* ``KeyReader``: keys from the terminal (used by the real-arm script, which has no viewer window);
* ``make_logger``: the ``sharklog`` logger used by both scripts.

Both scripts use the same keys:
    Space       start / pause the teleoperation (the mapping is re-aligned at every start)
    Right arrow start recording / stop recording and save the episode
    Left arrow  discard the recording in progress
    Enter       open / close the gripper
"""

from __future__ import annotations

import csv
import json
import math
import select
import sys
import threading
import time
from pathlib import Path

import mujoco
import numpy as np
import sharklog

# ----------------------------------------------------------------------------- model and conventions
MODEL_DIR = Path(__file__).resolve().parents[1] / "model" / "rebot_b601_rs_mjcf"
SCENES = {"table": "scene_table.xml", "cube": "scene_cube.xml"}
ARM_JOINTS = tuple(f"joint{i}" for i in range(1, 7))
MOTOR_NAMES = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_yaw", "wrist_roll", "gripper")
# Same conventions as the LeRobot driver of the physical arm: motor target = action x direction
DIRECTIONS = np.array([1, 1, -1, -1, -1, 1, 6], dtype=float)
SOFT_LIMITS_DEG = np.array([(-145, 145), (0, 170), (0, 200), (-80, 90), (-90, 90), (-130, 130), (0, 270)], dtype=float)
GRIPPER_STROKE, GRIPPER_MOTOR_MAX_DEG = 0.05, 270.0  # single-finger stroke (m) <-> gripper motor angle (deg)
HOME_QPOS = np.array([0.0, 1.532, 1.197, -1.236, 0.0, 0.0])  # rad; gripper vertical, TCP at (0.25, 0, 0.10) m
CONTROL_HZ = 30
IMAGE_HW = (480, 640)
WORKSPACE = np.array([[0.12, 0.42], [-0.25, 0.25], [0.03, 0.30]])  # TCP box (m); fingertips are 15 mm below the TCP
MAX_SPEED = 0.25  # TCP target speed limit (m/s)
MAX_ROT_SPEED = math.radians(90.0)  # TCP orientation speed limit (rad/s)
IK_TOL_POS, IK_TOL_ROT = 0.005, math.radians(5.0)  # a commanded pose must be reached this closely by the IK
STREAM_TIMEOUT = 0.25  # s without a new phone sample: hold the last target

# "Phone as gripper": one constant transform, ee_tf_iphone, the frame of the iPhone expressed in the frame of the
# end effector (the ``tcp`` site). Naming: a_tf_b is the pose of frame b in frame a, so a_p = a_tf_b @ b_p. Only
# the rotation part matters here (the translation cancels in a relative mapping), so it is a 3x3 matrix whose
# columns are the iPhone x, y, z axes written in ee coordinates. The ee frame: z out of the gripper (approach),
# y the open/close axis of the fingers, x across the fingers. The iPhone frame of the asMagic pose is the ARKit
# device frame: x along the long side towards the bottom of the phone, y towards the right edge, z out of the
# screen (the back camera looks along -z). Bottom -> ee y, right edge -> ee x, out of the screen -> ee -z, so the
# camera looks along ee +z. At the home pose the top of the phone (the camera end) points to the left of the arm
# seen from its base, and the right edge points forward. Check again after an app update: move the phone along one axis, watch the arm.
EE_TF_IPHONE = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])

# Keys, as GLFW key codes of the MuJoCo viewer; the terminal reader maps its escape sequences to the same codes
KEY_SPACE, KEY_ENTER, KEY_RIGHT, KEY_LEFT, KEY_Q = 32, 257, 262, 263, 81
KEY_HELP = "keys: Space = start/pause teleop, Right = start/stop+save recording, Left = discard recording, Enter = gripper"


def make_logger(name: str, debug: bool = False):
    """A ``sharklog`` logger: coloured level, message, time and source line on the terminal."""
    return sharklog.init(name=name, debug=debug)


def motor_deg_to_action(motor: np.ndarray) -> np.ndarray:
    return motor / DIRECTIONS


def action_to_motor_deg(action: np.ndarray) -> np.ndarray:
    return np.clip(action * DIRECTIONS, SOFT_LIMITS_DEG[:, 0], SOFT_LIMITS_DEG[:, 1])


def rot_z(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def quat_xyzw_to_matrix(q: np.ndarray) -> np.ndarray:
    x, y, z, w = np.asarray(q, dtype=float) / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def parse_pose(values) -> tuple[np.ndarray, np.ndarray] | None:
    """Position (m) and rotation matrix from the ``local_pose`` field: 7 values [x, y, z, qx, qy, qz, qw] or a
    4x4 matrix as 16 values (row-major, or column-major as ARKit stores it; detected from the last row)."""
    v = np.asarray(values, dtype=float)
    if v.size == 7:
        return v[:3].copy(), quat_xyzw_to_matrix(v[3:7])
    if v.size == 16:
        T = v.reshape(4, 4)
        if not np.allclose(T[3], [0, 0, 0, 1], atol=1e-3) and np.allclose(T[:, 3], [0, 0, 0, 1], atol=1e-3):
            T = T.T  # column-major flattening
        R = T[:3, :3]
        if abs(np.linalg.det(R) - 1.0) > 0.05:
            return None
        return T[:3, 3].copy(), R
    return None


def rotvec_to_matrix(r: np.ndarray) -> np.ndarray:
    a = float(np.linalg.norm(r))
    if a < 1e-12:
        return np.eye(3)
    k = r / a
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * K @ K


def matrix_to_rotvec(R: np.ndarray) -> np.ndarray:
    c = max(-1.0, min(1.0, (np.trace(R) - 1) / 2))
    a = math.acos(c)
    if a < 1e-9:
        return np.zeros(3)
    if math.pi - a < 1e-6:  # 180 degrees: axis from the symmetric part
        w, V = np.linalg.eigh((R + np.eye(3)) / 2)
        return math.pi * V[:, int(np.argmax(w))]
    return a / (2 * math.sin(a)) * np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])


# ----------------------------------------------------------------------------- phone input
class PhoneReader:
    """Receives the asMagic AR stream (ZeroMQ PUB on tcp://<phone-ip>:8000) in a background thread."""

    def __init__(self, ip: str, port: int) -> None:
        from asmagic import ARDataSubscriber

        self.sub = ARDataSubscriber(ip, port=port)
        self.address = f"tcp://{ip}:{port}"
        self.latest: tuple[np.ndarray, np.ndarray, float] | None = None  # (pos, rot, receive time)
        self.count, self.rate, self.pose_format = 0, 0.0, ""
        self._lock, self._stop = threading.Lock(), threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        t0, n0 = time.monotonic(), 0
        try:
            while not self._stop.is_set():
                try:
                    frame = self.sub.get(timeout=100)  # one get() per frame: all fields of the same instant
                    if frame is None or frame.local_pose is None:
                        continue
                    parsed = parse_pose(frame.local_pose)
                    if parsed is None:
                        continue
                    pos, rot = parsed
                    if self.count == 0:
                        self.pose_format = f"{len(frame.local_pose)} values"
                except Exception:
                    continue  # one bad frame must not stop the receiver
                now = time.monotonic()
                with self._lock:
                    self.latest = (pos, rot, now)
                    self.count += 1
                if now - t0 >= 1.0:
                    self.rate, t0, n0 = (self.count - n0) / (now - t0), now, self.count
        finally:
            self.sub.close()  # the socket is closed by the thread that owns it

    def get(self) -> tuple[np.ndarray, np.ndarray] | None:
        """The latest (position, rotation) of the phone, or None when no sample arrived for STREAM_TIMEOUT."""
        with self._lock:
            latest = self.latest
        if latest is None or time.monotonic() - latest[2] > STREAM_TIMEOUT:
            return None
        return latest[0], latest[1]

    def age(self) -> float | None:
        """Seconds since the latest sample, or None when none was received yet."""
        with self._lock:
            latest = self.latest
        return None if latest is None else time.monotonic() - latest[2]

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)


class PhoneMapper:
    """Clutched "phone as gripper" mapping: the phone motion since the start -> end-effector position and orientation.

    Frames: w = the AR world frame of the phone, wr = the robot base frame, iphone and ee the two bodies, with
    the constant ee_tf_iphone between them. At the start, the phone pose w_tf_iphone0 and the commanded
    end-effector pose wr_tf_ee0 fix the rotation between the two world frames,

        wr_R_w = wr_R_ee0 @ ee_R_iphone @ w_R_iphone0.T

    and from then on the end-effector pose is the chain wr_T_w @ w_T_iphone @ iphone_T_ee, with the translation
    offset chosen so that the start pose maps to the start pose:

        wr_p_ee = wr_p_ee0 + scale * wr_R_w @ (w_p_iphone - w_p_iphone0)
        wr_R_ee = wr_R_w @ w_R_iphone @ iphone_R_ee

    With ``track_rotation=False`` the end effector keeps its orientation and only the position follows.

    A tool with the phone mounted on it (the pusher) also gives the position of the phone in the ee frame,
    ``ee_p_iphone``. Then the end effector moves with the phone as one rigid body: the phone position follows
    the motion of the hand, and the TCP is the phone position plus the lever ``-wr_R_ee @ ee_p_iphone``, so a
    rotation of the phone swings the TCP. With ``ee_p_iphone`` = 0 (the gripper) both forms are the same.
    """

    def __init__(self, scale: float, track_rotation: bool, ee_R_iphone: np.ndarray = EE_TF_IPHONE,
                 ee_p_iphone: np.ndarray | None = None) -> None:
        self.ee_tf_iphone = np.asarray(ee_R_iphone, dtype=float)
        self.ee_p_iphone = np.zeros(3) if ee_p_iphone is None else np.asarray(ee_p_iphone, dtype=float)
        self.scale, self.track_rotation = scale, track_rotation
        self.w_p_iphone0 = self.wr_p_iphone0 = self.wr_R_ee0 = self.wr_R_w = self.filt = None

    def engage(self, w_p_iphone: np.ndarray, w_R_iphone: np.ndarray, wr_p_ee: np.ndarray, wr_R_ee: np.ndarray) -> None:
        self.w_p_iphone0, self.wr_R_ee0, self.filt = w_p_iphone.copy(), wr_R_ee.copy(), None
        self.wr_p_iphone0 = wr_p_ee + wr_R_ee @ self.ee_p_iphone  # where the phone is on the robot at the start
        self.wr_R_w = wr_R_ee @ self.ee_tf_iphone @ w_R_iphone.T  # the two world frames, related through the two bodies

    def map(self, w_p_iphone: np.ndarray, w_R_iphone: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """End-effector target position (m) and rotation matrix (robot base frame) for the current phone pose."""
        wr_p_iphone = self.wr_p_iphone0 + self.scale * (self.wr_R_w @ (w_p_iphone - self.w_p_iphone0))
        wr_R_ee = self.wr_R_w @ w_R_iphone @ self.ee_tf_iphone.T if self.track_rotation else self.wr_R_ee0.copy()
        wr_p_ee = wr_p_iphone - wr_R_ee @ self.ee_p_iphone
        self.filt = wr_p_ee if self.filt is None else 0.3 * self.filt + 0.7 * wr_p_ee  # first-order low-pass
        return self.filt.copy(), wr_R_ee


# ----------------------------------------------------------------------------- kinematics and control
class DlsIk:
    """Damped least-squares inverse kinematics on a private copy of the model state (kinematics only)."""

    def __init__(self, model: mujoco.MjModel, home: np.ndarray = HOME_QPOS) -> None:
        self.model, self.data = model, mujoco.MjData(model)
        self.home = np.asarray(home, dtype=float)
        self.site = model.site("tcp").id
        self.qadr = np.array([model.jnt_qposadr[model.joint(j).id] for j in ARM_JOINTS])
        self.dofadr = np.array([model.jnt_dofadr[model.joint(j).id] for j in ARM_JOINTS])
        lo = np.array([model.jnt_range[model.joint(j).id, 0] for j in ARM_JOINTS])
        hi = np.array([model.jnt_range[model.joint(j).id, 1] for j in ARM_JOINTS])
        self.lo = np.maximum(lo, np.radians(SOFT_LIMITS_DEG[:6, 0]))
        self.hi = np.minimum(hi, np.radians(SOFT_LIMITS_DEG[:6, 1]))
        self.jacp, self.jacr = np.zeros((3, model.nv)), np.zeros((3, model.nv))

    def fk(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        self.data.qpos[self.qadr] = q
        mujoco.mj_kinematics(self.model, self.data)
        mujoco.mj_comPos(self.model, self.data)
        return self.data.site_xpos[self.site].copy(), self.data.site_xmat[self.site].reshape(3, 3).copy()

    def solve(self, pos: np.ndarray, rot: np.ndarray, q0: np.ndarray, iters: int = 30) -> np.ndarray:
        q = np.clip(q0.copy(), self.lo, self.hi)
        for _ in range(iters):
            p, R = self.fk(q)
            e_pos = pos - p
            e_rot = 0.5 * sum(np.cross(R[:, k], rot[:, k]) for k in range(3))
            if np.linalg.norm(e_pos) < 1e-4 and np.linalg.norm(e_rot) < 1e-3:
                break
            mujoco.mj_jacSite(self.model, self.data, self.jacp, self.jacr, self.site)
            J = np.vstack([self.jacp[:, self.dofadr], 0.5 * self.jacr[:, self.dofadr]])
            e = np.concatenate([e_pos, 0.5 * e_rot])
            J_pinv = J.T @ np.linalg.solve(J @ J.T + 1e-3 * np.eye(6), np.eye(6))
            dq = J_pinv @ e + (np.eye(6) - J_pinv @ J) @ (0.05 * (self.home - q))
            n = np.linalg.norm(dq)
            if n > 0.2:
                dq *= 0.2 / n
            q = np.clip(q + dq, self.lo, self.hi)
        return q


class TcpController:
    """TCP target pose -> joint target: workspace clip, speed limits on position and orientation, IK.

    A step is accepted only when the IK reaches the new pose within IK_TOL_POS and IK_TOL_ROT (the soft joint
    limits make the reachable region small: with the gripper pointing down the TCP cannot go above about 0.12 m).
    Otherwise the commanded pose and the joint target stay where they are, and ``blocked`` is set, so the arm stops
    at the boundary of what it can reach and follows again when the phone comes back.
    """

    def __init__(self, model: mujoco.MjModel, q0: np.ndarray, workspace: np.ndarray = WORKSPACE,
                 home: np.ndarray = HOME_QPOS) -> None:
        self.ik = DlsIk(model, home=home)  # the IK prefers joint angles near ``home``
        self.workspace = np.asarray(workspace, dtype=float)
        self.q_cmd = q0.copy()
        self.target, self.rot = self.ik.fk(q0)
        self.blocked = False

    def command(self, pos: np.ndarray | None, rot: np.ndarray | None = None) -> np.ndarray:
        """Move the commanded pose towards (pos, rot) by at most the speed limits; return the joint target (rad)."""
        target, rot_cmd = self.target, self.rot
        if pos is not None:
            desired = np.array([np.clip(pos[k], *self.workspace[k]) for k in range(3)])
            step = desired - self.target
            n = np.linalg.norm(step)
            if n > MAX_SPEED / CONTROL_HZ:
                step *= MAX_SPEED / CONTROL_HZ / n
            target = self.target + step
        if rot is not None:
            dr = matrix_to_rotvec(rot @ self.rot.T)  # rotation still to do, in the world frame
            a = np.linalg.norm(dr)
            if a > MAX_ROT_SPEED / CONTROL_HZ:
                dr *= MAX_ROT_SPEED / CONTROL_HZ / a
            rot_cmd = rotvec_to_matrix(dr) @ self.rot
        q = self.ik.solve(target, rot_cmd, self.q_cmd)
        p, R = self.ik.fk(q)
        reached = np.linalg.norm(p - target) < IK_TOL_POS and np.linalg.norm(matrix_to_rotvec(R @ rot_cmd.T)) < IK_TOL_ROT
        if reached:
            self.target, self.rot, self.q_cmd = target, rot_cmd, q
        self.blocked = not reached
        return self.q_cmd.copy()


# ----------------------------------------------------------------------------- recorder
class Recorder:
    """Writes one folder per episode: meta.json, frames.csv and the camera images (if any)."""

    def __init__(self, out: Path, scene: str, robot_type: str, motor_names: tuple[str, ...] = MOTOR_NAMES,
                 directions: np.ndarray = DIRECTIONS) -> None:
        self.out, self.scene, self.robot_type = out, scene, robot_type
        self.motor_names, self.directions = tuple(motor_names), np.asarray(directions, dtype=float)
        self.out.mkdir(parents=True, exist_ok=True)
        self.n_saved = len(list(self.out.glob("episode_*")))
        self.rows: list[list] = []
        self.images: list[dict[str, np.ndarray]] = []
        self.active = False

    def start(self) -> None:
        self.rows, self.images, self.active = [], [], True
        self.t0 = time.monotonic()

    def add(self, state: np.ndarray, action: np.ndarray, images: dict[str, np.ndarray], phone_age: float, blocked: bool) -> None:
        """One frame: the wall-clock time since the start of the recording, the age of the latest phone sample
        (seconds; empty when no sample was received yet) and whether the controller was at its reach limit."""
        k = len(self.rows)
        age = "" if phone_age is None else round(phone_age, 4)
        self.rows.append([k, round(time.monotonic() - self.t0, 4), *state.tolist(), *action.tolist(), age, int(blocked)])
        self.images.append(images)

    def discard(self) -> int:
        n = len(self.rows)
        self.rows, self.images, self.active = [], [], False
        return n

    def save(self) -> Path | None:
        """Write the episode folder and return its path (None when nothing was recorded)."""
        self.active = False
        if not self.rows:
            return None
        from PIL import Image

        ep = self.out / f"episode_{self.n_saved:03d}"
        ep.mkdir()
        with open(ep / "frames.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["frame_index", "timestamp", *[f"state.{m}" for m in self.motor_names], *[f"action.{m}" for m in self.motor_names], "phone_age", "blocked"])
            w.writerows(self.rows)
        cams = sorted(self.images[0]) if self.images else []
        for cam in cams:
            (ep / cam).mkdir()
            for k, imgs in enumerate(self.images):
                if cam in imgs and imgs[cam] is not None:
                    Image.fromarray(imgs[cam]).save(ep / cam / f"{k:06d}.jpg", quality=90)
        (ep / "meta.json").write_text(json.dumps({
            "fps": CONTROL_HZ, "frames": len(self.rows), "scene": self.scene, "input": "asmagic",
            "robot_type": self.robot_type,
            "timestamp": "seconds since the start of the recording (wall clock)",
            "phone_age": "seconds since the latest phone sample at that frame", "blocked": "1 = at the reach limit",
            "observation.state": {"names": [f"{m}.pos" for m in self.motor_names], "unit": "deg (motor angle)"},
            "action": {"names": [f"{m}.pos" for m in self.motor_names], "unit": "deg (command space)",
                       "direction": self.directions.tolist(), "note": "motor target = action x direction"},
            "images": {cam: list(IMAGE_HW) + [3] for cam in cams},
        }, indent=2))
        self.n_saved += 1
        self.rows, self.images = [], []
        return ep


# ----------------------------------------------------------------------------- terminal keys
class KeyReader:
    """Reads single keys from the terminal without Enter (raw mode) and maps them to the viewer key codes.

    Arrow keys arrive as escape sequences (``ESC [ C`` = Right, ``ESC [ D`` = Left). Letters are accepted as
    aliases: ``r`` = Right, ``d`` = Left, ``g`` = Enter (gripper), ``q`` = quit.
    """

    ALIASES = {" ": KEY_SPACE, "\r": KEY_ENTER, "\n": KEY_ENTER, "r": KEY_RIGHT, "d": KEY_LEFT, "g": KEY_ENTER, "q": KEY_Q,
               "\x1b[C": KEY_RIGHT, "\x1b[D": KEY_LEFT, "\x03": KEY_Q}

    def __init__(self) -> None:
        import termios
        import tty

        self.fd = sys.stdin.fileno()
        self.saved = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        self._termios = termios

    def get(self) -> list[int]:
        """All keys pressed since the last call (non-blocking)."""
        keys: list[int] = []
        while select.select([sys.stdin], [], [], 0)[0]:
            ch = sys.stdin.read(1)
            if ch == "\x1b" and select.select([sys.stdin], [], [], 0.01)[0]:
                ch += sys.stdin.read(2)
            code = self.ALIASES.get(ch.lower() if len(ch) == 1 else ch)
            if code is not None:
                keys.append(code)
        return keys

    def close(self) -> None:
        self._termios.tcsetattr(self.fd, self._termios.TCSADRAIN, self.saved)
