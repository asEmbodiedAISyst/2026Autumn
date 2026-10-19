"""Generate pusher-tool (rod + phone) demonstrations with the scripted expert (headless).

``--embodiment handheld`` simulates human data collection: the expert moves the handheld tool (no robot)
with human-like variation (per-episode tilt, slow wobble, hand tremor). Every commanded tool pose is also
checked against the robot's IK, and episodes containing poses the robot could not reach are dropped, just
like a live reachability check during real collection.

``--embodiment pusher`` drives the robot-mounted tool instead (reference data from the robot itself).

The dataset uses the tool format (see ``rebot_sim.tool_env``): ``observation.images.phone``,
``observation.state`` = gravity in the tool frame, ``action`` = relative TCP motion in the tool frame.

Example::

    uv run python scripts/generate_tool_demos.py --embodiment handheld --num-episodes 100 \\
        --repo-id local/pusher_push_cube_handheld --root data/pusher_push_cube_handheld
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the package root

if sys.platform.startswith("linux"):  # headless EGL rendering on Linux; macOS uses its default (CGL)
    os.environ.setdefault("MUJOCO_GL", "egl")

import numpy as np  # noqa: E402

from rebot_sim.ik import DiffIK  # noqa: E402
from rebot_sim.pose import rot_z, rotvec_to_matrix  # noqa: E402
from rebot_sim.recording import TOOL_ROBOT_TYPES, DatasetRecorder, tool_feature_names  # noqa: E402
from rebot_sim.robot import PUSHER_HOME_QPOS, TCP_DOWN_ROT  # noqa: E402
from rebot_sim.scripted import PushCubeExpert, PushTExpert  # noqa: E402
from rebot_sim.sim import RebotSim  # noqa: E402
from rebot_sim.tasks import PUSH_HEIGHT  # noqa: E402
from rebot_sim.tool_env import ToolPushEnv  # noqa: E402


class HumanLikeOrientation:
    """Tool orientation like an operator holds it: facing the push direction (phone camera looking along the
    push, so cube and goal stay in view), plus a per-episode tilt and a slow wobble."""

    def __init__(self, rng: np.random.Generator, max_tilt_deg: float, wobble_deg: float, yaw_noise_deg: float) -> None:
        a = rng.uniform(0, 2 * np.pi)
        self.axis = np.array([np.cos(a), np.sin(a), 0.0])  # horizontal tilt axis
        self.tilt = np.radians(rng.uniform(0, max_tilt_deg))
        b = rng.uniform(0, 2 * np.pi)
        self.wobble_axis = np.array([np.cos(b), np.sin(b), 0.0])
        self.wobble = np.radians(wobble_deg)
        self.period = rng.uniform(1.5, 4.0)  # s
        self.yaw_offset = np.radians(rng.uniform(-yaw_noise_deg, yaw_noise_deg))

    def at(self, t: float, push_dir: np.ndarray) -> np.ndarray:
        yaw = np.arctan2(push_dir[1], push_dir[0]) + self.yaw_offset
        w = self.wobble * np.sin(2 * np.pi * t / self.period)
        return (rotvec_to_matrix(self.wobble_axis * w) @ rotvec_to_matrix(self.axis * self.tilt)
                @ rot_z(yaw) @ TCP_DOWN_ROT)


def push_direction(env: ToolPushEnv, expert) -> np.ndarray:
    """Direction the operator faces: the current push (Push-T primitive) or cube -> goal (Push Cube)."""
    if isinstance(expert, PushTExpert):
        prim = expert._prim
        return prim["dir"] if prim is not None else np.array([1.0, 0.0])
    cube, goal, _ = env.task._cube_goal(env.sim)
    return goal - cube


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", choices=["push_cube", "push_t"], default="push_cube")
    ap.add_argument("--embodiment", choices=["handheld", "pusher"], default="handheld")
    ap.add_argument("--action-mode", choices=["delta", "episode"], default="episode",
                    help="delta: relative motion per step (tool frame); episode: target pose relative to the first pose of the episode")
    ap.add_argument("--num-episodes", type=int, default=100)
    ap.add_argument("--repo-id", default="local/pusher_push_cube_handheld")
    ap.add_argument("--root", default=None)
    ap.add_argument("--image-size", default="480x640")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--max-steps", type=int, default=None, help="longest episode in frames; a longer episode is discarded (default push_cube 450, push_t 1500)")
    ap.add_argument("--extra-frames", type=int, default=10, help="frames recorded after the expert has finished")
    ap.add_argument("--max-tilt-deg", type=float, default=10.0, help="handheld: largest random tilt of the pusher tool per episode (deg)")
    ap.add_argument("--wobble-deg", type=float, default=3.0, help="handheld: amplitude of the slow wobble (deg)")
    ap.add_argument("--tremor-mm", type=float, default=1.0, help="handheld: standard deviation of the position tremor (mm)")
    ap.add_argument("--yaw-noise-deg", type=float, default=15.0, help="random deviation of the heading from the push direction (deg)")
    ap.add_argument("--max-unreachable-frac", type=float, default=0.0,
                    help="fraction of frames the arm cannot reach that a handheld episode may have (above it the episode is discarded; push_cube 0, push_t 0.02)")
    ap.add_argument("--env-state", action="store_true")
    ap.add_argument("--seed", type=int, default=3000)
    args = ap.parse_args()

    h, w = (int(v) for v in args.image_size.lower().split("x"))
    if args.max_steps is None:
        args.max_steps = 450 if args.task == "push_cube" else 1500
    env = ToolPushEnv(args.task, embodiment=args.embodiment, image_size=(h, w), fps=args.fps,
                      terminate_on_success=False, action_mode=args.action_mode)
    env_dim = env.task.object_state(env.sim).shape[0] if args.env_state else None
    rec = DatasetRecorder(args.repo_id, args.fps, ("phone",), (h, w), root=args.root, env_state_dim=env_dim,
                          robot_type=TOOL_ROBOT_TYPES[args.embodiment], **tool_feature_names(args.action_mode))
    handheld = args.embodiment == "handheld"
    # Reachability check of handheld poses on the robot-mounted tool (IK only, no physics)
    reach_ik = DiffIK(RebotSim("pusher_table", cameras=()).model, posture=PUSHER_HOME_QPOS) if handheld else None

    saved, tried, unreachable_eps = 0, 0, 0
    try:
        while saved < args.num_episodes:
            seed = args.seed + tried
            tried += 1
            rng = np.random.default_rng(seed)
            obs, _ = env.reset(seed=seed)
            if args.task == "push_cube":
                expert = PushCubeExpert(env.ctrl, env.task, push_height=PUSH_HEIGHT[args.embodiment], rng=rng)
            else:
                expert = PushTExpert(env.ctrl, env.task, push_height=PUSH_HEIGHT[args.embodiment], rng=rng)
            orient = HumanLikeOrientation(rng, args.max_tilt_deg if handheld else 0.0,
                                          args.wobble_deg if handheld else 0.0, args.yaw_noise_deg)
            q_reach, n_unreachable, n_frames, after = PUSHER_HOME_QPOS.copy(), 0, 0, None
            for t in range(args.max_steps):
                target = expert.target(env.sim)
                if handheld and args.tremor_mm > 0:
                    target = target + rng.normal(0, args.tremor_mm * 1e-3, 3)
                action = env.action_to(target, orient.at(t / args.fps, push_direction(env, expert)))
                obs_next, _, _, _, info = env.step(action)
                rec.add_frame(obs["agent_pos"], info["applied_action"], obs["pixels"], env.task.description,
                              obs["environment_state"] if args.env_state else None)
                obs = obs_next
                n_frames += 1
                if handheld:
                    res = reach_ik.solve(env.ctrl.target_pos, env.ctrl.target_rot, q_reach, max_iters=30)
                    if not res.success:  # retry from the preferred posture before counting it as unreachable
                        res = reach_ik.solve(env.ctrl.target_pos, env.ctrl.target_rot, PUSHER_HOME_QPOS, max_iters=300)
                    q_reach = res.q
                    n_unreachable += not res.success
                if expert.phase == "done" and info["is_success"] and after is None:
                    after = 0
                if after is not None:
                    after += 1
                    if after >= args.extra_frames:
                        break
            reachable = n_unreachable <= args.max_unreachable_frac * max(n_frames, 1)
            if after is not None and info["is_success"] and reachable:
                rec.save_episode()
                saved += 1
                print(f"[{saved}/{args.num_episodes}] seed={seed} success, {rec.dataset.meta.total_frames} frames in total")
            else:
                rec.discard_episode()
                unreachable_eps += not reachable
                print(f"seed={seed} {'unreachable for the arm' if not reachable else 'failed'}, discarded")
    finally:
        rec.finalize()
        env.close()
    print(f"done: {saved} episodes ({tried} attempts, {unreachable_eps} discarded as unreachable for the arm), dataset {rec.root}")


if __name__ == "__main__":
    main()
