"""Gymnasium environment for the rigid pusher tool (rod + phone) driven by relative poses.

The same rigid tool is either held by a (simulated) human (``embodiment="handheld"``, the tool is a mocap
body) or bolted to the arm flange (``embodiment="pusher"``, the commanded tool pose goes through IK to the
6 arm joints). Both share exactly the same action/observation definition, which is the point of the
"collect with a handheld tool, deploy on the robot" pipeline:

Two calibration-free action representations (``action_mode``):

* ``"delta"`` -- action (6,): motion of the commanded TCP pose during one control period, expressed in the
  current tool frame ``[dx, dy, dz (m), rx, ry, rz (rad)]``; state (3,): gravity direction in the tool frame.
* ``"episode"`` -- action (9,): next commanded TCP pose in the episode frame (gravity aligned, anchored at the
  tool pose at the start of the episode, see :class:`rebot_sim.pose.EpisodeFrame`) as position + rot6d;
  state (9,): measured TCP pose in the same frame.

Observation (``obs_type="pixels_agent_pos"``): ``pixels`` = ``{"phone": (H, W, 3) uint8}`` (the phone camera
rigidly mounted on the tool), ``agent_pos`` = the state above, ``environment_state`` = object state (sim only).

``info["applied_action"]`` is the action after the software limits (workspace, speed, tilt); datasets
store this value so that demonstrations only contain motions the robot executor would also perform.

The phone is the only camera, so the task must keep what matters in view: episodes start with the tool high
(the camera overlooks the workspace), and Push Cube goals lie close and "in front of" the cube (push direction
within +-70 deg of +x) so the operator can face the push direction.

The workspace and limits below are set for the default "ip17" tool (printed part held like a pen, see
tools/build_rebot_mjcf.py): it reaches best 0.30-0.48 m in front of the robot base, and its phone camera looks
almost straight down at the pusher tip (about +-8 cm visible ahead of the tip when pushing).
"""

from __future__ import annotations

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .ik import DiffIK
from .pose import EpisodeFrame, apply_delta, gravity_in_tool, pose_delta, rot_z
from .robot import PUSHER_HOME_QPOS, TCP_DOWN_ROT
from .sim import HandheldToolSim, RebotSim
from .tasks import PushCubeTask, Task, make_task
from .teleop.tool_controller import ToolController, ToolLimits

TOOL_EMBODIMENTS = ("handheld", "pusher")
ACTION_MODES = ("delta", "episode")
TOOL_START_POS = np.array([0.33, 0.0, 0.12])  # tip position at episode start (camera overlooks the workspace)
TOOL_START_NOISE = np.array([0.02, 0.04, 0.02])
PUSH_DIR_RANGE_DEG = 70.0
TOOL_WORKSPACE_X = (0.30, 0.48)  # object placement area for the tool tasks (m)
TOOL_WORKSPACE_Y = (-0.12, 0.12)
TOOL_PUSH_DIST = (0.05, 0.10)  # Push Cube: cube -> goal distance (m), short enough to keep the goal in view
TOOL_PUSH_T_GOAL = (0.40, 0.0, 0.0)  # Push-T: fixed goal pose (x, y, yaw)
TOOL_PUSH_T_WORKSPACE_X = (0.34, 0.46)  # Push-T start area: leaves room to push the T from every side


def default_tool_limits() -> ToolLimits:
    return ToolLimits(x=(0.22, 0.56), y=(-0.20, 0.20), z=(0.003, 0.20), max_yaw_deg=60.0)


def make_tool_task(name: str) -> Task:
    """Task variant for the phone-only camera and the tool workspace (see module docstring)."""
    if name == "push_cube":
        task = PushCubeTask(push_dir_range_deg=PUSH_DIR_RANGE_DEG)
        task.min_start_dist, task.max_start_dist = TOOL_PUSH_DIST
    else:
        task = make_task(name)
        if hasattr(task, "goal_pose"):
            task.goal_pose = TOOL_PUSH_T_GOAL
    task.workspace_x, task.workspace_y = TOOL_WORKSPACE_X, TOOL_WORKSPACE_Y
    if name == "push_t":
        task.workspace_x = TOOL_PUSH_T_WORKSPACE_X
    return task


class ToolPushEnv(gym.Env):
    metadata = {"render_modes": ["rgb_array"], "render_fps": 30}

    def __init__(
        self,
        task: str | Task = "push_cube",
        embodiment: str = "handheld",
        cameras: tuple[str, ...] = ("phone",),
        image_size: tuple[int, int] = (480, 640),
        fps: int = 30,
        episode_length: int = 600,
        obs_type: str = "pixels_agent_pos",
        render_mode: str | None = "rgb_array",
        render_camera: str = "phone",
        terminate_on_success: bool = True,
        start_noise: bool = True,
        limits: ToolLimits | None = None,
        delta_reference: str = "command",
        action_mode: str = "episode",
    ) -> None:
        super().__init__()
        if embodiment not in TOOL_EMBODIMENTS:
            raise ValueError(f"embodiment must be one of {TOOL_EMBODIMENTS}")
        self.task = make_tool_task(task) if isinstance(task, str) else task
        self.embodiment = embodiment
        self.obs_type = obs_type
        self.cameras = tuple(cameras)
        render_cams = tuple(dict.fromkeys((*cameras, render_camera)))
        scene = self.task.scene_for(embodiment)
        if embodiment == "handheld":
            self.sim: HandheldToolSim | RebotSim = HandheldToolSim(scene, fps, render_cams, image_size)
            self.ik = None
        else:
            self.sim = RebotSim(scene, fps, render_cams, image_size)
            self.ik = DiffIK(self.sim.model, posture=PUSHER_HOME_QPOS)
        self.ctrl = ToolController(fps, limits or default_tool_limits())
        self.q_cmd = PUSHER_HOME_QPOS.copy()
        self.render_mode = render_mode
        self.render_camera = render_camera
        self.episode_length = episode_length
        self.terminate_on_success = terminate_on_success
        self.start_noise = start_noise
        # "command": actions accumulate on the commanded pose (open loop w.r.t. tracking lag);
        # "measured": each action is applied to the measured TCP pose (closed loop, UMI style).
        # Identical for the handheld tool, which tracks its command exactly.
        if delta_reference not in ("command", "measured"):
            raise ValueError("delta_reference must be 'command' or 'measured'")
        self.delta_reference = delta_reference
        if action_mode not in ACTION_MODES:
            raise ValueError(f"action_mode must be one of {ACTION_MODES}")
        self.action_mode = action_mode
        self.frame = EpisodeFrame(np.zeros(3), np.eye(3))
        self.metadata = {**self.metadata, "render_fps": fps}

        a_dim, s_dim = (6, 3) if action_mode == "delta" else (9, 9)
        self.action_space = spaces.Box(-np.inf, np.inf, shape=(a_dim,), dtype=np.float32)
        h, w = image_size
        obs_spaces: dict[str, spaces.Space] = {
            "agent_pos": spaces.Box(-np.inf, np.inf, shape=(s_dim,), dtype=np.float32),
            "environment_state": spaces.Box(
                -np.inf, np.inf, shape=self.task.object_state(self.sim).shape, dtype=np.float32
            ),
        }
        if obs_type == "pixels_agent_pos":
            obs_spaces["pixels"] = spaces.Dict(
                {cam: spaces.Box(0, 255, shape=(h, w, 3), dtype=np.uint8) for cam in self.cameras}
            )
        elif obs_type != "state":
            raise ValueError(f"unknown obs_type: {obs_type}")
        self.observation_space = spaces.Dict(obs_spaces)
        self._step = 0

    # ------------------------------------------------------------------
    def _obs(self) -> dict:
        p, R = self.sim.tcp_pose()
        state = gravity_in_tool(R) if self.action_mode == "delta" else self.frame.encode(p, R)
        obs = {
            "agent_pos": state.astype(np.float32),
            "environment_state": self.task.object_state(self.sim),
        }
        if self.obs_type == "pixels_agent_pos":
            obs["pixels"] = {cam: self.sim.render(cam) for cam in self.cameras}
        return obs

    def _place_tool(self, pos: np.ndarray, rot: np.ndarray) -> None:
        self.ctrl.reset(pos, rot)
        if self.embodiment == "handheld":
            self.sim.reset(pos, rot)
        else:
            res = self.ik.solve(pos, rot, PUSHER_HOME_QPOS, max_iters=300)
            self.q_cmd = res.q
            self.sim.reset(res.q)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        rng = self.np_random
        pos, yaw = TOOL_START_POS.copy(), 0.0
        if self.start_noise:
            pos += rng.uniform(-TOOL_START_NOISE, TOOL_START_NOISE)
            yaw = rng.uniform(-0.4, 0.4)
        self._place_tool(pos, rot_z(yaw) @ TCP_DOWN_ROT)
        self.frame = EpisodeFrame(pos, rot_z(yaw) @ TCP_DOWN_ROT)
        self.task.reset(self.sim, rng)
        for _ in range(5):  # let the objects settle
            self.step(self.action_to(self.ctrl.target_pos, self.ctrl.target_rot))
        self._step = 0
        return self._obs(), {"is_success": False}

    def action_to(self, pos: np.ndarray, rot: np.ndarray | None = None) -> np.ndarray:
        """Action (in this env's ``action_mode``) that moves the commanded TCP pose towards an absolute
        world-frame target pose (``rot=None`` keeps the current orientation)."""
        rot = self.ctrl.target_rot if rot is None else rot
        if self.action_mode == "delta":
            return pose_delta(self.ctrl.target_pos, self.ctrl.target_rot, pos, rot)
        return self.frame.encode(pos, rot)

    delta_to = action_to  # backwards-compatible name

    def step(self, action: np.ndarray):
        if self.delta_reference == "measured" and self._step > 0:
            self.ctrl.reset(*self.sim.tcp_pose())
        p_prev, R_prev = self.ctrl.target_pos.copy(), self.ctrl.target_rot.copy()
        if self.action_mode == "delta":
            p_des, R_des = apply_delta(p_prev, R_prev, np.asarray(action, dtype=float))
        else:
            p_des, R_des = self.frame.decode(action)
        p, R = self.ctrl.command(p_des, R_des)
        applied = pose_delta(p_prev, R_prev, p, R) if self.action_mode == "delta" else self.frame.encode(p, R)
        ik_ok = True
        if self.embodiment == "handheld":
            self.sim.set_tcp_target(p, R)
        else:
            res = self.ik.solve(p, R, self.q_cmd, max_iters=30)
            self.q_cmd = res.q
            ik_ok = res.success
            self.sim.set_targets(res.q)
        self.sim.step()
        self._step += 1
        result = self.task.evaluate(self.sim)
        terminated = bool(result.success and self.terminate_on_success)
        truncated = self._step >= self.episode_length
        info = {"is_success": result.success, "applied_action": applied.astype(np.float32), "ik_ok": ik_ok, **result.info}
        return self._obs(), float(result.reward), terminated, truncated, info

    def tool_pose(self) -> tuple[np.ndarray, np.ndarray]:
        """Measured TCP pose (world frame)."""
        return self.sim.tcp_pose()

    def render(self):
        return self.sim.render(self.render_camera)

    def close(self) -> None:
        self.sim.close()
