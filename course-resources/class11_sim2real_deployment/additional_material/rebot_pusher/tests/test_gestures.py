"""Hands-free gestures of the handheld recorder (rebot_sim.teleop.gestures)."""

import numpy as np

from rebot_sim.pose import rot_z
from rebot_sim.teleop.gestures import GestureDetector

HZ = 50


def feed(det, poses, t0=0.0):
    """Feed (p, R) samples at HZ; return the list of (t, event)."""
    events = []
    for i, (p, R) in enumerate(poses):
        t = t0 + i / HZ
        g = det.update(p, R, t)
        if g:
            events.append((round(t, 2), g))
    return events


def still(p, seconds, R=None):
    return [(np.array(p, float), np.eye(3) if R is None else R)] * int(seconds * HZ)


def move(p0, p1, seconds, R=None):
    n = int(seconds * HZ)
    return [(np.array(p0, float) + (np.array(p1, float) - np.array(p0, float)) * k / n, np.eye(3) if R is None else R)
            for k in range(1, n + 1)]


def test_start_then_lift_to_save():
    det = GestureDetector()
    start = [0.33, 0.0, 0.12]
    poses = (still(start, 1.0) + move(start, [0.33, 0.0, 0.02], 1.0)  # go down to the table
             + move([0.33, 0, 0.02], [0.42, 0.05, 0.02], 2.0)  # push
             + move([0.42, 0.05, 0.02], [0.42, 0.05, 0.22], 1.0)  # lift 10 cm above the start height
             + still([0.42, 0.05, 0.22], 1.0))
    ev = feed(det, poses)
    assert [e for _, e in ev] == ["start", "save"]
    assert 1.3 <= ev[0][0] <= 1.6  # start about 0.3 s after the tool begins to move
    assert ev[1][0] > 5.5  # saved after holding still above the start height
    assert not det.recording  # back to idle after the save


def test_lift_without_hold_or_too_low_does_not_save():
    det = GestureDetector()
    start = [0.33, 0.0, 0.12]
    poses = still(start, 1.0) + move(start, [0.4, 0, 0.02], 1.5) + move([0.4, 0, 0.02], [0.4, 0, 0.17], 1.0) + still([0.4, 0, 0.17], 2.0)
    assert [e for _, e in feed(det, poses)] == ["start"]  # only 5 cm above the start height: no save
    det = GestureDetector()
    poses = still(start, 1.0) + move(start, [0.4, 0, 0.02], 1.5) + move([0.4, 0, 0.02], [0.4, 0, 0.3], 0.5) + move([0.4, 0, 0.3], [0.4, 0, 0.02], 0.5)
    assert [e for _, e in feed(det, poses)] == ["start"]  # lifted but not held still


def test_shake_discards():
    det = GestureDetector()
    start = [0.33, 0.0, 0.12]
    shake = [(np.array([0.4, 0, 0.05]), rot_z(np.radians(25) * np.sin(2 * np.pi * 3 * k / HZ)))  # +-25 deg twist at 3 Hz
             for k in range(int(0.8 * HZ))]
    poses = still(start, 1.0) + move(start, [0.4, 0, 0.05], 1.5) + shake
    ev = feed(det, poses)
    assert [e for _, e in ev] == ["start", "discard"]
    assert not det.recording


def test_no_start_without_a_still_phase():
    det = GestureDetector()
    poses = move([0.3, 0, 0.1], [0.5, 0, 0.1], 2.0)  # moving from the first sample on
    assert feed(det, poses) == []
    poses = still([0.5, 0, 0.1], 0.6) + move([0.5, 0, 0.1], [0.3, 0, 0.1], 1.0)
    assert [e for _, e in feed(det, poses, t0=2.0)] == ["start"]


def test_table_touch_before_start():
    from rebot_sim.teleop.gestures import table_from_touches

    det = GestureDetector()
    table, start = [0.33, 0.0, 0.0], [0.33, 0.0, 0.12]
    poses = still(table, 1.0) + move(table, start, 0.8) + still(start, 1.0) + move(start, [0.4, 0, 0.02], 1.0)
    samples, events = [], []
    for i, (p, R) in enumerate(poses):
        t = i / HZ
        g = det.update(p, R, t)
        if det.is_still:
            samples.append((t, float(p[2])))
        if g:
            events.append((t, g))
    assert [e for _, e in events] == ["start"]
    t_start = events[0][0]
    assert table_from_touches(samples, t_start, 0.12) == 0.0  # the rest on the table, 12 cm below the start
    assert table_from_touches(samples, t_start, 0.12, window=0.5) is None  # touch too long ago
    assert table_from_touches([(t_start - 1, 0.10)], t_start, 0.12) is None  # not far enough below the start
