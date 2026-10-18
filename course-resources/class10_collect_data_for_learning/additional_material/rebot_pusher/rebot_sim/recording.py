"""Write simulation data as LeRobot v3 datasets with the same features as the real ``seeed_b601_rs_follower``.

Features of real datasets (``lerobot-record``):

* ``observation.state``: float32[7], ``shoulder_pan.pos ... gripper.pos``, motor angles (deg);
* ``action``: float32[7], same names, command space (deg), ``state ≈ action * [1,1,-1,-1,-1,1,6]``;
* ``observation.images.<cam>``: video (480, 640, 3).

The simulation can optionally add ``observation.environment_state`` (object poses). Real datasets do
not have it, so it is off by default to allow mixing simulated and real data for training.

Pusher-tool datasets (handheld or robot-mounted rod + phone, see :mod:`rebot_sim.tool_env`) use
``TOOL_STATE_NAMES`` / ``TOOL_ACTION_NAMES`` and the single camera ``phone`` instead.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .robot import MOTOR_NAMES

SIM_ROBOT_TYPE = "seeed_b601_rs_sim"
JOINT_NAMES = tuple(f"{m}.pos" for m in MOTOR_NAMES)

# Pusher-tool format: gravity in the tool frame as state, relative TCP motion in the tool frame as action
TOOL_STATE_NAMES = ("gravity_x", "gravity_y", "gravity_z")
TOOL_ACTION_NAMES = ("dx", "dy", "dz", "rx", "ry", "rz")
# Episode-frame variant (action_mode="episode"): position + rot6d for both state and action
TOOL_EPISODE_NAMES = ("x", "y", "z", "r11", "r21", "r31", "r12", "r22", "r32")


def tool_feature_names(action_mode: str) -> dict[str, tuple[str, ...]]:
    if action_mode == "delta":
        return {"state_names": TOOL_STATE_NAMES, "action_names": TOOL_ACTION_NAMES}
    return {"state_names": TOOL_EPISODE_NAMES, "action_names": TOOL_EPISODE_NAMES}
TOOL_ROBOT_TYPES = {"handheld": "rebot_pusher_tool_handheld", "pusher": "rebot_pusher_tool_robot"}


def motor_features() -> dict[str, type]:
    return {name: float for name in JOINT_NAMES}


def dataset_features(
    cameras: tuple[str, ...],
    image_size: tuple[int, int],
    env_state_dim: int | None = None,
    use_videos: bool = True,
    state_names: tuple[str, ...] = JOINT_NAMES,
    action_names: tuple[str, ...] = JOINT_NAMES,
) -> dict[str, dict]:
    from lerobot.utils.feature_utils import hw_to_dataset_features

    h, w = image_size
    obs_hw = {**{n: float for n in state_names}, **{cam: (h, w, 3) for cam in cameras}}
    feats = {
        **hw_to_dataset_features({n: float for n in action_names}, "action", use_videos),
        **hw_to_dataset_features(obs_hw, "observation", use_videos),
    }
    if env_state_dim:
        feats["observation.environment_state"] = {
            "dtype": "float32",
            "shape": (env_state_dim,),
            "names": [f"env_{i}" for i in range(env_state_dim)],
        }
    return feats


class DatasetRecorder:
    """Write a LeRobot dataset frame by frame.

    Usage::

        rec = DatasetRecorder("local/rebot_push_cube", fps=30, cameras=("front", "side"))
        rec.add_frame(state_deg, action_cmd, images, task="...")
        rec.save_episode()   # or rec.discard_episode()
        rec.finalize()
    """

    def __init__(
        self,
        repo_id: str,
        fps: int,
        cameras: tuple[str, ...],
        image_size: tuple[int, int] = (480, 640),
        root: str | Path | None = None,
        env_state_dim: int | None = None,
        resume: bool = False,
        robot_type: str = SIM_ROBOT_TYPE,
        state_names: tuple[str, ...] = JOINT_NAMES,
        action_names: tuple[str, ...] = JOINT_NAMES,
    ) -> None:
        from lerobot.datasets.lerobot_dataset import LeRobotDataset

        self.cameras = tuple(cameras)
        self.features = dataset_features(
            self.cameras, image_size, env_state_dim, state_names=state_names, action_names=action_names
        )
        if resume:
            self.dataset = LeRobotDataset.resume(repo_id, root=root)
        else:
            self.dataset = LeRobotDataset.create(
                repo_id,
                fps=fps,
                features=self.features,
                root=root,
                robot_type=robot_type,
                use_videos=True,
                image_writer_threads=4 * max(1, len(self.cameras)),
            )
        self.env_state = env_state_dim is not None
        self.n_frames = 0

    @property
    def num_episodes(self) -> int:
        return self.dataset.meta.total_episodes

    @property
    def root(self) -> Path:
        return Path(self.dataset.root)

    def add_frame(
        self,
        state: np.ndarray,
        action: np.ndarray,
        images: dict[str, np.ndarray],
        task: str,
        env_state: np.ndarray | None = None,
    ) -> None:
        frame: dict = {
            "observation.state": np.asarray(state, dtype=np.float32),
            "action": np.asarray(action, dtype=np.float32),
            "task": task,
        }
        for cam in self.cameras:
            frame[f"observation.images.{cam}"] = images[cam]
        if self.env_state:
            frame["observation.environment_state"] = np.asarray(env_state, dtype=np.float32)
        self.dataset.add_frame(frame)
        self.n_frames += 1

    def save_episode(self) -> None:
        if self.n_frames:
            self.dataset.save_episode()
        self.n_frames = 0

    def discard_episode(self) -> None:
        if self.n_frames:
            self.dataset.clear_episode_buffer()
        self.n_frames = 0

    def finalize(self) -> None:
        self.dataset.finalize()
