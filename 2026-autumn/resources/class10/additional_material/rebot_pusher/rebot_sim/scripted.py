"""Scripted Push Cube expert (uses privileged simulator state: cube and goal positions).

Purpose: generate demonstrations automatically when no human teleoperation data is available, to
validate the full "record -> train -> evaluate" pipeline.
Strategy: lift and move behind the cube (relative to the goal direction), descend to pushing height,
push along the cube -> goal line, and re-approach if the cube drifts off the pushing line.
"""

from __future__ import annotations

import numpy as np

from .sim import SceneSim
from .tasks import PushCubeTask
from .teleop.ee_controller import EEController
from .teleop.tool_controller import ToolController


class PushCubeExpert:
    def __init__(
        self,
        controller: EEController | ToolController,
        task: PushCubeTask,
        safe_height: float = 0.07,
        push_speed: float = 0.08,
        stop_dist: float = 0.008,
        push_height: float | None = None,
        rng: np.random.Generator | None = None,
    ) -> None:
        assert getattr(controller, "mode", "xyz") in ("xyz", "6d"), "the expert controls the height: use the xyz mode"
        self.ctrl = controller
        self.task = task
        self.push_height = task.push_height if push_height is None else push_height
        self.safe_height = safe_height
        self.push_speed = push_speed
        self.stop_dist = stop_dist
        self._retreat = np.zeros(3)
        self.rng = rng or np.random.default_rng()
        self.reset()

    def reset(self) -> None:
        self.phase = "lift"
        # Randomize the approach standoff per episode for more diverse data
        self.standoff = self.rng.uniform(0.05, 0.065)
        self._descend_frames = 0

    def _geometry(self, sim: SceneSim) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        cube, goal, _ = self.task._cube_goal(sim)
        u = goal - cube
        n = np.linalg.norm(u)
        u = u / n if n > 1e-6 else np.array([1.0, 0.0])
        return cube, goal, u

    def act(self, sim: SceneSim) -> np.ndarray:
        """Robot use: return the 6-D joint target (rad) for this control period."""
        return self.ctrl.command(self.target(sim))

    def target(self, sim: SceneSim) -> np.ndarray:
        """Desired TCP position for this control period (the controller applies speed/workspace limits).

        Only reads the controller state, so it can drive any executor (robot IK or the handheld tool).
        """
        cube, goal, u = self._geometry(sim)
        tcp_cmd = self.ctrl.target_pos
        tcp = sim.tcp_pose()[0]  # actual TCP (PD tracking lags behind the target)
        h = self.push_height
        pre = cube - u * self.standoff
        rel = tcp[:2] - cube
        along = -float(np.dot(rel, u))  # > 0 means the TCP is behind the cube
        lateral = float(abs(u[0] * rel[1] - u[1] * rel[0]))
        dist = float(np.linalg.norm(goal - cube))

        if self.phase == "push" and dist < self.stop_dist:
            self.phase = "retreat"
            self._retreat = np.array([tcp[0] - u[0] * 0.02, tcp[1] - u[1] * 0.02, self.safe_height])
        if self.phase in ("retreat", "done") and dist > self.task.success_dist:
            self.phase = "lift"  # cube was knocked out of the goal: push again

        if self.phase == "retreat":  # in place: stop pushing, back off and lift
            target = self._retreat
            if tcp[2] > self.safe_height - 0.01:
                self.phase = "done"
        elif self.phase == "done":
            target = self._retreat
        elif self.phase == "lift":
            target = np.array([tcp_cmd[0], tcp_cmd[1], self.safe_height])
            if abs(tcp_cmd[2] - self.safe_height) < 0.005:
                self.phase = "move_over"
                self._descend_frames = 0
        elif self.phase == "move_over":
            target = np.array([pre[0], pre[1], self.safe_height])
            if np.linalg.norm(tcp_cmd[:2] - pre) < 0.006:
                self.phase = "descend"
        elif self.phase == "descend":
            target = np.array([pre[0], pre[1], h])
            self._descend_frames += 1
            if abs(tcp[2] - h) < 0.006:
                self.phase = "push"
            elif self._descend_frames > 40:  # probably landed on the cube: lift and increase the standoff
                self.standoff += 0.01
                self.phase = "lift"
        else:  # push: target on the pushing line (removes lateral error), slower near the goal
            speed = float(np.clip(2.0 * dist, 0.02, self.push_speed))
            on_line = cube - u * max(along, 0.0)
            xy = on_line + u * speed * self.ctrl.dt * 3.0
            target = np.array([xy[0], xy[1], h])
            if lateral > 0.015 or along < 0.0:
                self.phase = "lift"
        return target


class PushTExpert:
    """Scripted Push-T expert built from push primitives (uses privileged T / goal poses).

    Each primitive: lift, move above a standoff point, descend, push along a line, lift again, re-plan.

    * rotation push: when the angle error is large, push one end of the bar perpendicular to it (lever arm about
      the T centroid) to turn the T towards the goal angle;
    * translation push: otherwise push through the T centroid towards the goal centroid.
    """

    # Area-weighted centroid of the T in its local frame (bar 0.1 x 0.025 at the origin, stem below it)
    CENTROID = np.array([0.0, -0.05 * 0.001875 / 0.004375])

    def __init__(
        self,
        controller: EEController | ToolController,
        task,
        push_height: float,
        safe_height: float = 0.06,
        push_speed: float = 0.06,
        rot_threshold_deg: float = 12.0,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.ctrl = controller
        self.task = task
        self.push_height = push_height
        self.safe_height = safe_height
        self.push_speed = push_speed
        self.rot_threshold = np.radians(rot_threshold_deg)
        self.rng = rng or np.random.default_rng()
        self.phase = "plan"
        self._prim: dict | None = None
        self._frames = 0

    @staticmethod
    def _rot2(a: float) -> np.ndarray:
        return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])

    def _state(self, sim):
        x, y, th = self.task.t_pose(sim)
        gx, gy, gth = self.task.goal_pose
        c = np.array([x, y]) + self._rot2(th) @ self.CENTROID
        gc = np.array([gx, gy]) + self._rot2(gth) @ self.CENTROID
        dth = (gth - th + np.pi) % (2 * np.pi) - np.pi
        return np.array([x, y]), th, c, gc, dth

    def _reachable(self, pre: np.ndarray, margin: float = 0.01) -> bool:
        lim = getattr(self.ctrl, "limits", None)
        if lim is None:
            return True
        return lim.x[0] + margin <= pre[0] <= lim.x[1] - margin and lim.y[0] + margin <= pre[1] <= lim.y[1] - margin

    def _rotation_candidates(self, p, R, dth, c, gc) -> list[dict]:
        # Push a bar end perpendicular to the bar. For a counter-clockwise turn: +x end pushed along +y_local
        # (from below the bar) or -x end pushed along -y_local (from above); mirrored for clockwise.
        s = 1.0 if dth > 0 else -1.0
        dist = float(np.clip(abs(dth) * 0.035, 0.008, 0.03))
        cands = []
        for end, dy in ((s, 1.0), (-s, -1.0)):
            contact = p + R @ np.array([end * 0.042, -0.0125 * dy])
            direction = R @ np.array([0.0, dy])
            cands.append({"kind": "rot", "contact": contact, "dir": direction, "dist": dist,
                          "score": float(direction @ (gc - c))})  # prefer the push that also moves towards the goal
        return sorted(cands, key=lambda d: -d["score"])

    def _plan(self, sim) -> dict:
        p, th, c, gc, dth = self._state(sim)
        R = self._rot2(th)
        cands = []
        e = gc - c
        n = np.linalg.norm(e)
        # coarse: rotate when far off in angle; fine: once roughly in place, also fix small angle errors
        need_rot = abs(dth) > self.rot_threshold or (n < 0.015 and abs(dth) > np.radians(3.0))
        if need_rot:
            cands += self._rotation_candidates(p, R, dth, c, gc)
        direction = e / n if n > 1e-6 else np.array([1.0, 0.0])
        # entry point: where the line through the centroid (against the push direction) leaves the T
        s = 0.0
        while s < 0.12 and self.task._inside_t((np.array([c - direction * s]) - p) @ R)[0]:
            s += 0.002
        cands.append({"kind": "trans", "contact": c - direction * s, "dir": direction, "dist": float(min(n, 0.06)) + 0.005})
        if not need_rot:  # fallbacks if the translation push cannot start from where it should
            cands += self._rotation_candidates(p, R, dth if abs(dth) > 1e-3 else 1e-3, c, gc)
        for cand in cands:
            if self._reachable(cand["contact"] - cand["dir"] * 0.035):
                return cand
        return cands[0]

    def target(self, sim) -> np.ndarray:
        tcp_cmd = self.ctrl.target_pos
        tcp = sim.tcp_pose()[0]
        h = self.push_height
        success = self.task.evaluate(sim).success
        if success and self.phase not in ("retreat", "done"):
            self.phase = "retreat"
        if self.phase in ("retreat", "done"):
            if not success:
                self.phase = "plan"
            else:
                self.phase = "done" if tcp[2] > self.safe_height - 0.01 else "retreat"
                return np.array([tcp_cmd[0], tcp_cmd[1], self.safe_height])
        if self.phase == "plan":
            self._prim = self._plan(sim)
            self._prim["pre"] = self._prim["contact"] - self._prim["dir"] * 0.035
            self.phase, self._frames = "lift", 0
        prim = self._prim
        if self.phase == "lift":
            if abs(tcp_cmd[2] - self.safe_height) < 0.005 or tcp_cmd[2] > self.safe_height:
                self.phase = "move_over"
            return np.array([tcp_cmd[0], tcp_cmd[1], max(self.safe_height, tcp_cmd[2])])
        if self.phase == "move_over":
            self._frames += 1
            if np.linalg.norm(tcp_cmd[:2] - prim["pre"]) < 0.006:
                self.phase, self._frames = "descend", 0
            elif self._frames > 90:  # cannot get there (limits): re-plan
                self.phase = "plan"
            return np.array([*prim["pre"], self.safe_height])
        if self.phase == "descend":
            self._frames += 1
            if abs(tcp[2] - h) < 0.006:
                self.phase, self._frames = "push", 0
                prim["start"] = tcp[:2].copy()
            elif self._frames > 40:  # landed on the block: re-plan from a different place
                self.phase = "plan"
            return np.array([*prim["pre"], h])
        # push along the primitive line until the planned distance past the contact point
        self._frames += 1
        travelled = float(np.dot(tcp[:2] - prim["start"], prim["dir"]))
        if travelled > 0.035 + prim["dist"] or self._frames > 120:
            self.phase = "plan"
        xy = tcp_cmd[:2] + prim["dir"] * self.push_speed * self.ctrl.dt
        return np.array([xy[0], xy[1], h])

    def reset(self) -> None:
        self.phase, self._prim, self._frames = "plan", None, 0
