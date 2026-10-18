"""Record real handheld demonstrations: a person holds the printed tool (rod + iPhone running asMagic).

Each asMagic AR frame carries the phone camera pose (ARKit) and the color image of the same instant. The pose
is converted to the rod-tip (TCP) pose with the rigid camera -> TCP transform of the tool model, expressed in the
episode frame (gravity aligned, anchored at the first frame of the episode), and written as a LeRobot dataset in
the same "episode" tool format as the simulated data (``observation.images.phone``, ``observation.state`` and
``action`` = 9-D pose in the episode frame; the action is the pose of the next frame).

No robot is needed. Put a mark on the table where the robot base would be and start every episode with the rod
tip at the start mark (33 cm in front of the base, about 12 cm high, rod tilted ~30 deg forward): the script then
checks live whether the robot could reproduce the motion (IK on the robot with the same tool).

Controls (type in this terminal, then Enter):  [Enter] start / stop+save,  d = discard current episode,  q = quit.

Hands-free (``--gesture --voice``, no keyboard or screen needed while collecting): an episode starts when the
tool, after resting at the start mark, begins to move; **lift the tip 8 cm above the start height and hold still
0.7 s** to finish and save; **shake / twist the tool fast** to discard. Every event and the suggested cube / goal
placement are spoken (speech-dispatcher, English). The keyboard keeps working as a fallback.

Example::

    uv run python scripts/record_handheld.py --phone-ip 192.168.1.100 \\
        --repo-id local/real_push_cube --root datasets/real_push_cube --num-episodes 50

Test without a phone::

    uv run python -m rebot_sim.teleop.fake_phone --pattern circle --hold tool --image
    uv run python scripts/record_handheld.py --phone-ip 127.0.0.1 --root /tmp/real_test --auto 2
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the package root

from rebot_sim.ik import DiffIK
from rebot_sim.pose import EpisodeFrame, tilt_angle, yaw_of
from rebot_sim.robot import PUSHER_HOME_QPOS, TCP_DOWN_ROT
from rebot_sim.sim import HandheldToolSim, RebotSim
from rebot_sim.tasks import PushCubeTask
from rebot_sim.teleop.phone import ARKIT_TO_ROBOT, AsmagicFrameReader, PhoneFrame, RigidPhoneMapper
from rebot_sim.tool_env import TOOL_START_POS, make_tool_task

START_HEIGHT_CM = TOOL_START_POS[2] * 100  # the robot's tip height above the table at the start of every episode


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phone-ip", required=True)
    ap.add_argument("--phone-port", type=int, default=8000)
    ap.add_argument("--repo-id", default="local/real_push_cube")
    ap.add_argument("--root", default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--num-episodes", type=int, default=50)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--task", default=PushCubeTask.description, help="task description written to the dataset")
    ap.add_argument("--robot-type", default="rebot_pusher_tool_real",
                    help="robot_type written to the dataset; it must be the same as in teleop_real.py to merge the datasets with lerobot-edit-dataset")
    ap.add_argument("--max-jump-cm", type=float, default=3.0, help="a position jump above this between two frames is an ARKit tracking fault, cm")
    ap.add_argument("--max-unreachable-frac", type=float, default=0.02, help="the episode is not saved when the fraction of unreachable frames is above this value")
    ap.add_argument("--no-layout", action="store_true", help="do not print the suggested cube and goal placement")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--gesture", action="store_true", help="control with tool gestures: move after resting = start, lift and hold still = save, shake fast = discard")
    ap.add_argument("--lift-end", type=float, default=0.08, help="save gesture: lift of the rod tip above the start height, m (default 0.08)")
    ap.add_argument("--start-speed", type=float, default=0.04, help="start gesture: speed above which the tool counts as moving, m/s")
    ap.add_argument("--voice", action="store_true", help="spoken prompts (start, save, discard, placement suggestion, warnings)")
    ap.add_argument("--z-frame", choices=["start", "table"], default="table",
                    help="reference of z: table = height above the table (recommended; before the start, rest the rod tip on the table "
                         "for 1 s to calibrate); start = relative to the start height of the episode (old format)")
    ap.add_argument("--auto", type=int, default=0, help="test: record N episodes of 3 s each automatically, without keys")
    return ap.parse_args()


def tcp_pose_from_phone(f: PhoneFrame, mapper: RigidPhoneMapper) -> tuple[np.ndarray, np.ndarray]:
    """Rod-tip pose in a gravity-aligned z-up frame (heading arbitrary; removed by the episode frame)."""
    R_cam = ARKIT_TO_ROBOT @ f.rot
    p_cam = ARKIT_TO_ROBOT @ f.pos
    return p_cam + R_cam @ mapper.p_cam_tcp, R_cam @ mapper.R_cam_tcp


def to_image(img: np.ndarray | None) -> np.ndarray | None:
    if img is None:
        return None
    if img.shape[:2] != (480, 640):
        from PIL import Image

        img = np.asarray(Image.fromarray(img).resize((640, 480)))
    return np.ascontiguousarray(img[..., :3], dtype=np.uint8)


def print_layout(task: PushCubeTask, rng: np.random.Generator, voice=None) -> None:
    """Suggest where to put the cube and the goal for the next episode (same distribution as the simulation)."""
    cube, goal, yaw = task.sample_layout(rng)
    print(f"Suggested placement (from the base mark, x forward, y left, cm): cube ({cube[0] * 100:.0f}, {cube[1] * 100:.0f}) "
          f"turned {np.degrees(yaw):.0f} deg; goal ({goal[0] * 100:.0f}, {goal[1] * 100:.0f})")
    if voice is not None:
        voice.say(f"Cube: forward {cube[0] * 100:.0f}, {'left' if cube[1] >= 0 else 'right'} {abs(cube[1]) * 100:.0f}. "
                  f"Goal: forward {goal[0] * 100:.0f}, {'left' if goal[1] >= 0 else 'right'} {abs(goal[1]) * 100:.0f}.")


def calibrate_table(reader, mapper, voice, cmds, still_s: float = 1.0) -> float:
    """Table height in the gravity-aligned phone frame: the tip rests on the table until it is still for
    ``still_s`` (or Enter is pressed). ARKit keeps its world frame for the whole session, so one calibration
    serves every episode; it is corrected if a later episode goes below it."""
    print("Table calibration: put the rod tip on the table and hold it still for 1 s (or press Enter to accept the current height)... "
          "(in gesture mode, touch the table again before every episode)")
    voice.say("Put the tip on the table and hold still")
    hist: list[tuple[float, float]] = []
    last_seq = -1
    while True:
        if not cmds.empty():
            cmds.get_nowait()
            if hist:
                break
        f = reader.latest()
        if f is not None and f.seq != last_seq:
            last_seq = f.seq
            z = float(tcp_pose_from_phone(f, mapper)[0][2])
            hist.append((f.recv_time, z))
            hist = [(t, z) for t, z in hist if f.recv_time - t <= still_s]
            zs = [z for _, z in hist]
            if f.recv_time - hist[0][0] >= still_s * 0.95 and max(zs) - min(zs) < 0.005:
                break
        time.sleep(0.01)
    z_table = float(np.mean([z for _, z in hist]))
    print("Table height calibrated. Now lift the tool to the start position (about 12 cm high).")
    voice.say("Table calibrated. Lift to the start position")
    return z_table


def main() -> None:
    args = parse_args()
    layout_rng = np.random.default_rng(args.seed)
    layout_task = make_tool_task("push_cube")
    from rebot_sim.recording import DatasetRecorder, tool_feature_names

    rec = DatasetRecorder(args.repo_id, args.fps, ("phone",), (480, 640), root=args.root, resume=args.resume,
                          robot_type=args.robot_type, **tool_feature_names("episode"))
    print(f"recording to {rec.root} ({rec.num_episodes} episodes so far)")
    mapper = RigidPhoneMapper.from_model(HandheldToolSim("handheld_table", cameras=()).model)
    reach_ik = DiffIK(RebotSim("pusher_table", cameras=()).model, posture=PUSHER_HOME_QPOS)
    robot_origin = TOOL_START_POS.copy()
    if args.z_frame == "table":
        robot_origin[2] = 0.0  # the robot's episode frame then has z = height above the table
    robot_frame = EpisodeFrame(robot_origin, TCP_DOWN_ROT)  # where the robot would start the same episode
    reader = AsmagicFrameReader(args.phone_ip, args.phone_port)  # after the recorder (torch import), see devlog
    print(f"subscribed to asMagic: {reader.address}")

    from rebot_sim.teleop.gestures import GestureDetector, table_from_touches
    from rebot_sim.teleop.voice import Voice

    voice = Voice(args.voice)
    det = GestureDetector(start_speed=args.start_speed, lift_m=args.lift_end) if args.gesture else None
    cmds: queue.Queue[str] = queue.Queue()
    if not args.auto:
        threading.Thread(target=lambda: [cmds.put(line.strip().lower()) for line in sys.stdin], daemon=True).start()
        print("Enter: start / stop and save; d Enter: discard the episode; q Enter: quit")
    if det is not None:
        print("Gesture control: before every episode, rest the rod tip on the table for 0.5 s (table calibration), "
              "lift it to the start position and hold still for 0.5 s, then move = start; "
              "lift the tip 8 cm and hold still for 0.7 s = save; shake fast = discard")
    z_table = None
    if args.z_frame == "table":
        if args.auto:  # test mode: assume the first pose is START_HEIGHT above the table
            t_end = time.monotonic() + 5.0
            f0 = reader.latest()
            while f0 is None and time.monotonic() < t_end:
                time.sleep(0.05)
                f0 = reader.latest()
            z_table = float(tcp_pose_from_phone(f0, mapper)[0][2]) - START_HEIGHT_CM / 100 if f0 else 0.0
        else:
            z_table = calibrate_table(reader, mapper, voice, cmds)
    if not args.no_layout:
        print_layout(layout_task, layout_rng, voice)

    saved, recording, auto_left = 0, False, args.auto
    try:
        while saved < args.num_episodes:
            # ---- wait for "start"
            if args.auto:
                if auto_left == 0:
                    break
                time.sleep(0.5)
                cmd = ""
            elif det is not None:  # gesture: poll the pose stream, the keyboard still works
                det.reset()
                cmd, last_wait_seq = None, -1
                still_samples: list[tuple[float, float]] = []  # (t, z) while the tool rests: table touches
                touch_said = None
                while cmd is None:
                    if not cmds.empty():
                        cmd = cmds.get_nowait()
                        break
                    f = reader.latest()
                    if f is not None and f.seq != last_wait_seq:
                        last_wait_seq = f.seq
                        p, R = tcp_pose_from_phone(f, mapper)
                        g = det.update(p, R, f.recv_time)
                        if det.is_still:
                            still_samples.append((f.recv_time, float(p[2])))
                            still_samples = [(t, z) for t, z in still_samples if f.recv_time - t <= 30.0]
                            # announce a new lowest still height (the tip resting on the table)
                            if touch_said is None or p[2] < touch_said - 0.02:
                                touch_said = float(p[2])
                                voice.say("Table")
                        if g == "start":
                            if z_table is not None:  # per-episode table height: immune to ARKit drift
                                z_touch = table_from_touches(still_samples, f.recv_time, float(p[2]))
                                if z_touch is not None:
                                    z_table = z_touch
                                else:
                                    print("! no table touch before this episode: the previous table height is used (ARKit drift can cause an error)")
                                    voice.say("No table touch")
                            cmd = ""
                    time.sleep(0.01)
            else:
                cmd = cmds.get()
            if cmd == "q":
                break
            if reader.latest() is None:
                print("! no data from the phone: check the IP, the network and that the app is on the AR page")
                voice.say("No phone data")
                continue
            if det is not None and not det.recording:  # started from the keyboard: arm the end gestures
                det.recording, det._t0 = True, time.monotonic()
                f0 = reader.latest()
                det._z0 = float(tcp_pose_from_phone(f0, mapper)[0][2]) if f0 is not None else 0.0
            voice.say("Start")
            # ---- record one episode
            frame0 = None
            prev, last_seq, n, jumps, unreachable, q_reach = None, -1, 0, 0, 0, PUSHER_HOME_QPOS.copy()
            z_min = 0.0  # lowest tip height relative to the start: ~ -(start height) when the tip reaches the table
            end, t_ep, next_tick = None, time.monotonic(), time.monotonic()
            print(f"\n[episode {rec.num_episodes + 1}] recording... (Enter stops and saves, d Enter discards)")
            while end is None:
                if args.auto and time.monotonic() - t_ep > 3.0:
                    end = "save"
                while not cmds.empty():
                    c = cmds.get_nowait()
                    end = "discard" if c == "d" else "quit" if c == "q" else "save"
                f = reader.latest()
                if f is None or f.image is None:
                    sys.stdout.write("\r! data stream lost (no pose or no image)".ljust(100))
                    next_tick = time.monotonic() + 1.0 / args.fps
                    time.sleep(0.05)
                    continue
                if f.seq != last_seq:
                    last_seq = f.seq
                    p, R = tcp_pose_from_phone(f, mapper)
                    if det is not None:
                        g = det.update(p, R, f.recv_time)
                        if g in ("save", "discard"):
                            end = g
                    if frame0 is None:
                        origin = p if z_table is None else np.array([p[0], p[1], z_table])
                        frame0 = EpisodeFrame(origin, R)
                        start_height = float(p[2] - origin[2]) if z_table is not None else None
                    state = frame0.encode(p, R)
                    z_min = min(z_min, float(state[2]))
                    if prev is not None:
                        if np.linalg.norm(state[:3] - prev[0][:3]) > args.max_jump_cm / 100:
                            jumps += 1
                            if jumps == 1:
                                voice.say("Jump")
                        rec.add_frame(prev[0], state, {"phone": prev[1]}, args.task)  # action = next pose
                        n += 1
                    prev = (state, to_image(f.image))
                    # live check: could the robot do this (episode anchored at the robot start pose)?
                    pr, Rr = robot_frame.decode(state)
                    res = reach_ik.solve(pr, Rr, q_reach, max_iters=30)
                    q_reach = res.q
                    unreachable += not res.success
                    if not res.success and unreachable == 1:
                        voice.say("Out of reach")
                    sys.stdout.write(
                        f"\rframe {n:4d} | phone {reader.rate_hz:4.0f} Hz | displacement {np.round(state[:3] * 100, 1)} cm | "
                        f"tilt {np.degrees(tilt_angle(Rr)):4.1f} deg yaw {np.degrees(yaw_of(Rr)):5.1f} deg | "
                        f"{'robot can reach' if res.success else '! robot cannot reach'} | jumps {jumps}".ljust(110))
                    sys.stdout.flush()
                next_tick += 1.0 / args.fps
                time.sleep(max(0.0, next_tick - time.monotonic()))
            ok_reach = unreachable <= args.max_unreachable_frac * max(n, 1)
            keep = end == "save" and n >= 10 and jumps == 0 and ok_reach
            if keep:
                rec.save_episode()
                saved += 1
            else:
                rec.discard_episode()
            auto_left -= 1  # test mode: every attempt counts, so a failing setup cannot loop forever
            reason = "" if keep else f" ({n} frames, {jumps} jumps, {unreachable} unreachable)"
            print(f"\n[episode] {'saved' if keep else 'discarded'}{reason}; saved {saved}/{args.num_episodes}")
            # The robot starts every episode with the tip START_HEIGHT above the table. With the table frame the
            # start height is measured directly; with the start frame only the lowest point of the episode tells.
            if z_table is not None:
                height = (start_height or 0.0) * 100
                if z_min < -0.005 and keep:  # tip went below the calibrated table: the table estimate was too high
                    z_table += z_min
                    print(f"(the rod tip went {-z_min * 100:.1f} cm below the calibrated table: the table height is lowered)")
                height_note = f"start height {height:.0f} cm" + ("" if abs(height - START_HEIGHT_CM) <= 2.5 else f" (should be about {START_HEIGHT_CM:.0f} cm)")
                low, high = height < START_HEIGHT_CM - 2.5, height > START_HEIGHT_CM + 2.5
            else:
                drop = max(0.0, -z_min * 100)
                low, high = drop < START_HEIGHT_CM - 2.5, drop > START_HEIGHT_CM + 2.5
                height_note = f"lowest point {drop:.0f} cm below the start" + ("" if not (low or high) else f" (the start height should be about {START_HEIGHT_CM:.0f} cm)")
            print(height_note)
            if keep:
                voice.say(f"Saved, episode {saved}" + (". Start too low" if low else ". Start too high" if high else ""))
            else:
                why = "by hand" if end == "discard" else "too short" if n < 10 else "jumps" if jumps else "out of reach"
                voice.say(f"Discarded, {why}")
            if end == "quit":
                break
            if keep and not args.no_layout:
                print_layout(layout_task, layout_rng, voice)
    finally:
        rec.finalize()
        reader.close()
        print(f"dataset: {rec.root}, {rec.num_episodes} episodes")


if __name__ == "__main__":
    main()
