"""Teleoperate the simulated reBot Arm B601-RS with the asMagic app and record episodes (Class 09).

The arm and the table are the Class 08 model; ``--scene cube`` adds the black 40 mm cube. The iPhone runs the
asMagic app with the AR data stream on (Data Streaming page). The app publishes its ARKit pose over the network;
this script receives it and moves the gripper like the phone: a motion along the camera direction of the phone
moves the gripper along the direction it points at, a motion towards the top of the phone moves it along the
open/close direction of the fingers, a motion towards the right side of the phone moves it sideways, and a
rotation of the phone rotates the gripper the same way. The tool-centre-point (TCP) target is clipped to the
workspace and speed-limited, and inverse kinematics gives the six joint targets, 30 times per second. The recorder writes the same channels as the LeRobot driver of the physical arm.

    uv run python code/teleop_rebot_rs_sim.py --phone-ip 192.168.1.100                      # Ubuntu
    uv run mjpython code/teleop_rebot_rs_sim.py --phone-ip 192.168.1.100                    # macOS
    uv run python code/teleop_rebot_rs_sim.py --phone-ip 192.168.1.100 --scene cube --out recordings/cube
    uv run python code/teleop_rebot_rs_sim.py --phone-ip 127.0.0.1    # with fake_phone.py in another terminal

Keys (viewer window focused):
    Space       start / pause the teleoperation. At every start the current phone pose and the current gripper
                pose become the references of the mapping.
    Right arrow start recording; press again to stop and save the episode.
    Left arrow  discard the recording in progress.
    Enter       open / close the gripper.
Close the window to quit.

Recording: one folder per saved episode under --out, ``episode_000/`` with ``meta.json``, ``frames.csv``
(frame_index, timestamp since the start, 7 state values, 7 action values, phone_age, blocked) and the images
``front/000000.jpg``, ``side/000000.jpg``.
``observation.state`` = motor angles in degrees; ``action`` = joint target in command space (motor target divided
by the direction vector [1, 1, -1, -1, -1, 1, 6]).
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
    ARM_JOINTS, CONTROL_HZ, GRIPPER_MOTOR_MAX_DEG, GRIPPER_STROKE, HOME_QPOS, IMAGE_HW, KEY_ENTER, KEY_HELP,
    KEY_LEFT, KEY_RIGHT, KEY_SPACE, MODEL_DIR, SCENES, PhoneMapper, PhoneReader, Recorder, TcpController,
    make_logger, motor_deg_to_action,
)

log = make_logger("teleop_rebot_rs_sim")


class ArmSim:
    """The scene stepped at the control rate; renders the ``front`` and ``side`` cameras for the recorder."""

    def __init__(self, scene: str) -> None:
        self.model = mujoco.MjModel.from_xml_path(str(MODEL_DIR / SCENES[scene]))
        self.data = mujoco.MjData(self.model)
        self.n_sub = round(1.0 / CONTROL_HZ / self.model.opt.timestep)
        # Match the exact 30Hz control period, as in the pusher simulation.
        self.model.opt.timestep = 1.0 / (CONTROL_HZ * self.n_sub)
        self.qadr = np.array([self.model.jnt_qposadr[self.model.joint(j).id] for j in ARM_JOINTS])
        self.act = np.array([self.model.actuator(j).id for j in ARM_JOINTS])
        self.grip_act = self.model.actuator("gripper").id
        self.finger_qadr = np.array([self.model.jnt_qposadr[self.model.joint(j).id] for j in ("gripper_joint1", "gripper_joint2")])
        self.tcp = self.model.site("tcp").id
        self.renderer = mujoco.Renderer(self.model, height=IMAGE_HW[0], width=IMAGE_HW[1])
        self.vis = mujoco.MjvOption()
        for g in (1, 3, 4, 5):  # markers and collision geoms are not in the recorded images
            self.vis.geomgroup[g] = 0
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = HOME_QPOS
        self.data.ctrl[self.act] = HOME_QPOS
        self.data.ctrl[self.grip_act] = 0.0
        mujoco.mj_forward(self.model, self.data)
        for _ in range(5):
            self.step()

    def command(self, q: np.ndarray, gripper_m: float) -> None:
        self.data.ctrl[self.act] = q
        self.data.ctrl[self.grip_act] = float(np.clip(gripper_m, 0.0, GRIPPER_STROKE))

    def step(self) -> None:
        mujoco.mj_step(self.model, self.data, nstep=self.n_sub)

    def state_deg(self) -> np.ndarray:
        """The 7 motor angles in degrees, as observation.state of the physical arm."""
        grip = float(self.data.qpos[self.finger_qadr].mean()) / GRIPPER_STROKE * GRIPPER_MOTOR_MAX_DEG
        return np.concatenate([np.degrees(self.data.qpos[self.qadr]), [grip]])

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
    ap.add_argument("--scene", choices=list(SCENES), default="cube")
    ap.add_argument("--scale", type=float, default=1.0, help="metres of TCP per metre of phone motion")
    ap.add_argument("--no-rotation", action="store_true", help="the gripper keeps its orientation; only the position follows the phone")
    ap.add_argument("--out", default="recordings/sim", help="folder of the recorded episodes")
    ap.add_argument("--no-viewer", action="store_true", help="no window: teleop and recording start at once, stop after --duration")
    ap.add_argument("--duration", type=float, default=10.0, help="seconds to run with --no-viewer")
    ap.add_argument("--debug", action="store_true", help="log every state change of the phone stream")
    args = ap.parse_args()
    if args.debug:
        log.setLevel("DEBUG")
    if not args.no_viewer and sys.platform == "darwin" and "mjpython" not in sys.executable:
        sys.exit("On macOS the viewer must run under mjpython:  uv run mjpython code/teleop_rebot_rs_sim.py ...")

    sim = ArmSim(args.scene)
    ctrl = TcpController(sim.model, HOME_QPOS)
    recorder = Recorder(Path(args.out), args.scene, "seeed_b601_rs_sim")
    phone = PhoneReader(args.phone_ip, args.phone_port)
    mapper = PhoneMapper(args.scale, track_rotation=not args.no_rotation)
    log.info("scene %s; listening to the phone on %s; episodes go to %s", args.scene, phone.address, recorder.out)
    log.info(KEY_HELP)
    keys: queue.Queue[int] = queue.Queue()

    if args.no_viewer:
        v_ctx = Headless(args.duration)
    else:
        from mujoco import viewer

        v_ctx = viewer.launch_passive(sim.model, sim.data, key_callback=keys.put)
    teleop, gripper_m, stream_ok, last_report = False, 0.0, False, time.monotonic()
    log.info("waiting for the phone stream (AR Data on, same network)")
    with v_ctx as v:
        if not args.no_viewer:
            v.opt.geomgroup[3] = 0
            v.cam.lookat[:] = (0.27, 0.0, 0.05)
            v.cam.distance, v.cam.azimuth, v.cam.elevation = 1.0, 0.0, -40.0
        while v.is_running():
            tick = time.perf_counter()
            sample = phone.get()
            if (sample is not None) != stream_ok:  # stream state changed
                stream_ok = sample is not None
                if stream_ok:
                    log.info("phone stream received (%.0f Hz, pose as %s)", phone.rate, phone.pose_format)
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
                        log.info("teleop started at TCP (%.3f, %.3f, %.3f) m; the gripper now follows the phone", *ctrl.target)
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
                    gripper_m = GRIPPER_STROKE if gripper_m < GRIPPER_STROKE / 2 else 0.0
                    log.info("gripper %s", "open" if gripper_m > 0 else "closed")
            # ---- command path: phone -> TCP target -> joint target (rad)
            pos, rot = mapper.map(sample[0], sample[1]) if (teleop and sample is not None) else (None, None)
            q_cmd = ctrl.command(pos, rot)
            action = motor_deg_to_action(np.concatenate([np.degrees(q_cmd), [gripper_m / GRIPPER_STROKE * GRIPPER_MOTOR_MAX_DEG]]))
            # ---- response path: observation before the step, then the step
            state = sim.state_deg()
            if recorder.active:
                recorder.add(state, action, {"front": sim.render("front"), "side": sim.render("side")}, phone.age(), ctrl.blocked)
            sim.command(q_cmd, gripper_m)
            sim.step()
            v.sync()
            now = time.monotonic()
            if now - last_report >= 5.0:
                last_report = now
                tcp = sim.tcp_pos()
                log.debug("phone %.0f Hz | teleop %s%s | recording %s (%d frames) | TCP (%.3f, %.3f, %.3f) m",
                          phone.rate, "on" if teleop else "off", " (at the reach limit)" if ctrl.blocked else "",
                          "on" if recorder.active else "off", len(recorder.rows), *tcp)
            time.sleep(max(0.0, 1.0 / CONTROL_HZ - (time.perf_counter() - tick)))
    if recorder.active:
        ep = recorder.save()
        log.info("window closed while recording: %s saved", ep)
    phone.close()
    log.info("done: %d episode(s) in %s", recorder.n_saved, recorder.out)


if __name__ == "__main__":
    main()
