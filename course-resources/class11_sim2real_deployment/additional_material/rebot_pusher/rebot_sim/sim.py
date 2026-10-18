"""Core MuJoCo simulation: load scenes, step at the control rate, render cameras, read state.

* :class:`SceneSim`: anything shared by all scenes (stepping, rendering, object/mocap poses).
* :class:`RebotSim`: the reBot B601-RS arm (with the original gripper or the pusher tool). Control mirrors
  the real arm: one joint target per control period, tracked by MuJoCo position actuators
  (PD + gravity compensation), like the motors' MIT mode.
* :class:`HandheldToolSim`: the pusher tool without a robot, moved as a mocap body (simulated human
  data collection with the same rigid rod + phone tool).
"""

from __future__ import annotations

import atexit
from pathlib import Path

import mujoco
import numpy as np

from .robot import (
    ARM_JOINTS,
    FINGER_JOINTS,
    GRIPPER_STROKE,
    HOME_QPOS,
    sim_to_motor_deg,
)

ASSET_DIR = Path(__file__).resolve().parents[1] / "model" / "rebot_b601_rs_mjcf"

# End effectors: "gripper" = original parallel gripper, "pusher" = rigid rod + phone tool on the arm,
# "handheld" = the same tool held by a (simulated) human, no robot.
EMBODIMENTS = ("gripper", "pusher", "handheld")


def _scene_file(embodiment: str, task: str) -> Path:
    name = f"scene_{task}.xml" if embodiment == "gripper" else f"scene_{embodiment}_{task}.xml"
    return ASSET_DIR / name


SCENES = {
    ("" if ee == "gripper" else f"{ee}_") + task: _scene_file(ee, task)
    for ee in EMBODIMENTS
    for task in ("table", "push_cube", "push_t")
}

# Geom groups hidden in recorded images: 1 = teleop markers, 3 = collision geoms, 4/5 = debug
HIDDEN_GEOM_GROUPS = (1, 3, 4, 5)


def resolve_scene(scene: str | Path) -> Path:
    if isinstance(scene, str) and scene in SCENES:
        return SCENES[scene]
    path = Path(scene)
    if not path.is_file():
        raise FileNotFoundError(f"scene not found: {scene} (built-in scenes: {list(SCENES)})")
    return path


class SceneSim:
    """A MuJoCo scene stepped at a fixed control rate, with offscreen camera rendering.

    Args:
        scene: Built-in scene name (see ``SCENES``) or a path to an MJCF file.
        fps: Control rate (Hz); matches the LeRobot recording rate, default 30.
        cameras: Names of the cameras to render.
        image_size: Render resolution (height, width); defaults to the real cameras' 480x640.
    """

    def __init__(
        self,
        scene: str | Path,
        fps: int = 30,
        cameras: tuple[str, ...] = ("front", "side"),
        image_size: tuple[int, int] = (480, 640),
    ) -> None:
        self.scene_path = resolve_scene(scene)
        self.model = mujoco.MjModel.from_xml_path(str(self.scene_path))
        self.data = mujoco.MjData(self.model)
        self.fps = fps
        # Make the control period an exact multiple of the physics timestep
        base_dt = self.model.opt.timestep
        self.n_substeps = max(1, round(1.0 / fps / base_dt))
        self.model.opt.timestep = 1.0 / fps / self.n_substeps
        self.control_dt = 1.0 / fps
        self.tcp_site = self.model.site("tcp").id

        self.cameras = tuple(cameras)
        for cam in self.cameras:
            self.model.camera(cam)  # raises KeyError if the camera does not exist
        self.image_size = image_size
        self._renderer: mujoco.Renderer | None = None
        self._scene_option = mujoco.MjvOption()
        for g in HIDDEN_GEOM_GROUPS:
            self._scene_option.geomgroup[g] = 0

    # ------------------------------------------------------------------ state
    def step(self) -> None:
        """Advance one control period."""
        mujoco.mj_step(self.model, self.data, nstep=self.n_substeps)

    @property
    def time(self) -> float:
        return float(self.data.time)

    def tcp_pose(self) -> tuple[np.ndarray, np.ndarray]:
        """TCP (position, rotation matrix) in the world frame (= robot base frame)."""
        return self.data.site_xpos[self.tcp_site].copy(), self.data.site_xmat[self.tcp_site].reshape(3, 3).copy()

    def body_pose(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        b = self.data.body(name)
        return b.xpos.copy(), b.xquat.copy()

    def set_free_body_pose(self, joint: str, pos: np.ndarray, quat: np.ndarray) -> None:
        j = self.model.joint(joint)
        adr, dadr = self.model.jnt_qposadr[j.id], self.model.jnt_dofadr[j.id]
        self.data.qpos[adr : adr + 3] = pos
        self.data.qpos[adr + 3 : adr + 7] = quat
        self.data.qvel[dadr : dadr + 6] = 0.0

    def set_mocap_pose(self, body: str, pos: np.ndarray, quat: np.ndarray | None = None) -> None:
        mid = self.model.body(body).mocapid[0]
        self.data.mocap_pos[mid] = pos
        if quat is not None:
            self.data.mocap_quat[mid] = quat

    def has_body(self, name: str) -> bool:
        return mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name) >= 0

    # ------------------------------------------------------------------ rendering
    def init_renderer(self) -> None:
        """Create the offscreen renderer.

        When used together with the MuJoCo viewer, call this **before** ``launch_passive``: the EGL
        context must be created before the viewer's GLFW context, otherwise EGL fails with
        "Failed to make the EGL context current".
        """
        if self._renderer is None:
            h, w = self.image_size
            self._renderer = mujoco.Renderer(self.model, height=h, width=w)
            # Release the GL context before interpreter shutdown to avoid EGL errors during teardown
            atexit.register(self.close)

    def render(self, camera: str) -> np.ndarray:
        """Render a camera and return an (H, W, 3) uint8 RGB image."""
        self.init_renderer()
        self._renderer.update_scene(self.data, camera=camera, scene_option=self._scene_option)
        return self._renderer.render().copy()

    def render_all(self) -> dict[str, np.ndarray]:
        return {cam: self.render(cam) for cam in self.cameras}

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    def __del__(self) -> None:  # pragma: no cover
        try:
            self.close()
        except Exception:
            pass


class RebotSim(SceneSim):
    """reBot B601-RS in MuJoCo, with the original gripper or (``pusher_*`` scenes) the rigid pusher tool."""

    def __init__(
        self,
        scene: str | Path = "table",
        fps: int = 30,
        cameras: tuple[str, ...] = ("front", "side"),
        image_size: tuple[int, int] = (480, 640),
    ) -> None:
        super().__init__(scene, fps, cameras, image_size)
        m = self.model
        self.arm_qadr = np.array([m.jnt_qposadr[m.joint(j).id] for j in ARM_JOINTS])
        self.arm_dofadr = np.array([m.jnt_dofadr[m.joint(j).id] for j in ARM_JOINTS])
        self.arm_act = np.array([m.actuator(j).id for j in ARM_JOINTS])
        self.has_gripper = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, "gripper") >= 0
        if self.has_gripper:
            self.finger_qadr = np.array([m.jnt_qposadr[m.joint(j).id] for j in FINGER_JOINTS])
            self.gripper_act = m.actuator("gripper").id
        else:
            self.finger_qadr = np.zeros(0, dtype=int)
            self.gripper_act = None
        self.reset()

    def reset(self, arm_q: np.ndarray = HOME_QPOS, gripper: float = 0.0) -> None:
        """Reset to the given joint angles (rad) and gripper opening (m); other bodies return to their MJCF poses."""
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.arm_qadr] = arm_q
        self.data.qpos[self.finger_qadr] = gripper
        self.set_targets(arm_q, gripper)
        mujoco.mj_forward(self.model, self.data)

    def set_targets(self, arm_q: np.ndarray, gripper: float = 0.0) -> None:
        """Set joint targets: 6 arm joint angles (rad) + single-finger gripper opening (m, ignored without gripper)."""
        lo = self.model.actuator_ctrlrange[self.arm_act, 0]
        hi = self.model.actuator_ctrlrange[self.arm_act, 1]
        self.data.ctrl[self.arm_act] = np.clip(arm_q, lo, hi)
        if self.has_gripper:
            self.data.ctrl[self.gripper_act] = float(np.clip(gripper, 0.0, GRIPPER_STROKE))

    def arm_q(self) -> np.ndarray:
        return self.data.qpos[self.arm_qadr].copy()

    def arm_target(self) -> np.ndarray:
        return self.data.ctrl[self.arm_act].copy()

    def gripper_q(self) -> float:
        return float(self.data.qpos[self.finger_qadr].mean()) if self.has_gripper else 0.0

    def motor_state_deg(self) -> np.ndarray:
        """7 motor angles (deg), same meaning as the real ``observation.state`` (gripper 0 without gripper)."""
        return sim_to_motor_deg(self.arm_q(), self.gripper_q())


class HandheldToolSim(SceneSim):
    """The rigid pusher tool moved as a mocap body (no robot): simulated human data collection.

    The tool is commanded by its TCP (rod tip) pose. Within one control period the mocap pose is interpolated
    over the physics substeps so that contacts with objects stay smooth.
    """

    def __init__(
        self,
        scene: str | Path = "handheld_table",
        fps: int = 30,
        cameras: tuple[str, ...] = ("phone",),
        image_size: tuple[int, int] = (480, 640),
    ) -> None:
        super().__init__(scene, fps, cameras, image_size)
        self.mocap_id = self.model.body("handheld").mocapid[0]
        # TCP pose in the mocap (= tool) body frame; the tool is rigidly attached to the mocap body
        self._tcp_local = self.model.site_pos[self.tcp_site].copy()
        self._tcp_local_rot = np.zeros(9)
        mujoco.mju_quat2Mat(self._tcp_local_rot, self.model.site_quat[self.tcp_site])
        self._tcp_local_rot = self._tcp_local_rot.reshape(3, 3)
        self._target_pos = np.zeros(3)
        self._target_quat = np.array([1.0, 0, 0, 0])
        mujoco.mj_forward(self.model, self.data)

    def _tcp_to_body(self, tcp_pos: np.ndarray, tcp_rot: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        body_rot = np.asarray(tcp_rot, dtype=float) @ self._tcp_local_rot.T
        quat = np.zeros(4)
        mujoco.mju_mat2Quat(quat, body_rot.ravel())
        return np.asarray(tcp_pos, dtype=float) - body_rot @ self._tcp_local, quat

    def reset(self, tcp_pos: np.ndarray, tcp_rot: np.ndarray) -> None:
        """Reset the scene and place the tool TCP at the given pose."""
        mujoco.mj_resetData(self.model, self.data)
        self._target_pos, self._target_quat = self._tcp_to_body(tcp_pos, tcp_rot)
        self.data.mocap_pos[self.mocap_id] = self._target_pos
        self.data.mocap_quat[self.mocap_id] = self._target_quat
        mujoco.mj_forward(self.model, self.data)

    def set_tcp_target(self, tcp_pos: np.ndarray, tcp_rot: np.ndarray) -> None:
        """Pose the tool TCP should reach at the end of the next control period."""
        self._target_pos, self._target_quat = self._tcp_to_body(tcp_pos, tcp_rot)

    def step(self) -> None:
        p0 = self.data.mocap_pos[self.mocap_id].copy()
        q0 = self.data.mocap_quat[self.mocap_id].copy()
        q1 = self._target_quat if np.dot(q0, self._target_quat) >= 0 else -self._target_quat
        for i in range(1, self.n_substeps + 1):
            a = i / self.n_substeps
            q = (1 - a) * q0 + a * q1
            self.data.mocap_pos[self.mocap_id] = (1 - a) * p0 + a * self._target_pos
            self.data.mocap_quat[self.mocap_id] = q / np.linalg.norm(q)
            mujoco.mj_step(self.model, self.data)
