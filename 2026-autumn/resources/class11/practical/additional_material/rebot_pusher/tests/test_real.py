"""Real-robot pusher pipeline, tested without hardware (stub follower / MuJoCo arm backend)."""

import math
from types import SimpleNamespace

import numpy as np
import pytest

from rebot_sim.real.arm import ARM_MOTORS, RealArm, SimArm
from rebot_sim.real.camera import SimCamera
from rebot_sim.real.env import RealToolPushEnv
from rebot_sim.robot import DIRECTIONS
from rebot_sim.tool_env import TOOL_START_POS, make_tool_task


class StubMotor:
    def __init__(self, follower=None, index=0):
        self.mit = []
        self.zeroed = False
        self.follower, self.index = follower, index

    def send_mit(self, *args):
        self.mit.append(args)

    def get_state(self):
        if self.follower is None:
            return None
        return SimpleNamespace(pos=math.radians(self.follower.motor_deg[self.index]), vel=0.0, torq=0.0, t_mos=30.0,
                               status_code=0)

    def set_zero_position(self):
        self.zeroed = True


class StubFollower:
    """Mimics seeed_b601_rs_follower: observation = motor deg, motor target = action * direction."""

    def __init__(self, motor_deg):
        self.motor_deg = np.array(motor_deg, dtype=float)
        self.sent = None
        self.is_connected = True
        self.motors = {m: StubMotor(self, i) for i, m in enumerate(ARM_MOTORS)}
        self.torque_disabled = False
        self._skip_safe_zero_on_disconnect = False

    def disable_torque(self):
        self.torque_disabled = True

    def get_observation(self):
        return {f"{m}.pos": float(v) for m, v in zip(ARM_MOTORS, self.motor_deg)}

    def send_action(self, action):
        self.sent = np.array([action[f"{m}.pos"] for m in ARM_MOTORS]) * DIRECTIONS[:6]
        return action


def test_real_arm_units_and_jump_guard():
    arm = RealArm(filter_tau=0.0, max_step_deg=30.0)  # no filter / rate limit: the motor target is exactly the command
    arm.robot = StubFollower([0.0, 30.0, 40.0, -20.0, 5.0, 0.0])
    q = arm.read_q()
    np.testing.assert_allclose(np.degrees(q), [0.0, 30.0, 40.0, -20.0, 5.0, 0.0])
    target = q + np.radians([1.0, -2.0, 3.0, -4.0, 5.0, 6.0])
    arm.command_q(target)
    np.testing.assert_allclose(arm.robot.sent, np.degrees(target))  # motor target = degrees(joint angle)
    with pytest.raises(RuntimeError):
        arm.command_q(q + np.radians([0, 40.0, 0, 0, 0, 0]))  # refuse large jumps


def test_real_arm_target_filter_and_gains():
    arm = RealArm(fps=30, filter_tau=0.1, kp_scale=0.8)
    assert 0.6 < arm._keep < 0.8  # exp(-1/3)
    arm.robot = StubFollower([0.0, 30.0, 40.0, -20.0, 5.0, 0.0])
    q = arm.read_q()
    target = q + np.radians([0, 10.0, 0, 0, 0, 0])
    sent = [arm.command_q(target) or arm.robot.sent.copy() for _ in range(60)]
    assert 30.0 < sent[0][1] < 35.0  # first command moves only a fraction of the way
    assert np.all(np.diff([s[1] for s in sent]) >= -1e-9) and abs(sent[-1][1] - 40.0) < 0.1  # converges
    arm.disable_torque()
    assert arm._q_filt is None and arm._q_prev is None  # filter and rate limit restart from the measured pose
    with pytest.raises(ValueError):
        RealArm(kp_scale=0)


def test_lag_and_stall_detection(monkeypatch):
    import rebot_sim.real.arm as arm_mod

    clock = [100.0]
    monkeypatch.setattr(arm_mod.time, "monotonic", lambda: clock[0])
    arm = RealArm(fps=30, filter_tau=0.0, max_step_deg=30.0)
    arm.robot = StubFollower([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])  # the stub arm never moves
    q = arm.read_q()
    arm.command_q(q + np.radians([0, 5.0, 0, 0, 0, 0]))
    arm.read_q()
    assert arm.lag_deg() == pytest.approx(5.0)
    arm.check_stall()  # 5 deg is lag, not a stall
    arm.command_q(q + np.radians([0, 20.0, 0, 0, 0, 0]))
    arm.read_q()
    assert arm.lag_deg() == pytest.approx(20.0)
    arm.check_stall()  # lag episode starts: no error yet
    clock[0] += 0.5
    arm.check_stall()  # still inside the time window
    clock[0] += 0.6
    with pytest.raises(RuntimeError, match="is stuck"):
        arm.check_stall()
    assert arm.robot.torque_disabled
    # a lagging joint that keeps moving is not a stall
    arm2 = RealArm(fps=30, filter_tau=0.0, max_step_deg=30.0)
    arm2.robot = StubFollower([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    q = arm2.read_q()
    arm2.command_q(q + np.radians([0, 20.0, 0, 0, 0, 0]))
    for k in range(5):
        arm2.robot.motor_deg[1] = 2.0 * (k + 1)  # moves 2 deg per check
        arm2.read_q()
        arm2.check_stall()
        clock[0] += 0.6
    assert not arm2.robot.torque_disabled


def test_jump_guard_is_relative_to_previous_target():
    arm = RealArm(fps=30, filter_tau=0.0, max_step_deg=30.0)
    arm.robot = StubFollower([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    q = arm.read_q()
    arm.command_q(q + np.radians([0, 20.0, 0, 0, 0, 0]))
    arm.command_q(q + np.radians([0, 40.0, 0, 0, 0, 0]))  # 20 deg from the previous target: fine although the arm lags 40
    with pytest.raises(RuntimeError, match="IK"):
        arm.command_q(q + np.radians([0, 70.0, 0, 0, 0, 0]))  # 30 deg jump in one cycle


def test_real_env_slows_down_while_the_arm_lags(monkeypatch):
    arm = SimArm("pusher_push_cube")
    env = RealToolPushEnv(arm, SimCamera(arm), start_noise=False)
    arm.sim.init_renderer()
    try:
        env.reset(seed=0)
        step = env.ctrl.limits.max_speed / env.fps
        monkeypatch.setattr(arm, "lag_deg", lambda: 40.0)  # twice SLOW_LAG_DEG: frozen
        p0 = env.ctrl.target_pos.copy()
        _, _, _, _, info = env.step(env.action_to(p0 + np.array([0.05, 0, 0])))
        assert info["lagging"] and info["ik_ok"] and info["speed_factor"] == 0.0
        np.testing.assert_allclose(env.ctrl.target_pos, p0)  # target not advanced
        monkeypatch.setattr(arm, "lag_deg", lambda: 30.0)  # halfway: half speed
        _, _, _, _, info = env.step(env.action_to(p0 + np.array([0.05, 0, 0])))
        assert info["speed_factor"] == pytest.approx(0.5)
        assert np.linalg.norm(env.ctrl.target_pos - p0) == pytest.approx(0.5 * step, rel=1e-6)
        assert env.ctrl.limits.max_speed == pytest.approx(step * env.fps)  # limit restored
        monkeypatch.setattr(arm, "lag_deg", lambda: 15.0)  # below SLOW_LAG_DEG: full speed
        p1 = env.ctrl.target_pos.copy()
        _, _, _, _, info = env.step(env.action_to(p0 + np.array([0.05, 0, 0])))
        assert not info["lagging"] and np.linalg.norm(env.ctrl.target_pos - p1) == pytest.approx(step, rel=1e-6)
    finally:
        env.close()


def test_gravity_feedforward_from_pusher_model():
    import mujoco

    from rebot_sim.sim import RebotSim

    arm = RealArm(gravity_compensation=True, gravity_scale=1.0)
    arm.robot = StubFollower([0.0, 54.5, 40.2, -15.7, 0.0, 0.0])
    arm._install_gravity_model()
    try:
        assert arm.robot._gravity_feedforward() == {}  # nothing measured yet
        arm.read_q()
        ff = arm.robot._gravity_feedforward()
        ref = RebotSim("pusher_table", cameras=())
        mujoco.mj_resetData(ref.model, ref.data)
        ref.data.qpos[ref.arm_qadr] = np.radians([0.0, 54.5, 40.2, -15.7, 0.0, 0.0])
        mujoco.mj_forward(ref.model, ref.data)
        expected = ref.data.qfrc_bias[ref.arm_dofadr]
        ref.close()
        np.testing.assert_allclose([ff[m] for m in ARM_MOTORS], expected, atol=1e-6)
        assert 3.0 < ff["elbow_flex"] < 8.0  # the elbow carries the forearm + tool
        arm.gravity_scale = 0.5
        np.testing.assert_allclose(arm.gravity_torques(), expected * 0.5, atol=1e-6)
    finally:
        arm._gsim.close()
    assert RealArm(gravity_compensation=False).gravity_torques().tolist() == [0.0] * 6


def test_real_arm_rate_limit_is_relative_to_previous_target():
    arm = RealArm(fps=30, filter_tau=0.0, max_step_deg=3.0)
    arm.robot = StubFollower([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])  # the stub arm does not move at all
    q = arm.read_q()
    target = q + np.radians([0, 20.0, 0, 0, 0, 0])
    sent = [arm.command_q(target) or arm.robot.sent.copy() for _ in range(5)]
    np.testing.assert_allclose([s[1] for s in sent], [3.0, 6.0, 9.0, 12.0, 15.0])  # keeps advancing although the arm lags
    assert arm.robot.sent[1] == 15.0  # the plugin, not RealArm, applies the max_error_deg clamp


def test_move_to_staged_opens_shoulder_and_elbow_first():
    from rebot_sim.real.arm import move_to_staged

    arm = RealArm(fps=200, filter_tau=0.0)
    arm.robot = StubFollower([0.0, 0.0, 0.0, 0.0, 0.0, -40.0])  # folded, wrist roll off zero
    target = np.radians([10.0, 54.5, 40.2, -15.7, 5.0, 0.0])
    arm.robot.sent_all = []
    orig = arm.robot.send_action

    def record(action):
        out = orig(action)
        arm.robot.motor_deg = arm.robot.sent.copy()  # the stub arm follows the target exactly
        arm.robot.sent_all.append(arm.robot.sent.copy())
        return out

    arm.robot.send_action = record
    move_to_staged(arm, target, speed_deg_s=400.0)
    sent = np.array(arm.robot.sent_all)
    np.testing.assert_allclose(sent[-1], np.degrees(target), atol=1e-6)
    first_wrist_move = np.flatnonzero(np.abs(sent[:, 3] - 0.0) > 1e-9)[0]
    assert np.allclose(sent[:first_wrist_move, 0], 0.0) and np.allclose(sent[:first_wrist_move, 5], -40.0)  # base, roll held
    assert np.allclose(sent[first_wrist_move:, 1], 54.5) and np.allclose(sent[first_wrist_move:, 2], 40.2)  # arm already open


def test_set_zero_only_selected_motors(monkeypatch):
    import rebot_sim.real.arm as arm_mod

    monkeypatch.setattr(arm_mod.time, "sleep", lambda s: None)
    arm = RealArm()
    arm.robot = StubFollower([0.0, 30.0, 40.0, -20.0, 5.0, 0.0])
    arm.set_zero(["wrist_roll"])
    assert arm.robot.torque_disabled
    assert [m for m, mot in arm.robot.motors.items() if mot.zeroed] == ["wrist_roll"]


def test_no_camera_backend():
    from rebot_sim.real.camera import NoCamera

    cam = NoCamera()
    assert cam.wait(0.0) and cam.read()[0] is None and cam.read()[1] == float("inf")


def test_real_arm_requests_feedback_only_when_idle(monkeypatch):
    import rebot_sim.real.arm as arm_mod

    monkeypatch.setattr(arm_mod.time, "sleep", lambda s: None)
    arm = RealArm()
    arm.robot = StubFollower([0.0, 30.0, 40.0, -20.0, 5.0, 0.0])
    q = arm.read_q()  # idle: zero-gain frame to every motor requests the reply
    assert all(m.mit == [(0.0, 0.0, 0.0, 0.0, 0.0)] for m in arm.robot.motors.values())
    arm.command_q(q)  # holding: the command is the request, no zero-gain frames any more
    arm.read_q()
    arm.read_q()
    assert all(len(m.mit) == 1 for m in arm.robot.motors.values())
    arm.disable_torque()  # read-only again
    assert arm.robot.torque_disabled and arm.robot._skip_safe_zero_on_disconnect
    arm.read_q()
    assert all(len(m.mit) == 2 for m in arm.robot.motors.values())


def test_plugin_config_without_gripper(tmp_path):
    pytest.importorskip("lerobot_robot_seeed_b601")
    from lerobot_robot_seeed_b601 import SeeedB601RSFollower, SeeedB601RSFollowerConfig

    from rebot_sim.real.arm import ensure_calibration_file

    d = SeeedB601RSFollowerConfig(port="can0")
    cfg = SeeedB601RSFollowerConfig(port="can0", id="test_pusher", calibration_dir=tmp_path,
                                    motor_can_ids={m: d.motor_can_ids[m] for m in ARM_MOTORS},
                                    joint_limits={m: d.joint_limits[m] for m in ARM_MOTORS},
                                    joint_directions={m: d.joint_directions[m] for m in ARM_MOTORS})
    robot = SeeedB601RSFollower(cfg)
    assert list(robot.action_features) == [f"{m}.pos" for m in ARM_MOTORS]
    np.testing.assert_allclose([d.joint_directions[m] for m in ARM_MOTORS], DIRECTIONS[:6])
    assert ensure_calibration_file(robot) and (tmp_path / "test_pusher.json").is_file()
    assert set(robot.calibration) == set(ARM_MOTORS)  # 6 motors, no gripper entry
    assert SeeedB601RSFollower(cfg).is_calibrated  # a new instance loads it: connect() will not re-zero


def test_real_env_refuses_unreachable_targets():
    from rebot_sim.teleop.tool_controller import ToolLimits

    limits = ToolLimits(x=(0.10, 0.90), y=(-0.5, 0.5), z=(0.003, 0.30), max_speed=5.0)  # box far beyond reach
    arm = SimArm("pusher_push_cube")
    env = RealToolPushEnv(arm, SimCamera(arm), start_noise=False, limits=limits)
    arm.sim.init_renderer()
    try:
        env.reset(seed=0)
        far = np.array([0.90, 0.0, 0.10])  # 90 cm ahead: beyond reach; the controller walks towards it
        refused = False
        for _ in range(30):
            q_before, p_before = env.q_cmd.copy(), env.ctrl.target_pos.copy()
            obs, _, _, _, info = env.step(env.action_to(far))
            if not info["ik_ok"]:
                refused = True
                np.testing.assert_allclose(env.q_cmd, q_before)  # refused: previous joint command kept
                np.testing.assert_allclose(env.ctrl.target_pos, p_before)  # commanded pose rolled back
                break
        assert refused and 0.5 < env.ctrl.target_pos[0] < 0.75  # stopped at the reach boundary, well inside the box
    finally:
        env.close()


def test_real_env_with_sim_arm_reaches_start_and_tracks():
    arm = SimArm("pusher_push_cube")
    env = RealToolPushEnv(arm, SimCamera(arm), start_noise=False, sim_task=make_tool_task("push_cube"))
    arm.sim.init_renderer()
    try:
        obs, info = env.reset(seed=0)
        p, _ = env.tool_pose()
        np.testing.assert_allclose(p, TOOL_START_POS, atol=5e-3)  # moved from the zero pose to the start pose
        np.testing.assert_allclose(obs["agent_pos"][:3], 0.0, atol=5e-3)
        assert obs["pixels"]["phone"].shape == (480, 640, 3)
        target = np.r_[0.04, -0.03, -0.05, obs["agent_pos"][3:]]
        for _ in range(45):
            obs, _, _, _, info = env.step(target)
        np.testing.assert_allclose(info["applied_action"], target, atol=1e-5)
        np.testing.assert_allclose(obs["agent_pos"][:3], target[:3], atol=5e-3)
    finally:
        env.close()


def test_check_can_up(tmp_path):
    from rebot_sim.real.arm import check_can_up

    (tmp_path / "can0").mkdir()
    (tmp_path / "can0" / "flags").write_text("0x40080\n")  # NOARP|ECHO, not UP
    with pytest.raises(SystemExit, match="DOWN"):
        check_can_up("can0", sysfs=str(tmp_path))
    (tmp_path / "can0" / "flags").write_text("0x40081\n")  # IFF_UP set
    check_can_up("can0", sysfs=str(tmp_path))
    with pytest.raises(SystemExit, match="not found"):
        check_can_up("can1", sysfs=str(tmp_path))
    check_can_up("/dev/ttyACM0", sysfs=str(tmp_path))  # serial bridges are not checked


def test_target_streamer_interpolates_with_velocity_feedforward():
    import time

    arm = RealArm(fps=30, filter_tau=0.0, max_step_deg=30.0, stream_hz=300, max_error_deg=10.0, gravity_compensation=False)
    arm._kp, arm._kd = np.array([40.0, 120.0, 120.0, 40.0, 40.0, 40.0]), np.array([2.4, 8.0, 8.0, 4.0, 3.2, 3.2])
    arm.robot = StubFollower([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])  # the stub arm stays at 0: the torque cap must bite
    q = arm.read_q()
    arm._start_stream()
    try:
        arm.command_q(q + np.radians([0, 12.0, 0, 0, 0, 0]))
        time.sleep(0.12)  # a few control periods: the streamer must have reached the target in ~33 ms
    finally:
        arm._stop_stream()
    mit = [m for m in arm.robot.motors["shoulder_lift"].mit if m[2] > 0]  # streamed frames (kp > 0), not the feedback pokes
    pos = np.degrees([m[0] for m in mit]); vel = np.degrees([m[1] for m in mit])
    assert len(mit) >= 10  # ~300 Hz streaming, not one send per control cycle
    assert np.all(np.diff(pos) >= -1e-9) and pos.max() == pytest.approx(10.0, abs=1e-6)  # ramp, capped at measured + 10 deg
    assert pos[0] < 10.0 and ((pos > 0.5) & (pos < 9.5)).sum() >= 3  # intermediate values, not one full step
    assert vel[0] == pytest.approx(12.0 * 30, rel=1e-6) and vel[-1] == 0.0  # feedforward during the ramp, 0 once there
    assert mit[0][2] == 120.0 and mit[0][3] == 8.0  # shoulder gains
    assert all(m[2] == 0.0 for m in arm.robot.motors["wrist_roll"].mit[:0])  # (no MIT before the stream started)
    assert arm.stream_error is None
    arm.disable_torque()  # streamer idles when nothing is held
    n = len(mit)
    arm._start_stream()
    time.sleep(0.05)
    arm._stop_stream()
    assert len([m for m in arm.robot.motors["shoulder_lift"].mit if m[2] > 0]) == n


def test_temperature_guard(monkeypatch):
    arm = RealArm()
    arm.robot = StubFollower([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    arm.read_q()  # 30 C: fine
    hot = SimpleNamespace(pos=0.0, vel=0.0, torq=0.0, t_mos=130.0, status_code=0)
    monkeypatch.setattr(arm.robot.motors["elbow_flex"], "get_state", lambda: hot)
    with pytest.raises(RuntimeError, match="temperature"):
        arm.read_q()
    assert arm.robot.torque_disabled
