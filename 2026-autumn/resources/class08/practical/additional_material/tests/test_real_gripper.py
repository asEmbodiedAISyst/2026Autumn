"""Stock-arm (gripper) bring-up backend, tested without hardware (stub motorbridge motors / plugin stub).

Run from additional_material/: uv run --group dev pytest tests
"""

import math
from types import SimpleNamespace

import numpy as np
import pytest

from rebot_sim.real import gripper_arm as ga
from rebot_sim.real.gripper_arm import (
    ARM_MOTORS,
    MAX_JUMP_DEG,
    MOTOR_NAMES,
    GripperTwin,
    MotorSnapshot,
    RealGripperArm,
    TrackingError,
    ensure_calibration_file,
    format_table,
)
from rebot_sim.robot import DIRECTIONS


class StubMotor:
    def __init__(self, pos_deg: float):
        self.pos_deg = pos_deg
        self.mit = []  # raw send_mit calls (pos, vel, kp, kd, tau)
        self.zeroed = False
        self.missing = False

    def request_feedback(self):
        pass

    def get_state(self):
        if self.missing:
            return None
        return SimpleNamespace(pos=math.radians(self.pos_deg), vel=0.0, torq=0.1, t_mos=30.0, status_code=0)

    def send_mit(self, pos, vel, kp, kd, tau):
        self.mit.append((pos, vel, kp, kd, tau))

    def set_zero_position(self):
        self.zeroed = True
        self.pos_deg = 0.0


class StubFollower:
    """Mimics the parts of seeed_b601_rs_follower used by RealGripperArm (7 motors, follows targets if ``track``)."""

    def __init__(self, motor_deg, track=True):
        self.motors = {m: StubMotor(v) for m, v in zip(MOTOR_NAMES, motor_deg)}
        self.bus = SimpleNamespace(poll_feedback_once=lambda: None, disable_all=lambda: None)
        self.track = track
        self.sent = []  # motor targets (deg) derived from the actions
        self.torque_disabled = False
        self.is_connected = True
        self._skip_safe_zero_on_disconnect = False
        self.disconnected = False

    def send_action(self, action):
        motor = np.array([action.get(f"{m}.pos", np.nan) for m in MOTOR_NAMES]) * DIRECTIONS
        self.sent.append(motor)
        if self.track:
            for m, v in zip(MOTOR_NAMES, motor):
                if not np.isnan(v):
                    self.motors[m].pos_deg = v
        return action

    def disable_torque(self):
        self.torque_disabled = True

    def _gravity_feedforward(self):
        return {m: 1.0 + i for i, m in enumerate(ARM_MOTORS)}

    def disconnect(self):
        self.disconnected = True
        self.is_connected = False


def test_read_snapshot_and_missing_feedback():
    arm = RealGripperArm()
    arm.robot = StubFollower([0, 10, 20, -30, 5, 0, 90])
    snap = arm.read()
    np.testing.assert_allclose(snap.pos_deg, [0, 10, 20, -30, 5, 0, 90])
    assert snap.ok.all() and (snap.status == 0).all()
    np.testing.assert_allclose(np.degrees(snap.arm_q()), [0, 10, 20, -30, 5, 0])
    assert snap.gripper_m() == pytest.approx(90 / 270 * 0.05)
    arm.robot.motors["elbow_flex"].missing = True
    snap = arm.read()
    assert not snap.ok[2] and snap.pos_deg[2] == 20  # keeps the last value, flagged
    assert "NO FEEDBACK" in format_table(snap)[3]


def test_read_requests_feedback_only_when_idle(monkeypatch):
    monkeypatch.setattr(ga.time, "sleep", lambda s: None)
    arm = RealGripperArm()
    arm.robot = StubFollower([0, 10, 20, -30, 5, 0, 90])
    arm.read()  # nothing sent before: every motor gets a zero-gain MIT frame
    assert all(m.mit == [(0.0, 0.0, 0.0, 0.0, 0.0)] for m in arm.robot.motors.values())
    arms = [arm.robot.motors[m] for m in ARM_MOTORS]
    arm.hold()  # reads once more (poke), then holds: from now on the plugin command is the feedback request
    assert all(len(m.mit) == 2 for m in arms)
    assert len(arm.robot.motors["gripper"].mit) == 3  # gripper not active: one zero-torque frame per command
    arm.read()
    arm.read()
    assert all(len(m.mit) == 2 for m in arms)  # no zero-gain frame while holding
    arm.disable_torque()  # back to read-only: pokes again
    arm.read()
    assert all(len(m.mit) == 3 for m in arms)
    arm.gravity_compensation = True
    arm.send_gravity_only()  # gravity frames already request the reply
    arm.read()
    assert all(len(m.mit) == 4 for m in arms)


def test_gripper_zero_torque_unless_active():
    arm = RealGripperArm()
    arm.robot = StubFollower([0, 10, 20, -30, 5, 0, 90])
    arm.read()
    n0 = len(arm.robot.motors["gripper"].mit)
    arm.command(np.array([0, 10, 20, -30, 5, 0, 120.0]))
    assert np.isnan(arm.robot.sent[-1][6]) and arm.robot.motors["gripper"].mit[-1] == (0.0, 0.0, 0.0, 0.0, 0.0)
    assert len(arm.robot.motors["gripper"].mit) == n0 + 1 and arm.target[6] == 120.0
    arm.gripper_active = True
    arm.command(np.array([0, 10, 20, -30, 5, 0, 120.0]))
    assert arm.robot.sent[-1][6] == 120.0 and len(arm.robot.motors["gripper"].mit) == n0 + 1


def test_command_units_limits_and_jump_guard():
    arm = RealGripperArm()
    arm.gripper_active = True
    arm.robot = StubFollower([0, 10, 20, -30, 5, 0, 90])
    arm.read()
    sent = arm.command(np.array([1.0, 12.0, 23.0, -34.0, 10.0, 6.0, 120.0]))
    np.testing.assert_allclose(arm.robot.sent[-1], sent)  # action / direction round-trips to motor degrees
    np.testing.assert_allclose(sent, [1.0, 12.0, 23.0, -34.0, 10.0, 6.0, 120.0])
    clipped = arm.command(np.array([0, -5.0, 20, -30, 5, 0, 90]))  # shoulder_lift soft limit is [0, 170]
    assert clipped[1] == 0.0
    with pytest.raises(RuntimeError):
        arm.command(np.array([0, 10 + MAX_JUMP_DEG + 1, 20, -30, 5, 0, 90]))
    with pytest.raises(ValueError):
        arm.command(np.zeros(6))


def test_zero_torque_and_gravity_only_commands():
    arm = RealGripperArm(gravity_compensation=True)
    arm.robot = StubFollower([0, 30, 40, -20, 0, 0, 0])
    arm.send_zero_torque()
    assert all(m.mit[-1] == (0.0, 0.0, 0.0, 0.0, 0.0) for m in arm.robot.motors.values())
    arm.read()
    tau = arm.send_gravity_only(scale=0.5, damping=0.3, tau_max=2.0)
    np.testing.assert_allclose(tau, np.clip(0.5 * np.arange(1, 7), -2.0, 2.0))
    for i, m in enumerate(ARM_MOTORS):
        pos, vel, kp, kd, t = arm.robot.motors[m].mit[-1]
        assert (pos, vel, kp, kd) == (0.0, 0.0, 0.0, 0.3) and t == pytest.approx(tau[i])
    assert arm.robot.motors["gripper"].mit[-1] == (0.0, 0.0, 0.0, 0.0, 0.0)
    arm.gravity_compensation = False
    np.testing.assert_allclose(arm.gravity_torques(), 0.0)


def test_move_to_and_two_stage_return_to_zero():
    arm = RealGripperArm(fps=200)
    arm.gripper_active = True
    arm.robot = StubFollower([10, 30, 40, -20, 15, -10, 50])
    arm.hold()
    np.testing.assert_allclose(arm.robot.sent[-1], [10, 30, 40, -20, 15, -10, 50])
    target = arm.target.copy()
    target[0] = 20.0
    worst = arm.move_to(target, speed_deg_s=200.0)
    assert worst == pytest.approx(0.0, abs=1e-9)
    np.testing.assert_allclose(arm.target, target)
    steps = np.array(arm.robot.sent)
    assert np.all(np.diff(steps[:, 0]) >= -1e-9) and np.all(np.abs(np.diff(steps[:, 0])) <= 2.0)  # monotone, small steps
    n_before = len(arm.robot.sent)
    arm.return_to_zero(speed_deg_s=400.0)
    sent = np.array(arm.robot.sent[n_before:])
    np.testing.assert_allclose(arm.target[:6], 0.0)
    assert arm.target[6] == 50.0  # gripper untouched
    # stage 1 moves base / wrist while shoulder and elbow are held, stage 2 the other way round
    first_shoulder_move = np.flatnonzero(np.abs(sent[:, 1] - 30.0) > 1e-9)[0]
    assert np.allclose(sent[:first_shoulder_move, 1], 30.0) and np.allclose(sent[:first_shoulder_move, 2], 40.0)
    assert np.allclose(sent[first_shoulder_move:, 0], 0.0) and np.allclose(sent[first_shoulder_move:, 3], 0.0)


def test_tracking_guard_cuts_torque():
    arm = RealGripperArm(fps=200, abort_error_deg=5.0)
    arm.robot = StubFollower([0, 30, 40, -20, 0, 0, 0], track=False)  # the arm does not move at all
    arm.hold()
    target = arm.target.copy()
    target[1] = 45.0
    with pytest.raises(TrackingError):
        arm.move_to(target, speed_deg_s=500.0)
    assert arm.robot.torque_disabled and arm.target is None


def test_close_skips_plugin_safe_zero():
    arm = RealGripperArm()
    arm.robot = StubFollower([0, 0, 0, 0, 0, 0, 0])
    robot = arm.robot
    arm.close(return_to_zero=False)
    assert robot.disconnected and robot._skip_safe_zero_on_disconnect and arm.robot is None


def test_set_zero_here_disables_torque_first(monkeypatch):
    arm = RealGripperArm()
    arm.robot = StubFollower([1, 2, 3, 4, 5, 6, 7])
    calls = []
    arm.robot.bus = SimpleNamespace(poll_feedback_once=lambda: None, disable_all=lambda: calls.append("disable"))
    monkeypatch.setattr(ga.time, "sleep", lambda s: None)
    arm.set_zero_here()
    assert calls == ["disable"] and all(m.zeroed for m in arm.robot.motors.values())


def test_gravity_scale_and_offset_adjust_plugin_feedforward():
    arm = RealGripperArm(gravity_scale={"shoulder_lift": 0.5}, gravity_offset={"elbow_flex": -1.0})
    arm.robot = StubFollower([0, 30, 40, -20, 0, 0, 0])
    arm._install_gravity_adjust()
    arm._install_gravity_adjust()  # idempotent
    arm.read()
    tau = arm.gravity_torques()  # stub feedforward is 1..6 N*m
    np.testing.assert_allclose(tau, [1.0, 2.0 * 0.5, 3.0 - 1.0, 4.0, 5.0, 6.0])
    assert arm.robot._gravity_feedforward()["shoulder_lift"] == 1.0  # what send_action will add
    with pytest.raises(ValueError):
        RealGripperArm(gravity_scale={"gripper": 1.0})


def test_gravity_fit_term_uses_the_motor_angle():
    arm = RealGripperArm(gravity_fit={"shoulder_lift": (-1.0, 0.5)})
    arm.robot = StubFollower([0, 60, 40, -20, 0, 0, 0])
    arm._install_gravity_adjust()
    arm.read()
    tau = arm.gravity_torques()
    expected = 2.0 - 1.0 * math.cos(math.radians(60)) + 0.5 * math.sin(math.radians(60))
    assert tau[1] == pytest.approx(expected)
    np.testing.assert_allclose(np.delete(tau, 1), [1.0, 3.0, 4.0, 5.0, 6.0])


def test_parse_joint_values():
    import argparse

    from real_gripper_drag import parse_joint_fits, parse_joint_values  # code/ is on sys.path (conftest.py)

    assert parse_joint_fits("2=-0.8:0.2") == {"shoulder_lift": (-0.8, 0.2)}
    with pytest.raises(argparse.ArgumentTypeError):
        parse_joint_fits("shoulder_lift=0.5")
    assert parse_joint_values("shoulder_lift=0.7, 3=0.9") == {"shoulder_lift": 0.7, "elbow_flex": 0.9}
    assert parse_joint_values(None) == {}
    with pytest.raises(argparse.ArgumentTypeError):
        parse_joint_values("gripper=1")


def test_soft_gains_and_kp_scale():
    arm = RealGripperArm(kp_scale=4.0)
    assert arm.mit_kp["shoulder_lift"] == 160.0 and arm.mit_kd["shoulder_lift"] == pytest.approx(8.0)
    with pytest.raises(ValueError):
        RealGripperArm(kp_scale=0.0)


def test_ensure_calibration_file_with_plugin(tmp_path):
    pytest.importorskip("lerobot_robot_seeed_b601")
    from lerobot_robot_seeed_b601 import SeeedB601RSFollower, SeeedB601RSFollowerConfig

    cfg = SeeedB601RSFollowerConfig(port="can0", id="test_gripper", calibration_dir=tmp_path)
    robot = SeeedB601RSFollower(cfg)
    assert not robot.is_calibrated
    assert ensure_calibration_file(robot)
    assert (tmp_path / "test_gripper.json").is_file()
    assert set(robot.calibration) == set(MOTOR_NAMES) and robot.calibration["gripper"].id == 7
    robot2 = SeeedB601RSFollower(cfg)  # a new instance loads the file: connect() will not re-zero the motors
    assert robot2.is_calibrated and not ensure_calibration_file(robot2)


def test_gripper_twin_follows_snapshot():
    twin = GripperTwin()
    try:
        snap = MotorSnapshot(np.array([0, 30, 40, -20, 0, 0, 135.0]), np.zeros(7), np.zeros(7), np.full(7, 30.0),
                             np.zeros(7, dtype=int), np.ones(7, dtype=bool))
        twin.update(snap)
        np.testing.assert_allclose(np.degrees(twin.data.qpos[twin.sim.arm_qadr]), [0, 30, 40, -20, 0, 0])
        np.testing.assert_allclose(twin.data.qpos[twin.sim.finger_qadr], 0.025)
        p, _ = twin.tcp_pose()
        assert p[2] > 0 and len(format_table(snap, tcp=p)) == 9
    finally:
        twin.close()


def test_gripper_twin_uses_the_course_model():
    from rebot_sim.sim import MODEL_DIR

    twin = GripperTwin()
    try:
        assert twin.sim.scene_path == MODEL_DIR / "scene_table.xml" and twin.sim.scene_path.is_file()
        assert MODEL_DIR.parent.name == "model"
        # folded zero pose: the gripper points forward, the TCP is above the table
        twin.update(MotorSnapshot(np.zeros(7), np.zeros(7), np.zeros(7), np.full(7, 30.0),
                                  np.zeros(7, dtype=int), np.ones(7, dtype=bool)))
        p, _ = twin.tcp_pose()
        assert p[0] > 0 and p[2] > 0
    finally:
        twin.close()


def test_check_can_up(tmp_path):
    ga.check_can_up("can0", sysfs=str(tmp_path / "missing"))  # no sysfs (e.g. macOS): no check
    with pytest.raises(SystemExit, match="not found"):
        ga.check_can_up("can0", sysfs=str(tmp_path))
    (tmp_path / "can0").mkdir()
    (tmp_path / "can0" / "flags").write_text("0x80\n")
    with pytest.raises(SystemExit, match="DOWN"):
        ga.check_can_up("can0", sysfs=str(tmp_path))
    (tmp_path / "can0" / "flags").write_text("0x81\n")
    ga.check_can_up("can0", sysfs=str(tmp_path))  # UP: no exception
