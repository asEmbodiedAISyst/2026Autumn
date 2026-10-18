"""Checks without hardware: pose maths, model loading, the simulated arm env, and the two recording paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("MUJOCO_GL", "egl")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from rebot_sim.pose import EpisodeFrame, from_rot6d, rot_z, rotvec_to_matrix, to_rot6d  # noqa: E402
from rebot_sim.robot import PUSHER_HOME_QPOS, TCP_DOWN_ROT  # noqa: E402
from rebot_sim.sim import HandheldToolSim, RebotSim  # noqa: E402
from rebot_sim.teleop.phone import RigidPhoneMapper  # noqa: E402


def test_rot6d_roundtrip():
    rng = np.random.default_rng(0)
    for _ in range(20):
        R = rotvec_to_matrix(rng.normal(size=3))
        np.testing.assert_allclose(from_rot6d(to_rot6d(R)), R, atol=1e-9)


def test_episode_frame_is_invariant_to_world_yaw_and_translation():
    rng = np.random.default_rng(1)
    p0, R0 = rng.normal(size=3), rot_z(0.3) @ TCP_DOWN_ROT
    p1, R1 = p0 + rng.normal(size=3), rotvec_to_matrix(0.2 * rng.normal(size=3)) @ R0
    a = EpisodeFrame(p0, R0).encode(p1, R1)
    W, t = rot_z(1.1), rng.normal(size=3)  # the same motion seen in a frame rotated about gravity and moved
    b = EpisodeFrame(W @ p0 + t, W @ R0).encode(W @ p1 + t, W @ R1)
    np.testing.assert_allclose(a, b, atol=1e-9)


def test_models_load_and_share_the_camera_to_tip_transform():
    hand = RigidPhoneMapper.from_model(HandheldToolSim("handheld_table", cameras=()).model)
    robot = RigidPhoneMapper.from_model(RebotSim("pusher_table", cameras=()).model)
    np.testing.assert_allclose(hand.R_cam_tcp, robot.R_cam_tcp, atol=1e-9)
    np.testing.assert_allclose(hand.p_cam_tcp, robot.p_cam_tcp, atol=1e-9)


def test_sim_arm_env_reaches_the_start_pose_and_steps():
    from rebot_sim.real.arm import SimArm
    from rebot_sim.real.camera import SimCamera
    from rebot_sim.real.env import RealToolPushEnv
    from rebot_sim.tool_env import TOOL_START_POS, make_tool_task

    arm = SimArm("pusher_push_cube")
    env = RealToolPushEnv(arm, SimCamera(arm), sim_task=make_tool_task("push_cube"), start_noise=False)
    arm.sim.init_renderer()
    obs, info = env.reset(seed=0)
    p, _ = env.tool_pose()
    assert np.linalg.norm(p - TOOL_START_POS) < 0.01
    assert obs["pixels"]["phone"].shape == (480, 640, 3)
    for _ in range(10):
        obs, _, _, _, info = env.step(env.action_to(env.ctrl.target_pos + np.array([0.001, 0, 0])))
    assert info["ik_ok"] and info["applied_action"].shape == (9,)
    env.close()


@pytest.mark.skipif(pytest.importorskip("lerobot", reason="lerobot not installed") is None, reason="lerobot")
def test_handheld_and_teleop_datasets_have_the_same_features(tmp_path, monkeypatch):
    """record_handheld.py (fake phone, test mode) and the teleoperation recorder write identical features."""
    import socket

    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    import record_handheld
    from rebot_sim.recording import DatasetRecorder, tool_feature_names
    from rebot_sim.teleop.fake_phone import FakePhonePublisher, tool_vertical_quat

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    pub = FakePhonePublisher(port=port, pattern="circle", quat=tool_vertical_quat(), image=True)
    try:
        monkeypatch.setattr(sys, "argv", ["record_handheld.py", "--phone-ip", "127.0.0.1", "--phone-port", str(port),
                                          "--repo-id", "local/a", "--root", str(tmp_path / "a"), "--auto", "1",
                                          "--no-layout"])
        record_handheld.main()
    finally:
        pub.close()
    b = DatasetRecorder("local/b", 30, ("phone",), (480, 640), root=str(tmp_path / "b"),
                        robot_type="rebot_pusher_tool_real", **tool_feature_names("episode"))
    img = np.zeros((480, 640, 3), np.uint8)
    for i in range(12):
        s9 = np.full(9, i, dtype=np.float32)
        b.add_frame(s9, s9 + 1, {"phone": img}, "t")
    b.save_episode()
    b.finalize()
    ma = LeRobotDataset("local/a", root=str(tmp_path / "a")).meta
    mb = LeRobotDataset("local/b", root=str(tmp_path / "b")).meta
    assert ma.total_episodes == 1
    assert {k: (v["dtype"], tuple(v["shape"]), v.get("names")) for k, v in ma.features.items()} == \
           {k: (v["dtype"], tuple(v["shape"]), v.get("names")) for k, v in mb.features.items()}
    assert ma.robot_type == mb.robot_type == "rebot_pusher_tool_real"
