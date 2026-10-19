"""Teleoperate the physical reBot Arm B601-RS with the asMagic app and record episodes (Class 09).

The script has the same command path, keys and recording format as ``teleop_rebot_rs_sim.py``; only the arm is
different: the seven RobStride motors (RS-06 x3, RS-00 x4) on the CAN bus (SocketCAN adapter, can0), driven
through the ``motorbridge`` SDK in MIT (impedance) mode with the gains of the vendor LeRobot driver. Verified on
the physical arm on 9 Oct 2026.

SAFETY RULES. READ THEM BEFORE YOU RUN THE SCRIPT.
  * One person keeps control of the power switch at all times and can cut the power without delay.
  * Nobody stays inside the workspace of the arm while the motors are enabled; hold the phone outside its reach.
  * Normal stop: press q (or Ctrl-C). The arm returns to its zero pose, wrist first, then the motors are disabled.
    Wait for the log line "motors disabled" before you touch the arm.
  * The power switch is the emergency stop only; after it the arm falls to its mechanical stops.

    uv sync --extra real                                              # motor SDK (one time)
    sudo ip link set can0 up type can bitrate 1000000                 # SocketCAN adapter (one time per boot)
    uv run python code/teleop_rebot_rs_real.py --phone-ip 192.168.1.100 --can can0 --set-zero      # only if the Class 08 zero is missing
    uv run python code/teleop_rebot_rs_real.py --phone-ip 192.168.1.100 --can can0
    uv run python code/teleop_rebot_rs_real.py --phone-ip 192.168.1.100 --can can0 --camera front=0

Sequence: connect, read the joint angles, move slowly to the home pose (shoulder and elbow first, then the wrist),
then wait for the keys. At the end (``q`` or Ctrl-C) the arm moves slowly back to the zero pose (wrist first,
then shoulder and elbow) and the motors are disabled.

Keys (in the terminal):
    Space       start / pause the teleoperation (the phone pose and the gripper pose are the references at every start)
    Right / r   start recording; press again to stop and save the episode
    Left / d    discard the recording in progress
    Enter / g   open / close the gripper
    q           quit (return to zero, disable the motors)

Limits in the script: the joint targets are clipped to the soft limits and to at most MAX_JOINT_STEP_DEG per
control period, then a first-order filter (TARGET_FILTER_TAU, option --filter-tau) smooths them before the motors; when the phone stream stops the arm holds its last target; a motor over TEMP_WARN_C is reported,
over TEMP_STOP_C the script returns to zero and stops.
"""

from __future__ import annotations

import argparse
import math
import sys
import threading
import time
from pathlib import Path

import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from teleop_common import (  # noqa: E402
    CONTROL_HZ, GRIPPER_MOTOR_MAX_DEG, GRIPPER_STROKE, HOME_QPOS, IMAGE_HW, KEY_ENTER, KEY_HELP, KEY_LEFT, KEY_Q,
    KEY_RIGHT, KEY_SPACE, MODEL_DIR, MOTOR_NAMES, SCENES, KeyReader, PhoneMapper, PhoneReader, Recorder,
    TcpController, action_to_motor_deg, make_logger, motor_deg_to_action,
)

log = make_logger("teleop_rebot_rs_real")

# ----------------------------------------------------------------------------- arm (values of the vendor driver)
MOTOR_CAN_IDS = (1, 2, 3, 4, 5, 6, 7)  # send IDs; feedback goes to the host ID
HOST_ID = 0xFD
MOTOR_MODELS = ("rs-06", "rs-06", "rs-06", "rs-00", "rs-00", "rs-00", "rs-00")
MIT_KP = (40.0, 120.0, 120.0, 40.0, 40.0, 40.0)  # arm joints, Nm/rad (vendor driver: 50, 150, 150, 50, 50, 50)
MIT_KD = (2.5, 8.0, 8.0, 4.0, 3.2, 3.2)  # Nm s/rad (vendor driver: 3, 10, 10, 5, 4, 4)
GRIPPER_KP, GRIPPER_KD, GRIPPER_TAU_MAX, GRIPPER_TAU_HOLD = 12.0, 0.05, 3.5, 1.0  # impedance in Python, torque command
MAX_JOINT_STEP_DEG = 2.0  # per control period (60 deg/s)
TARGET_FILTER_TAU = 0.1  # s, first-order filter on the joint targets sent to the motors (0 = off)
TEMP_WARN_C, TEMP_STOP_C = 115.0, 125.0
HOME_MOTOR_DEG = np.concatenate([np.degrees(HOME_QPOS), [0.0]])  # motor angle = MuJoCo joint angle
STAGE_SHOULDER = [1, 2]  # shoulder_lift, elbow_flex: raised first when leaving zero, lowered last when returning
STAGE_WRIST = [0, 3, 4, 5, 6]


class RebotArmRS:
    """The physical arm on the CAN bus: reads the 7 motor angles (deg) and sends MIT position targets (deg)."""

    def __init__(self, can: str | None, dm_serial: str | None) -> None:
        from motorbridge import Controller, Mode

        self.bus = Controller.from_dm_serial(dm_serial) if dm_serial else Controller(channel=can or "can0")
        self.motors = [self.bus.add_robstride_motor(mid, HOST_ID, model) for mid, model in zip(MOTOR_CAN_IDS, MOTOR_MODELS)]
        self.bus.disable_all()
        for name, m in zip(MOTOR_NAMES, self.motors):
            for attempt in range(10):
                try:
                    m.ensure_mode(Mode.MIT)
                    break
                except Exception as exc:  # the vendor driver retries the mode switch as well
                    if attempt == 9:
                        raise RuntimeError(f"motor {name} does not switch to MIT mode: {exc}") from exc
                    time.sleep(0.01)
        self.last_deg = np.zeros(7)
        self.temps = np.zeros(7)
        self._grip_prev_target = self._grip_prev_vel = self._grip_prev_pos = None
        self._grip_stall = 0

    def set_zero(self) -> None:
        """Torque off; the user puts the arm in its zero pose; the current position becomes zero for all motors."""
        self.bus.disable_all()
        input("Torque is off. Put the arm in its ZERO pose (folded, gripper closed), then press Enter ")
        for m in self.motors:
            m.set_zero_position()
            time.sleep(0.1)
        log.info("zero position set on all motors")

    def enable(self) -> None:
        self.bus.enable_all()

    def disable(self) -> None:
        self.bus.disable_all()

    def read(self) -> np.ndarray:
        """The 7 motor angles in degrees (observation.state); a motor without feedback keeps its last value."""
        for m in self.motors:
            m.request_feedback()
        try:
            self.bus.poll_feedback_once()
        except Exception as exc:
            log.warning("CAN feedback poll failed: %s", exc)
        states = [m.get_state() for m in self.motors]
        for k, st in enumerate(states):
            if st is not None:
                self.last_deg[k] = math.degrees(st.pos)
                self.temps[k] = st.t_mos
        return self.last_deg.copy()

    def send(self, motor_deg: np.ndarray) -> None:
        """MIT position targets for the six joints; impedance torque for the gripper (as the vendor driver)."""
        for k in range(6):
            self.motors[k].send_mit(math.radians(motor_deg[k]), 0.0, MIT_KP[k], MIT_KD[k], 0.0)
        st = self.motors[6].get_state()
        if st is None:
            return
        dt, target = 1.0 / CONTROL_HZ, math.radians(motor_deg[6])
        target_vel = 0.0 if self._grip_prev_target is None else (target - self._grip_prev_target) / dt
        if self._grip_prev_vel is not None:
            target_vel = 0.3 * target_vel + 0.7 * self._grip_prev_vel
        target_vel = max(-3.0, min(3.0, target_vel))
        state_vel = 0.0 if self._grip_prev_pos is None else (st.pos - self._grip_prev_pos) / dt
        self._grip_prev_target, self._grip_prev_vel, self._grip_prev_pos = target, target_vel, st.pos
        tau = GRIPPER_KP * (target - st.pos) + GRIPPER_KD * (target_vel - st.vel)
        stalled = abs(state_vel) < 0.25
        self._grip_stall = self._grip_stall + 1 if (target - st.pos > 0.05 and stalled) else 0
        if self._grip_stall >= 5:  # commanded to open but blocked: no torque against the stop
            tau = 0.0
        lim = GRIPPER_TAU_HOLD if stalled else GRIPPER_TAU_MAX
        self.motors[6].send_mit(0.0, 0.0, 0.0, 1.5, max(-lim, min(lim, tau)))

    def move_to(self, target_deg: np.ndarray, joints: list[int], seconds: float) -> None:
        """Move the listed joints to ``target_deg`` with a cosine profile; the others hold their position."""
        start = self.read()
        goal = start.copy()
        goal[joints] = target_deg[joints]
        n = max(1, int(seconds * CONTROL_HZ))
        for i in range(1, n + 1):
            s = 0.5 - 0.5 * math.cos(math.pi * i / n)
            self.send(start + s * (goal - start))
            self.read()
            time.sleep(1.0 / CONTROL_HZ)

    def close(self) -> None:
        for m in self.motors:
            try:
                m.disable()
                m.clear_error()
                m.close()
            except Exception:
                pass
        self.bus.close()


class CameraReader:
    """A USB camera read in a background thread (OpenCV); the latest frame is kept, resized to IMAGE_HW, RGB."""

    def __init__(self, name: str, index: int) -> None:
        import cv2

        self.cv2, self.name = cv2, name
        self.cap = cv2.VideoCapture(index)
        if not self.cap.isOpened():
            raise RuntimeError(f"camera {name}: index {index} does not open")
        self.frame = None
        self._lock, self._stop = threading.Lock(), threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            ok, img = self.cap.read()
            if ok:
                img = self.cv2.resize(img, (IMAGE_HW[1], IMAGE_HW[0]))
                with self._lock:
                    self.frame = self.cv2.cvtColor(img, self.cv2.COLOR_BGR2RGB)

    def get(self) -> np.ndarray | None:
        with self._lock:
            return None if self.frame is None else self.frame.copy()

    def close(self) -> None:
        self._stop.set()
        self.cap.release()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phone-ip", required=True, help="IP shown on the Data Streaming page of the asMagic app")
    ap.add_argument("--phone-port", type=int, default=8000)
    bus = ap.add_mutually_exclusive_group()
    bus.add_argument("--can", default="can0", help="SocketCAN interface (default can0)")
    bus.add_argument("--dm-serial", help="Damiao USB serial bridge instead of SocketCAN, e.g. /dev/ttyACM0")
    ap.add_argument("--set-zero", action="store_true", help="set the motor zero at the folded pose before starting (only if the Class 08 zero in Motorbridge Studio is missing)")
    ap.add_argument("--scale", type=float, default=1.0, help="metres of TCP per metre of phone motion")
    ap.add_argument("--filter-tau", type=float, default=TARGET_FILTER_TAU,
                    help=f"time constant (s) of the first-order filter on the joint targets, 0 = off (default {TARGET_FILTER_TAU})")
    ap.add_argument("--no-rotation", action="store_true", help="the gripper keeps its orientation; only the position follows the phone")
    ap.add_argument("--camera", action="append", default=[], metavar="NAME=INDEX", help="USB camera to record, e.g. front=0 (repeatable)")
    ap.add_argument("--out", default="recordings/real")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    if args.debug:
        log.setLevel("DEBUG")

    model = mujoco.MjModel.from_xml_path(str(MODEL_DIR / SCENES["table"]))  # kinematics only
    recorder = Recorder(Path(args.out), "real", "seeed_b601_rs_follower")
    cams = {}
    for spec in args.camera:
        name, idx = spec.split("=")
        cams[name] = CameraReader(name, int(idx))
    phone = PhoneReader(args.phone_ip, args.phone_port)
    mapper = PhoneMapper(args.scale, track_rotation=not args.no_rotation)
    log.info("connecting to the arm on %s", args.dm_serial or args.can)
    arm = RebotArmRS(None if args.dm_serial else args.can, args.dm_serial)
    keys = None
    try:
        if args.set_zero:
            arm.set_zero()
        arm.enable()
        start = arm.read()
        log.info("motor angles at start (deg): %s", np.round(start, 1).tolist())
        if np.any(np.abs(start[:6]) > 30.0):
            log.warning("the arm is not near its zero pose; it moves to the home pose from here in 6 s")
        log.info("moving to the home pose")
        arm.move_to(HOME_MOTOR_DEG, STAGE_SHOULDER, 3.0)
        arm.move_to(HOME_MOTOR_DEG, STAGE_WRIST, 3.0)
        q0 = np.radians(arm.read()[:6])
        ctrl = TcpController(model, q0)
        log.info("home pose reached; TCP (%.3f, %.3f, %.3f) m. %s", *ctrl.target, KEY_HELP)
        log.info("waiting for the phone stream on %s (AR Data on, same network); q = quit", phone.address)
        keys = KeyReader()
        teleop, gripper_m, stream_ok, last_report, motor_prev, run = False, 0.0, False, time.monotonic(), arm.read(), True
        motor_filt = motor_prev.copy()
        filt_keep = math.exp(-1.0 / (CONTROL_HZ * args.filter_tau)) if args.filter_tau > 0 else 0.0  # weight of the old value
        while run:
            tick = time.perf_counter()
            sample = phone.get()
            if (sample is not None) != stream_ok:
                stream_ok = sample is not None
                if stream_ok:
                    log.info("phone stream received (%.0f Hz, pose as %s)", phone.rate, phone.pose_format)
                else:
                    log.warning("phone stream lost: the arm holds its last target")
            for k in keys.get():
                if k == KEY_SPACE:
                    if teleop:
                        teleop = False
                        log.info("teleop paused; the arm holds its position")
                    elif sample is None:
                        log.warning("cannot start: no phone pose received")
                    else:
                        mapper.engage(sample[0], sample[1], ctrl.target, ctrl.rot)
                        teleop = True
                        log.info("teleop started at TCP (%.3f, %.3f, %.3f) m", *ctrl.target)
                elif k == KEY_RIGHT:
                    if recorder.active:
                        n = len(recorder.rows)
                        log.info("recording stopped: %s saved (%d frames)", recorder.save(), n)
                    else:
                        recorder.start()
                        log.info("recording started (episode_%03d)", recorder.n_saved)
                elif k == KEY_LEFT:
                    log.info("recording discarded (%d frames)", recorder.discard()) if recorder.active else log.info("no recording in progress")
                elif k == KEY_ENTER:
                    gripper_m = GRIPPER_STROKE if gripper_m < GRIPPER_STROKE / 2 else 0.0
                    log.info("gripper %s", "open" if gripper_m > 0 else "closed")
                elif k == KEY_Q:
                    run = False
            # ---- command path: phone -> TCP target -> joint target -> motor target (deg), rate-limited
            pos, rot = mapper.map(sample[0], sample[1]) if (teleop and sample is not None) else (None, None)
            q_cmd = ctrl.command(pos, rot)
            action = motor_deg_to_action(np.concatenate([np.degrees(q_cmd), [gripper_m / GRIPPER_STROKE * GRIPPER_MOTOR_MAX_DEG]]))
            motor_target = action_to_motor_deg(action)  # clipped to the soft limits
            motor_target = motor_prev + np.clip(motor_target - motor_prev, -MAX_JOINT_STEP_DEG, MAX_JOINT_STEP_DEG)
            motor_prev = motor_target
            # first-order filter on the six arm joints (the gripper keeps its own velocity handling in arm.send)
            motor_filt[:6] = filt_keep * motor_filt[:6] + (1.0 - filt_keep) * motor_target[:6]
            motor_filt[6] = motor_target[6]
            # ---- response path: observation, then the command
            state = arm.read()
            if recorder.active:
                recorder.add(state, action, {name: cam.get() for name, cam in cams.items()}, phone.age(), ctrl.blocked)
            arm.send(motor_filt)
            if arm.temps.max() > TEMP_STOP_C:
                log.error("motor temperature %.0f C over %.0f C: stopping", arm.temps.max(), TEMP_STOP_C)
                run = False
            now = time.monotonic()
            if now - last_report >= 5.0:
                last_report = now
                if arm.temps.max() > TEMP_WARN_C:
                    log.warning("motor temperature %.0f C", arm.temps.max())
                log.debug("phone %.0f Hz | teleop %s%s | recording %s (%d frames) | TCP (%.3f, %.3f, %.3f) m | tracking error %.1f deg",
                          phone.rate, "on" if teleop else "off", " (at the reach limit)" if ctrl.blocked else "",
                          "on" if recorder.active else "off", len(recorder.rows),
                          *ctrl.target, np.abs(state[:6] - motor_target[:6]).max())
            time.sleep(max(0.0, 1.0 / CONTROL_HZ - (time.perf_counter() - tick)))
    except KeyboardInterrupt:
        log.info("interrupted")
    finally:
        if keys is not None:
            keys.close()
        if recorder.active:
            log.info("stopped while recording: %s saved", recorder.save())
        try:
            log.info("returning to the zero pose")
            zero = np.zeros(7)
            arm.move_to(zero, STAGE_WRIST, 3.0)
            arm.move_to(zero, STAGE_SHOULDER, 3.0)
        except Exception as exc:
            log.error("return to zero failed: %s", exc)
        arm.disable()
        arm.close()
        phone.close()
        for cam in cams.values():
            cam.close()
        log.info("motors disabled; %d episode(s) in %s", recorder.n_saved, recorder.out)


if __name__ == "__main__":
    main()
