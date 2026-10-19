"""Hands-free episode control from the motion of the handheld tool (no keyboard needed while collecting).

The operator holds the tool with both hands and cannot reach a keyboard; the recording is controlled by three
gestures read from the gravity-aligned pusher-tip pose stream:

* **start**: after the tool has been still for a moment at the start mark, it starts moving;
* **save**: the tip is lifted clearly above the start height (``lift_m``) and held still (``hold_time``);
* **discard**: the tool is shaken / twisted fast (angular speed above ``shake_rate`` for ``shake_time``).

The detector also exposes whether the tool is currently still (:attr:`GestureDetector.is_still`), which the
recorder uses to find the **table touch** before an episode: the tip rests on the table for a moment, is lifted
to the start pose and the episode starts; :func:`table_from_touches` picks the touch height out of the still
samples. ARKit's position drifts by centimetres over minutes, so the table is re-measured for every episode.
"""

from __future__ import annotations

from collections import deque

import numpy as np


class GestureDetector:
    def __init__(self, start_speed: float = 0.04, still_speed: float = 0.02, still_time: float = 0.5,
                 move_time: float = 0.3, lift_m: float = 0.08, hold_time: float = 0.7, shake_rate: float = 5.0,
                 shake_time: float = 0.4, min_episode_time: float = 1.0, window: float = 1.0,
                 lift_reject: float = 0.04) -> None:
        # lift_reject: a movement that rises more than this above the still pose is a lift (e.g. from the table
        # touch up to the start pose), not the start of an episode; a new still phase is required afterwards
        self.lift_reject = lift_reject
        self.start_speed, self.still_speed = start_speed, still_speed
        self.still_time, self.move_time = still_time, move_time
        self.lift_m, self.hold_time = lift_m, hold_time
        self.shake_rate, self.shake_time = shake_rate, shake_time
        self.min_episode_time, self.window = min_episode_time, window
        self.reset()

    def reset(self) -> None:
        """Back to idle: a new start needs a still phase first."""
        self.recording = False
        self._hist: deque[tuple[float, np.ndarray, np.ndarray]] = deque()
        self._still_since: float | None = None
        self._still_pos: np.ndarray | None = None  # where the tool rested during the last still phase
        self.is_still = False  # speed below still_speed for at least still_time (updated by update())
        self.last_pos: np.ndarray | None = None
        self._moving_since: float | None = None
        self._lift_since: float | None = None
        self._shake: deque[tuple[float, float]] = deque()  # (t, dt) samples above shake_rate
        self._z0 = 0.0
        self._t0 = 0.0

    def _rates(self, t: float) -> tuple[float, float] | None:
        """Linear speed (m/s) over the last ~0.1-0.25 s and angular speed (rad/s) between the last two samples
        (a shake reverses direction several times per second, so it must not be averaged over the window);
        None until there is enough history."""
        ref = None
        for t_old, p_old, R_old in self._hist:
            if t - t_old <= 0.25:
                ref = (t_old, p_old, R_old)
                break
        if ref is None or t - ref[0] < 0.1:
            return None
        t_old, p_old, _ = ref
        _, p, R = self._hist[-1]
        t_prev, _, R_prev = self._hist[-2]
        ang = np.arccos(np.clip((np.trace(R_prev.T @ R) - 1) / 2, -1.0, 1.0))
        return float(np.linalg.norm(p - p_old) / (t - t_old)), float(ang / max(t - t_prev, 1e-3))

    def update(self, p: np.ndarray, R: np.ndarray, t: float) -> str | None:
        """Feed one pose sample; returns "start", "save", "discard" or None."""
        self._hist.append((t, np.asarray(p, dtype=float).copy(), np.asarray(R, dtype=float).copy()))
        while self._hist and t - self._hist[0][0] > self.window:
            self._hist.popleft()
        rates = self._rates(t)
        self.last_pos = self._hist[-1][1]
        if rates is None:
            return None
        speed, ang_speed = rates
        if not self.recording:
            if speed < self.still_speed:
                self._still_since = t if self._still_since is None else self._still_since
                self._still_pos = self.last_pos
                self._moving_since = None
                self.is_still = t - self._still_since >= self.still_time
                return None
            self.is_still = False
            was_still = self._still_since is not None and t - self._still_since >= self.still_time
            if was_still and self._still_pos is not None and p[2] - self._still_pos[2] > self.lift_reject:
                self._still_since = None  # lifting off (table touch -> start pose): wait for a new still phase
                self._moving_since = None
                return None
            # _still_since is kept while moving so that a short wobble does not reset the still phase
            if speed > self.start_speed and was_still:
                self._moving_since = t if self._moving_since is None else self._moving_since
                if t - self._moving_since >= self.move_time:
                    self.recording = True
                    self._t0 = t
                    self._z0 = float(self._hist[0][1][2])  # height where the tool was resting before it moved
                    self._lift_since = None
                    self._shake.clear()
                    return "start"
            else:
                self._moving_since = None
            return None
        # recording
        if t - self._t0 < self.min_episode_time:
            return None
        dt = t - self._hist[-2][0] if len(self._hist) > 1 else 0.0
        if ang_speed > self.shake_rate:
            self._shake.append((t, dt))
        while self._shake and t - self._shake[0][0] > self.window:
            self._shake.popleft()
        if sum(d for _, d in self._shake) >= self.shake_time:
            self.reset()
            return "discard"
        if p[2] - self._z0 > self.lift_m and speed < self.still_speed:
            self._lift_since = t if self._lift_since is None else self._lift_since
            if t - self._lift_since >= self.hold_time:
                self.reset()
                return "save"
        else:
            self._lift_since = None
        return None


def table_from_touches(still_samples: list[tuple[float, float]], t_start: float, start_z: float,
                       window: float = 30.0, min_drop: float = 0.05) -> float | None:
    """Table height from the still phases before an episode start.

    ``still_samples`` are ``(t, z)`` of samples taken while the tool was still; the touch is the lowest still
    height within ``window`` seconds before ``t_start`` that lies at least ``min_drop`` below the start height
    (the tool rests on the table, is lifted and then starts). None if no such touch was seen.
    """
    zs = [z for t, z in still_samples if t_start - window <= t <= t_start]
    if not zs:
        return None
    z = min(zs)
    return z if start_z - z >= min_drop else None
