"""Teleoperate the simulated reBot Arm B601-RS with the pusher tool instead of the gripper (Class 09).

The same teleoperation as ``teleop_rebot_rs_sim.py``, with another end effector: a printed rod with the iPhone on
it (the tool of Classes 10 and 11). The phone is mounted on the tool, so the tool moves with the phone as one rigid
body: a motion of the phone moves the pusher tip the same way, and a rotation of the phone swings the pusher tip about
the phone, as with the printed tool in your hand. The end effector frame is the ``tcp`` site at the pusher tip; the
transform between the phone and the pusher tip, ``ee_tf_iphone``, is read from the ``phone`` camera of the model.
Changing the end effector changes three things only: the model, the start pose and ``ee_tf_iphone``.

    uv run python code/teleop_rebot_rs_pusher_sim.py --phone-ip 192.168.1.100               # Ubuntu
    uv run mjpython code/teleop_rebot_rs_pusher_sim.py --phone-ip 192.168.1.100             # macOS
    uv run python code/teleop_rebot_rs_pusher_sim.py --phone-ip 127.0.0.1    # with fake_phone.py in another terminal

Hold the phone as it sits on the tool: in landscape, the back camera looking forward and down at the table.
Press Space: from then on the motion of the phone is the motion of the tool.

Keys (viewer window focused):
    Space       start / pause the teleoperation. At every start the current phone pose and the current tool
                pose become the references of the mapping.
    Right arrow start recording; press again to stop and save the episode.
    Left arrow  discard the recording in progress.
Close the window to quit.

Recording: as ``teleop_rebot_rs_sim.py``, with six joints (no gripper) and three images per frame: ``front/``,
``side/`` and ``phone/`` (the camera of the phone on the tool).
"""

from __future__ import annotations

import argparse
import queue
import sys
import time
from pathlib import Path

import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from teleop_common import (  # noqa: E402
    ARM_JOINTS, CONTROL_HZ, DIRECTIONS, IMAGE_HW, KEY_ENTER, KEY_LEFT, KEY_RIGHT, KEY_SPACE, MODEL_DIR, MOTOR_NAMES,
    PhoneMapper, PhoneReader, Recorder, TcpController, make_logger,
)

log = make_logger("teleop_rebot_rs_pusher_sim")

SCENE = "scene_pusher_cube.xml"
# Start pose: the rod vertical, its tip at (0.22, 0, 0.10) m (the home pose of the pusher in Classes 10 and 11)
PUSHER_HOME_QPOS = np.array([0.0, 0.349, 0.5, -0.677, 0.0, 0.0])
# Box of the rod tip (m): low enough to push the 40 mm cube; the rod tip has no fingers below it
PUSHER_WORKSPACE = np.array([[0.15, 0.50], [-0.25, 0.25], [0.005, 0.25]])
PUSHER_MOTORS = MOTOR_NAMES[:6]
PUSHER_DIRECTIONS = DIRECTIONS[:6]
CAMERAS = ("front", "side", "phone")
KEY_HELP = "keys: Space = start/pause teleop, Right = start/stop+save recording, Left = discard recording"


def ee_tf_iphone_from_model(model: mujoco.MjModel) -> tuple[np.ndarray, np.ndarray]:
    """Rotation and position of the phone camera frame in the ``tcp`` frame (a fixed part of the tool).

    The MuJoCo camera frame (x right, y up in the image, looking along -z) is the ARKit frame of the phone held in
    landscape, so the camera ``phone`` of the model is the iPhone frame of the asMagic pose.
    """
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    R_tcp, R_cam = data.site("tcp").xmat.reshape(3, 3), data.cam("phone").xmat.reshape(3, 3)
    return R_tcp.T @ R_cam, R_tcp.T @ (data.cam("phone").xpos - data.site("tcp").xpos)


class PusherSim:
    """The pusher scene stepped at the control rate; renders the ``front``, ``side`` and ``phone`` cameras."""

    def __init__(self) -> None:
        self.model = mujoco.MjModel.from_xml_path(str(MODEL_DIR / SCENE))
        self.data = mujoco.MjData(self.model)
        self.n_sub = round(1.0 / CONTROL_HZ / self.model.opt.timestep)
        self.model.opt.timestep = 1.0 / (CONTROL_HZ * self.n_sub)  # control period exactly 1/30 s
        self.qadr = np.array([self.model.jnt_qposadr[self.model.joint(j).id] for j in ARM_JOINTS])
        self.act = np.array([self.model.actuator(j).id for j in ARM_JOINTS])
        self.tcp = self.model.site("tcp").id
        self.renderer = mujoco.Renderer(self.model, height=IMAGE_HW[0], width=IMAGE_HW[1])
        self.vis = mujoco.MjvOption()
        for g in (1, 3, 4, 5):  # markers and collision geoms are not in the recorded images
            self.vis.geomgroup[g] = 0
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = PUSHER_HOME_QPOS
        self.data.ctrl[self.act] = PUSHER_HOME_QPOS
        mujoco.mj_forward(self.model, self.data)
        for _ in range(5):
            self.step()

    def command(self, q: np.ndarray) -> None:
        self.data.ctrl[self.act] = q

    def step(self) -> None:
        mujoco.mj_step(self.model, self.data, nstep=self.n_sub)

    def state_deg(self) -> np.ndarray:
        """The 6 motor angles in degrees, as observation.state of the physical arm."""
        return np.degrees(self.data.qpos[self.qadr])

    def tcp_pos(self) -> np.ndarray:
        return self.data.site_xpos[self.tcp].copy()

    def render(self, cam: str) -> np.ndarray:
        self.renderer.update_scene(self.data, camera=cam, scene_option=self.vis)
        return self.renderer.render().copy()


class Headless:
    """Stands in for the viewer handle in --no-viewer mode (tests without a window)."""

    def __init__(self, seconds: float) -> None:
        self.t_end = time.monotonic() + seconds

    def is_running(self) -> bool:
        return time.monotonic() < self.t_end

    def sync(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phone-ip", required=True, help="IP shown on the Data Streaming page of the asMagic app")
    ap.add_argument("--phone-port", type=int, default=8000, help="AR data port of the app (default 8000)")
    ap.add_argument("--scale", type=float, default=1.0, help="metres of phone motion on the robot per metre of phone motion in the hand")
    ap.add_argument("--no-rotation", action="store_true", help="the tool keeps its orientation; only the position follows the phone")
    ap.add_argument("--out", default="recordings/pusher", help="folder of the recorded episodes")
    ap.add_argument("--no-viewer", action="store_true", help="no window: teleop and recording start at once, stop after --duration")
    ap.add_argument("--duration", type=float, default=10.0, help="seconds to run with --no-viewer")
    ap.add_argument("--debug", action="store_true", help="log the state every 5 s")
    args = ap.parse_args()
    if args.debug:
        log.setLevel("DEBUG")

    sim = PusherSim()
    ee_R_iphone, ee_p_iphone = ee_tf_iphone_from_model(sim.model)
    ctrl = TcpController(sim.model, PUSHER_HOME_QPOS, workspace=PUSHER_WORKSPACE, home=PUSHER_HOME_QPOS)
    recorder = Recorder(Path(args.out), "pusher_cube", "seeed_b601_rs_pusher_sim", PUSHER_MOTORS, PUSHER_DIRECTIONS)
    phone = PhoneReader(args.phone_ip, args.phone_port)
    mapper = PhoneMapper(args.scale, track_rotation=not args.no_rotation, ee_R_iphone=ee_R_iphone, ee_p_iphone=ee_p_iphone)
    log.info("pusher tool: phone at (%.3f, %.3f, %.3f) m in the pusher-tip frame; listening to %s; episodes go to %s",
             *ee_p_iphone, phone.address, recorder.out)
    log.info(KEY_HELP)
    keys: queue.Queue[int] = queue.Queue()

    if args.no_viewer:
        v_ctx = Headless(args.duration)
    else:
        from mujoco import viewer

        v_ctx = viewer.launch_passive(sim.model, sim.data, key_callback=keys.put)
    teleop, stream_ok, last_report = False, False, time.monotonic()
    log.info("waiting for the phone stream (AR Data on, same network)")
    with v_ctx as v:
        if not args.no_viewer:
            v.opt.geomgroup[3] = 0
            v.cam.lookat[:] = (0.3, 0.0, 0.05)
            v.cam.distance, v.cam.azimuth, v.cam.elevation = 1.0, -30.0, -45.0  # from behind the arm, to its right
        while v.is_running():
            tick = time.perf_counter()
            sample = phone.get()
            if (sample is not None) != stream_ok:  # stream state changed
                stream_ok = sample is not None
                if stream_ok:
                    log.info("phone stream received (pose as %s)", phone.pose_format)
                else:
                    log.warning("phone stream lost: the arm holds its last target (check Wi-Fi and the AR Data switch)")
            if args.no_viewer and sample is not None and not teleop:
                keys.put(KEY_SPACE)  # headless test: start the teleoperation and the recording at once
                keys.put(KEY_RIGHT)
            # ---- keys from the viewer thread
            while not keys.empty():
                k = keys.get_nowait()
                if k == KEY_SPACE:
                    if teleop:
                        teleop = False
                        log.info("teleop paused; the arm holds its position")
                    elif sample is None:
                        log.warning("cannot start: no phone pose received (check the IP, the network and the AR Data switch)")
                    else:
                        mapper.engage(sample[0], sample[1], ctrl.target, ctrl.rot)
                        teleop = True
                        log.info("teleop started at pusher tip (%.3f, %.3f, %.3f) m; the tool now follows the phone", *ctrl.target)
                elif k == KEY_RIGHT:
                    if recorder.active:
                        n = len(recorder.rows)
                        log.info("recording stopped: %s saved (%d frames)", recorder.save(), n)
                    else:
                        recorder.start()
                        log.info("recording started (episode_%03d)", recorder.n_saved)
                elif k == KEY_LEFT:
                    if recorder.active:
                        log.info("recording discarded (%d frames)", recorder.discard())
                    else:
                        log.info("no recording in progress")
                elif k == KEY_ENTER:
                    log.info("the pusher tool has no gripper")
            # ---- command path: phone -> rod-tip target -> joint target (rad)
            pos, rot = mapper.map(sample[0], sample[1]) if (teleop and sample is not None) else (None, None)
            q_cmd = ctrl.command(pos, rot)
            action = np.degrees(q_cmd) / PUSHER_DIRECTIONS
            # ---- response path: observation before the step, then the step
            state = sim.state_deg()
            if recorder.active:
                recorder.add(state, action, {cam: sim.render(cam) for cam in CAMERAS}, phone.age(), ctrl.blocked)
            sim.command(q_cmd)
            sim.step()
            v.sync()
            now = time.monotonic()
            if now - last_report >= 5.0:
                last_report = now
                log.debug("phone %.0f Hz | teleop %s%s | recording %s (%d frames) | pusher tip (%.3f, %.3f, %.3f) m",
                          phone.rate, "on" if teleop else "off", " (at the reach limit)" if ctrl.blocked else "",
                          "on" if recorder.active else "off", len(recorder.rows), *sim.tcp_pos())
            time.sleep(max(0.0, 1.0 / CONTROL_HZ - (time.perf_counter() - tick)))
    if recorder.active:
        ep = recorder.save()
        log.info("window closed while recording: %s saved", ep)
    phone.close()
    log.info("done: %d episode(s) in %s", recorder.n_saved, recorder.out)


if __name__ == "__main__":
    main()
