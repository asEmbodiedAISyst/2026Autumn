"""Pusher tool (rod + phone): relative-pose math, handheld vs robot embodiments, rigid phone mapping."""

import time

import numpy as np
import pytest

from rebot_sim.pose import (
    EpisodeFrame,
    apply_delta,
    gravity_in_tool,
    limit_tilt,
    pose_delta,
    rot_z,
    rotvec_to_matrix,
    tilt_angle,
    yaw_of,
)
from rebot_sim.robot import PUSHER_HOME_QPOS, TCP_DOWN_ROT, TOOL_HOME_POS
from rebot_sim.sim import HandheldToolSim, RebotSim
from rebot_sim.teleop.phone import ARKIT_TO_ROBOT, PhonePose, RigidPhoneMapper
from rebot_sim.tool_env import ToolPushEnv


def _random_pose(rng):
    return rng.normal(size=3), rotvec_to_matrix(rng.normal(size=3))


def test_delta_roundtrip_and_frame_invariance():
    rng = np.random.default_rng(0)
    for _ in range(20):
        (p0, R0), (p1, R1) = _random_pose(rng), _random_pose(rng)
        d = pose_delta(p0, R0, p1, R1)
        p, R = apply_delta(p0, R0, d)
        np.testing.assert_allclose(p, p1, atol=1e-9)
        np.testing.assert_allclose(R, R1, atol=1e-9)
        # The same physical motion seen from another world frame gives the same delta
        Rw, tw = rotvec_to_matrix(rng.normal(size=3)), rng.normal(size=3)
        d2 = pose_delta(Rw @ p0 + tw, Rw @ R0, Rw @ p1 + tw, Rw @ R1)
        np.testing.assert_allclose(d2, d, atol=1e-9)


def test_tilt_limit_and_gravity():
    R = rotvec_to_matrix(np.array([1.0, 0.0, 0.0]) * np.radians(50)) @ TCP_DOWN_ROT
    assert abs(np.degrees(tilt_angle(R)) - 50) < 1e-6
    R_lim = limit_tilt(R, np.radians(30))
    assert abs(np.degrees(tilt_angle(R_lim)) - 30) < 1e-6
    np.testing.assert_allclose(gravity_in_tool(TCP_DOWN_ROT), [0, 0, 1], atol=1e-12)


def test_pusher_home_and_tool_geometry():
    sim = RebotSim("pusher_table", cameras=())
    sim.reset(PUSHER_HOME_QPOS)
    pos, R = sim.tcp_pose()
    np.testing.assert_allclose(pos, TOOL_HOME_POS, atol=2e-3)
    assert np.degrees(tilt_angle(R)) < 1.0
    assert not sim.has_gripper


def test_handheld_and_robot_phone_views_match():
    """Same tool pose -> nearly identical phone images (the robot never appears in the phone view)."""
    rng = np.random.default_rng(1)
    for emb_seed in range(2):
        envs = {e: ToolPushEnv("push_cube", embodiment=e, image_size=(120, 160), start_noise=False, action_mode="delta")
                for e in ("handheld", "pusher")}
        obs = {e: env.reset(seed=emb_seed)[0] for e, env in envs.items()}
        for _ in range(20):  # same relative commands on both
            a = np.r_[rng.uniform(-0.004, 0.004, 3), rng.uniform(-0.01, 0.01, 3)]
            obs = {e: env.step(a)[0] for e, env in envs.items()}
        for _ in range(15):  # let the robot catch up with its commanded pose
            obs = {e: env.step(np.zeros(6))[0] for e, env in envs.items()}
        diff = np.abs(obs["handheld"]["pixels"]["phone"].astype(int) - obs["pusher"]["pixels"]["phone"].astype(int))
        assert diff.mean() < 12, diff.mean()  # residual: robot shadow + small tracking error
        np.testing.assert_allclose(obs["handheld"]["agent_pos"], obs["pusher"]["agent_pos"], atol=0.02)
        for env in envs.values():
            env.close()


def test_applied_action_respects_limits():
    env = ToolPushEnv("push_cube", embodiment="handheld", obs_type="state", start_noise=False, action_mode="delta")
    env.reset(seed=0)
    _, _, _, _, info = env.step(np.array([0.5, 0, 0, 0, 0, 0]))  # 0.5 m in one step
    assert np.linalg.norm(info["applied_action"][:3]) <= env.ctrl.limits.max_speed * env.ctrl.dt + 1e-6
    _, _, _, _, info = env.step(np.array([0, 0, 0, 1.5, 0, 0]))  # large tilt
    assert np.degrees(tilt_angle(env.ctrl.target_rot)) <= env.ctrl.limits.max_tilt_deg + 1e-6
    for _ in range(60):  # keep turning about the rod: heading saturates at the yaw limit
        env.step(np.array([0, 0, 0, 0, 0, 0.1]))
    assert abs(np.degrees(yaw_of(env.ctrl.target_rot))) <= env.ctrl.limits.max_yaw_deg + 1e-6


@pytest.mark.parametrize("embodiment", ["handheld", "pusher"])
def test_rigid_phone_mapper_follows_phone(embodiment):
    sim = HandheldToolSim("handheld_table", cameras=()) if embodiment == "handheld" else RebotSim("pusher_table", cameras=())
    m = RigidPhoneMapper.from_model(sim.model)
    to_phone = lambda R_tcp, p_tcp: PhonePose(  # noqa: E731
        ARKIT_TO_ROBOT.T @ (p_tcp - (R_tcp @ m.R_cam_tcp.T) @ m.p_cam_tcp), ARKIT_TO_ROBOT.T @ R_tcp @ m.R_cam_tcp.T,
        0.0, time.monotonic())
    # real tool somewhere in the ARKit frame, vertical, arbitrary heading
    R_real, p_real = rot_z(2.0) @ TCP_DOWN_ROT, np.array([1.0, -0.4, 0.3])
    m.engage(to_phone(R_real, p_real), TOOL_HOME_POS, TCP_DOWN_ROT)
    # tilt the real tool 15 deg about its own y axis around the tip, then move the tip 5 cm along its x axis
    R2 = rotvec_to_matrix(R_real[:, 1] * np.radians(15)) @ R_real
    pos, R = m.map(to_phone(R2, p_real + R_real[:, 0] * 0.05))
    np.testing.assert_allclose(pos, TOOL_HOME_POS + TCP_DOWN_ROT[:, 0] * 0.05, atol=1e-9)
    assert abs(np.degrees(tilt_angle(R)) - 15) < 1e-6


def test_episode_frame_roundtrip_and_invariance():
    rng = np.random.default_rng(3)
    for _ in range(10):
        p0, R0 = rng.normal(size=3), rotvec_to_matrix(rng.normal(size=3) * 0.3) @ rot_z(rng.uniform(-3, 3))
        p, R = rng.normal(size=3), rotvec_to_matrix(rng.normal(size=3))
        f = EpisodeFrame(p0, R0)
        v = f.encode(p, R)
        p2, R2 = f.decode(v)
        np.testing.assert_allclose(p2, p, atol=1e-9)
        np.testing.assert_allclose(R2, R, atol=1e-9)
        # Rotating the whole world about gravity (another heading / ARKit session) gives the same encoding
        Rw, tw = rot_z(rng.uniform(-3, 3)), rng.normal(size=3)
        fw = EpisodeFrame(Rw @ p0 + tw, Rw @ R0)
        np.testing.assert_allclose(fw.encode(Rw @ p + tw, Rw @ R), v, atol=1e-9)


@pytest.mark.parametrize("embodiment", ["handheld", "pusher"])
def test_episode_mode_tracks_targets(embodiment):
    env = ToolPushEnv("push_cube", embodiment=embodiment, obs_type="state", action_mode="episode")
    obs, _ = env.reset(seed=2)
    np.testing.assert_allclose(obs["agent_pos"][:3], 0.0, atol=3e-3)  # starts at the frame origin
    target = np.r_[0.04, -0.03, -0.05, obs["agent_pos"][3:]]  # move 4 cm forward, 3 cm right, 5 cm down
    for _ in range(45):
        obs, _, _, _, info = env.step(target)
    np.testing.assert_allclose(info["applied_action"], target, atol=1e-5)
    np.testing.assert_allclose(obs["agent_pos"][:3], target[:3], atol=4e-3)


def test_ip17_tool_geometry():
    """Designer intent: the phone's main camera axis is coplanar with the rod and the tip is near the image centre."""
    sim = HandheldToolSim("handheld_table", cameras=())
    sim.reset(TOOL_HOME_POS, TCP_DOWN_ROT)
    d = sim.data
    cam = d.cam("phone")
    R_cam = cam.xmat.reshape(3, 3)
    tip = d.site("tcp").xpos
    v = R_cam.T @ (tip - cam.xpos)  # tip in the camera frame (camera looks along -z)
    assert v[2] < 0
    assert abs(np.degrees(np.arctan2(np.hypot(v[0], v[1]), -v[2]))) < 3.0  # tip within 3 deg of the optical axis
    # nominal pose: TCP frame = TCP_DOWN_ROT, rod tilted 30 deg forward
    rod = d.geom("tool_rod").xmat.reshape(3, 3)[:, 0]
    assert abs(np.degrees(np.arccos(abs(rod @ np.array([0, 0, -1.0])))) - 30.0) < 1.0


def test_rigid_mapper_relative_orientation_and_engage_blend(monkeypatch):
    import rebot_sim.teleop.phone as phone_mod
    from rebot_sim.pose import rot_z as rz

    clock = [10.0]
    monkeypatch.setattr(phone_mod.time, "monotonic", lambda: clock[0])
    R_cam_tcp, p_cam_tcp = np.eye(3), np.array([0.0, 0.0, -0.2])
    # the hand phone is tilted 20 deg about x; the robot tool is at a different orientation
    tilt = np.array([[1, 0, 0], [0, np.cos(0.35), -np.sin(0.35)], [0, np.sin(0.35), np.cos(0.35)]])
    phone = PhonePose(pos=np.array([0.1, 0.2, 0.3]), rot=ARKIT_TO_ROBOT.T @ tilt, stamp=0.0, recv_time=0.0)
    tcp_pos, tcp_rot = np.array([0.3, 0.0, 0.1]), rz(0.5)

    m_abs = RigidPhoneMapper(R_cam_tcp, p_cam_tcp, orientation="absolute", blend_s=1.0)
    m_abs.engage(phone, tcp_pos, tcp_rot)
    p0, R0 = m_abs.map(phone)
    np.testing.assert_allclose(p0, tcp_pos, atol=1e-9)  # position always continuous at engage
    np.testing.assert_allclose(R0, tcp_rot, atol=1e-9)  # blend starts at the robot's orientation
    clock[0] += 0.5
    _, R_half = m_abs.map(phone)
    clock[0] += 0.6
    _, R_end = m_abs.map(phone)
    assert not np.allclose(R_end, tcp_rot, atol=1e-3)  # absolute: ends at the phone's (tilted) orientation
    ang = lambda A, B: np.degrees(np.linalg.norm(phone_mod.matrix_to_rotvec(A @ B.T)))  # noqa: E731
    assert 0.3 * ang(R_end, tcp_rot) < ang(R_half, tcp_rot) < 0.7 * ang(R_end, tcp_rot)  # halfway through the blend

    m_rel = RigidPhoneMapper(R_cam_tcp, p_cam_tcp, orientation="relative", blend_s=0.0)
    m_rel.engage(phone, tcp_pos, tcp_rot)
    _, R = m_rel.map(phone)
    np.testing.assert_allclose(R, tcp_rot, atol=1e-9)  # relative: the hand pose at engage is the tool pose
    phone2 = PhonePose(pos=phone.pos, rot=phone.rot @ rz(0.2), stamp=0.0, recv_time=0.0)  # rotate the hand 0.2 rad about its own z
    _, R2 = m_rel.map(phone2)
    assert ang(R2, tcp_rot) == pytest.approx(np.degrees(0.2), abs=1e-6)  # followed relative to engage
    with pytest.raises(ValueError):
        RigidPhoneMapper(R_cam_tcp, p_cam_tcp, orientation="other")
