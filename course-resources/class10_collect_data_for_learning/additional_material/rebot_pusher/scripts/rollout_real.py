"""Run a trained pusher-tool policy (ACT / Diffusion Policy, "episode" format) on the real reBot B601-RS.

Real-robot counterpart of ``scripts/eval_policy.py --embodiment pusher``: the observation is the image of the
robot-mounted iPhone (asMagic) + the measured tool pose in the episode frame; the policy output goes through the
same software limits and IK as in simulation. Success is judged by the operator.

Keys (MuJoCo window = digital twin of the measured arm, must have focus):

* ``Space``: start the episode (after placing the objects) / pause (the arm holds still) / continue;
* ``Right``: end the episode as a success;  ``Left``: end it as a failure. The arm then returns to a start pose;
* closing the window or Ctrl+C: stop; the arm folds back to its zero pose and torque is disabled.

Test without hardware (simulated arm and phone camera; success is then evaluated automatically)::

    uv run python scripts/rollout_real.py --robot sim --auto \\
        --policy-path outputs/train/act_ip17v2_cube300_handheld/checkpoints/last/pretrained_model

Real robot::

    uv run python scripts/rollout_real.py --robot real --can-port can0 --camera-ip 192.168.1.102 \\
        --policy-path outputs/train/act_real/checkpoints/last/pretrained_model --episodes 10 --max-speed 0.10
"""

from __future__ import annotations

import argparse
import queue
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the package root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from teleop_real import KEY_LEFT, KEY_RIGHT, KEY_SPACE, Status, add_robot_args, connect, make_env, open_viewer  # noqa: E402


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_robot_args(ap)
    ap.add_argument("--policy-path", required=True)
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--max-steps", type=int, default=600, help="maximum control steps per episode (600 = 20 s at 30 Hz); a timeout counts as a failure")
    ap.add_argument("--n-action-steps", type=int, default=None, help="actions executed per inference (ACT default 100; Diffusion Policy 16-32)")
    ap.add_argument("--temporal-ensemble", type=float, default=None, metavar="COEFF",
                    help="ACT temporal ensembling (0.01 in the ACT paper): the policy runs at every step and the overlapping action chunks are averaged with weights, so there is no jump at each re-plan; do not use it with --n-action-steps")
    ap.add_argument("--device", default=None)
    ap.add_argument("--max-image-age", type=float, default=0.3, help="the policy pauses when the image is older than this (s)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--auto", action="store_true", help="test: no keys; every episode starts at once and ends at --max-steps or on success")
    ap.add_argument("--video-dir", default=None,
                    help="save the phone images of every episode as mp4 and the states and actions as npz (to compare the robot view with the recorded data afterwards)")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    import torch
    from eval_policy import default_device, load_policy
    from lerobot.common.control_utils import predict_action

    from eval_policy import save_video
    import numpy as np

    device = args.device or default_device()
    cfg, policy, pre, post = load_policy(args.policy_path, device, args.temporal_ensemble)
    if args.n_action_steps is not None and args.temporal_ensemble is None:
        policy.config.n_action_steps = args.n_action_steps
    action_dim = cfg.output_features["action"].shape[0]
    args.action_mode = "episode" if action_dim == 9 else "delta"
    env = make_env(args)

    keys: queue.Queue[int] = queue.Queue()
    viewer = None
    status = Status()
    results: list[bool] = []
    try:
        connect(env, args)
        viewer, view_sim = open_viewer(env, keys, not args.no_viewer)
        mocap_id = view_sim.model.body("ee_target").mocapid[0]
        running = lambda: viewer.is_running() if viewer is not None else True  # noqa: E731
        for ep in range(args.episodes):
            if not running():
                break
            print("\nthe arm moves to the start pose...")
            obs, info = env.reset(seed=args.seed + ep)
            policy.reset()
            started, paused, end, steps = args.auto, False, None, 0
            frames, states, actions = [], [], []
            if not args.auto:
                print(f"[episode {ep + 1}] place the objects, then Space starts; Space pauses / continues, Right = success, Left = failure")
            while running() and end is None:
                tick = time.perf_counter()
                while not keys.empty():
                    k = keys.get_nowait()
                    if k == KEY_SPACE:
                        if not started:
                            started = True
                        else:
                            paused = not paused
                    elif k == KEY_RIGHT:
                        end = True
                    elif k == KEY_LEFT:
                        end = False
                image = obs["pixels"]["phone"]
                stale = image is None or info["image_age"] > args.max_image_age
                if started and not paused and not stale:
                    lerobot_obs = {"observation.state": obs["agent_pos"], "observation.images.phone": image}
                    with torch.inference_mode():
                        action = predict_action(lerobot_obs, policy, torch.device(device), pre, post, use_amp=False,
                                                task=env.task.description).squeeze(0).cpu().numpy()
                    if args.video_dir:
                        frames.append(image.copy()); states.append(obs["agent_pos"].copy()); actions.append(action.copy())
                    obs, _, _, _, info = env.step(action)
                    steps += 1
                else:
                    obs, _, _, _, info = env.hold()
                view_sim.data.mocap_pos[mocap_id] = env.ctrl.target_pos
                if viewer is not None:
                    viewer.sync()
                if info["is_success"]:  # only with --robot sim
                    end = True
                elif steps >= args.max_steps:
                    end = False
                state = "waiting" if not started else "paused" if paused else "! image lost, holding" if stale else "running"
                status.show(f"ep {ep + 1} | {state} | step {steps}/{args.max_steps} | IK {'ok' if info['ik_ok'] else 'FAIL'}"
                            f" | image age {info['image_age'] * 1000:.0f} ms | success {sum(results)}/{len(results)}")
                dt = time.perf_counter() - tick
                if dt < 1.0 / env.fps:
                    time.sleep(1.0 / env.fps - dt)
            if end is not None:
                results.append(bool(end))
                print(f"\n[episode {ep + 1}] {'success' if end else 'failure'} ({steps} steps)")
            if args.video_dir and frames:
                out = Path(args.video_dir)
                save_video(frames, out / f"episode_{ep:03d}.mp4", env.fps)
                np.savez(out / f"episode_{ep:03d}.npz", state=np.array(states), action=np.array(actions),
                         success=bool(end) if end is not None else False)
                print(f"saved {out / f'episode_{ep:03d}.mp4'}")
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        if results:
            print(f"\nsuccess rate: {100 * sum(results) / len(results):.1f}% ({sum(results)}/{len(results)})")
        print("the arm returns to its zero pose; torque off...")
        env.close()
        if viewer is not None:
            from rebot_sim.viewer_utils import close_viewer

            close_viewer(viewer)


if __name__ == "__main__":
    main()
