"""reBot B601-RS with the original gripper (all 7 RobStride motors): bring-up and safety checks.

Backend of ``code/real_gripper_drag.py`` and ``code/real_gripper_motion_test.py`` for the first power-on tests
of the stock arm with the gripper. (The pusher-tool backend of Classes 10-11 is a separate module.)

What makes it safe for a first power-on:

* **soft MIT gains** (:data:`SOFT_MIT_KP` / :data:`SOFT_MIT_KD`, roughly 1/3 of the plugin defaults): the arm
  can be pushed by hand and a wrong target cannot produce violent motion;
* **connecting never moves the arm**: the plugin's zero-calibration prompt is skipped (the zero set in
  Motorbridge Studio is stored in the motors; a trivial calibration file is written once so the plugin does
  not ask to re-zero), the gripper zero probe is off by default, and the first command after the motors
  are enabled is an explicit zero-torque command;
* **gravity-compensation-only mode** (:meth:`RealGripperArm.send_gravity_only`): torque on, no position
  control, the arm can be dragged by hand and stays where it is left;
* **slow joint-space moves with a tracking guard** (:meth:`RealGripperArm.move_to`): torque is cut as soon
  as the arm does not follow the target, e.g. when it hits something.

Feedback: motorbridge updates a RobStride motor's state only from the reply (type-2 frame) to a command; its
``request_feedback()`` is a no-op for RobStride and the motors' own periodic "active report" frames are not
parsed. So :meth:`RealGripperArm.read` sends a zero-gain MIT frame (kp = kd = tau = 0) to every motor when no
command was sent since the previous read. Verified on the arm: disabled motors answer within ~3 ms and stay
disabled (mode bits 0); when a command was sent in this cycle (hold / move / gravity) its reply is used instead.

Units: motor angles in degrees as the plugin reports them (``<motor>.pos``); for the 6 arm joints this equals
the URDF / MuJoCo joint angle (see :mod:`rebot_sim.robot`). Actions sent to the plugin are
``motor_deg / joint_direction`` because the plugin multiplies by the direction again.
"""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Callable

import mujoco
import numpy as np

from ..robot import DIRECTIONS, MOTOR_LIMITS_DEG, MOTOR_NAMES, motor_deg_to_sim

log = logging.getLogger(__name__)

ARM_MOTORS = MOTOR_NAMES[:6]
GRIPPER_MOTOR = MOTOR_NAMES[6]
N_MOTORS = len(MOTOR_NAMES)
MOTOR_CAN_IDS = tuple(range(1, N_MOTORS + 1))

# Soft MIT gains (kp: N*m/rad, kd: N*m*s/rad), about 1/3 of the plugin defaults (50/150/150/50/50/50).
# 10 deg of error on the shoulder gives ~7 N*m, enough to hold the arm with gravity compensation on, but the
# arm can still be pushed away by hand. Scale with ``kp_scale`` once the basic checks pass.
SOFT_MIT_KP: dict[str, float] = {
    "shoulder_pan": 20.0,
    "shoulder_lift": 40.0,
    "elbow_flex": 40.0,
    "wrist_flex": 15.0,
    "wrist_yaw": 10.0,
    "wrist_roll": 10.0,
}
SOFT_MIT_KD: dict[str, float] = {
    "shoulder_pan": 2.0,
    "shoulder_lift": 4.0,
    "elbow_flex": 4.0,
    "wrist_flex": 1.5,
    "wrist_yaw": 1.0,
    "wrist_roll": 1.0,
}
# Joint targets further than this from the measured position are refused (deg): never a valid test step.
MAX_JUMP_DEG = 25.0
# Wait between the zero-gain feedback request and the poll (s); replies arrive within ~1 ms per motor.
FEEDBACK_WAIT_S = 0.003
# Upper bound of the gravity feedforward torque sent in gravity-only mode (N*m): protects against a wrong
# model / pairing. The stock arm needs well under 10 N*m on the shoulder when stretched out horizontally.
GRAVITY_TAU_MAX = 10.0
# Return to the folded zero pose in two stages, same order as the plugin's safe_zero (checked collision-free
# by Seeed): base and wrist first, then shoulder and elbow.
ZERO_STAGES: tuple[tuple[str, ...], ...] = (
    ("shoulder_pan", "wrist_flex", "wrist_yaw", "wrist_roll"),
    ("shoulder_lift", "elbow_flex"),
)


class TrackingError(RuntimeError):
    """The arm did not follow the commanded target; torque has already been disabled."""


# ---------------------------------------------------------------------- CAN and calibration file
def check_can_up(port: str = "can0", sysfs: str = "/sys/class/net") -> None:
    """Exit with a clear hint when the SocketCAN interface is missing or DOWN (needs root to bring up).

    The interface comes up DOWN after every boot or re-plug of the USB adapter unless the systemd unit from
    ``tools/can/setup_can0.sh`` is installed. Non-Linux hosts and non-SocketCAN ports are not checked.
    """
    base = os.path.join(sysfs, port)
    if not os.path.isdir(sysfs) or "/" in port:
        return
    if not os.path.isdir(base):
        raise SystemExit(f"CAN interface {port} not found. Is the USB-CAN adapter connected? "
                         f"(check with: ip -br link; driver: peak_usb)")
    try:
        flags = int(open(os.path.join(base, "flags")).read().strip(), 16)
    except (OSError, ValueError):
        return
    if not flags & 0x1:  # IFF_UP
        raise SystemExit(
            f"CAN interface {port} is DOWN. To bring it up by hand:\n"
            f"    sudo ip link set {port} type can bitrate 1000000 restart-ms 100 && sudo ip link set {port} up\n"
            f"To bring it up automatically (after each boot and each re-plug), run once:\n"
            f"    sudo tools/can/setup_can0.sh")


def ensure_calibration_file(robot) -> bool:
    """Write the plugin's calibration file if missing so ``connect()`` never asks to re-zero the motors.

    The content is exactly what the plugin's own ``calibrate()`` writes (homing offset 0, range +-90): the
    zero position itself lives in the motors (set in Motorbridge Studio), the file only tells the plugin
    that calibration was done. Returns True when a file was written.
    """
    if robot.is_calibrated:
        return False
    from lerobot.motors import MotorCalibration

    robot.calibration = {
        name: MotorCalibration(id=send_id, drive_mode=0, homing_offset=0, range_min=-90, range_max=90)
        for name, (send_id, _recv_id) in robot.config.motor_can_ids.items()
    }
    robot._save_calibration()
    log.info("calibration file written: %s (the zero lives in the motors; this file only stops the plugin "
             "from asking to re-zero)", robot.calibration_fpath)
    return True


@dataclass
class MotorSnapshot:
    """One feedback poll of all 7 motors (index order = :data:`rebot_sim.robot.MOTOR_NAMES`)."""

    pos_deg: np.ndarray
    vel_deg_s: np.ndarray
    torque: np.ndarray  # N*m as reported by the motor
    t_mos: np.ndarray  # MOSFET temperature, deg C
    status: np.ndarray  # motor status code (0 = OK)
    ok: np.ndarray  # feedback received in this poll

    def arm_q(self) -> np.ndarray:
        """6 arm joint angles (rad, MuJoCo convention)."""
        return motor_deg_to_sim(self.pos_deg)[0]

    def gripper_m(self) -> float:
        """Single-finger opening (m) from the (uncalibrated) gripper ratio in :mod:`rebot_sim.robot`."""
        return motor_deg_to_sim(self.pos_deg)[1]


class RealGripperArm:
    """Stock reBot B601-RS (6 arm motors + gripper) through Seeed's ``seeed_b601_rs_follower`` plugin.

    Args:
        port: SocketCAN interface.
        robot_id: calibration-file id (separate from the pusher's ``rebot_pusher``).
        fps: control rate of :meth:`move_to`.
        max_step_deg: per-cycle clamp applied by the plugin to every target (deg).
        kp_scale: multiplies :data:`SOFT_MIT_KP` (kd is scaled by its square root to keep the damping ratio).
        gravity_compensation: add the plugin's gravity feedforward (URDF with the gripper, so it matches
            this configuration) to every MIT command.
        check_gripper_zero: run the plugin's gripper zero probe at connect (closes the gripper with a small
            torque and checks that it reads ~0 deg). Off by default: it is the only part of ``connect`` that
            applies torque.
        abort_error_deg: :meth:`move_to` cuts torque when any arm joint lags the target by more than this.
        gravity_scale / gravity_offset / gravity_fit: per-motor correction of the model feedforward,
            ``tau = g(q) * scale + offset + a * cos(q_motor) + b * sin(q_motor)`` with ``gravity_fit[m] = (a, b)``
            in N*m. The URDF masses and the motors' torque constants are approximate; the shoulder in particular
            drifts when the model is a few tenths of a N*m off. The ``(a, b)`` term is exactly what a shifted
            centre of mass of the upper arm adds to the shoulder torque; ``real_gripper_motion_test.py
            --gravity-sweep`` measures it. Tune by hand in gravity-only mode (``real_gripper_drag.py --mode
            gravity``) until the arm stays put, or use the numbers printed by the motion test.
    """

    def __init__(
        self,
        port: str = "can0",
        robot_id: str = "rebot_gripper",
        fps: int = 30,
        max_step_deg: float = 5.0,
        kp_scale: float = 1.0,
        gravity_compensation: bool = True,
        check_gripper_zero: bool = False,
        abort_error_deg: float = 15.0,
        gravity_scale: dict[str, float] | None = None,
        gravity_offset: dict[str, float] | None = None,
        gravity_fit: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        if kp_scale <= 0:
            raise ValueError("kp_scale must be greater than 0")
        for d in (gravity_scale or {}, gravity_offset or {}, gravity_fit or {}):
            unknown = set(d) - set(ARM_MOTORS)
            if unknown:
                raise ValueError(f"unknown joint {sorted(unknown)}, valid joints: {list(ARM_MOTORS)}")
        self.gravity_scale = dict(gravity_scale or {})
        self.gravity_offset = dict(gravity_offset or {})
        self.gravity_fit = {m: (float(a), float(b)) for m, (a, b) in (gravity_fit or {}).items()}
        self.port = port
        self.robot_id = robot_id
        self.fps = fps
        self.max_step_deg = max_step_deg
        self.gravity_compensation = gravity_compensation
        self.check_gripper_zero = check_gripper_zero
        self.abort_error_deg = abort_error_deg
        self.mit_kp = {m: SOFT_MIT_KP[m] * kp_scale for m in ARM_MOTORS}
        self.mit_kd = {m: SOFT_MIT_KD[m] * math.sqrt(kp_scale) for m in ARM_MOTORS}
        self.robot = None
        self.last: MotorSnapshot | None = None  # last feedback poll
        self.target: np.ndarray | None = None  # last commanded motor target (deg), None until the first command
        self._sent_since_read = False  # a command (and therefore a feedback reply) is pending for the next read
        self._gravity_warned = False
        # The gripper is only position-controlled (plugin impedance, up to 3.5 N*m against its stops) while this is
        # True; otherwise ``command`` keeps it at zero torque so arm tests do not load the gripper motor.
        self.gripper_active = False

    # ------------------------------------------------------------------ connection
    def connect(self) -> MotorSnapshot:
        """Open the bus, enable the motors in MIT mode with **zero torque**, and return the first snapshot."""
        try:
            from lerobot_robot_seeed_b601 import SeeedB601RSFollower, SeeedB601RSFollowerConfig
        except ImportError as e:  # pragma: no cover - depends on the optional "real" dependency group
            raise SystemExit("The driver for the physical arm is missing: uv sync --group real "
                             "(installs lerobot-robot-seeed-b601 / motorbridge)") from e

        check_can_up(self.port)
        cfg = SeeedB601RSFollowerConfig(
            port=self.port,
            id=self.robot_id,
            max_relative_target=self.max_step_deg,
            mit_kp=dict(self.mit_kp),
            mit_kd=dict(self.mit_kd),
            gravity_mit_kp=dict(self.mit_kp),
            gravity_mit_kd=dict(self.mit_kd),
            gravity_compensation=self.gravity_compensation,
        )
        self.robot = SeeedB601RSFollower(cfg)
        ensure_calibration_file(self.robot)
        # calibrate=True would only run the gripper zero probe here (the calibration file exists, so the
        # plugin never asks to re-zero the motors).
        self.robot.connect(calibrate=self.check_gripper_zero)
        self._install_gravity_adjust()
        self.send_zero_torque()
        snap = self.read()
        if not snap.ok.any():
            self.disable_torque()
            raise RuntimeError("No feedback from any motor: check that the 48 V power is on and the CAN cable is connected")
        log.info("physical arm connected (zero torque), motor angles (deg): %s", np.round(snap.pos_deg, 1))
        return snap

    @property
    def is_connected(self) -> bool:
        return self.robot is not None and bool(self.robot.is_connected)

    def close(self, return_to_zero: bool = False, speed_deg_s: float = 5.0) -> None:
        """Optionally return to the folded zero pose (slow, guarded), then disable torque and close the bus."""
        if self.robot is None:
            return
        try:
            if self.robot.is_connected:
                if return_to_zero:
                    self.return_to_zero(speed_deg_s)
                # The plugin's own safe_zero (25 deg/s, no tracking check) is never used from here.
                self.robot._skip_safe_zero_on_disconnect = True
                self.robot.disconnect()  # torque off, clear errors, close the bus
        finally:
            self.robot = None

    # ------------------------------------------------------------------ feedback
    def read(self) -> MotorSnapshot:
        """Fresh feedback from all motors. Motors that did not answer keep their previous values, ``ok=False``.

        When nothing was sent since the previous read and no position hold is active, a zero-gain MIT frame is
        sent to every motor to request the reply (see the module docstring). While a position target is
        held, ``read`` must follow a ``command`` in the same cycle (``move_to`` does this), otherwise the
        state is simply the last reply.
        """
        r = self.robot
        if not self._sent_since_read and self.target is None:
            for motor in r.motors.values():
                motor.send_mit(0.0, 0.0, 0.0, 0.0, 0.0)  # zero output: only asks for the feedback frame
            time.sleep(FEEDBACK_WAIT_S)
        self._sent_since_read = False
        try:
            r.bus.poll_feedback_once()
        except Exception as e:  # noqa: BLE001 - the plugin does the same; a missed poll is not fatal
            log.warning("CAN feedback read failed: %s", e)
        prev = self.last
        pos = prev.pos_deg.copy() if prev is not None else np.zeros(N_MOTORS)
        vel, torque, t_mos = np.zeros(N_MOTORS), np.zeros(N_MOTORS), np.full(N_MOTORS, np.nan)
        status, ok = np.zeros(N_MOTORS, dtype=int), np.zeros(N_MOTORS, dtype=bool)
        for i, name in enumerate(MOTOR_NAMES):
            st = r.motors[name].get_state()
            if st is None:
                continue
            ok[i] = True
            pos[i] = math.degrees(st.pos)
            vel[i] = math.degrees(st.vel)
            torque[i] = st.torq
            t_mos[i] = st.t_mos
            status[i] = st.status_code
        self.last = MotorSnapshot(pos, vel, torque, t_mos, status, ok)
        return self.last

    # ------------------------------------------------------------------ torque-level commands
    def send_zero_torque(self) -> None:
        """MIT command with kp = kd = tau = 0 to every motor: enabled, but no output."""
        for motor in self.robot.motors.values():
            motor.send_mit(0.0, 0.0, 0.0, 0.0, 0.0)
        self._sent_since_read = True

    def disable_torque(self) -> None:
        self.robot.disable_torque()
        self.target = None

    def _install_gravity_adjust(self) -> None:
        """Wrap the plugin's feedforward so that ``send_action`` and :meth:`gravity_torques` both apply
        ``gravity_scale`` / ``gravity_offset`` (the plugin adds its feedforward inside ``send_action``)."""
        if not (self.gravity_scale or self.gravity_offset or self.gravity_fit) or getattr(self.robot, "_gravity_adjusted", False):
            return
        original = self.robot._gravity_feedforward

        def adjusted() -> dict[str, float]:
            ff = original()
            out = {}
            for m, v in ff.items():
                v = v * self.gravity_scale.get(m, 1.0) + self.gravity_offset.get(m, 0.0)
                if m in self.gravity_fit and self.last is not None:
                    a, b = self.gravity_fit[m]
                    q = math.radians(self.last.pos_deg[MOTOR_NAMES.index(m)])
                    v += a * math.cos(q) + b * math.sin(q)
                out[m] = v
            return out

        self.robot._gravity_feedforward = adjusted
        self.robot._gravity_adjusted = True

    def gravity_torques(self) -> np.ndarray:
        """Gravity feedforward for the 6 arm motors (N*m) at the last snapshot, after ``gravity_scale`` /
        ``gravity_offset``; zeros when disabled."""
        if not self.gravity_compensation:
            return np.zeros(6)
        ff = self.robot._gravity_feedforward()
        if not ff and not self._gravity_warned:
            self._gravity_warned = True
            log.warning("the gravity model of the plugin is not available (URDF joint count does not match the "
                        "motor count?); the gravity feedforward is 0")
        return np.array([ff.get(m, 0.0) for m in ARM_MOTORS])

    def send_gravity_only(self, scale: float = 1.0, damping: float = 0.3, tau_max: float = GRAVITY_TAU_MAX) -> np.ndarray:
        """Gravity feedforward only (kp = 0, small kd) on the arm motors, zero torque on the gripper.

        Call :meth:`read` first in every cycle (the feedforward uses the cached motor states). Returns the
        torques that were sent.
        """
        tau = np.clip(self.gravity_torques() * scale, -tau_max, tau_max)
        for i, name in enumerate(ARM_MOTORS):
            self.robot.motors[name].send_mit(0.0, 0.0, 0.0, damping, float(tau[i]))
        self.robot.motors[GRIPPER_MOTOR].send_mit(0.0, 0.0, 0.0, 0.0, 0.0)
        self.target = None
        self._sent_since_read = True
        return tau

    def set_zero_here(self) -> None:
        """Store the current pose as the motors' zero (what Motorbridge Studio / the plugin's calibrate do).

        Torque is switched off first. Only call this with the arm held in the folded zero pose (all joints
        0 deg, gripper closed): it overwrites the zero stored in the motors.
        """
        self.robot.bus.disable_all()
        self.target = None
        for motor in self.robot.motors.values():
            motor.set_zero_position()
            time.sleep(0.1)

    # ------------------------------------------------------------------ position commands (soft MIT)
    def command(self, motor_deg: np.ndarray) -> np.ndarray:
        """Send 7 motor targets (deg) through the plugin (soft gains, optional gravity feedforward).

        Targets are clipped to the soft limits and refused when an arm joint would jump more than
        :data:`MAX_JUMP_DEG` from the last measured position. The gripper target is only sent while
        ``gripper_active`` is True (otherwise the gripper gets a zero-torque frame). Returns the clipped target.
        """
        motor = np.asarray(motor_deg, dtype=float)
        if motor.shape != (N_MOTORS,):
            raise ValueError(f"need {N_MOTORS} motor targets, got shape {motor.shape}")
        lo = np.array([MOTOR_LIMITS_DEG[m][0] for m in MOTOR_NAMES])
        hi = np.array([MOTOR_LIMITS_DEG[m][1] for m in MOTOR_NAMES])
        motor = np.clip(motor, lo, hi)
        ref = (self.last if self.last is not None else self.read()).pos_deg
        jump = np.abs(motor[:6] - ref[:6]).max()
        if jump > MAX_JUMP_DEG:
            raise RuntimeError(f"joint target is {jump:.1f} deg from the current position (> {MAX_JUMP_DEG} deg): refused")
        names = MOTOR_NAMES if self.gripper_active else ARM_MOTORS
        self.robot.send_action({f"{m}.pos": float(v) for m, v in zip(names, motor / DIRECTIONS)})
        if not self.gripper_active:
            self.robot.motors[GRIPPER_MOTOR].send_mit(0.0, 0.0, 0.0, 0.0, 0.0)  # zero torque, still answers
        self.target = motor
        self._sent_since_read = True
        return motor

    def hold(self) -> MotorSnapshot:
        """Switch from zero torque to position hold at the measured pose (no motion if the arm is still)."""
        snap = self.read()
        self.command(snap.pos_deg)
        return snap

    def check_tracking(self, snap: MotorSnapshot, target: np.ndarray) -> float:
        """Largest arm-joint error (deg); disables torque and raises :class:`TrackingError` above the limit."""
        err = np.abs(target[:6] - snap.pos_deg[:6])
        worst = int(err.argmax())
        if err[worst] > self.abort_error_deg:
            self.disable_torque()
            raise TrackingError(
                f"{MOTOR_NAMES[worst]} is {err[worst]:.1f} deg behind the target (> {self.abort_error_deg} deg): "
                f"collision, too little stiffness or wrong direction. Torque is off"
            )
        return float(err[worst])

    def move_to(
        self,
        motor_deg: np.ndarray,
        speed_deg_s: float = 5.0,
        on_step: Callable[[MotorSnapshot, np.ndarray], None] | None = None,
        settle_s: float = 0.5,
    ) -> float:
        """Smooth joint-space move to 7 motor targets (deg) at ``speed_deg_s`` (fastest joint), then settle.

        Every cycle reads the motors, calls ``on_step(snapshot, target)`` and checks tracking. Returns the
        largest arm-joint error seen during the move (deg).
        """
        q1 = np.asarray(motor_deg, dtype=float)
        q0 = self.target if self.target is not None else self.read().pos_deg
        span = float(np.abs(q1 - q0).max())
        n = max(1, math.ceil(span / max(speed_deg_s, 1e-6) * self.fps))
        worst = 0.0
        for i in range(1, n + 1 + int(settle_s * self.fps)):
            t0 = time.perf_counter()
            a = min(1.0, i / n)
            s = a * a * (3 - 2 * a)  # smoothstep: zero velocity at both ends
            target = self.command(q0 + s * (q1 - q0))
            time.sleep(max(0.0, 1.0 / self.fps - (time.perf_counter() - t0)))
            snap = self.read()
            if on_step is not None:
                on_step(snap, target)
            worst = max(worst, self.check_tracking(snap, target))
        return worst

    def return_to_zero(self, speed_deg_s: float = 5.0, on_step=None) -> float:
        """Two-stage guarded move to the folded zero pose (gripper untouched). Returns the worst error (deg)."""
        if self.target is None:
            self.hold()
        worst = 0.0
        for stage in ZERO_STAGES:
            target = self.target.copy()
            for name in stage:
                target[MOTOR_NAMES.index(name)] = 0.0
            worst = max(worst, self.move_to(target, speed_deg_s, on_step))
        return worst


# ---------------------------------------------------------------------- helpers
class GripperTwin:
    """Kinematic MuJoCo twin of the stock arm (course gripper table scene) driven by measured motor angles.

    The twin is never stepped: :meth:`update` writes the measured angles into ``qpos`` and runs the
    kinematics only. The model is ``model/rebot_b601_rs_mjcf/scene_table.xml`` (see :mod:`rebot_sim.sim`).
    """

    def __init__(self) -> None:
        from ..sim import RebotSim

        self.sim = RebotSim("table")
        self.model, self.data = self.sim.model, self.sim.data

    def update(self, snap: MotorSnapshot) -> None:
        arm_q, gripper = motor_deg_to_sim(snap.pos_deg)
        self.data.qpos[self.sim.arm_qadr] = arm_q
        self.data.qpos[self.sim.finger_qadr] = gripper
        mujoco.mj_kinematics(self.model, self.data)

    def tcp_pose(self) -> tuple[np.ndarray, np.ndarray]:
        return self.sim.tcp_pose()

    def close(self) -> None:
        self.sim.close()


def format_table(snap: MotorSnapshot, target: np.ndarray | None = None, tau_g: np.ndarray | None = None,
                 tcp: np.ndarray | None = None) -> list[str]:
    """Human-readable status block: one row per motor plus an optional TCP line (for in-place refresh)."""
    lines = [f"{'motor':<14}{'ID':>3} {'angle deg':>9} {'target':>8} {'vel deg/s':>9} {'torque Nm':>9} "
             f"{'grav Nm':>8} {'temp':>6}  state"]
    for i, name in enumerate(MOTOR_NAMES):
        tgt = f"{target[i]:+8.1f}" if target is not None else f"{'--':>8}"
        g = f"{tau_g[i]:+8.2f}" if tau_g is not None and i < len(tau_g) else f"{'--':>8}"
        temp = f"{snap.t_mos[i]:5.0f}C" if np.isfinite(snap.t_mos[i]) else f"{'--':>6}"
        state = "OK" if snap.ok[i] and snap.status[i] == 0 else ("NO FEEDBACK" if not snap.ok[i] else f"ERROR CODE {snap.status[i]}")
        lines.append(f"{name:<14}{MOTOR_CAN_IDS[i]:>3} {snap.pos_deg[i]:+9.1f} {tgt} {snap.vel_deg_s[i]:+9.1f} "
                     f"{snap.torque[i]:+9.2f} {g} {temp}  {state}")
    if tcp is not None:
        lines.append(f"gripper TCP (model) x={tcp[0] * 100:6.1f} y={tcp[1] * 100:6.1f} z={tcp[2] * 100:6.1f} cm   "
                     f"gripper opening {snap.gripper_m() * 1000:5.1f} mm (ratio not calibrated)")
    return lines
