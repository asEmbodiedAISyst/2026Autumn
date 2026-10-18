"""Teleoperate the real reBot B601-RS with the pusher tool through asMagic, and record LeRobot datasets.

Real-robot counterpart of ``scripts/teleop.py --embodiment pusher --input asmagic``: same keys, same software
limits, same IK, same dataset format (``observation.images.phone`` + 9-D episode-frame tool pose); only the
arm and the camera are real. Two iPhones running asMagic are needed:

* the **controller** phone (``--phone-ip``), held by the operator -- ideally in the handheld print
  (``hand_tool.stl``), so that moving the handheld tool moves the robot tool the same way;
* the **camera** phone (``--camera-ip``), mounted on the robot tool (``robot_tool.stl``): its image is the
  policy observation, exactly like the handheld demonstrations.

Keys (in the MuJoCo window = digital twin of the measured arm, or typed in the terminal):

* ``Space``: engage / disengage. While disengaged the arm holds still and the phone can be repositioned;
* ``Right`` / ``r``: finish and save the episode;  ``Left`` / ``d``: discard it. The arm then returns to a new
  start pose;
* ``q``, closing the window or Ctrl+C: stop; the arm folds back to its zero pose and torque is disabled.

The terminal shows whether the controller phone (pose) and the robot camera phone (image) are connected, waits up
to 10 s for the controller phone after connecting, and prints a line on every change of the stream.

Test everything without hardware (simulated arm and phone camera, same code path)::

    uv run python -m rebot_sim.teleop.fake_phone --pattern circle --hold tool
    uv run python scripts/teleop_real.py --robot sim --phone-ip 127.0.0.1 --auto-engage

Real robot (after ``uv sync --group real``, CAN up and calibration done, see README.md)::

    uv run python scripts/teleop_real.py --robot real --can-port can0 \\
        --phone-ip 192.168.1.101 --camera-ip 192.168.1.102 \\
        --record --repo-id local/real_teleop_push_cube --root datasets/real_teleop_push_cube --num-episodes 50
"""

from __future__ import annotations

import argparse
import os
import queue
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the package root

if sys.platform.startswith("linux"):
    os.environ.setdefault("MUJOCO_GL", "egl")

import numpy as np  # noqa: E402

from rebot_sim.tasks import PushCubeTask, PushTTask  # noqa: E402

KEY_SPACE, KEY_RIGHT, KEY_LEFT, KEY_Q = 32, 262, 263, 81
TASK_DESCRIPTIONS = {"push_cube": PushCubeTask.description, "push_t": PushTTask.description}
KEY_HELP = "Keys (MuJoCo window or this terminal): Space engage/disengage | Right or r save | Left or d discard | q quit (zero pose, torque off)"


class TerminalKeys:
    """Keys typed in the terminal (cbreak mode, background thread) mapped to the viewer key codes.

    Lets Space / arrows / r / d / q work without giving the MuJoCo window the focus. Start it only after
    the last ``input()`` prompt; ``close()`` restores the terminal.
    """

    def __init__(self, out: queue.Queue) -> None:
        import threading

        self.out = out
        self._fd = None
        self._old = None
        if not sys.stdin.isatty():
            return
        import termios
        import tty

        self._fd = sys.stdin.fileno()
        self._old = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        import select

        buf = ""
        while not self._stop.is_set():
            if not select.select([sys.stdin], [], [], 0.1)[0]:
                buf = ""
                continue
            ch = sys.stdin.read(1)
            buf += ch
            if buf == "\x1b" or buf == "\x1b[":
                continue  # escape sequence in progress
            code = {" ": KEY_SPACE, "r": KEY_RIGHT, "d": KEY_LEFT, "q": KEY_Q, "\x1b[C": KEY_RIGHT, "\x1b[D": KEY_LEFT}.get(buf)
            buf = ""
            if code is not None:
                self.out.put(code)

    def close(self) -> None:
        if self._fd is not None:
            import termios

            self._stop.set()
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)


def phone_state(reader) -> str:
    """'ok 50Hz' when poses are arriving, otherwise 'NOT CONNECTED'."""
    return f"ok {reader.rate_hz:.0f}Hz" if reader.latest() is not None else "NOT CONNECTED"


def camera_state(camera) -> str:
    if camera.address == "none":
        return "none"
    return f"ok {camera.rate_hz:.0f}Hz" if camera.rate_hz > 0 else "NOT CONNECTED"


def wait_for_phone(reader, timeout: float = 10.0) -> bool:
    """Wait for the controller phone stream, printing progress once a second; returns True when it arrived."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if reader.latest() is not None:
            print(f"\rcontroller phone connected: {reader.address}, {reader.rate_hz:.0f} Hz".ljust(80))
            return True
        sys.stdout.write(f"\rwaiting for the pose of the controller phone {reader.address}... {time.monotonic() - t0:3.0f} s ({reader.frame_count} frames received)".ljust(80))
        sys.stdout.flush()
        time.sleep(0.25)
    print(f"\r! no pose from the controller phone {reader.address} within {timeout:.0f} s: check the phone IP, the network and that asMagic is on the AR Data page with streaming on."
          f" You can continue and press Space once it is connected.".ljust(80))
    return False


def pair(text: str) -> tuple[float, float]:
    """'0.10,0.65' -> (0.10, 0.65)."""
    a, b = (float(v) for v in text.split(","))
    if a >= b:
        raise argparse.ArgumentTypeError(f"the lower bound must be below the upper bound: {text!r}")
    return a, b


def add_robot_args(ap: argparse.ArgumentParser) -> None:
    """Arguments shared by the real-robot scripts."""
    ap.add_argument("--robot", choices=["real", "sim"], default="real", help="real: the physical arm; sim: the simulated arm (test)")
    ap.add_argument("--can-port", default="can0", help="SocketCAN interface")
    ap.add_argument("--robot-id", default="rebot_pusher", help="calibration id (first run scripts/real_check.py; do not use lerobot-calibrate, which expects 7 motors)")
    ap.add_argument("--camera-ip", default=None, help="IP of the phone on the robot tool (asMagic); not needed with --robot sim")
    ap.add_argument("--camera-port", type=int, default=8000)
    ap.add_argument("--no-camera", action="store_true", help="no phone on the robot (teleoperation test only; no valid recording)")
    ap.add_argument("--task", choices=["push_cube", "push_t"], default="push_cube")
    ap.add_argument("--action-mode", choices=["delta", "episode"], default="episode")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--max-speed", type=float, default=0.15, help="maximum speed of the rod tip, m/s (simulation data 0.25; start low on the physical arm)")
    ap.add_argument("--z-min", type=float, default=0.003, help="lowest height of the rod tip above the table, m")
    ap.add_argument("--start-z", type=float, default=None,
                    help="height of the rod tip above the table at the start of every episode, m (default 0.12 = simulation data). "
                         "The policy replays relative motion, so this must match the start height of the demonstrations: "
                         "use how far the lowest tip point is below the start in the recorded data (record_handheld.py prints it)")
    ap.add_argument("--start-x", type=float, default=None, help="distance of the rod tip in front of the base at the start of every episode, m (default 0.33)")
    ap.add_argument("--z-frame", choices=["start", "table"], default="start",
                    help="reference of z in the state and action: start = relative to the start height (original format); "
                         "table = height above the table (for a policy trained on data converted with "
                         "tools/anchor_z_to_table.py, or on data recorded with a table calibration)")
    ap.add_argument("--x-range", type=pair, default=(0.10, 0.65), metavar="X0,X1",
                    help="x range of the rod tip, m (in front of the base; simulation data 0.22,0.56); points inside the box that the IK cannot reach are refused and the arm holds")
    ap.add_argument("--y-range", type=pair, default=(-0.45, 0.45), metavar="Y0,Y1", help="y range of the rod tip, m (simulation data -0.20,0.20)")
    ap.add_argument("--z-max", type=float, default=0.30, help="highest rod tip, m (simulation data 0.20; above 0.30 only a small region is reachable)")
    ap.add_argument("--max-yaw", type=float, default=80.0, help="yaw limit of the tool, deg (simulation data 60)")
    ap.add_argument("--max-tilt", type=float, default=30.0, help="tilt limit of the rod, deg")
    ap.add_argument("--max-step-deg", type=float, default=3.0, help="largest change of a joint target per control period, deg (relative to the previous target; 3 = 90 deg/s)")
    ap.add_argument("--max-error-deg", type=float, default=10.0,
                    help="the driver clips the target to the measured position +- this value, deg: a torque cap kp x angle (10 deg = 21 N m at the shoulder and elbow); too small and the arm cannot lift")
    ap.add_argument("--kp-scale", type=float, default=0.8, help="MIT gain factor on the plugin defaults (0.8 = the verified 40/120/120/40/40/40)")
    ap.add_argument("--no-gravity", action="store_true", help="no gravity feedforward (default: from the pusher MuJoCo model; without it the tool sags about 4 deg at the soft gains)")
    ap.add_argument("--stream-hz", type=int, default=150,
                    help="rate at which the motor targets are sent, Hz: a background thread interpolates linearly between two 30 Hz targets (no knocking from steps); 0 = send directly from the control loop")
    ap.add_argument("--gravity-scale", type=float, default=1.0, help="gravity feedforward factor (above 1 when the tool is heavier than the model)")
    ap.add_argument("--filter-tau", type=float, default=0.1, help="time constant of the first-order filter on the joint targets, s (0 = off)")
    ap.add_argument("--start-speed", type=float, default=20.0, help="joint speed of the move to the start pose, deg/s")
    ap.add_argument("--no-start-noise", action="store_true", help="start every episode at the fixed start pose (default: a small random offset, as in simulation)")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation before the first motion")
    ap.add_argument("--no-viewer", action="store_true", help="no MuJoCo window (test; keys only from the terminal)")


def make_env(args):
    """Arm + camera backends and the real tool env (``--robot sim`` uses the MuJoCo arm and phone camera)."""
    from rebot_sim.real.arm import RealArm, SimArm
    from rebot_sim.real.camera import AsmagicCamera, NoCamera, SimCamera
    from rebot_sim.real.env import RealToolPushEnv
    from rebot_sim.tool_env import default_tool_limits, make_tool_task

    limits = default_tool_limits()
    limits.max_speed = args.max_speed
    limits.x, limits.y, limits.z = tuple(args.x_range), tuple(args.y_range), (args.z_min, args.z_max)
    limits.max_yaw_deg, limits.max_tilt_deg = args.max_yaw, args.max_tilt
    sim_task = None
    if args.robot == "sim":
        arm = SimArm(f"pusher_{args.task}", fps=args.fps)
        camera = SimCamera(arm)
        sim_task = make_tool_task(args.task)
    else:
        if not args.camera_ip and not args.no_camera:
            sys.exit("--robot real needs --camera-ip (the phone on the robot) or --no-camera (teleoperation test only)")
        arm = RealArm(args.can_port, args.robot_id, fps=args.fps, max_step_deg=args.max_step_deg,
                      kp_scale=args.kp_scale, filter_tau=args.filter_tau, max_error_deg=args.max_error_deg,
                      gravity_compensation=not args.no_gravity, gravity_scale=args.gravity_scale,
                      stream_hz=args.stream_hz)
        camera = NoCamera() if args.no_camera else AsmagicCamera(args.camera_ip, args.camera_port)
    from rebot_sim.tool_env import TOOL_START_POS

    start_pos = TOOL_START_POS.copy()
    if args.start_z is not None:
        start_pos[2] = args.start_z
    if args.start_x is not None:
        start_pos[0] = args.start_x
    env = RealToolPushEnv(arm, camera, TASK_DESCRIPTIONS[args.task], fps=args.fps, action_mode=args.action_mode,
                          limits=limits, start_noise=not args.no_start_noise, start_speed_deg_s=args.start_speed,
                          sim_task=sim_task, start_pos=start_pos, z_frame=args.z_frame)
    return env


def connect(env, args) -> None:
    if args.robot == "real" and not args.yes:
        input(f"The arm will be connected and move slowly to the start pose (rod tip about {env.start_pos[0] * 100:.0f} cm "
              f"in front of the base, {env.start_pos[2] * 100:.0f} cm high).\n"
              "Check: the emergency stop works, no hands or objects in the workspace, the phone is mounted. Enter continues, Ctrl+C cancels...")
    env.arm.connect()
    if args.robot == "sim":
        env.arm.sim.init_renderer()  # the EGL context must exist before the viewer opens
    if not env.camera.wait(5.0):
        print(f"! no image from the phone on the robot within 5 s ({env.camera.address}): check the IP and that the app is on the AR page")


def open_viewer(env, keys: queue.Queue | None, enabled: bool = True):
    """MuJoCo window: the simulated arm (``--robot sim``) or the kinematic twin of the real arm."""
    sim = env.arm.sim if hasattr(env.arm, "sim") else env.kin
    if not enabled:
        return None, sim
    import mujoco.viewer

    viewer = mujoco.viewer.launch_passive(sim.model, sim.data, key_callback=keys.put if keys else None,
                                          show_left_ui=False)
    viewer.cam.lookat[:] = (0.3, 0.0, 0.05)
    viewer.cam.distance, viewer.cam.azimuth, viewer.cam.elevation = 0.95, 180.0, -35.0
    return viewer, sim


class Status:
    def __init__(self) -> None:
        self._last = 0.0

    def show(self, text: str, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last > 0.25:
            sys.stdout.write("\r" + text.ljust(120))
            sys.stdout.flush()
            self._last = now


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_robot_args(ap)
    ap.add_argument("--phone-ip", required=True, help="IP of the phone in the hand of the operator (asMagic)")
    ap.add_argument("--phone-port", type=int, default=8000)
    ap.add_argument("--orientation", choices=["absolute", "relative"], default="absolute",
                    help="absolute: the tool tilt is the real tilt of the phone to gravity (only position and yaw are aligned at engage; use it for recording); "
                         "relative: the whole rotation is aligned at engage, the pose of the hand at Space is the neutral pose, no jump and no constant offset")
    ap.add_argument("--engage-blend", type=float, default=1.0, help="time over which the orientation blends from the arm pose to the phone pose after engage, s (0 = off)")
    ap.add_argument("--record", action="store_true", help="record a LeRobot dataset")
    ap.add_argument("--robot-type", default=None,
                    help="robot_type written to the dataset (default rebot_pusher_tool_<real|sim>); it must be the same as in record_handheld.py to merge the datasets")
    ap.add_argument("--repo-id", default="local/real_teleop")
    ap.add_argument("--root", default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--num-episodes", type=int, default=10)
    ap.add_argument("--episode-time-s", type=float, default=60.0, help="longest episode, s; a longer episode is discarded")
    ap.add_argument("--max-image-age", type=float, default=0.2, help="a frame whose image is older than this (s) counts as missing")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--auto-engage", action="store_true", help="test: engage at the start of every episode and save after 3 s")
    ap.add_argument("--max-duration-s", type=float, default=None, help="total run time limit, s (test)")
    ap.add_argument("--log-mapping", default=None, metavar="CSV",
                    help="write the raw controller phone pose, the mapped tip pose, the commanded pose and the measured pose of every frame to a CSV file (offline analysis of the mapping)")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    env = make_env(args)

    recorder = None
    if args.record and getattr(args, "no_camera", False):
        sys.exit("--record needs the camera on the robot (frames without an image are missing frames and the episode is discarded)")
    if args.record:  # create the recorder (imports torch) before the phone receiver threads start
        from rebot_sim.recording import DatasetRecorder, tool_feature_names

        recorder = DatasetRecorder(args.repo_id, args.fps, ("phone",), (480, 640), root=args.root, resume=args.resume,
                                   robot_type=args.robot_type or f"rebot_pusher_tool_{args.robot}",
                                   **tool_feature_names(args.action_mode))
        print(f"recording to {recorder.root} ({recorder.num_episodes} episodes so far)")

    from rebot_sim.teleop.phone import AsmagicPoseReader, RigidPhoneMapper

    reader = AsmagicPoseReader(args.phone_ip, args.phone_port)
    # The controller phone sits in the handheld print: map it to the rod tip with the same rigid transform
    mapper = RigidPhoneMapper.from_model(env.kin.model, smoothing=0.3, orientation=args.orientation,
                                         blend_s=args.engage_blend)
    print(f"controller phone: {reader.address}; robot camera: {env.camera.address}")

    maplog = None
    if args.log_mapping:
        from pathlib import Path

        Path(args.log_mapping).parent.mkdir(parents=True, exist_ok=True)
        maplog = open(args.log_mapping, "w")
        cols = ["t", "episode", "engaged", "phone_ok", "ik_ok", "lag_deg", "speed_factor", "phone_speed"]
        cols += [f"phone_{c}" for c in ("x", "y", "z", "rx", "ry", "rz")]  # raw ARKit pose (m, rotvec rad)
        cols += [f"map_{c}" for c in ("x", "y", "z", "rx", "ry", "rz")]  # mapped tool pose (robot frame)
        cols += [f"cmd_{c}" for c in ("x", "y", "z", "rx", "ry", "rz")]  # commanded (after limits / IK rejection)
        cols += [f"meas_{c}" for c in ("x", "y", "z", "rx", "ry", "rz")]  # measured robot TCP
        maplog.write(",".join(cols) + "\n")
        print(f"mapping log: {args.log_mapping}")

    last_phone = {"pos": None, "t": None}

    def log_mapping(episode: int, engaged: bool, phone, desired, info) -> None:
        from rebot_sim.pose import matrix_to_rotvec

        def pose6(p, R):
            return list(np.asarray(p, dtype=float)) + list(matrix_to_rotvec(np.asarray(R, dtype=float)))

        nan6 = [float("nan")] * 6
        now = time.monotonic()
        speed = float("nan")
        if phone is not None:
            if last_phone["pos"] is not None and now > last_phone["t"]:
                speed = float(np.linalg.norm(phone.pos - last_phone["pos"]) / (now - last_phone["t"]))  # hand speed (m/s)
            last_phone["pos"], last_phone["t"] = np.asarray(phone.pos, dtype=float).copy(), now
        p_meas, R_meas = env.kin.tcp_pose()
        row = [now, episode, int(engaged), int(phone is not None), int(info["ik_ok"]), info["lag_deg"], info["speed_factor"], speed]
        row += pose6(phone.pos, phone.rot) if phone is not None else nan6
        row += pose6(*desired) if engaged else nan6
        row += pose6(env.ctrl.target_pos, env.ctrl.target_rot)
        row += pose6(p_meas, R_meas)
        maplog.write(",".join(f"{v:.6f}" if isinstance(v, float) else str(v) for v in row) + "\n")

    keys: queue.Queue[int] = queue.Queue()
    viewer = None
    term_keys = None
    status = Status()
    saved, episode, t_start, quit_requested = 0, 0, time.monotonic(), False
    try:
        connect(env, args)
        phone_ok = wait_for_phone(reader, 10.0)
        print(f"robot camera: {camera_state(env.camera)} ({env.camera.address})")
        print(KEY_HELP)
        term_keys = TerminalKeys(keys)  # after the last input() prompt
        viewer, view_sim = open_viewer(env, keys, not args.no_viewer)
        mocap_id = view_sim.model.body("ee_target").mocapid[0]

        def running() -> bool:
            if quit_requested:
                return False
            if args.max_duration_s is not None and time.monotonic() - t_start > args.max_duration_s:
                return False
            return viewer.is_running() if viewer is not None else True

        while running() and saved < args.num_episodes:
            print(f"\nthe arm moves to the start pose...")
            obs, info = env.reset(seed=args.seed + episode)
            episode += 1
            mapper.disengage()
            engaged, frames, missing, end_reason, ep_t0 = False, 0, 0, None, None
            print(f"[episode {episode}] {env.task.description}  Place the objects, then press Space to engage (controller phone {phone_state(reader)})")
            while running() and end_reason is None:
                tick = time.perf_counter()
                want_engage = args.auto_engage and not engaged and ep_t0 is None
                while not keys.empty():
                    k = keys.get_nowait()
                    if k == KEY_SPACE:
                        if engaged:
                            engaged = False
                            mapper.disengage()
                            print("\ndisengaged: the arm holds; press Space to engage again")
                        else:
                            want_engage = True
                    elif k == KEY_RIGHT:
                        end_reason = "save"
                    elif k == KEY_LEFT:
                        end_reason = "discard"
                    elif k == KEY_Q:
                        end_reason, quit_requested = "quit", True
                phone = reader.latest()
                if (phone is not None) != phone_ok:  # persistent line on every change of the controller stream
                    phone_ok = phone is not None
                    print(f"\n{'controller phone connected' if phone_ok else '! controller phone stream lost'}: {reader.address} ({reader.rate_hz:.0f} Hz, {reader.frame_count} frames received)")
                if want_engage:
                    if phone is None:
                        print(f"\n! cannot engage: no pose from the controller phone {reader.address} ({reader.frame_count} frames received). "
                              "Check the phone IP, the network and that asMagic streams on the AR Data page, then press Space")
                    else:
                        mapper.engage(phone, env.ctrl.target_pos, env.ctrl.target_rot)
                        engaged = True
                        ep_t0 = ep_t0 or time.monotonic()
                        print(f"\nengaged: the motion of the hand tool = the motion of the robot tool (rod tip {np.round(env.ctrl.target_pos * 100, 1)} cm)")
                if engaged and phone is None:  # controller stream lost: hold still
                    engaged = False
                    mapper.disengage()
                    print("\n! controller phone stream lost: disengaged, the arm holds (press Space to engage again once connected)")

                desired = mapper.map(phone) if engaged else (env.ctrl.target_pos, env.ctrl.target_rot)
                obs_prev = obs
                obs, _, _, _, info = env.step(env.action_to(*desired))
                if maplog is not None:
                    log_mapping(episode, engaged, phone, desired, info)
                view_sim.data.mocap_pos[mocap_id] = env.ctrl.target_pos
                if viewer is not None:
                    viewer.sync()

                if ep_t0 is not None:
                    frames += 1
                    image = obs_prev["pixels"]["phone"]
                    if image is None or info["image_age"] > args.max_image_age:
                        missing += 1
                    if recorder is not None and image is not None:
                        recorder.add_frame(obs_prev["agent_pos"], info["applied_action"], {"phone": image},
                                           env.task.description)
                    if args.auto_engage and time.monotonic() - ep_t0 > 3.0:
                        end_reason = "save"
                    elif time.monotonic() - ep_t0 > args.episode_time_s:
                        end_reason = "timeout"
                p = env.ctrl.target_pos
                lag_txt = f" LAGGING x{info['speed_factor']:.1f}" if info.get("lagging") else ""
                status.show(
                    f"ep {episode} | {'ENGAGED' if engaged else 'disengaged'} | frames {frames} | tip {np.round(p * 100, 1)} cm"
                    f" | IK {'ok' if info['ik_ok'] else 'FAIL'}{lag_txt}"
                    f" | tracking joint {info['joint_err_deg']:.1f} deg rot {info['tcp_rot_err_deg']:.1f} deg pos {info['tcp_pos_err_mm']:.0f} mm"
                    f" | image age {info['image_age'] * 1000:.0f} ms | missing {missing}"
                    f" | controller {phone_state(reader)} | camera {camera_state(env.camera)} | saved {saved}/{args.num_episodes}"
                )
                dt = time.perf_counter() - tick
                if dt < 1.0 / args.fps:
                    time.sleep(1.0 / args.fps - dt)

            mapper.disengage()
            keep = end_reason == "save" and frames >= 10 and missing <= 0.05 * max(frames, 1)
            reason = end_reason or "stopped"
            if end_reason == "save" and not keep:
                reason = f"save, but too many missing frames ({missing}/{frames}) or too short"
            if recorder is not None:
                if keep and recorder.n_frames > 0:
                    recorder.save_episode()
                else:
                    recorder.discard_episode()
            saved += keep
            print(f"\n[episode {episode}] end: {reason}, {'saved' if keep else 'discarded'} ({frames} frames)")
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        if recorder is not None:
            recorder.finalize()
            print(f"dataset: {recorder.root}, {recorder.num_episodes} episodes")
        if term_keys is not None:
            term_keys.close()
        if maplog is not None:
            maplog.close()
        reader.close()
        print("the arm returns to its zero pose; torque off...")
        env.close()
        if viewer is not None:
            from rebot_sim.viewer_utils import close_viewer

            close_viewer(viewer)


if __name__ == "__main__":
    main()
