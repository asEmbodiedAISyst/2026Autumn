"""Check a pusher-tool dataset ("episode" format) recorded by hand: could the robot reproduce it?

Every episode is anchored at the robot's tool start pose and replayed kinematically on the simulated robot with
the same tool (IK only, no objects). Reports per episode: robot-reachable fraction, peak speed, tilt and yaw
range. ``--video`` renders one episode: the robot following the human trajectory next to the recorded phone image.

Example::

    uv run python scripts/check_handheld_dataset.py --root datasets/real_push_cube
    uv run python scripts/check_handheld_dataset.py --root datasets/real_push_cube --video 0 --out outputs/check_ep0.mp4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if sys.platform.startswith("linux"):  # headless EGL rendering on Linux; macOS uses its default (CGL)
    os.environ.setdefault("MUJOCO_GL", "egl")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the package root

import numpy as np  # noqa: E402

from rebot_sim.ik import DiffIK  # noqa: E402
from rebot_sim.pose import EpisodeFrame, tilt_angle, yaw_of  # noqa: E402
from rebot_sim.robot import PUSHER_HOME_QPOS, TCP_DOWN_ROT  # noqa: E402
from rebot_sim.sim import RebotSim  # noqa: E402
from rebot_sim.tool_env import TOOL_START_POS, default_tool_limits  # noqa: E402


def load_states(root: Path) -> tuple[dict[int, np.ndarray], int]:
    import pandas as pd
    import pyarrow.parquet as pq

    fps = json.loads((root / "meta" / "info.json").read_text())["fps"]
    df = pd.concat(pq.read_table(f, columns=["episode_index", "frame_index", "observation.state"]).to_pandas()
                   for f in sorted((root / "data").glob("chunk-*/file-*.parquet")))
    eps = {}
    for ep, g in df.sort_values(["episode_index", "frame_index"]).groupby("episode_index"):
        eps[int(ep)] = np.stack(g["observation.state"].to_numpy())
    return eps, fps


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="dataset directory")
    ap.add_argument("--video", type=int, default=None, help="render a video of the robot following this episode")
    ap.add_argument("--out", default="outputs/check_episode.mp4")
    args = ap.parse_args()

    root = Path(args.root)
    eps, fps = load_states(root)
    sim = RebotSim("pusher_table", cameras=())
    ik = DiffIK(sim.model, posture=PUSHER_HOME_QPOS)
    frame = EpisodeFrame(TOOL_START_POS, TCP_DOWN_ROT)
    lim = default_tool_limits()
    rows, joint_traj = [], {}
    for ep, states in eps.items():
        q, ok, qs = PUSHER_HOME_QPOS.copy(), 0, []
        poses = [frame.decode(s) for s in states]
        for p, R in poses:
            res = ik.solve(p, R, q, max_iters=30)
            if not res.success:
                res = ik.solve(p, R, PUSHER_HOME_QPOS, max_iters=300)
            q = res.q
            ok += res.success
            qs.append(q.copy())
        joint_traj[ep] = np.array(qs)
        P = np.array([p for p, _ in poses])
        speed = np.linalg.norm(np.diff(P, axis=0), axis=1) * fps if len(P) > 1 else np.zeros(1)
        tilts = np.degrees([tilt_angle(R) for _, R in poses])
        yaws = np.degrees([yaw_of(R) for _, R in poses])
        rows.append((ep, len(states), ok / len(states), speed.max(), np.percentile(speed, 95), tilts.max(),
                     yaws.min(), yaws.max()))
    print(f"{'ep':>4} {'frames':>6} {'reach':>6} {'peak speed':>11} {'P95 speed':>10} {'max tilt':>9} {'yaw range':>14}")
    for ep, n, r, vmax, v95, tmax, ymin, ymax in rows:
        flag = "" if r >= 0.98 and vmax <= lim.max_speed * 1.05 and tmax <= lim.max_tilt_deg and max(abs(ymin), abs(ymax)) <= lim.max_yaw_deg else "  !"
        print(f"{ep:4d} {n:6d} {r:6.0%} {vmax:7.2f} m/s {v95:6.2f} m/s {tmax:7.1f} deg {ymin:6.0f} ~ {ymax:4.0f} deg{flag}")
    print(f"\nsoftware limits: speed <= {lim.max_speed} m/s, tilt <= {lim.max_tilt_deg} deg, yaw <= +-{lim.max_yaw_deg} deg; "
          "! marks an episode with unreachable frames (< 98 %) or motions outside the limits: the robot would clip or slow them")

    if args.video is not None:
        import av
        import mujoco
        from lerobot.datasets.lerobot_dataset import LeRobotDataset

        ds = LeRobotDataset("local/check", root=root, episodes=[args.video])
        r = mujoco.Renderer(sim.model, 480, 640)
        cam = mujoco.MjvCamera()
        cam.lookat[:] = (0.3, 0.0, 0.1)
        cam.distance, cam.azimuth, cam.elevation = 0.95, 135, -20
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with av.open(str(out), "w") as container:
            stream = container.add_stream("libx264", rate=fps)
            stream.height, stream.width, stream.pix_fmt = 480, 1280, "yuv420p"
            for i, q in enumerate(joint_traj[args.video]):
                sim.reset(q)
                r.update_scene(sim.data, cam)
                robot = r.render()
                phone = (ds[i]["observation.images.phone"].permute(1, 2, 0).numpy() * 255).astype(np.uint8)
                img = np.concatenate([phone, robot], axis=1)
                for pkt in stream.encode(av.VideoFrame.from_ndarray(img, format="rgb24")):
                    container.mux(pkt)
            for pkt in stream.encode():
                container.mux(pkt)
        r.close()
        print(f"video: {out} (left: phone image; right: the robot following the human trajectory)")


if __name__ == "__main__":
    main()
