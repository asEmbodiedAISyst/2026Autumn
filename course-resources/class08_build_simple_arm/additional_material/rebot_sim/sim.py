"""The reBot B601-RS with the stock gripper in MuJoCo (kinematic base of the digital twin).

Only the gripper table scene of the course model is available: ``model/rebot_b601_rs_mjcf/scene_table.xml``
(the same file that ``code/view_arm_scene.py`` and ``code/controlled_motion.py`` load). Control mirrors the
physical arm: one joint target per control period, tracked by MuJoCo position actuators.
"""

from __future__ import annotations

from pathlib import Path

import mujoco
import numpy as np

from .robot import ARM_JOINTS, FINGER_JOINTS, GRIPPER_STROKE, HOME_QPOS, sim_to_motor_deg

# The course model folder: additional_material/model/rebot_b601_rs_mjcf
MODEL_DIR = Path(__file__).resolve().parents[1] / "model" / "rebot_b601_rs_mjcf"

SCENES = {"table": MODEL_DIR / "scene_table.xml"}


def resolve_scene(scene: str | Path) -> Path:
    if isinstance(scene, str) and scene in SCENES:
        return SCENES[scene]
    path = Path(scene)
    if not path.is_file():
        raise FileNotFoundError(f"scene not found: {scene} (built-in scenes: {list(SCENES)})")
    return path


class RebotSim:
    """reBot B601-RS with the stock gripper in MuJoCo.

    Args:
        scene: Built-in scene name (``"table"``) or a path to an MJCF file.
        fps: Control rate (Hz).
    """

    def __init__(self, scene: str | Path = "table", fps: int = 30) -> None:
        self.scene_path = resolve_scene(scene)
        self.model = mujoco.MjModel.from_xml_path(str(self.scene_path))
        self.data = mujoco.MjData(self.model)
        self.fps = fps
        # Make the control period an exact multiple of the physics time step
        base_dt = self.model.opt.timestep
        self.n_substeps = max(1, round(1.0 / fps / base_dt))
        self.model.opt.timestep = 1.0 / fps / self.n_substeps
        self.control_dt = 1.0 / fps
        self.tcp_site = self.model.site("tcp").id

        m = self.model
        self.arm_qadr = np.array([m.jnt_qposadr[m.joint(j).id] for j in ARM_JOINTS])
        self.arm_dofadr = np.array([m.jnt_dofadr[m.joint(j).id] for j in ARM_JOINTS])
        self.arm_act = np.array([m.actuator(j).id for j in ARM_JOINTS])
        self.finger_qadr = np.array([m.jnt_qposadr[m.joint(j).id] for j in FINGER_JOINTS])
        self.gripper_act = m.actuator("gripper").id
        self.reset()

    def step(self) -> None:
        """Advance one control period."""
        mujoco.mj_step(self.model, self.data, nstep=self.n_substeps)

    @property
    def time(self) -> float:
        return float(self.data.time)

    def reset(self, arm_q: np.ndarray = HOME_QPOS, gripper: float = 0.0) -> None:
        """Reset to the given joint angles (rad) and gripper opening (m)."""
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.arm_qadr] = arm_q
        self.data.qpos[self.finger_qadr] = gripper
        self.set_targets(arm_q, gripper)
        mujoco.mj_forward(self.model, self.data)

    def set_targets(self, arm_q: np.ndarray, gripper: float = 0.0) -> None:
        """Set joint targets: 6 arm joint angles (rad) + single-finger gripper opening (m)."""
        lo = self.model.actuator_ctrlrange[self.arm_act, 0]
        hi = self.model.actuator_ctrlrange[self.arm_act, 1]
        self.data.ctrl[self.arm_act] = np.clip(arm_q, lo, hi)
        self.data.ctrl[self.gripper_act] = float(np.clip(gripper, 0.0, GRIPPER_STROKE))

    def tcp_pose(self) -> tuple[np.ndarray, np.ndarray]:
        """TCP (position, rotation matrix) in the world frame (= robot base frame)."""
        return self.data.site_xpos[self.tcp_site].copy(), self.data.site_xmat[self.tcp_site].reshape(3, 3).copy()

    def arm_q(self) -> np.ndarray:
        return self.data.qpos[self.arm_qadr].copy()

    def gripper_q(self) -> float:
        return float(self.data.qpos[self.finger_qadr].mean())

    def motor_state_deg(self) -> np.ndarray:
        """7 motor angles (deg), same meaning as the angles that the physical motors report."""
        return sim_to_motor_deg(self.arm_q(), self.gripper_q())

    def close(self) -> None:
        """Nothing to release (no offscreen renderer); kept so that callers can always close the sim."""
