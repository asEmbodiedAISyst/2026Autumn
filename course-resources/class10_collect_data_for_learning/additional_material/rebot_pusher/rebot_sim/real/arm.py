"""Joint-space arm backends for the pusher tool: the real reBot B601-RS follower or the MuJoCo arm.

Both expose the same small interface used by :class:`rebot_sim.real.env.RealToolPushEnv`:

* ``connect()`` / ``close()``;
* ``read_q()`` -> 6 joint angles (rad, MuJoCo / URDF convention);
* ``command_q(q)`` -> send 6 joint targets (rad);
* ``move_to(q, speed_deg_s)`` -> slow joint-space interpolation (blocking), used between episodes.

Unit conventions (see :mod:`rebot_sim.robot`): motor angle (deg) = degrees(URDF joint angle) for the 6 arm
joints, and the follower's ``send_action`` multiplies the action by ``joint_directions``, so
``action = motor target / direction``.

Feedback: motorbridge updates a RobStride motor state only from the reply to a command (its
``request_feedback()`` is a no-op for RobStride and the motors' periodic active-report frames are ignored), so a
read-only loop (torque off, ``scripts/real_check.py``) would see frozen values. :meth:`RealArm.read_q` therefore
sends a zero-gain MIT frame (kp = kd = tau = 0, no output) to every motor when nothing was commanded since the
previous read and no position is being held; during control the reply to the last command is used.
"""

from __future__ import annotations

import logging
import math
import threading
import time

import numpy as np

from ..robot import DIRECTIONS, MOTOR_LIMITS_DEG, MOTOR_NAMES

log = logging.getLogger(__name__)

ARM_MOTORS = MOTOR_NAMES[:6]  # the gripper motor (ID 7) is removed together with the gripper
ARM_DIRECTIONS = DIRECTIONS[:6]
# A joint target that differs from the previous target by more than this (deg) is refused: a jump this large
# in one cycle means a bug or a bad IK solution, never a valid teleoperation / policy step at 30 Hz.
MAX_JUMP_DEG = 25.0
# Lagging vs. stuck. A joint more than LAG_DEG behind its target is "lagging": the caller should stop advancing
# the target and let the arm catch up (no abort). If the lag persists for STALL_TIME_S while the joint moves less
# than STALL_PROGRESS_DEG, the joint is stuck (collision, obstacle) and ``check_stall`` raises.
LAG_DEG = 10.0
STALL_TIME_S = 1.0
STALL_PROGRESS_DEG = 1.0
# Teleoperation slow-down: the commanded pose advances at full speed up to SLOW_LAG_DEG of joint lag, slows down
# linearly and stops at 2 * SLOW_LAG_DEG. At 30 cm/s a 200 ms tracking delay alone is ~10 deg of lag, so this is
# looser than the stall threshold above.
SLOW_LAG_DEG = 20.0
# Motor MOS temperature limits (deg C) used by the direct MIT path (the plugin checks them in send_action).
TEMP_WARN_C, TEMP_STOP_C = 115.0, 125.0
# Rate at which the motor targets are streamed (Hz). The control loop runs at ``fps`` (30 Hz); the streamer
# interpolates linearly between consecutive targets so the motors do not see 30 Hz steps (audible knocking with
# stiff gains and a short filter). 0 = send directly from the control loop.
STREAM_HZ = 150
# Wait between the zero-gain feedback request and the plugin's poll (s); the motors reply within ~1 ms each.
FEEDBACK_WAIT_S = 0.003
# The plugin clips every target to this distance from the *measured* position (deg). With MIT control that caps
# the motor torque at kp * angle (10 deg * 120 N*m/rad = 21 N*m on the shoulder / elbow, 7 N*m on the wrist):
# small enough to stop against an obstacle, large enough to lift the arm (the elbow needs ~7 N*m when folded).
# A tighter value (3 deg) left the shoulder unable to lift at all.
DEFAULT_MAX_ERROR_DEG = 10.0
# Upper bound of the gravity feedforward per joint (N*m): protects against a wrong model.
GRAVITY_TAU_MAX = 10.0
# Joints that leave the folded zero pose first (shoulder_lift, elbow_flex): in that pose the wrist (link5) rests
# against the upper arm (link2) and link4 is 3 mm from it, so the wrist must not flex before the arm has opened.
UNFOLD_JOINTS = (1, 2)
# Default MIT gain factor on the plugin defaults (kp 50/150/150/50/50/50, kd 3/10/10/5/4/4): 0.8 gives the
# 40/120/120/40/40/40 set that the class-09 teleoperation script verified on the arm.
DEFAULT_KP_SCALE = 0.8
# First-order filter on the joint targets sent to the motors (s): takes the phone jitter and the IK steps out
# of the motion. 0 disables it.
DEFAULT_FILTER_TAU = 0.1


class SimArm:
    """MuJoCo pusher arm (physics), for running the real-robot scripts without hardware."""

    def __init__(self, scene: str = "pusher_push_cube", fps: int = 30, cameras: tuple[str, ...] = ("phone",),
                 image_size: tuple[int, int] = (480, 640)) -> None:
        from ..robot import ZERO_QPOS
        from ..sim import RebotSim

        self.sim = RebotSim(scene, fps, cameras, image_size)
        self.sim.reset(ZERO_QPOS)  # like the real arm: powered up in the folded zero pose
        self.fps = fps

    def connect(self) -> None:
        pass

    def read_q(self) -> np.ndarray:
        return self.sim.arm_q()

    def command_q(self, q: np.ndarray) -> None:
        self.sim.set_targets(np.asarray(q, dtype=float))
        self.sim.step()

    def move_to(self, q: np.ndarray, speed_deg_s: float = 20.0) -> None:
        _interpolate(self, q, speed_deg_s, self.fps, sleep=False)

    def lag_deg(self) -> float:
        """Largest distance between the joint targets and the simulated joints (deg)."""
        return float(np.degrees(np.abs(self.sim.arm_target() - self.sim.arm_q())).max())

    def check_stall(self) -> None:
        pass  # the simulated arm cannot collide with unmodelled objects

    def close(self) -> None:
        self.sim.close()


class RealArm:
    """reBot B601-RS follower with the pusher tool: Seeed ``seeed_b601_rs_follower`` with the 6 arm motors only.

    ``connect()`` writes the plugin's calibration marker file if missing (no re-zeroing: the zero set in
    Motorbridge Studio is in the motors), then runs the plugin's connect (MIT mode, torque on with zero gains).
    ``close()`` uses the plugin's ``disconnect()``, which brings the arm back to the folded zero pose in two
    stages (joints 1/4/5/6, then 2/3; checked collision-free with the tool in simulation) and disables torque.

    Faults: a target jumping more than :data:`MAX_JUMP_DEG` from the previous target is refused (IK anomaly).
    A joint more than :data:`LAG_DEG` behind is reported by :meth:`lag_deg` so the caller can wait instead of
    advancing; :meth:`check_stall` raises (torque off) only when the lag persists without the joint moving.

    MIT gains are the plugin defaults times ``kp_scale`` (0.8 = the set verified in the class-09 script); the
    joint targets are rate-limited (``max_step_deg`` per cycle, relative to the previous target) and go through
    a first-order filter (``filter_tau``). ``max_error_deg`` is the plugin's clamp around the measured position,
    i.e. the torque cap kp * max_error_deg. A background thread streams the targets to the motors at
    ``stream_hz`` with linear interpolation between consecutive control-loop targets (no 30 Hz steps).
    """

    def __init__(self, port: str = "can0", robot_id: str = "rebot_pusher", fps: int = 30,
                 max_step_deg: float = 3.0, gravity_compensation: bool = True,
                 kp_scale: float = DEFAULT_KP_SCALE, filter_tau: float = DEFAULT_FILTER_TAU,
                 max_error_deg: float = DEFAULT_MAX_ERROR_DEG, gravity_scale: float = 1.0,
                 stream_hz: int = STREAM_HZ) -> None:
        if kp_scale <= 0 or filter_tau < 0 or max_step_deg <= 0 or max_error_deg <= 0 or gravity_scale < 0 or stream_hz < 0:
            raise ValueError("kp_scale, max_step_deg and max_error_deg must be positive; filter_tau, gravity_scale and stream_hz must not be negative")
        self.gravity_scale = gravity_scale
        self._gsim = None  # MuJoCo pusher model used for the gravity feedforward
        # High-rate target streamer (see STREAM_HZ). All bus access goes through _bus_lock.
        self.stream_hz = stream_hz
        self._bus_lock = threading.Lock()
        self._target_lock = threading.Lock()
        self._stream_target: np.ndarray | None = None  # latest filtered target (deg)
        self._stream_from: np.ndarray | None = None  # where the current interpolation started (deg)
        self._stream_t0 = 0.0
        self._stream_sent: np.ndarray | None = None  # last target actually sent (deg)
        self._stream_thread: threading.Thread | None = None
        self._stream_stop = threading.Event()
        self.stream_error: BaseException | None = None
        self._kp = self._kd = None  # per-motor MIT gains (set in connect), used by the direct MIT path
        self._temp_warned = False
        self.port = port
        self.robot_id = robot_id
        self.fps = fps
        self.max_step_deg = max_step_deg  # rate limit: change of the commanded target per cycle (deg)
        self.max_error_deg = max_error_deg  # plugin clamp of the target around the measured position (torque cap)
        self._q_prev: np.ndarray | None = None  # last rate-limited target (deg)
        self._q_meas: np.ndarray | None = None  # last measured joints (deg), kept across commands
        self._lag_since: float | None = None  # when the current lag episode started
        self._lag_q0: np.ndarray | None = None  # measured joints at its start (progress check)
        self.gravity_compensation = gravity_compensation
        self.kp_scale = kp_scale
        self.filter_tau = filter_tau
        # weight of the previous filtered target: exp(-dt / tau)
        self._keep = math.exp(-1.0 / (fps * filter_tau)) if filter_tau > 0 else 0.0
        self._q_filt: np.ndarray | None = None  # filtered motor target (deg), reset by connect / disable_torque
        self.robot = None
        self._q_last: np.ndarray | None = None  # last measured joints (reused by command_q in the same cycle)
        self._sent_since_read = False  # a command was sent since the last read: its reply carries the feedback
        self._holding = False  # a position target is active (never send zero-gain frames then)

    def connect(self) -> None:
        try:
            from lerobot_robot_seeed_b601 import SeeedB601RSFollower, SeeedB601RSFollowerConfig
        except ImportError as e:  # pragma: no cover - depends on the optional "real" dependency group
            raise SystemExit("the arm driver is missing: run uv sync --group real (installs lerobot-robot-seeed-b601 and motorbridge)") from e

        check_can_up(self.port)
        defaults = SeeedB601RSFollowerConfig(port=self.port)
        cfg = SeeedB601RSFollowerConfig(
            port=self.port,
            id=self.robot_id,
            motor_can_ids={m: defaults.motor_can_ids[m] for m in ARM_MOTORS},
            joint_limits={m: defaults.joint_limits[m] for m in ARM_MOTORS},
            joint_directions={m: defaults.joint_directions[m] for m in ARM_MOTORS},
            mit_kp={m: defaults.mit_kp[m] * self.kp_scale for m in ARM_MOTORS},
            mit_kd={m: defaults.mit_kd[m] * self.kp_scale for m in ARM_MOTORS},
            # the plugin switches to these gains when gravity_compensation is on: keep ours
            gravity_mit_kp={m: defaults.mit_kp[m] * self.kp_scale for m in ARM_MOTORS},
            gravity_mit_kd={m: defaults.mit_kd[m] * self.kp_scale for m in ARM_MOTORS},
            # The plugin clips every target to this distance from the measured position (deg): a torque cap.
            max_relative_target=self.max_error_deg,
            gravity_compensation=self.gravity_compensation,
        )
        self.robot = SeeedB601RSFollower(cfg)
        self._kp = np.array([cfg.mit_kp[m] for m in ARM_MOTORS])
        self._kd = np.array([cfg.mit_kd[m] for m in ARM_MOTORS])
        # The zero position lives in the motors (Motorbridge Studio); the plugin's calibration file is only a
        # marker. Writing it here keeps connect() from asking to re-zero the motors at whatever pose the arm is in.
        ensure_calibration_file(self.robot)
        self.robot.connect(calibrate=True)
        self._install_gravity_model()
        self._sent_since_read = self._holding = False  # enabled with zero gains until the first command
        self._q_filt = self._q_prev = None
        self._start_stream()
        q = self.read_q()
        log.info("arm connected, joint angles (deg): %s", np.round(np.degrees(q), 1))

    def read_q(self) -> np.ndarray:
        if not self._sent_since_read and not self._holding:
            with self._bus_lock:
                for motor in getattr(self.robot, "motors", {}).values():
                    motor.send_mit(0.0, 0.0, 0.0, 0.0, 0.0)  # zero output: only requests the feedback frame
            time.sleep(FEEDBACK_WAIT_S)
        self._sent_since_read = False
        with self._bus_lock:
            obs = self.robot.get_observation()
        self._q_last = np.radians([obs[f"{m}.pos"] for m in ARM_MOTORS])
        self._q_meas = np.degrees(self._q_last)
        self._check_temperatures()
        return self._q_last.copy()

    def _check_temperatures(self) -> None:
        """MOS temperature guard on the cached states (the plugin does this inside send_action, which the
        streaming path bypasses): warn above TEMP_WARN_C, torque off and raise above TEMP_STOP_C."""
        motors = getattr(self.robot, "motors", None)
        if not motors:
            return
        for name in ARM_MOTORS:
            st = motors[name].get_state() if name in motors else None
            if st is None:
                continue
            if st.t_mos > TEMP_STOP_C:
                self.disable_torque()
                raise RuntimeError(f"{name} temperature {st.t_mos:.0f} °C is above {TEMP_STOP_C:.0f} °C; torque disabled")
            if st.t_mos > TEMP_WARN_C and not self._temp_warned:
                self._temp_warned = True
                log.warning("%s temperature %.0f °C is high", name, st.t_mos)

    def _install_gravity_model(self) -> None:
        """Replace the plugin's gravity feedforward (URDF with the gripper) by the MuJoCo pusher-arm model.

        The plugin adds ``_gravity_feedforward()`` to every MIT command when ``gravity_compensation`` is on; here
        the torques come from the same model the IK uses (arm links from the vendor URDF, 0.3 kg tool with the
        phone), evaluated at the last measured joints. Without it the soft gains sag by ~2 deg at the elbow and
        the tool tilts forward by ~4 deg.
        """
        if not self.gravity_compensation:
            return
        from ..sim import RebotSim

        self._gsim = RebotSim("pusher_table", cameras=())
        arm = self

        def feedforward() -> dict[str, float]:
            if arm._q_meas is None:
                return {}
            return {name: float(t) for name, t in zip(ARM_MOTORS, arm.gravity_torques())}

        self.robot._gravity_feedforward = feedforward

    def gravity_torques(self) -> np.ndarray:
        """Gravity torque of the 6 arm joints at the last measured pose (N*m, pusher model), scaled and clipped."""
        if self._gsim is None or self._q_meas is None:
            return np.zeros(6)
        import mujoco

        m, d = self._gsim.model, self._gsim.data
        d.qpos[self._gsim.arm_qadr] = np.radians(self._q_meas)
        d.qvel[:] = 0.0
        mujoco.mj_forward(m, d)  # qfrc_bias at zero velocity = gravity
        tau = d.qfrc_bias[self._gsim.arm_dofadr] * self.gravity_scale
        return np.clip(tau, -GRAVITY_TAU_MAX, GRAVITY_TAU_MAX)

    def lag_deg(self) -> float:
        """Largest distance between the commanded target and the last measured position (deg); 0 before any command."""
        if self._q_prev is None or self._q_meas is None:
            return 0.0
        return float(np.abs(self._q_prev - self._q_meas).max())

    def check_stall(self) -> None:
        """Raise when a joint has been more than LAG_DEG behind for STALL_TIME_S without moving: stuck, not lagging."""
        if self._q_prev is None or self._q_meas is None:
            return
        err = np.abs(self._q_prev - self._q_meas)
        now = time.monotonic()
        if err.max() <= LAG_DEG:
            self._lag_since = self._lag_q0 = None
            return
        if self._lag_since is None:
            self._lag_since, self._lag_q0 = now, self._q_meas.copy()
            return
        progress = np.abs(self._q_meas - self._lag_q0)
        if now - self._lag_since > STALL_TIME_S and progress.max() < STALL_PROGRESS_DEG:
            j = int(err.argmax())
            self.disable_torque()
            raise RuntimeError(
                f"{ARM_MOTORS[j]} is stuck: {err[j]:.1f} deg behind its target, moved only {progress[j]:.1f} deg in {STALL_TIME_S:.0f} s"
                f" (collision, obstacle or not enough torque); torque disabled")
        if progress.max() >= STALL_PROGRESS_DEG:  # still moving: restart the window from here
            self._lag_since, self._lag_q0 = now, self._q_meas.copy()

    def set_zero(self, motors: list[str] | None = None) -> None:
        """Store the current position as zero for the given motors (default all 6); same as Motorbridge Studio.

        Torque is switched off first. Only call with the joints in their zero pose: it overwrites the zero
        stored in the motors.
        """
        self.disable_torque()
        for name in motors or list(ARM_MOTORS):
            with self._bus_lock:
                self.robot.motors[name].set_zero_position()
            time.sleep(0.1)
        self._q_last = None

    def disable_torque(self) -> None:
        """Torque off for read-only use (the arm can be moved by hand); ``close()`` then does not move it back to zero."""
        self._holding = False  # first: the streamer stops sending position targets
        with self._target_lock:
            self._stream_target = self._stream_from = self._stream_sent = None
        with self._bus_lock:
            self.robot.disable_torque()
        self.robot._skip_safe_zero_on_disconnect = True
        self._q_filt = self._q_prev = None
        self._lag_since = self._lag_q0 = None

    def command_q(self, q: np.ndarray) -> None:
        q = np.asarray(q, dtype=float)
        motor = np.degrees(q)
        lo = np.array([MOTOR_LIMITS_DEG[m][0] for m in ARM_MOTORS])
        hi = np.array([MOTOR_LIMITS_DEG[m][1] for m in ARM_MOTORS])
        motor = np.clip(motor, lo, hi)
        q_now = self._q_last if self._q_last is not None else self.read_q()
        ref = self._q_prev if self._q_prev is not None else np.degrees(q_now)  # previous target, or measured at first
        err = np.abs(motor - ref)
        j = int(err.argmax())
        if err[j] > MAX_JUMP_DEG:
            raise RuntimeError(
                f"{ARM_MOTORS[j]} target jumps from {ref[j]:.1f} to {motor[j]:.1f} deg ({err[j]:.1f} > {MAX_JUMP_DEG} deg): refused"
                f" (IK or pose input anomaly); jumps of all joints (deg) {np.round(err, 1)}")
        if self._q_prev is None:  # first command after connect / torque off: start from the measured pose
            self._q_prev = self._q_filt = np.degrees(q_now)
        # rate limit relative to the previous *target* (not to the measured position, which would cap the torque)
        motor = self._q_prev + np.clip(motor - self._q_prev, -self.max_step_deg, self.max_step_deg)
        self._q_prev = motor
        self._q_filt = self._keep * self._q_filt + (1.0 - self._keep) * motor
        motor = self._q_filt
        if self.stream_error is not None:
            raise RuntimeError(f"streaming thread error: {self.stream_error!r}")
        if self._stream_thread is not None and self._stream_thread.is_alive():
            with self._target_lock:  # the streamer interpolates from the last sent target to this one
                self._stream_from = self._stream_sent if self._stream_sent is not None else np.degrees(q_now)
                self._stream_target = motor.copy()
                self._stream_t0 = time.perf_counter()
        else:
            self._send(motor)
        self._q_last = None
        self._sent_since_read = self._holding = True

    def _send(self, motor_deg: np.ndarray, vel_deg_s: np.ndarray | None = None) -> None:
        """Send one set of motor targets (deg). From the control loop: the plugin's ``send_action``. From the
        streamer: direct MIT frames with velocity feedforward (the plugin always sends vel = 0, so its kd term
        brakes every motion and adds ~kd/kp = 70 ms of lag), the same gains, the same torque cap
        (``max_error_deg`` around the measured position) and the gravity feedforward."""
        motor_deg = np.asarray(motor_deg, dtype=float)
        if vel_deg_s is None or self._kp is None:
            with self._bus_lock:
                self.robot.send_action({f"{m}.pos": float(v) for m, v in zip(ARM_MOTORS, motor_deg / ARM_DIRECTIONS)})
        else:
            tau = self.gravity_torques()
            with self._bus_lock:
                for i, name in enumerate(ARM_MOTORS):
                    motor = self.robot.motors[name]
                    st = motor.get_state()
                    pos = motor_deg[i]
                    if st is not None:  # torque cap: never ask for more than max_error_deg of position error
                        meas = math.degrees(st.pos)
                        pos = meas + float(np.clip(pos - meas, -self.max_error_deg, self.max_error_deg))
                    motor.send_mit(math.radians(pos), math.radians(float(vel_deg_s[i])), float(self._kp[i]),
                                   float(self._kd[i]), float(tau[i]))
        self._stream_sent = motor_deg.copy()
        self._sent_since_read = True

    def _start_stream(self) -> None:
        if self.stream_hz <= 0 or (self._stream_thread is not None and self._stream_thread.is_alive()):
            return
        self._stream_stop.clear()
        self.stream_error = None
        self._stream_thread = threading.Thread(target=self._stream_loop, name="rebot-stream", daemon=True)
        self._stream_thread.start()

    def _stop_stream(self) -> None:
        self._stream_stop.set()
        if self._stream_thread is not None:
            self._stream_thread.join(timeout=1.0)
        self._stream_thread = None

    def _stream_loop(self) -> None:
        """Send the interpolated target at ``stream_hz`` while a position is held (see STREAM_HZ)."""
        period = 1.0 / self.stream_hz
        try:
            while not self._stream_stop.is_set():
                t0 = time.perf_counter()
                with self._target_lock:
                    target, start, t_set = self._stream_target, self._stream_from, self._stream_t0
                if self._holding and target is not None and start is not None:
                    a = min(1.0, (t0 - t_set) * self.fps)  # reach the new target within one control period
                    vel = (target - start) * self.fps if a < 1.0 else np.zeros_like(target)  # deg/s feedforward
                    self._send(start + a * (target - start), vel)
                time.sleep(max(0.0, period - (time.perf_counter() - t0)))
        except BaseException as e:  # noqa: BLE001 - surfaced to the control loop by command_q
            self.stream_error = e
            log.exception("streaming thread error")

    def move_to(self, q: np.ndarray, speed_deg_s: float = 20.0) -> None:
        _interpolate(self, q, speed_deg_s, self.fps, sleep=True)

    def close(self) -> None:
        self._stop_stream()
        if self.robot is not None and self.robot.is_connected:
            with self._bus_lock:
                self.robot.disconnect()  # safe_zero (two stages) + torque off
        self.robot = None
        if self._gsim is not None:
            self._gsim.close()
            self._gsim = None


def check_can_up(port: str = "can0", sysfs: str = "/sys/class/net") -> None:
    """Exit with a clear hint when the SocketCAN interface is missing or DOWN (needs root to bring up).

    The interface comes up DOWN after every boot or re-plug of the USB adapter unless the systemd unit from
    ``tools/can/setup_can0.sh`` is installed. Non-Linux hosts and non-SocketCAN ports are not checked.
    """
    import os

    base = os.path.join(sysfs, port)
    if not os.path.isdir(sysfs) or "/" in port:
        return
    if not os.path.isdir(base):
        raise SystemExit(f"CAN interface {port} not found. Make sure that the USB-CAN adapter is connected (check with ip -br link; driver peak_usb).")
    try:
        flags = int(open(os.path.join(base, "flags")).read().strip(), 16)
    except (OSError, ValueError):
        return
    if not flags & 0x1:  # IFF_UP
        raise SystemExit(
            f"CAN interface {port} is DOWN. To bring it up manually:\n"
            f"    sudo ip link set {port} type can bitrate 1000000 restart-ms 100 && sudo ip link set {port} up\n"
            f"To bring it up automatically after every boot or re-plug (one-time setup):\n"
            f"    sudo tools/can/setup_can0.sh")


def move_to_staged(arm, q_target: np.ndarray, speed_deg_s: float = 20.0) -> None:
    """Leave the folded zero pose in two stages: shoulder_lift + elbow_flex first, then base and wrist.

    The reverse of the plugin's ``safe_zero`` (wrist and base first, shoulder and elbow last). A straight
    joint-space line from the folded pose flexes the wrist while the arm is still closed and passes within
    10 mm of the upper arm in the model; on the real arm that rubs. Works with both ``RealArm`` and ``SimArm``.
    """
    q_target = np.asarray(q_target, dtype=float)
    stage1 = arm.read_q()
    stage1[list(UNFOLD_JOINTS)] = q_target[list(UNFOLD_JOINTS)]
    arm.move_to(stage1, speed_deg_s)
    arm.move_to(q_target, speed_deg_s)


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
    log.info("calibration file written: %s (the zero lives in the motors; the file only keeps the plugin from asking to re-zero)", robot.calibration_fpath)
    return True


def _interpolate(arm, q_target: np.ndarray, speed_deg_s: float, fps: int, sleep: bool) -> None:
    """Linear joint-space move from the measured position to ``q_target`` at ``speed_deg_s`` (largest joint)."""
    q0 = arm.read_q()
    q1 = np.asarray(q_target, dtype=float)
    span = np.degrees(np.abs(q1 - q0)).max()
    n = max(1, math.ceil(span / speed_deg_s * fps))
    for i in range(1, n + 1):
        t0 = time.perf_counter()
        a = i / n
        s = a * a * (3 - 2 * a)  # smoothstep: zero velocity at both ends
        arm.command_q(q0 + s * (q1 - q0))
        if sleep:
            time.sleep(max(0.0, 1.0 / fps - (time.perf_counter() - t0)))
            arm.read_q()
            arm.check_stall()  # collision during a slow move: abort (torque off) instead of pushing on
    for _ in range(int(0.5 * fps)):  # settle
        t0 = time.perf_counter()
        arm.command_q(q1)
        if sleep:
            time.sleep(max(0.0, 1.0 / fps - (time.perf_counter() - t0)))
