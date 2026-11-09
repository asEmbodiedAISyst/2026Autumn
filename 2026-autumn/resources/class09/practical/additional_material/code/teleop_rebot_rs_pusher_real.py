"""Teleoperate the physical reBot Arm B601-RS with the pusher tool through the asMagic app (Class 09).

The physical counterpart of ``teleop_rebot_rs_pusher_sim.py``: the same command path (phone -> rod-tip target ->
IK -> joint target), the same model and ``ee_tf_iphone``, workspace, start pose, keys and recording format. Only
the arm is different. It is driven as in ``teleop_rebot_rs_real.py`` (motorbridge, MIT mode, the same gains, step
limit, target filter and temperature limits), with three changes for the pusher tool:

* six motors: the gripper motor (ID 7) is removed together with the gripper;
* a torque cap: every joint target is kept within ``--max-error-deg`` of the measured angle, so the rod pressing on
  the table or the cube gives at most kp x max-error (10 deg: about 21 N m at the shoulder and the elbow, 7 N m at
  the wrist) instead of a growing force;
* the way back: from the teleoperation pose the arm first returns to the start pose (rod vertical, tip 10 cm above
  the table), then to the folded zero pose by the reverse of the start path (base and wrist first, then shoulder and
  elbow).

There is no gravity feedforward, as in ``teleop_rebot_rs_real.py``: at these gains the rod and the phone make the
arm sag by a few degrees; the operator closes the loop.

SAFETY RULES. READ THEM BEFORE YOU RUN THE SCRIPT.
  * The arm must have passed the power-on of Class 08 with the pusher tool mounted (zero in Motorbridge Studio).
  * One person keeps control of the power switch at all times and can cut the power without delay.
  * Nobody stays inside the workspace of the arm while the motors are enabled; hold the phone outside its reach.
  * Start with the arm in the folded zero pose and the rod clear of the table and of the cube.
  * Normal stop: press q (or Ctrl-C). The arm returns to the start pose and then to the zero pose, wrist first,
    then the motors are disabled. Wait for the log line "motors disabled" before you touch the arm.
  * The power switch is the emergency stop only; after it the arm falls to its mechanical stops.

    uv sync --extra real                                              # motor SDK (one time)
    sudo ip link set can0 up type can bitrate 1000000                 # SocketCAN adapter (one time per boot)
    uv run python code/teleop_rebot_rs_pusher_real.py --phone-ip 192.168.1.100 --can can0
    uv run python code/teleop_rebot_rs_pusher_real.py --phone-ip 192.168.1.100 --can can0 --scale 0.5   # first run
    uv run python code/teleop_rebot_rs_pusher_real.py --phone-ip 192.168.1.100 --can can0 --camera front=0

Hold the phone as it sits on the tool, ideally in the handheld print: in landscape, the back camera looking forward
and down at the table. Press Space: from then on the motion of the phone is the motion of the tool.

Keys (in the terminal):
    Space       start / pause the teleoperation (the phone pose and the tool pose are the references at every start)
    Right / r   start recording; press again to stop and save the episode
    Left / d    discard the recording in progress
    q           quit (start pose, zero pose, disable the motors)

Recording: as ``teleop_rebot_rs_pusher_sim.py``, six joints (no gripper); images only from the USB cameras given
with ``--camera``.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from teleop_common import (  # noqa: E402
    CONTROL_HZ, KEY_ENTER, KEY_LEFT, KEY_Q, KEY_RIGHT, KEY_SPACE, MODEL_DIR, SOFT_LIMITS_DEG, KeyReader, PhoneMapper,
    PhoneReader, Recorder, TcpController, make_logger,
)
from teleop_rebot_rs_pusher_sim import (  # noqa: E402
    PUSHER_DIRECTIONS, PUSHER_HOME_QPOS, PUSHER_MOTORS, PUSHER_WORKSPACE, SCENE, ee_tf_iphone_from_model,
)
from teleop_rebot_rs_real import (  # noqa: E402
    HOST_ID, MAX_JOINT_STEP_DEG, MIT_KD, MIT_KP, MOTOR_CAN_IDS, MOTOR_MODELS, TARGET_FILTER_TAU, TEMP_STOP_C,
    TEMP_WARN_C, CameraReader, RebotArmRS,
)

log = make_logger("teleop_rebot_rs_pusher_real")

N_JOINTS = 6
MAX_ERROR_DEG = 10.0  # torque cap: largest distance between a joint target and the measured angle (deg)
PUSHER_HOME_MOTOR_DEG = np.degrees(PUSHER_HOME_QPOS)  # motor angle = MuJoCo joint angle for the six arm joints
PUSHER_SOFT_LIMITS_DEG = SOFT_LIMITS_DEG[:N_JOINTS]
STAGE_SHOULDER = [1, 2]  # shoulder_lift, elbow_flex: raised first when leaving zero, lowered last when returning
STAGE_WRIST = [0, 3, 4, 5]
KEY_HELP = "keys: Space = start/pause teleop, Right = start/stop+save recording, Left = discard recording, q = quit"


class PusherArmRS(RebotArmRS):
    """The physical arm with the pusher tool: the six arm motors of :class:`RebotArmRS`, no gripper motor.

    ``send`` keeps every target within ``max_error_deg`` of the angle measured by the last ``read`` (torque cap).
    """

    def __init__(self, can: str | None, dm_serial: str | None, max_error_deg: float = MAX_ERROR_DEG) -> None:
        from motorbridge import Controller, Mode

        if max_error_deg <= 0:
            raise ValueError("max_error_deg must be positive")
        self.max_error_deg = max_error_deg
        self.bus = Controller.from_dm_serial(dm_serial) if dm_serial else Controller(channel=can or "can0")
        self.motors = [self.bus.add_robstride_motor(mid, HOST_ID, model)
                       for mid, model in zip(MOTOR_CAN_IDS[:N_JOINTS], MOTOR_MODELS[:N_JOINTS])]
        self.bus.disable_all()
        for name, m in zip(PUSHER_MOTORS, self.motors):
            for attempt in range(10):
                try:
                    m.ensure_mode(Mode.MIT)
                    break
                except Exception as exc:  # the vendor driver retries the mode switch as well
                    if attempt == 9:
                        raise RuntimeError(f"motor {name} does not switch to MIT mode: {exc}") from exc
                    time.sleep(0.01)
        self.last_deg = np.zeros(N_JOINTS)
        self.temps = np.zeros(N_JOINTS)

    def set_zero(self) -> None:
        """Torque off; the user puts the arm in its zero pose; the current position becomes zero for all motors."""
        self.bus.disable_all()
        input("Torque is off. Put the arm in its ZERO pose (folded, rod clear of the table), then press Enter ")
        for m in self.motors:
            m.set_zero_position()
            time.sleep(0.1)
        log.info("zero position set on the six motors")

    def missing_feedback(self) -> list[str]:
        """Names of the motors that have not answered yet."""
        return [name for name, m in zip(PUSHER_MOTORS, self.motors) if m.get_state() is None]

    def send(self, motor_deg: np.ndarray) -> None:
        """MIT position targets for the six joints, each within max_error_deg of its measured angle."""
        for k in range(N_JOINTS):
            target = float(motor_deg[k])
            st = self.motors[k].get_state()
            if st is not None:
                meas = math.degrees(st.pos)
                target = meas + max(-self.max_error_deg, min(self.max_error_deg, target - meas))
            self.motors[k].send_mit(math.radians(target), 0.0, MIT_KP[k], MIT_KD[k], 0.0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phone-ip", required=True, help="IP shown on the Data Streaming page of the asMagic app")
    ap.add_argument("--phone-port", type=int, default=8000, help="AR data port of the app (default 8000)")
    bus = ap.add_mutually_exclusive_group()
    bus.add_argument("--can", default="can0", help="SocketCAN interface (default can0)")
    bus.add_argument("--dm-serial", help="Damiao USB serial bridge instead of SocketCAN, e.g. /dev/ttyACM0")
    ap.add_argument("--set-zero", action="store_true", help="set the motor zero at the folded pose before starting (only if the Class 08 zero in Motorbridge Studio is missing)")
    ap.add_argument("--scale", type=float, default=1.0, help="metres of tool motion per metre of phone motion")
    ap.add_argument("--no-rotation", action="store_true", help="the tool keeps its orientation; only the position follows the phone")
    ap.add_argument("--filter-tau", type=float, default=TARGET_FILTER_TAU,
                    help=f"time constant (s) of the first-order filter on the joint targets, 0 = off (default {TARGET_FILTER_TAU})")
    ap.add_argument("--max-error-deg", type=float, default=MAX_ERROR_DEG,
                    help=f"torque cap: a joint target stays within this angle of the measured angle (default {MAX_ERROR_DEG} deg)")
    ap.add_argument("--camera", action="append", default=[], metavar="NAME=INDEX", help="USB camera to record, e.g. front=0 (repeatable)")
    ap.add_argument("--out", default="recordings/pusher_real", help="folder of the recorded episodes")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation before the first motion")
    ap.add_argument("--debug", action="store_true", help="log the state every 5 s")
    args = ap.parse_args()
    if args.debug:
        log.setLevel("DEBUG")
    if args.scale <= 0 or args.filter_tau < 0 or args.max_error_deg <= 0:
        ap.error("--scale and --max-error-deg must be positive, --filter-tau must not be negative")

    model = mujoco.MjModel.from_xml_path(str(MODEL_DIR / SCENE))  # kinematics only
    ee_R_iphone, ee_p_iphone = ee_tf_iphone_from_model(model)
    recorder = Recorder(Path(args.out), "pusher_cube", "seeed_b601_rs_pusher", PUSHER_MOTORS, PUSHER_DIRECTIONS)
    cams = {}
    for spec in args.camera:
        name, idx = spec.split("=")
        cams[name] = CameraReader(name, int(idx))
    phone = PhoneReader(args.phone_ip, args.phone_port)
    mapper = PhoneMapper(args.scale, track_rotation=not args.no_rotation, ee_R_iphone=ee_R_iphone, ee_p_iphone=ee_p_iphone)
    log.info("pusher tool: phone at (%.3f, %.3f, %.3f) m in the rod-tip frame", *ee_p_iphone)
    if not args.yes:
        input("The motors will be enabled and the arm moves slowly to the start pose (rod vertical, tip 22 cm in front "
              "of the base, 10 cm high).\nCheck: the power switch is within reach, nobody in the workspace, the rod "
              "is clear of the table and the cube. Enter continues, Ctrl-C cancels... ")
    log.info("connecting to the arm on %s", args.dm_serial or args.can)
    arm = PusherArmRS(None if args.dm_serial else args.can, args.dm_serial, args.max_error_deg)
    keys = None
    moved = False  # the angles were checked and the arm left its start pose: return it before the torque goes off
    try:
        if args.set_zero:
            arm.set_zero()
        arm.enable()
        start = arm.read()
        start = arm.read()  # the first read can come before every reply
        missing = arm.missing_feedback()
        if missing:  # unknown angles: never move, only disable (finally)
            raise RuntimeError(f"no feedback from {', '.join(missing)}: check the power, the CAN cable and the motor IDs")
        log.info("motor angles at start (deg): %s", np.round(start, 1).tolist())
        moved = True
        if np.any(np.abs(start) > 30.0):
            log.warning("the arm is not near its zero pose; it moves to the start pose from here in 6 s")
        log.info("moving to the start pose")
        arm.move_to(PUSHER_HOME_MOTOR_DEG, STAGE_SHOULDER, 3.0)
        arm.move_to(PUSHER_HOME_MOTOR_DEG, STAGE_WRIST, 3.0)
        q0 = np.radians(arm.read())
        ctrl = TcpController(model, q0, workspace=PUSHER_WORKSPACE, home=PUSHER_HOME_QPOS)
        log.info("start pose reached; rod tip (%.3f, %.3f, %.3f) m. %s", *ctrl.target, KEY_HELP)
        log.info("waiting for the phone stream on %s (AR Data on, same network); episodes go to %s", phone.address, recorder.out)
        keys = KeyReader()
        teleop, stream_ok, last_report, run = False, False, time.monotonic(), True
        motor_prev = arm.read()
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
                    log.warning("phone stream lost: the arm holds its last target (check Wi-Fi and the AR Data switch)")
            for k in keys.get():
                if k == KEY_SPACE:
                    if teleop:
                        teleop = False
                        log.info("teleop paused; the arm holds its position")
                    elif sample is None:
                        log.warning("cannot start: no phone pose received (check the IP, the network and the AR Data switch)")
                    else:
                        mapper.engage(sample[0], sample[1], ctrl.target, ctrl.rot)
                        teleop = True
                        log.info("teleop started at rod tip (%.3f, %.3f, %.3f) m; the tool now follows the phone", *ctrl.target)
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
                    log.info("the pusher tool has no gripper")
                elif k == KEY_Q:
                    run = False
            # ---- command path: phone -> rod-tip target -> joint target -> motor target (deg), rate-limited
            pos, rot = mapper.map(sample[0], sample[1]) if (teleop and sample is not None) else (None, None)
            q_cmd = ctrl.command(pos, rot)
            action = np.degrees(q_cmd) / PUSHER_DIRECTIONS
            motor_target = np.clip(action * PUSHER_DIRECTIONS, PUSHER_SOFT_LIMITS_DEG[:, 0], PUSHER_SOFT_LIMITS_DEG[:, 1])
            motor_target = motor_prev + np.clip(motor_target - motor_prev, -MAX_JOINT_STEP_DEG, MAX_JOINT_STEP_DEG)
            motor_prev = motor_target
            motor_filt = filt_keep * motor_filt + (1.0 - filt_keep) * motor_target
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
                log.debug("phone %.0f Hz | teleop %s%s | recording %s (%d frames) | rod tip (%.3f, %.3f, %.3f) m | tracking error %.1f deg",
                          phone.rate, "on" if teleop else "off", " (at the reach limit)" if ctrl.blocked else "",
                          "on" if recorder.active else "off", len(recorder.rows),
                          *ctrl.target, np.abs(state - motor_target).max())
            time.sleep(max(0.0, 1.0 / CONTROL_HZ - (time.perf_counter() - tick)))
    except KeyboardInterrupt:
        log.info("interrupted")
    except Exception as exc:
        log.error("stopping: %s: %s", type(exc).__name__, exc)
    finally:
        if keys is not None:
            keys.close()
        if recorder.active:
            log.info("stopped while recording: %s saved", recorder.save())
        if moved:
            try:
                log.info("returning to the start pose, then to the zero pose")
                arm.move_to(PUSHER_HOME_MOTOR_DEG, list(range(N_JOINTS)), 3.0)
                zero = np.zeros(N_JOINTS)
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
