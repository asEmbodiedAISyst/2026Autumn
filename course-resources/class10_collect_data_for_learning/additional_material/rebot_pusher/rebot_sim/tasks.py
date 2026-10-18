"""Tabletop pushing tasks: Push Cube and Push-T.

Each task selects its scene, randomizes the initial layout, computes reward/success and reports the
object state. The ``description`` string is written to the ``task`` field of LeRobot datasets (used by VLAs).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .sim import SceneSim

# Pushing workspace (robot base frame, m): reachable with the gripper pointing down, with some margin
WORKSPACE_X = (0.18, 0.36)
WORKSPACE_Y = (-0.15, 0.15)

# TCP height while pushing, per end effector: gripper TCP sits 1.5 cm inside the fingertips (fingertips about
# 1 cm above the table); the pusher tool TCP is the bottom of the rod tip (6 mm above the table).
PUSH_HEIGHT = {"gripper": 0.025, "pusher": 0.006, "handheld": 0.006}


def yaw_to_quat(yaw: float) -> np.ndarray:
    return np.array([math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)])


def quat_to_yaw(q: np.ndarray) -> float:
    w, x, y, z = q
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def wrap_angle(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


@dataclass
class TaskResult:
    success: bool
    reward: float
    info: dict = field(default_factory=dict)


class Task:
    name: str = ""
    workspace_x: tuple[float, float] = WORKSPACE_X  # object placement area (robot base frame, m)
    workspace_y: tuple[float, float] = WORKSPACE_Y
    scene: str = "table"
    description: str = ""
    # Default TCP height while pushing: fingertips about 1 cm above the table
    push_height: float = 0.025

    def scene_for(self, embodiment: str) -> str:
        """Scene name for an end effector ("gripper" / "pusher" / "handheld")."""
        return self.scene if embodiment == "gripper" else f"{embodiment}_{self.scene}"

    def reset(self, sim: SceneSim, rng: np.random.Generator) -> None:
        raise NotImplementedError

    def evaluate(self, sim: SceneSim) -> TaskResult:
        raise NotImplementedError

    def object_state(self, sim: SceneSim) -> np.ndarray:
        """Object state (simulation only; can be used as ``observation.environment_state``)."""
        raise NotImplementedError


class PushCubeTask(Task):
    """Push a 4 cm black cube into a 6 cm green target area."""

    name = "push_cube"
    scene = "push_cube"
    description = "Push the black cube into the green target area."
    success_dist = 0.015
    cube_half = 0.02
    min_start_dist = 0.10
    max_start_dist = 0.22

    def __init__(self, push_dir_range_deg: float | None = None) -> None:
        # If set, the goal is placed "in front of" the cube: the push direction (cube -> goal) is within
        # +-push_dir_range_deg of +x (away from the robot base). Used with the wrist-only phone camera, so the
        # operator can face the push direction and keep cube and goal in view.
        self.push_dir_range = None if push_dir_range_deg is None else math.radians(push_dir_range_deg)

    def reset(self, sim: SceneSim, rng: np.random.Generator) -> None:
        cube, goal, yaw = self.sample_layout(rng)
        sim.set_free_body_pose("cube_joint", np.array([*cube, self.cube_half]), yaw_to_quat(yaw))
        sim.set_mocap_pose("goal", np.array([*goal, 0.0]))

    def sample_layout(self, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, float]:
        """Random cube xy, goal xy (robot base frame, m) and cube yaw (rad); also used to lay out real episodes."""
        lo = np.array([self.workspace_x[0], self.workspace_y[0]])
        hi = np.array([self.workspace_x[1], self.workspace_y[1]])
        for _ in range(1000):
            cube = rng.uniform(lo, hi)
            if self.push_dir_range is None:
                goal = rng.uniform(lo, hi)
            else:
                a = rng.uniform(-self.push_dir_range, self.push_dir_range)
                goal = cube + rng.uniform(self.min_start_dist, self.max_start_dist) * np.array([math.cos(a), math.sin(a)])
            d = np.linalg.norm(cube - goal)
            if self.min_start_dist <= d <= self.max_start_dist and np.all(goal >= lo) and np.all(goal <= hi):
                break
        return cube, goal, rng.uniform(-math.pi / 4, math.pi / 4)

    def _cube_goal(self, sim: SceneSim) -> tuple[np.ndarray, np.ndarray, float]:
        pos, quat = sim.body_pose("cube")
        goal = sim.data.mocap_pos[sim.model.body("goal").mocapid[0]][:2].copy()
        return pos[:2], goal, quat_to_yaw(quat)

    def evaluate(self, sim: SceneSim) -> TaskResult:
        cube, goal, _ = self._cube_goal(sim)
        d = float(np.linalg.norm(cube - goal))
        return TaskResult(success=d < self.success_dist, reward=-d, info={"distance": d})

    def object_state(self, sim: SceneSim) -> np.ndarray:
        cube, goal, yaw = self._cube_goal(sim)
        return np.array([*cube, yaw, *goal], dtype=np.float32)


class PushTTask(Task):
    """Push a T-shaped block onto a fixed target T (coverage >= success_coverage)."""

    name = "push_t"
    scene = "push_t"
    description = "Push the T-shaped block to match the green T target."
    goal_pose = (0.27, 0.0, 0.0)  # x, y, yaw
    success_coverage = 0.90
    t_half_height = 0.0125
    # T shape (local frame; rectangle centers and half sizes), must match scene_push_t.xml
    rects = (((0.0, 0.0), (0.05, 0.0125)), ((0.0, -0.05), (0.0125, 0.0375)))

    def __init__(self) -> None:
        # Uniform sample points inside the T, used to compute coverage
        pts = []
        res = 0.002
        for (cx, cy), (hx, hy) in self.rects:
            nx, ny = max(2, round(2 * hx / res)), max(2, round(2 * hy / res))
            # Use cell centers so every sample lies strictly inside its rectangle
            xs = cx - hx + (np.arange(nx) + 0.5) * (2 * hx / nx)
            ys = cy - hy + (np.arange(ny) + 0.5) * (2 * hy / ny)
            gx, gy = np.meshgrid(xs, ys)
            pts.append(np.stack([gx.ravel(), gy.ravel()], 1))
        self._samples = np.concatenate(pts)

    def _inside_t(self, pts: np.ndarray) -> np.ndarray:
        inside = np.zeros(len(pts), dtype=bool)
        for (cx, cy), (hx, hy) in self.rects:
            inside |= (np.abs(pts[:, 0] - cx) <= hx) & (np.abs(pts[:, 1] - cy) <= hy)
        return inside

    def coverage(self, pose: tuple[float, float, float]) -> float:
        """Fraction of the target T covered by a T at ``pose``."""
        x, y, yaw = pose
        gx, gy, gyaw = self.goal_pose
        c, s = math.cos(yaw), math.sin(yaw)
        world = self._samples @ np.array([[c, s], [-s, c]]) + np.array([x, y])
        cg, sg = math.cos(gyaw), math.sin(gyaw)
        local = (world - np.array([gx, gy])) @ np.array([[cg, -sg], [sg, cg]])
        return float(self._inside_t(local).mean())

    def reset(self, sim: SceneSim, rng: np.random.Generator) -> None:
        gx, gy, gyaw = self.goal_pose
        sim.set_mocap_pose("t_goal", np.array([gx, gy, 0.0]), yaw_to_quat(gyaw))
        for _ in range(1000):
            x = rng.uniform(self.workspace_x[0] + 0.02, self.workspace_x[1] - 0.02)
            y = rng.uniform(self.workspace_y[0] + 0.02, self.workspace_y[1] - 0.02)
            yaw = rng.uniform(-math.pi, math.pi)
            if self.coverage((x, y, yaw)) < 0.3:
                break
        sim.set_free_body_pose("tblock_joint", np.array([x, y, self.t_half_height]), yaw_to_quat(yaw))

    def t_pose(self, sim: SceneSim) -> tuple[float, float, float]:
        pos, quat = sim.body_pose("tblock")
        return float(pos[0]), float(pos[1]), quat_to_yaw(quat)

    def evaluate(self, sim: SceneSim) -> TaskResult:
        cov = self.coverage(self.t_pose(sim))
        return TaskResult(success=cov >= self.success_coverage, reward=cov, info={"coverage": cov})

    def object_state(self, sim: SceneSim) -> np.ndarray:
        return np.array(self.t_pose(sim), dtype=np.float32)


TASKS: dict[str, type[Task]] = {"push_cube": PushCubeTask, "push_t": PushTTask}


def make_task(name: str) -> Task:
    if name not in TASKS:
        raise KeyError(f"unknown task {name!r}; choices: {list(TASKS)}")
    return TASKS[name]()
