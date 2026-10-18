"""Real-robot counterpart of :class:`rebot_sim.tool_env.ToolPushEnv` (pusher tool on the reBot arm).

Same actions, observations, software limits and IK as the simulated ``embodiment="pusher"`` env; the
differences are only where the data comes from:

* joint angles are read from the arm backend; the TCP pose is computed on a kinematic MuJoCo twin of the
  pusher arm (the same model the IK uses);
* ``pixels["phone"]`` is the image of the robot-mounted phone (asMagic stream);
* there is no object state and no automatic success detection on the real robot (``is_success`` is always
  False; the operator decides when an episode ends). With the ``SimArm`` backend a simulated task can be
  attached for testing (objects are placed and success is evaluated as in simulation).
"""

from __future__ import annotations

from types import SimpleNamespace

import mujoco
import numpy as np

from ..ik import DiffIK
from .arm import SLOW_LAG_DEG, move_to_staged
from ..pose import EpisodeFrame, apply_delta, gravity_in_tool, matrix_to_rotvec, pose_delta, rot_z
from ..robot import PUSHER_HOME_QPOS, TCP_DOWN_ROT
from ..sim import RebotSim
from ..tasks import PushCubeTask
from ..teleop.tool_controller import ToolController, ToolLimits
from ..tool_env import ACTION_MODES, TOOL_START_NOISE, TOOL_START_POS, default_tool_limits


class RealToolPushEnv:
    def __init__(
        self,
        arm,
        camera,
        task_description: str = PushCubeTask.description,
        fps: int = 30,
        action_mode: str = "episode",
        limits: ToolLimits | None = None,
        start_noise: bool = True,
        start_speed_deg_s: float = 20.0,
        sim_task=None,
        start_pos: np.ndarray | None = None,
        z_frame: str = "start",
    ) -> None:
        if action_mode not in ACTION_MODES:
            raise ValueError(f"action_mode must be one of {ACTION_MODES}")
        self.arm = arm
        self.camera = camera
        self.task = sim_task if sim_task is not None else SimpleNamespace(description=task_description)
        self.sim_task = sim_task
        self.fps = fps
        self.action_mode = action_mode
        self.start_noise = start_noise
        self.start_speed_deg_s = start_speed_deg_s
        # Tip position at the start of every episode. The policy replays *relative* motion, so the start height
        # must match the height the demonstrations started at (recorded data: see record_handheld.py).
        self.start_pos = np.array(TOOL_START_POS if start_pos is None else start_pos, dtype=float)
        # "start": z of the episode frame is the start height (original format); "table": z = height above the
        # table (datasets converted with tools/anchor_z_to_table.py or recorded with a table calibration).
        if z_frame not in ("start", "table"):
            raise ValueError("z_frame must be 'start' or 'table'")
        self.z_frame = z_frame
        self.kin = RebotSim("pusher_table", cameras=())  # kinematic twin (FK / IK / viewer), never stepped
        self.ik = DiffIK(self.kin.model, posture=PUSHER_HOME_QPOS)
        self.ctrl = ToolController(fps, limits or default_tool_limits())
        self.frame = EpisodeFrame(np.zeros(3), np.eye(3))
        self.q_cmd = PUSHER_HOME_QPOS.copy()
        self.q_meas = PUSHER_HOME_QPOS.copy()
        self.np_random = np.random.default_rng()
        self._step = 0

    # ------------------------------------------------------------------
    def _update_twin(self, q: np.ndarray) -> None:
        self.q_meas = np.asarray(q, dtype=float)
        self.kin.data.qpos[self.kin.arm_qadr] = self.q_meas
        mujoco.mj_kinematics(self.kin.model, self.kin.data)

    def tool_pose(self) -> tuple[np.ndarray, np.ndarray]:
        """Measured TCP pose (world = robot base frame)."""
        self._update_twin(self.arm.read_q())
        return self.kin.tcp_pose()

    def _obs(self) -> tuple[dict, float]:
        p, R = self.tool_pose()
        state = gravity_in_tool(R) if self.action_mode == "delta" else self.frame.encode(p, R)
        image, age = self.camera.read()
        obs = {
            "agent_pos": state.astype(np.float32),
            "pixels": {"phone": image},
            "environment_state": (self.sim_task.object_state(self.arm.sim) if self.sim_task is not None
                                  else np.zeros(1, dtype=np.float32)),
        }
        return obs, age

    def start_q(self, pos: np.ndarray, rot: np.ndarray) -> np.ndarray:
        res = self.ik.solve(pos, rot, PUSHER_HOME_QPOS, max_iters=300)
        if not res.success:
            raise RuntimeError(f"start pose out of reach: {np.round(pos, 3)}")
        return res.q

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        """Move (slowly, joint space) to the episode start pose; the episode frame is anchored there."""
        if seed is not None:
            self.np_random = np.random.default_rng(seed)
        rng = self.np_random
        pos, yaw = self.start_pos.copy(), 0.0
        if self.start_noise:
            pos += rng.uniform(-TOOL_START_NOISE, TOOL_START_NOISE)
            yaw = rng.uniform(-0.4, 0.4)
        rot = rot_z(yaw) @ TCP_DOWN_ROT
        q = self.start_q(pos, rot)
        move_to_staged(self.arm, q, self.start_speed_deg_s)  # shoulder/elbow first: no wrist flex in the folded pose
        self.q_cmd = q
        self.ctrl.reset(pos, rot)
        origin = pos if self.z_frame == "start" else np.array([pos[0], pos[1], 0.0])
        self.frame = EpisodeFrame(origin, rot)
        if self.sim_task is not None:
            # SimArm: like the operator on the real robot, place the objects once the arm is at the start pose
            self.arm.sim.reset(self.arm.read_q())
            self.sim_task.reset(self.arm.sim, rng)
            for _ in range(5):  # let the objects settle
                self.arm.command_q(q)
        self._step = 0
        obs, age = self._obs()
        return obs, {"is_success": False, "image_age": age}

    def action_to(self, pos: np.ndarray, rot: np.ndarray | None = None) -> np.ndarray:
        rot = self.ctrl.target_rot if rot is None else rot
        if self.action_mode == "delta":
            return pose_delta(self.ctrl.target_pos, self.ctrl.target_rot, pos, rot)
        return self.frame.encode(pos, rot)

    def step(self, action: np.ndarray):
        p_prev, R_prev = self.ctrl.target_pos.copy(), self.ctrl.target_rot.copy()
        if self.action_mode == "delta":
            p_des, R_des = apply_delta(p_prev, R_prev, np.asarray(action, dtype=float))
        else:
            p_des, R_des = self.frame.decode(action)
        lag = self.arm.lag_deg()
        lagging = lag > SLOW_LAG_DEG
        # The arm is far behind its target: slow the commanded pose down in proportion (full speed up to
        # SLOW_LAG_DEG, frozen at 2 * SLOW_LAG_DEG) so that it catches up without stop-and-go. A joint that
        # stays behind without moving is a fault (check_stall raises, torque off; its own tighter threshold).
        slow = float(np.clip((2 * SLOW_LAG_DEG - lag) / SLOW_LAG_DEG, 0.0, 1.0)) if lagging else 1.0
        self.arm.check_stall()
        if slow <= 0.0:
            p, R, ik_ok = p_prev, R_prev, True
        else:
            full_speed, full_ang = self.ctrl.limits.max_speed, self.ctrl.limits.max_ang_speed
            self.ctrl.limits.max_speed, self.ctrl.limits.max_ang_speed = full_speed * slow, full_ang * slow
            try:
                p, R = self.ctrl.command(p_des, R_des)
            finally:
                self.ctrl.limits.max_speed, self.ctrl.limits.max_ang_speed = full_speed, full_ang
            res = self.ik.solve(p, R, self.q_cmd, max_iters=30)
            ik_ok = res.success
            if ik_ok:
                self.q_cmd = res.q
            else:
                # Out of reach / joint limits: refuse the step, keep the previous commanded pose (the arm holds).
                # The workspace box is only a coarse bound; the reachable region inside it is decided here.
                self.ctrl.reset(p_prev, R_prev)
                p, R = p_prev, R_prev
        applied = pose_delta(p_prev, R_prev, p, R) if self.action_mode == "delta" else self.frame.encode(p, R)
        self.arm.command_q(self.q_cmd)
        self._step += 1
        obs, age = self._obs()
        # tracking diagnostics: commanded vs measured (the twin holds the measured pose after _obs)
        p_meas, R_meas = self.kin.tcp_pose()
        info = {"is_success": False, "applied_action": applied.astype(np.float32), "ik_ok": ik_ok,
                "lagging": lagging, "lag_deg": float(lag), "speed_factor": slow, "image_age": age,
                "joint_err_deg": float(np.degrees(np.abs(self.q_cmd - self.q_meas)).max()),
                "tcp_pos_err_mm": float(np.linalg.norm(self.ctrl.target_pos - p_meas) * 1000),
                "tcp_rot_err_deg": float(np.degrees(np.linalg.norm(matrix_to_rotvec(self.ctrl.target_rot @ R_meas.T))))}
        if self.sim_task is not None:
            result = self.sim_task.evaluate(self.arm.sim)
            info.update(is_success=result.success, **result.info)
        return obs, 0.0, False, False, info

    def hold(self):
        """Keep the current commanded pose (e.g. while the operator is disengaged)."""
        return self.step(self.action_to(self.ctrl.target_pos, self.ctrl.target_rot))

    def close(self) -> None:
        try:
            self.camera.close()
        finally:
            self.arm.close()
            self.kin.close()
