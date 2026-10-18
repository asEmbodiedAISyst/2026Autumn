import json

import numpy as np
import pytest

pytest.importorskip("lerobot")

from rebot_sim.recording import DatasetRecorder  # noqa: E402


def test_tool_format_dataset(tmp_path):
    from rebot_sim.recording import TOOL_ACTION_NAMES, TOOL_ROBOT_TYPES, TOOL_STATE_NAMES
    from rebot_sim.tool_env import ToolPushEnv

    root = tmp_path / "tool_ds"
    env = ToolPushEnv("push_t", embodiment="handheld", image_size=(64, 80), action_mode="delta")
    rec = DatasetRecorder("local/tool", 30, ("phone",), (64, 80), root=root, robot_type=TOOL_ROBOT_TYPES["handheld"],
                          state_names=TOOL_STATE_NAMES, action_names=TOOL_ACTION_NAMES)
    obs, _ = env.reset(seed=0)
    for _ in range(6):
        nxt, _, _, _, info = env.step(np.array([0.002, 0, 0, 0, 0, 0.01]))
        rec.add_frame(obs["agent_pos"], info["applied_action"], obs["pixels"], env.task.description)
        obs = nxt
    rec.save_episode()
    rec.finalize()
    env.close()
    info = json.loads((root / "meta" / "info.json").read_text())
    assert info["robot_type"] == "rebot_pusher_tool_handheld"
    assert info["features"]["action"]["names"] == list(TOOL_ACTION_NAMES)
    assert info["features"]["observation.state"]["shape"] == [3]
    assert "observation.images.phone" in info["features"]
