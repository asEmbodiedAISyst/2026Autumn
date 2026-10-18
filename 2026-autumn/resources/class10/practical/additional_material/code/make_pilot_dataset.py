"""Make the Class 10 pilot dataset: a small set of handheld Push Cube episodes that includes episodes a data
audit must reject.

Run it from ``additional_material/rebot_pusher`` (it imports ``rebot_sim`` of that package)::

    uv run python ../code/make_pilot_dataset.py --root datasets/pilot_push_cube_handheld

Every episode is written, successful or not (unlike ``scripts/generate_tool_demos.py``, which drops failures),
so that students can find the bad ones. The script writes ``audit_reference.json`` next to the dataset with the
ground truth of the audit: per episode, the outcome, the fraction of frames in which both the cube and the goal
are inside the phone image, the robot-reachable fraction, the frame count and the injected fault, if any.

Injected faults (one per episode, see ``PLAN``):

* ``none``: a normal episode;
* ``camera_away``: the operator faces away from the push direction (yaw limit lifted); cube and goal leave
  the image, and most poses are also unreachable for the robot;
* ``truncated``: the recording stops before the task is finished (timeout);
* ``too_fast``: the speed limit is raised, so the robot would have to clip the motion;
* ``unreachable``: the tool yaw limit is removed, so some poses cannot be reached by the robot.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if sys.platform.startswith("linux"):
    os.environ.setdefault("MUJOCO_GL", "egl")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rebot_pusher"))  # rebot_sim of the class package

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

from rebot_sim.ik import DiffIK  # noqa: E402
from rebot_sim.pose import rot_z, rotvec_to_matrix  # noqa: E402
from rebot_sim.recording import TOOL_ROBOT_TYPES, DatasetRecorder, tool_feature_names  # noqa: E402
from rebot_sim.robot import PUSHER_HOME_QPOS, TCP_DOWN_ROT  # noqa: E402
from rebot_sim.scripted import PushCubeExpert  # noqa: E402
from rebot_sim.sim import RebotSim  # noqa: E402
from rebot_sim.tasks import PUSH_HEIGHT  # noqa: E402
from rebot_sim.tool_env import ToolPushEnv  # noqa: E402

# (seed, fault)
PLAN = [
    (7100, "none"),
    (7101, "none"),
    (7102, "camera_away"),
    (7103, "none"),
    (7104, "truncated"),
    (7105, "none"),
    (7106, "too_fast"),
    (7107, "unreachable"),
    (7108, "none"),
    (7109, "camera_away"),
]


def point_in_image(sim, cam: str, p_world: np.ndarray) -> bool:
    """True if a world point projects inside the image of camera ``cam`` and lies in front of it."""
    cid = sim.model.camera(cam).id
    R = sim.data.cam_xmat[cid].reshape(3, 3)
    t = sim.data.cam_xpos[cid]
    p = R.T @ (p_world - t)  # camera frame: x right, y up, looks along -z
    if p[2] >= 0:
        return False
    fovy = np.radians(sim.model.cam_fovy[cid])
    h, w = sim.image_size
    fy = (h / 2) / np.tan(fovy / 2)
    u = fy * p[0] / -p[2]
    v = fy * p[1] / -p[2]
    return abs(u) <= w / 2 and abs(v) <= h / 2


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--repo-id", default="local/pilot_push_cube_handheld")
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    env = ToolPushEnv("push_cube", embodiment="handheld", image_size=(480, 640), fps=args.fps,
                      terminate_on_success=False, action_mode="episode")
    env_dim = env.task.object_state(env.sim).shape[0]
    rec = DatasetRecorder(args.repo_id, args.fps, ("phone",), (480, 640), root=args.root, env_state_dim=env_dim,
                          robot_type=TOOL_ROBOT_TYPES["handheld"], **tool_feature_names("episode"))
    reach_ik = DiffIK(RebotSim("pusher_table", cameras=()).model, posture=PUSHER_HOME_QPOS)
    default_speed = env.ctrl.limits.max_speed
    default_yaw = env.ctrl.limits.max_yaw_deg
    audit = []
    try:
        for ep, (seed, fault) in enumerate(PLAN):
            rng = np.random.default_rng(seed)
            env.ctrl.limits.max_speed = 0.6 if fault == "too_fast" else default_speed
            env.ctrl.limits.max_yaw_deg = 180.0 if fault in ("unreachable", "camera_away") else default_yaw
            obs, _ = env.reset(seed=seed)
            expert = PushCubeExpert(env.ctrl, env.task, push_height=PUSH_HEIGHT["handheld"], rng=rng,
                                    push_speed=0.25 if fault == "too_fast" else 0.08)
            max_steps = 45 if fault == "truncated" else 450
            yaw_offset = np.radians(180.0) if fault == "camera_away" else np.radians(rng.uniform(-15, 15))
            if fault == "unreachable":
                yaw_offset = np.radians(110.0)
            tilt_axis = np.array([np.cos(a := rng.uniform(0, 2 * np.pi)), np.sin(a), 0.0])
            tilt = np.radians(rng.uniform(0, 10))
            q_reach, n_unreach, n_vis, n, after = PUSHER_HOME_QPOS.copy(), 0, 0, 0, None
            for t in range(max_steps):
                cube, goal, _ = env.task._cube_goal(env.sim)
                d = goal - cube
                yaw = np.arctan2(d[1], d[0]) + yaw_offset
                rot = rotvec_to_matrix(tilt_axis * tilt) @ rot_z(yaw) @ TCP_DOWN_ROT
                target = expert.target(env.sim) + rng.normal(0, 1e-3, 3)
                action = env.action_to(target, rot)
                obs_next, _, _, _, info = env.step(action)
                rec.add_frame(obs["agent_pos"], info["applied_action"], obs["pixels"], env.task.description,
                              obs["environment_state"])
                obs = obs_next
                n += 1
                mujoco.mj_forward(env.sim.model, env.sim.data)
                cube3 = np.array([*cube, 0.02])
                goal3 = np.array([*goal, 0.0])
                n_vis += point_in_image(env.sim, "phone", cube3) and point_in_image(env.sim, "phone", goal3)
                res = reach_ik.solve(env.ctrl.target_pos, env.ctrl.target_rot, q_reach, max_iters=30)
                if not res.success:
                    res = reach_ik.solve(env.ctrl.target_pos, env.ctrl.target_rot, PUSHER_HOME_QPOS, max_iters=300)
                q_reach = res.q
                n_unreach += not res.success
                if expert.phase == "done" and info["is_success"] and after is None:
                    after = 0
                if after is not None:
                    after += 1
                    if after >= 10:
                        break
            rec.save_episode()
            final = env.task.evaluate(env.sim)
            audit.append({
                "episode_index": ep, "seed": seed, "fault": fault, "frames": n,
                "success": bool(final.success), "final_distance_m": round(float(final.info["distance"]), 4),
                "both_visible_fraction": round(n_vis / n, 3), "robot_reachable_fraction": round(1 - n_unreach / n, 3),
                "max_speed_limit_m_s": env.ctrl.limits.max_speed, "max_yaw_limit_deg": env.ctrl.limits.max_yaw_deg,
            })
            print(audit[-1])
    finally:
        rec.finalize()
        env.close()
    Path(args.root, "audit_reference.json").write_text(json.dumps(audit, indent=2))
    print(f"dataset: {rec.root} ({rec.num_episodes} episodes); audit reference written")


if __name__ == "__main__":
    main()
