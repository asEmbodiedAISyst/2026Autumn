"""Evaluate a pusher-tool policy (ACT / Diffusion Policy / SmolVLA, "episode" or "delta" format) in simulation; report the success rate and save videos.

Example::

    uv run python scripts/eval_policy.py \\
        --policy-path outputs/train/act_push_cube_scripted/checkpoints/last/pretrained_model \\
        --task push_cube --episodes 20 --video-dir outputs/eval/act_push_cube

The policy's input cameras must match the training data (camera names are read from the policy config).

``--embodiment``: ``handheld`` (the tool moved by the simulated human) or ``pusher`` (the tool on the simulated
arm). A policy trained on handheld (human) data is evaluated on the robot with ``--embodiment pusher``.
A policy trained on real phone images is not meaningful in the renderer: use ``eval_offline.py`` for it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the package root

import argparse
import json
import os
import sys
from pathlib import Path

if sys.platform.startswith("linux"):  # headless EGL rendering on Linux; macOS uses its default (CGL)
    os.environ.setdefault("MUJOCO_GL", "egl")

import numpy as np  # noqa: E402
import torch  # noqa: E402

from rebot_sim.recording import TOOL_ROBOT_TYPES  # noqa: E402
from rebot_sim.tool_env import ToolPushEnv  # noqa: E402


def default_device() -> str:
    """CUDA (Linux / cloud GPU), then Apple Silicon MPS (macOS), then CPU."""
    if torch.cuda.is_available():
        return "cuda"
    return "mps" if torch.backends.mps.is_available() else "cpu"


def dataset_camera_keys(path: str, cfg) -> tuple[str, ...]:
    """Image keys the policy expects *from the dataset / robot*. Fine-tuned VLAs (SmolVLA) keep the base model's
    camera names (camera1..3) and rename the dataset keys in their preprocessor; padded "empty_camera_*" slots
    need no input. Returns the dataset-side names, e.g. ("phone",)."""
    import json
    from pathlib import Path as _P

    rename = {}
    pre = _P(path) / "policy_preprocessor.json"
    if pre.exists():
        for step in json.loads(pre.read_text()).get("steps", []):
            rename.update(step.get("config", {}).get("rename_map", {}) or {})
    inverse = {v: k for k, v in rename.items()}
    keys = []
    for k in cfg.input_features:
        if not k.startswith("observation.images.") or "empty_camera" in k:
            continue
        k = inverse.get(k, k)
        if k in inverse.values() or not rename:  # renamed from a dataset key, or no renaming at all
            keys.append(k.removeprefix("observation.images."))
    return tuple(dict.fromkeys(keys))


def load_policy(path: str, device: str, temporal_ensemble: float | None = None):
    """Load a LeRobot policy + its pre/post processors. ``temporal_ensemble`` (ACT only, e.g. 0.01) enables
    ACT's temporal ensembling: predict at every step and average the overlapping chunks (smooth, no re-planning
    jumps); it implies n_action_steps = 1 and must be set before the model is built."""
    from lerobot.configs import PreTrainedConfig
    from lerobot.policies import get_policy_class, make_pre_post_processors

    cfg = PreTrainedConfig.from_pretrained(path)
    cfg.device = device
    if temporal_ensemble is not None:
        if cfg.type != "act":
            raise SystemExit("--temporal-ensemble works only with ACT")
        cfg.temporal_ensemble_coeff = temporal_ensemble
        cfg.n_action_steps = 1
    policy = get_policy_class(cfg.type).from_pretrained(path, config=cfg)
    policy.to(device).eval()
    pre, post = make_pre_post_processors(
        cfg, pretrained_path=path, preprocessor_overrides={"device_processor": {"device": device}}
    )
    return cfg, policy, pre, post


def save_video(frames: list[np.ndarray], path: Path, fps: int) -> None:
    import av

    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), "w") as out:
        stream = out.add_stream("libx264", rate=fps)
        stream.height, stream.width = frames[0].shape[:2]
        stream.pix_fmt = "yuv420p"
        for f in frames:
            for pkt in stream.encode(av.VideoFrame.from_ndarray(f, format="rgb24")):
                out.mux(pkt)
        for pkt in stream.encode():
            out.mux(pkt)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policy-path", required=True)
    ap.add_argument("--task", choices=["push_cube", "push_t"], default="push_cube")
    ap.add_argument("--embodiment", choices=["handheld", "pusher"], default="pusher",
                    help="handheld: the tool held by the simulated human; pusher: the tool on the simulated arm")
    ap.add_argument("--n-action-steps", type=int, default=None, help="override the number of actions executed per inference (ACT default 100)")
    ap.add_argument("--delta-reference", choices=["command", "measured"], default="command",
                    help="delta actions accumulate on the commanded pose or on the measured pose (pusher only)")
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--max-steps", type=int, default=600, help="maximum steps per episode (30 Hz)")
    ap.add_argument("--seed", type=int, default=100000, help="first evaluation seed (disjoint from the training seeds)")
    ap.add_argument("--image-size", default="480x640")
    ap.add_argument("--video-dir", default=None, help="directory for the videos of the evaluation episodes")
    ap.add_argument("--max-videos", type=int, default=5)
    ap.add_argument("--device", default=default_device())
    args = ap.parse_args()

    from lerobot.common.control_utils import predict_action

    cfg, policy, pre, post = load_policy(args.policy_path, args.device)
    if args.n_action_steps is not None:
        policy.config.n_action_steps = args.n_action_steps
    cameras = dataset_camera_keys(args.policy_path, cfg)
    print(f"policy {cfg.type}, input cameras {cameras}")
    h, w = (int(v) for v in args.image_size.lower().split("x"))
    action_dim = cfg.output_features["action"].shape[0]
    action_mode = {6: "delta", 9: "episode"}[action_dim]
    print(f"tool action representation: {action_mode}")
    env = ToolPushEnv(args.task, embodiment=args.embodiment, cameras=cameras, image_size=(h, w),
                      episode_length=args.max_steps, render_camera="front", delta_reference=args.delta_reference,
                      action_mode=action_mode)
    robot_type = TOOL_ROBOT_TYPES[args.embodiment]
    device = torch.device(args.device)

    results = []
    for ep in range(args.episodes):
        obs, _ = env.reset(seed=args.seed + ep)
        policy.reset()
        frames, success, steps = [], False, 0
        for steps in range(1, args.max_steps + 1):
            lerobot_obs = {"observation.state": obs["agent_pos"]}
            for cam in cameras:
                lerobot_obs[f"observation.images.{cam}"] = obs["pixels"][cam]
            action = predict_action(lerobot_obs, policy, device, pre, post, use_amp=False,
                                    task=env.task.description, robot_type=robot_type)
            action = action.squeeze(0).cpu().numpy()
            obs, reward, terminated, truncated, info = env.step(action)
            if args.video_dir and ep < args.max_videos:
                views = [obs["pixels"][c] for c in cameras]
                views.append(env.render())  # third-person view next to the phone view
                frames.append(np.concatenate(views, axis=1) if views else env.render())
            if terminated or truncated:
                success = bool(info["is_success"])
                break
        metric = {k: float(v) for k, v in info.items() if k != "is_success" and np.ndim(v) == 0}
        results.append({"episode": ep, "seed": args.seed + ep, "success": success, "steps": steps, **metric})
        print(f"episode {ep}: {'success' if success else 'failure'}, {steps} steps, {metric}")
        if frames:
            save_video(frames, Path(args.video_dir) / f"episode_{ep:03d}.mp4", env.metadata["render_fps"])

    rate = np.mean([r["success"] for r in results])
    print(f"\nsuccess rate: {rate:.1%} ({sum(r['success'] for r in results)}/{len(results)})")
    if args.video_dir:
        Path(args.video_dir).mkdir(parents=True, exist_ok=True)
        (Path(args.video_dir) / "results.json").write_text(
            json.dumps({"policy": args.policy_path, "task": args.task, "success_rate": rate, "episodes": results},
                       indent=2, ensure_ascii=False)
        )
    env.close()


if __name__ == "__main__":
    main()
