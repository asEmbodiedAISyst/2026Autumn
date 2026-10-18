"""Offline (open-loop) evaluation of a pusher-tool policy on recorded episodes ("episode" format).

At anchor frames of the chosen (held-out) episodes the policy predicts its action chunk from the recorded
observation; the predicted tool poses 1, 10 and 30 frames ahead (about 0.03 / 0.33 / 1 s at 30 Hz) are compared
with what the human actually did. This is the evaluation that works for
policies trained on *real* phone images, which cannot be tested closed-loop in the MuJoCo renderer (the images look
different) until the real robot is available. A "hold still" baseline (predict the current pose) is reported for
comparison: a useful policy should beat it clearly at the longer horizons.

Example (train on episodes 0-39, evaluate on 40-49)::

    uv run lerobot-train ... --dataset.episodes="[0,1,...,39]"
    uv run python scripts/eval_offline.py --policy-path outputs/train/act_real/checkpoints/last/pretrained_model \\
        --root datasets/real_push_cube --episodes 40-49
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the package root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_policy import dataset_camera_keys, default_device, load_policy  # noqa: E402

from rebot_sim.pose import from_rot6d  # noqa: E402


def parse_episodes(spec: str) -> list[int]:
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def pose_error(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Position (mm) and rotation (deg) difference between two 9-D episode-frame poses."""
    Ra, Rb = from_rot6d(a[3:9]), from_rot6d(b[3:9])
    ang = np.degrees(np.arccos(np.clip((np.trace(Ra.T @ Rb) - 1) / 2, -1, 1)))
    return float(np.linalg.norm(a[:3] - b[:3]) * 1000), float(ang)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policy-path", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--repo-id", default="local/offline_eval")
    ap.add_argument("--episodes", required=True, help="e.g. 40-49 or 3,7,12")
    ap.add_argument("--stride", type=int, default=10, help="frames between two evaluation anchors")
    ap.add_argument("--device", default=default_device())
    args = ap.parse_args()
    horizons = (1, 10, 30)

    from lerobot.common.control_utils import predict_action
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    cfg, policy, pre, post = load_policy(args.policy_path, args.device)
    H = max(horizons)
    policy.config.n_action_steps = H  # one chunk per anchor, then pop H actions from the queue
    device = torch.device(args.device)
    cams = [f"observation.images.{c}" for c in dataset_camera_keys(args.policy_path, cfg)]
    err = {h: [] for h in horizons}
    base = {h: [] for h in horizons}
    for ep in parse_episodes(args.episodes):
        ds = LeRobotDataset(args.repo_id, root=args.root, episodes=[ep])
        actions = np.stack([ds.hf_dataset[i]["action"].numpy() for i in range(len(ds))])
        for t in range(0, len(ds) - H, args.stride):
            f = ds[t]
            obs = {"observation.state": f["observation.state"].numpy()}
            for k in cams:
                obs[k] = f[k].permute(1, 2, 0).numpy()  # HWC float in [0, 1]
            policy.reset()
            chunk = [predict_action(obs, policy, device, pre, post, use_amp=False, task=f["task"]).squeeze(0).cpu().numpy()
                     for _ in range(H)]
            for h in horizons:  # action at index h-1 = target pose h frames after the anchor
                err[h].append(pose_error(chunk[h - 1], actions[t + h - 1]))
                base[h].append(pose_error(f["observation.state"].numpy(), actions[t + h - 1]))
        print(f"episode {ep}: " + ", ".join(
            f"{h} frames ahead {np.mean([e[0] for e in err[h][-((len(ds) - H - 1) // args.stride + 1):]]):.1f} mm" for h in horizons))
    print("\nOverall (prediction / hold-still baseline):")
    for h in horizons:
        e, b = np.array(err[h]), np.array(base[h])
        print(f"  {h:2d} frames ahead ({h / 30:.2f} s): position {e[:, 0].mean():5.1f} / {b[:, 0].mean():5.1f} mm, "
              f"rotation {e[:, 1].mean():4.1f} / {b[:, 1].mean():4.1f} deg")


if __name__ == "__main__":
    main()
