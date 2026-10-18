"""Both bring-up scripts end to end without hardware: a stub Seeed plugin replaces the CAN bus.

The stub motors follow every position target at once, so the motion test runs its full sequence (hold, one
joint +-A, summary, two-stage return to zero, JSON log). The drag script runs until a simulated Ctrl+C.
"""

import io
import json
import sys
import types

import numpy as np
import pytest

from rebot_sim.real import gripper_arm as ga
from test_real_gripper import StubFollower


class PluginFollower(StubFollower):
    """StubFollower with the connection API of SeeedB601RSFollower."""

    is_calibrated = True
    interrupt_after: int | None = None  # simulate Ctrl+C after this many feedback polls

    def __init__(self, cfg):
        super().__init__([5.0, 12.0, 20.0, -8.0, 3.0, -4.0, 0.0])
        self.cfg = cfg
        self.is_connected = False
        self.polls = 0
        self.bus = types.SimpleNamespace(poll_feedback_once=self._poll, disable_all=lambda: None)
        PluginFollower.last = self

    def _poll(self):
        self.polls += 1
        if self.interrupt_after is not None and self.polls in (self.interrupt_after, 2 * self.interrupt_after):
            raise KeyboardInterrupt

    def connect(self, calibrate=False):
        self.calibrate = calibrate
        self.is_connected = True


@pytest.fixture
def stub_plugin(monkeypatch):
    mod = types.ModuleType("lerobot_robot_seeed_b601")
    mod.SeeedB601RSFollower = PluginFollower
    mod.SeeedB601RSFollowerConfig = lambda **kw: types.SimpleNamespace(**kw)
    monkeypatch.setitem(sys.modules, "lerobot_robot_seeed_b601", mod)
    monkeypatch.setattr(ga, "check_can_up", lambda port: None)
    monkeypatch.setattr(ga.time, "sleep", lambda s: None)
    monkeypatch.setattr(PluginFollower, "interrupt_after", None)
    return mod


def test_motion_test_full_sequence(stub_plugin, monkeypatch, tmp_path, capsys):
    import real_gripper_motion_test as mt

    monkeypatch.setattr(mt, "RESULTS", {})
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    log = tmp_path / "motion_{time}.json"
    monkeypatch.setattr(sys, "argv", ["real_gripper_motion_test.py", "--yes", "--joints", "1,4", "--amplitude", "5",
                                      "--speed", "100", "--log", str(log)])
    mt.main()
    robot = PluginFollower.last
    out = capsys.readouterr().out
    assert "Return to the folded zero pose in two stages" in out and "At the zero pose. Torque off." in out
    np.testing.assert_allclose(robot.sent[-1][:6], 0.0, atol=1e-9)  # back at the folded zero
    assert np.isnan(robot.sent[-1][6])  # the gripper was never position-controlled
    assert robot.disconnected and robot._skip_safe_zero_on_disconnect
    assert robot.cfg.max_relative_target == 5.0 and robot.cfg.gravity_compensation
    sent = np.array(robot.sent)
    assert sent[:, 0].max() == pytest.approx(10.0) and sent[:, 0].min() == pytest.approx(0.0)  # 5 + 5, then to 0
    files = list(tmp_path.glob("motion_*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert [j["joint"] for j in data["joints"]] == ["shoulder_pan", "wrist_flex"]
    assert "hold" in data and data["args"]["amplitude"] == 5.0


def test_motion_test_tracking_abort(stub_plugin, monkeypatch, tmp_path, capsys):
    import real_gripper_motion_test as mt

    monkeypatch.setattr(mt, "RESULTS", {})
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    monkeypatch.setattr(PluginFollower, "send_action", lambda self, action: action)  # the arm does not move
    monkeypatch.setattr(sys, "argv", ["real_gripper_motion_test.py", "--yes", "--joints", "1", "--amplitude", "20",
                                      "--abort-error", "3", "--speed", "100", "--log", str(tmp_path / "m.json")])
    mt.main()
    out = capsys.readouterr().out
    assert "Aborted: shoulder_pan is" in out and "Torque is off" in out
    assert PluginFollower.last.torque_disabled and PluginFollower.last.disconnected


def test_drag_zero_torque_until_ctrl_c(stub_plugin, monkeypatch, capsys):
    import real_gripper_drag as drag

    monkeypatch.setattr(PluginFollower, "interrupt_after", 20)
    monkeypatch.setattr(sys, "argv", ["real_gripper_drag.py"])
    drag.main()
    robot = PluginFollower.last
    out = capsys.readouterr().out
    assert "Zero-torque mode: torque is off" in out and "Torque off and disconnect" in out
    assert robot.torque_disabled and robot.disconnected and robot.sent == []  # never a position command
    for m in robot.motors.values():  # only zero-gain frames
        assert all(f == (0.0, 0.0, 0.0, 0.0, 0.0) for f in m.mit)


def test_drag_gravity_first_ctrl_c_keeps_compensation_until_enter(stub_plugin, monkeypatch, capsys):
    import real_gripper_drag as drag

    monkeypatch.setattr(PluginFollower, "interrupt_after", 10)
    calls = {"n": 0}

    def has_line():  # Enter arrives a few cycles after the first Ctrl+C
        calls["n"] += 1
        return calls["n"] > 5

    monkeypatch.setattr(drag, "stdin_has_line", has_line)
    clock = {"t": 0.0}

    def monotonic():  # 0.1 s per call, so the 1 s ramp of the feedforward completes
        clock["t"] += 0.1
        return clock["t"]

    monkeypatch.setattr(drag.time, "monotonic", monotonic)
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n"))
    monkeypatch.setattr(sys, "argv", ["real_gripper_drag.py", "--mode", "gravity"])
    drag.main()
    robot = PluginFollower.last
    out = capsys.readouterr().out
    assert "Ctrl+C received: fold the arm, then press Enter" in out
    assert robot.polls > 10 + 5  # compensation continued after the first Ctrl+C
    pos, vel, kp, kd, tau = robot.motors["shoulder_lift"].mit[-1]
    assert kp == 0.0 and kd == 0.3 and tau == pytest.approx(2.0)  # gravity only, stub feedforward 2 N*m
    assert robot.disconnected


def test_drag_rezero_needs_zero_torque_mode(monkeypatch):
    import real_gripper_drag as drag

    monkeypatch.setattr(sys, "argv", ["real_gripper_drag.py", "--mode", "gravity", "--rezero"])
    with pytest.raises(SystemExit, match="--rezero works only"):
        drag.main()


def test_drag_rezero_asks_for_yes(stub_plugin, monkeypatch, capsys):
    import real_gripper_drag as drag

    arm = ga.RealGripperArm()
    arm.robot = PluginFollower(None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "no")
    drag.rezero(arm)
    assert not any(m.zeroed for m in arm.robot.motors.values()) and "Cancelled" in capsys.readouterr().out
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")
    drag.rezero(arm)
    assert all(m.zeroed for m in arm.robot.motors.values())
    np.testing.assert_allclose(arm.last.pos_deg, 0.0)
