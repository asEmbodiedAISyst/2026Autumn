"""Controlled-motion example for the reBot Arm B601-RS in simulation (Class 08).

Two motions, with smooth targets and declared joint bounds:

* ``joints``: joint-by-joint motion. From the home pose, each of the six joints moves +10 degrees, back, -10 degrees
  and back with a smooth (cosine) profile while the other joints hold. Then the gripper opens and closes.
  This is the motion of Gate C ("bounded motion of +-10 degrees for each joint").
* ``letters``: Cartesian motion. The tool centre point (TCP) keeps the gripper vertical and draws the letters
  "ROB" on a plane 3 cm above the table, with a lift between the letters. Inverse kinematics (damped least squares
  on the MuJoCo Jacobian) turns each TCP target into joint targets. The viewer draws the TCP path as small spheres.

Standalone: needs only ``mujoco`` and ``numpy``. The model is ``../model/rebot_b601_rs_mjcf/scene_table.xml``.

     .venv/bin/python code/controlled_motion.py                    # Ubuntu: both motions, in the viewer
    .venv/bin/mjpython code/controlled_motion.py                  # macOS: the viewer needs mjpython
     .venv/bin/python code/controlled_motion.py --mode joints      # only the joint-by-joint motion
     .venv/bin/python code/controlled_motion.py --mode letters     # only the "ROB" drawing
     .venv/bin/python code/controlled_motion.py --no-viewer        # no window: run the motions and print the errors

What the terminal prints: for each joint, the largest tracking error between the commanded and the measured joint
angle (degrees); for the drawing, the largest distance between the commanded and the measured TCP position (mm).
These numbers are the simulation side of the Gate C evidence. The same motions on the physical arm are not part
of this package yet.

How the script works:

1. The arm is driven like the physical arm: one joint target per control period (30 Hz) that the position
   actuators (PD + gravity compensation) follow. Between two control periods the physics runs in 17 steps per period at 1/510 s per step.
2. ``cosine_profile`` makes a smooth target that starts and ends at rest.
3. ``DlsIk.solve`` iterates ``dq = J^T (J J^T + lambda I)^-1 e`` with the position and orientation error of the TCP
   site, clipped to the joint limits, with a small pull toward the home posture.
4. The "ROB" letters are polylines in a unit box, scaled to 6 cm and placed in front of the arm. The letters read
   correctly when you look down at the table with the robot base at the top of the view.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import mujoco
import numpy as np

MODEL_DIR = Path(__file__).resolve().parents[1] / "model" / "rebot_b601_rs_mjcf"
SCENE = "scene_table.xml"
ARM_JOINTS = tuple(f"joint{i}" for i in range(1, 7))
HOME_QPOS = np.array([0.0, 1.532, 1.197, -1.236, 0.0, 0.0])  # rad; gripper vertical, TCP at (0.25, 0, 0.10) m
# Soft limits of the physical arm (motor degrees), in joint order; the motions stay inside them.
SOFT_LIMITS_DEG = ((-145, 145), (0, 170), (0, 200), (-80, 90), (-90, 90), (-130, 130))
# TCP orientation with the gripper pointing down: columns are the TCP axes in the world frame
# (z down = approach direction, y to world -y = left-finger opening direction, x forward).
TCP_DOWN_ROT = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]])

CONTROL_HZ = 30  # same as the LeRobot recording rate of the course
JOINT_AMPLITUDE_DEG = 10.0  # Gate C bounded motion
JOINT_SEGMENT_S = 1.5  # time of one move (home -> +10 deg), then the same back
GRIPPER_OPEN_M = 0.03  # single-finger stroke (m)
DRAW_SPEED = 0.04  # segment duration scale (m/s); half-cosine interpolation has a higher peak speed
DRAW_Z, LIFT_Z = 0.03, 0.08  # TCP height on the drawing plane and between letters (m)
LETTER_HEIGHT = 0.06  # m
LETTER_ORIGIN = np.array([0.33, -0.075])  # world (x, y) of the lower-left corner of the first letter

# Letters as polylines in a unit box (u to the right, v up); each stroke is one pen-down segment.
LETTERS = {
    "R": [[(0, 0), (0, 1), (0.6, 1), (0.7, 0.9), (0.7, 0.6), (0.6, 0.5), (0, 0.5)], [(0.3, 0.5), (0.7, 0)]],
    "O": [[(0.35 + 0.35 * np.cos(a), 0.5 + 0.5 * np.sin(a)) for a in np.linspace(np.pi / 2, np.pi / 2 + 2 * np.pi, 25)]],
    "B": [[(0, 0), (0, 1), (0.55, 1), (0.7, 0.85), (0.7, 0.65), (0.55, 0.5), (0, 0.5)],
          [(0.55, 0.5), (0.7, 0.35), (0.7, 0.15), (0.55, 0), (0, 0)]],
}
LETTER_WIDTH, LETTER_GAP = 0.7, 0.3  # in unit-box units


# ----------------------------------------------------------------------------- simulation helpers
class ArmSim:
    """The scene stepped at the control rate, with the same actuator interface as the physical arm."""

    def __init__(self) -> None:
        self.model = mujoco.MjModel.from_xml_path(str(MODEL_DIR / SCENE))
        self.data = mujoco.MjData(self.model)
        self.n_sub = round(1.0 / CONTROL_HZ / self.model.opt.timestep)  # physics steps per control period
        # Match the exact 30Hz control period, as in the pusher simulation.
        self.model.opt.timestep = 1.0 / (CONTROL_HZ * self.n_sub)
        self.qadr = np.array([self.model.jnt_qposadr[self.model.joint(j).id] for j in ARM_JOINTS])
        self.dofadr = np.array([self.model.jnt_dofadr[self.model.joint(j).id] for j in ARM_JOINTS])
        self.act = np.array([self.model.actuator(j).id for j in ARM_JOINTS])
        self.grip_act = self.model.actuator("gripper").id
        self.tcp = self.model.site("tcp").id
        self.reset(HOME_QPOS)

    def reset(self, q: np.ndarray) -> None:
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[self.qadr] = q
        self.data.ctrl[self.act] = q
        mujoco.mj_forward(self.model, self.data)

    def command(self, q: np.ndarray, gripper: float | None = None) -> None:
        """Set the joint targets (rad) and the gripper target (m) for the next control period."""
        self.data.ctrl[self.act] = q
        if gripper is not None:
            self.data.ctrl[self.grip_act] = gripper

    def step(self) -> None:
        mujoco.mj_step(self.model, self.data, nstep=self.n_sub)

    def q(self) -> np.ndarray:
        return self.data.qpos[self.qadr].copy()

    def tcp_pos(self) -> np.ndarray:
        return self.data.site_xpos[self.tcp].copy()


class DlsIk:
    """Damped least-squares inverse kinematics on a private copy of the state (does not touch the simulation)."""

    def __init__(self, model: mujoco.MjModel, damping: float = 1e-3, posture_gain: float = 0.05) -> None:
        self.model = model
        self.data = mujoco.MjData(model)
        self.site = model.site("tcp").id
        self.qadr = np.array([model.jnt_qposadr[model.joint(j).id] for j in ARM_JOINTS])
        self.dofadr = np.array([model.jnt_dofadr[model.joint(j).id] for j in ARM_JOINTS])
        # Joint limits: the tighter of the MJCF range and the soft limits of the physical arm
        lo = np.array([model.jnt_range[model.joint(j).id, 0] for j in ARM_JOINTS])
        hi = np.array([model.jnt_range[model.joint(j).id, 1] for j in ARM_JOINTS])
        self.lo = np.maximum(lo, np.radians([l for l, _ in SOFT_LIMITS_DEG]))
        self.hi = np.minimum(hi, np.radians([h for _, h in SOFT_LIMITS_DEG]))
        self.damping, self.posture_gain = damping, posture_gain
        self.jacp, self.jacr = np.zeros((3, model.nv)), np.zeros((3, model.nv))

    def fk(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        self.data.qpos[self.qadr] = q
        mujoco.mj_kinematics(self.model, self.data)
        mujoco.mj_comPos(self.model, self.data)
        return self.data.site_xpos[self.site].copy(), self.data.site_xmat[self.site].reshape(3, 3).copy()

    def solve(self, target_pos: np.ndarray, target_rot: np.ndarray, q0: np.ndarray, iters: int = 30) -> np.ndarray:
        q = np.clip(q0.copy(), self.lo, self.hi)
        for _ in range(iters):
            pos, rot = self.fk(q)
            e_pos = target_pos - pos
            # Orientation error as a small rotation vector (sum of the cross products of the axes)
            e_rot = 0.5 * sum(np.cross(rot[:, k], target_rot[:, k]) for k in range(3))
            if np.linalg.norm(e_pos) < 1e-4 and np.linalg.norm(e_rot) < 1e-3:
                break
            mujoco.mj_jacSite(self.model, self.data, self.jacp, self.jacr, self.site)
            J = np.vstack([self.jacp[:, self.dofadr], 0.3 * self.jacr[:, self.dofadr]])
            e = np.concatenate([e_pos, 0.3 * e_rot])
            J_pinv = J.T @ np.linalg.solve(J @ J.T + self.damping * np.eye(6), np.eye(6))
            dq = J_pinv @ e + (np.eye(6) - J_pinv @ J) @ (self.posture_gain * (HOME_QPOS - q))
            n = np.linalg.norm(dq)
            if n > 0.2:  # limit one iteration step to 0.2 rad
                dq *= 0.2 / n
            q = np.clip(q + dq, self.lo, self.hi)
        return q


def cosine_profile(a: float, b: float, n: int) -> np.ndarray:
    """``n`` values from ``a`` to ``b`` that start and end at rest (half-cosine ramp)."""
    s = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))
    return a + (b - a) * s


# ----------------------------------------------------------------------------- the two motions
def joint_by_joint(sim: ArmSim, show) -> None:
    """Each joint: home -> +10 deg -> home -> -10 deg -> home. Then the gripper opens and closes."""
    n = int(JOINT_SEGMENT_S * CONTROL_HZ)
    amp = np.radians(JOINT_AMPLITUDE_DEG)
    print("\njoint-by-joint motion: +-10 deg from the home pose, cosine profile, 1.5 s per move")
    for i, name in enumerate(ARM_JOINTS):
        worst = 0.0
        for sign in (+1.0, -1.0):
            target = HOME_QPOS[i] + sign * amp
            lo, hi = np.radians(SOFT_LIMITS_DEG[i])
            if not lo <= target <= hi:  # stay inside the soft limits of the physical arm
                print(f"  {name}: {sign * JOINT_AMPLITUDE_DEG:+.0f} deg skipped (outside the soft limit)")
                continue
            for q_i in np.concatenate([cosine_profile(HOME_QPOS[i], target, n), cosine_profile(target, HOME_QPOS[i], n)]):
                q = HOME_QPOS.copy()
                q[i] = q_i
                sim.command(q)
                sim.step()
                worst = max(worst, abs(np.degrees(sim.q()[i] - q_i)))
                show()
        print(f"  {name}: largest tracking error {worst:.2f} deg")
    print("  gripper: open to 0.03 m and close")
    for g in np.concatenate([cosine_profile(0.0, GRIPPER_OPEN_M, n), cosine_profile(GRIPPER_OPEN_M, 0.0, n)]):
        sim.command(HOME_QPOS, g)
        sim.step()
        show()


def letter_path() -> list[tuple[np.ndarray, bool]]:
    """TCP waypoints (x, y, z) in the world frame and a pen-down flag, for the letters ROB."""
    s = LETTER_HEIGHT
    pts: list[tuple[np.ndarray, bool]] = []
    u_off = 0.0
    for ch in "ROB":
        for stroke in LETTERS[ch]:
            first = True
            for u, v in stroke:
                # Seen from above (looking down at the table) with the robot base at the top of the view, image
                # right is world +y and image up is world -x. So u (right) -> +y and v (up) -> -x.
                p = np.array([LETTER_ORIGIN[0] - v * s, LETTER_ORIGIN[1] + (u_off + u) * s, DRAW_Z])
                if first:  # move above the stroke start with the pen lifted, then lower
                    pts.append((p + [0, 0, LIFT_Z - DRAW_Z], False))
                    pts.append((p, False))
                    first = False
                else:
                    pts.append((p, True))
            pts.append((pts[-1][0] + [0, 0, LIFT_Z - DRAW_Z], False))  # lift at the end of the stroke
        u_off += LETTER_WIDTH + LETTER_GAP
    return pts


def draw_letters(sim: ArmSim, show, trace) -> None:
    """Move the TCP along the ROB path using the DRAW_SPEED segment duration scale with the gripper vertical; report the tracking error."""
    ik = DlsIk(sim.model)
    pts = letter_path()
    q_cmd = sim.q()
    # Go from the home pose to the first waypoint
    start = sim.tcp_pos()
    worst = 0.0
    print(f"\nCartesian motion: the TCP draws ROB with segment duration scale {DRAW_SPEED} m/s, {LETTER_HEIGHT * 100:.0f} cm high, {DRAW_Z * 100:.0f} cm above the table")
    prev = start
    for p, pen in pts:
        n = max(2, int(np.linalg.norm(p - prev) / DRAW_SPEED * CONTROL_HZ))
        for k in range(1, n + 1):
            target = prev + (p - prev) * (0.5 - 0.5 * np.cos(np.pi * k / n))
            q_cmd = ik.solve(target, TCP_DOWN_ROT, q_cmd)
            sim.command(q_cmd)
            sim.step()
            err = np.linalg.norm(sim.tcp_pos() - target)
            worst = max(worst, err)
            if pen:
                trace(sim.tcp_pos())
            show()
        prev = p
    print(f"  largest TCP tracking error {worst * 1000:.1f} mm (the PD actuators lag behind the moving target)")
    # Back to home
    q_now = sim.q()
    for a in cosine_profile(0.0, 1.0, int(2 * CONTROL_HZ)):
        sim.command(q_now + (HOME_QPOS - q_now) * a)
        sim.step()
        show()


# ----------------------------------------------------------------------------- entry point
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["all", "joints", "letters"], default="all")
    ap.add_argument("--no-viewer", action="store_true", help="run without a window and print the errors")
    args = ap.parse_args()

    sim = ArmSim()
    print(f"model: model/rebot_b601_rs_mjcf/{SCENE}; control {CONTROL_HZ} Hz, {sim.n_sub} physics steps per period")

    if args.no_viewer:
        run(sim, args.mode, show=lambda: None, trace=lambda p: None)
        return
    if sys.platform == "darwin" and "mjpython" not in sys.executable:
        sys.exit("On macOS the viewer must run under mjpython:  .venv/bin/mjpython code/controlled_motion.py")
    from mujoco import viewer

    with viewer.launch_passive(sim.model, sim.data) as v:
        v.opt.geomgroup[3] = 0
        v.cam.lookat[:] = (0.25, 0.0, 0.1)
        v.cam.distance, v.cam.azimuth, v.cam.elevation = 1.0, 160, -35
        period = 1.0 / CONTROL_HZ

        def show() -> None:  # redraw and keep real time
            t0 = time.perf_counter()
            v.sync()
            time.sleep(max(0.0, period - (time.perf_counter() - t0)))
            if not v.is_running():
                sys.exit(0)

        def trace(p: np.ndarray) -> None:  # one small sphere per drawn point, kept in the viewer's user scene
            scn = v.user_scn
            if scn.ngeom < scn.maxgeom:
                mujoco.mjv_initGeom(scn.geoms[scn.ngeom], mujoco.mjtGeom.mjGEOM_SPHERE, np.array([0.002, 0, 0]),
                                    p, np.eye(3).ravel(), np.array([0.9, 0.2, 0.1, 1.0], dtype=np.float32))
                scn.ngeom += 1

        print("close the window to stop")
        run(sim, args.mode, show, trace)
        while v.is_running():  # keep the window open after the motions
            show()


def run(sim: ArmSim, mode: str, show, trace) -> None:
    if mode in ("all", "joints"):
        joint_by_joint(sim, show)
    if mode in ("all", "letters"):
        draw_letters(sim, show, trace)
    print("\ndone")


if __name__ == "__main__":
    main()
