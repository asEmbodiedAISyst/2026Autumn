"""Camera geometry and motion checks of the Claude-controlled pusher (scripts/agent_control.py)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from agent_control import Executor, camera_model, draw_grid, pixel_to_table, project, tool_specs  # noqa: E402


def _env():
    from rebot_sim.real.arm import SimArm
    from rebot_sim.real.camera import SimCamera
    from rebot_sim.real.env import RealToolPushEnv
    from rebot_sim.tool_env import make_tool_task

    arm = SimArm("pusher_push_cube")
    env = RealToolPushEnv(arm, SimCamera(arm), start_noise=False, sim_task=make_tool_task("push_cube"))
    arm.sim.init_renderer()
    return env


def test_projection_round_trip_and_grid():
    env = _env()
    try:
        obs, info = env.reset(seed=0)
        env.tool_pose()
        c, R, f = camera_model(env)
        hw = (480, 640)
        pts = np.array([[0.35, 0.0, 0.0], [0.42, 0.06, 0.0], [0.30, -0.08, 0.0]])
        uv = project(pts, c, R, f, hw)
        assert not np.isnan(uv).any() and (uv[:, 0] > 0).all() and (uv[:, 0] < 640).all()
        for p, (u, v) in zip(pts, uv):
            back = pixel_to_table(u, v, c, R, f, hw)
            np.testing.assert_allclose(back, p, atol=1e-6)
        # the real cube in the image: its projected centre reprojects to the simulated cube position
        cube_xy = env.sim_task.object_state(env.arm.sim)[:2]
        u, v = project(np.array([[cube_xy[0], cube_xy[1], 0.02]]), c, R, f, hw)[0]
        back = pixel_to_table(u, v, c, R, f, hw, z=0.02)
        np.testing.assert_allclose(back[:2], cube_xy, atol=1e-6)
        annotated = draw_grid(obs["pixels"]["phone"], env, env.ctrl.target_pos)
        assert annotated.shape == (480, 640, 3) and (annotated != obs["pixels"]["phone"]).any()
    finally:
        env.close()


def test_relative_moves_are_checked_and_executed():
    env = _env()
    try:
        env.reset(seed=1)
        ex = Executor(env)
        ex.last_obs, ex.last_info = env._obs()[0], {}
        p0 = ex.tip()
        report, success = ex.move_relative([{"dx_cm": 4, "dy_cm": -3, "dz_cm": -5, "dyaw_deg": 0}])
        assert "done" in report and not success
        np.testing.assert_allclose(ex.tip(), p0 + np.array([0.04, -0.03, -0.05]), atol=1e-6)
        report, _ = ex.move_relative([{"dx_cm": 0, "dy_cm": 0, "dz_cm": -14, "dyaw_deg": 0}])  # below the table
        assert "rejected" in report and "z" in report
        np.testing.assert_allclose(ex.tip(), p0 + np.array([0.04, -0.03, -0.05]), atol=1e-6)  # unchanged
        report, _ = ex.move_relative([{"dx_cm": 30, "dy_cm": 0, "dz_cm": 0, "dyaw_deg": 0}])
        assert "rejected" in report and "longer" in report
    finally:
        env.close()


def test_push_primitive_succeeds_in_simulation():
    env = _env()
    try:
        env.reset(seed=2)
        ex = Executor(env)
        ex.last_obs, ex.last_info = env._obs()[0], {}
        wins = 0
        for seed in range(2, 8):  # the primitive is open loop per call; re-observing the cube corrects the rest
            env.reset(seed=seed); ex.success = False
            for _ in range(4):
                st = env.sim_task.object_state(env.arm.sim)
                ex.push(np.array(st[:2]), np.array(st[3:5]))
                if ex.success:
                    break
            wins += ex.success
        assert wins >= 5, f"{wins}/6 pushes succeeded"
    finally:
        env.close()


def test_tool_specs_are_strict():
    for mode in ("step", "push"):
        for t in tool_specs(mode):
            assert t["strict"] and t["input_schema"]["additionalProperties"] is False
    assert [t["name"] for t in tool_specs("push")] == ["locate", "move", "push", "done"]
    assert [t["name"] for t in tool_specs("step")] == ["locate", "move", "done"]
