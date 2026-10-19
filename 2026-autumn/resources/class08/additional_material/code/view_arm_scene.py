"""View the reBot Arm B601-RS on the table in the MuJoCo viewer (Class 08).

Standalone: needs only ``mujoco`` and ``numpy``. The model is the converted MJCF in ``../model/rebot_b601_rs_mjcf``.

    uv run python code/view_arm_scene.py                      # Ubuntu: table scene, home pose
    source .venv/bin/activate && python code/view_arm_scene.py   # same, with the venv activated
    uv run mjpython code/view_arm_scene.py                    # macOS: the viewer needs mjpython
    uv run python code/view_arm_scene.py --pose zero          # start from the zero (calibration) pose
    uv run python code/view_arm_scene.py --list               # print the joint table only, no window

In the viewer, open the "Control" group of the right panel: one slider per actuator, in the order of the joint
table that this script prints (joints in radians, gripper in metres). Left-drag rotates the camera, right-drag
pans, the wheel zooms. Keys: Z moves the arm to the zero pose, H to the home pose.

How the script works, in four steps:

1. ``MjModel.from_xml_path`` compiles the scene file ``scene_table.xml`` (arm + table) into a model. ``MjData``
   holds the state of that model: joint positions ``qpos``, actuator targets ``ctrl``, and so on.
2. ``set_pose`` writes a start pose into ``qpos`` and the same values into ``ctrl``. The arm joints are driven by
   position actuators (PD controllers), so the target must agree with the position; otherwise the arm moves.
3. ``print_joint_table`` lists the seven actuators in the order of the viewer's sliders, with the names and limits
   used in the course.
4. ``viewer.launch_passive`` opens the window. The script keeps the physics running with ``mj_step`` at the
   model time step, so the arm follows the sliders. The key callback resets the pose.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import mujoco
import numpy as np

# The model folder next to this script: additional_material/model/rebot_b601_rs_mjcf
MODEL_DIR = Path(__file__).resolve().parents[1] / "model" / "rebot_b601_rs_mjcf"
# The scene file to load. It includes rebot_b601_rs.xml (the arm) and table_env.xml (table, lights, cameras).
SCENE = "scene_table.xml"

# Joint conventions of the course (same as the vendor LeRobot driver; see the Class 08 paper, Table I).
# The tuples are in actuator order: joints 1 to 6, then the gripper.
LEROBOT_NAMES = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_yaw", "wrist_roll", "gripper")
MOTOR_TYPES = ("RS-06", "RS-06", "RS-06", "RS-00", "RS-00", "RS-00", "RS-00")
# Factor between a LeRobot action and the motor target. The gripper factor maps the action range 0-45 to the motor
# range 0-270 degrees. The simulation uses the URDF joint axes, so a MuJoCo joint angle equals the motor angle.
DIRECTIONS = (1, 1, -1, -1, -1, 1, 6)
# Soft limits of the physical arm (motor degrees). The MJCF ranges are wider; the driver clips to these.
SOFT_LIMITS_DEG = ((-145, 145), (0, 170), (0, 200), (-80, 90), (-90, 90), (-130, 130), (0, 270))
# Two reference poses, as the six arm joint angles in radians (the gripper stays closed).
HOME_QPOS = np.array([0.0, 1.532, 1.197, -1.236, 0.0, 0.0])  # gripper vertical, TCP at (0.25, 0, 0.10) m
ZERO_QPOS = np.zeros(6)  # folded, gripper horizontal and pointing forward (calibration pose of the physical arm)


def print_joint_table(model: mujoco.MjModel) -> None:
    """Print one line per actuator: ID, MJCF joint, LeRobot name, motor, model range, soft limit, direction.

    The ID is the position of the slider in the viewer's Control group (1 to 7). The six arm actuators drive one
    hinge joint each; the gripper actuator drives a tendon that couples the two finger joints, so its range is a
    finger stroke in metres, not an angle.
    """
    print(f"model: {MODEL_DIR}")
    print(f"{'ID':>2}  {'MJCF joint':<18}{'LeRobot name':<15}{'motor':<7}{'MJCF range (deg)':<20}{'soft limit (deg)':<18}dir")
    for i in range(model.nu):  # nu = number of actuators
        jid = model.actuator_trnid[i, 0]  # the joint (or tendon) that actuator i drives
        if model.actuator_trntype[i] == mujoco.mjtTrn.mjTRN_JOINT:
            jname = model.joint(jid).name
            lo, hi = np.degrees(model.jnt_range[jid])  # the MJCF stores joint ranges in radians
            rng = f"{lo:6.1f} to {hi:6.1f}"
        else:  # gripper: one actuator drives a tendon over both finger joints
            jname = "gripper_joint1/2"
            lo, hi = model.actuator_ctrlrange[i]  # control range of the actuator: single-finger stroke in metres
            rng = f"{lo:5.3f} to {hi:5.3f} m"
        print(f"{i + 1:>2}  {jname:<18}{LEROBOT_NAMES[i]:<15}{MOTOR_TYPES[i]:<7}{rng:<20}{str(SOFT_LIMITS_DEG[i]):<18}{DIRECTIONS[i]:+d}")
    print("Actuator ID = position of the slider in the viewer's Control group. MuJoCo joint angle (rad) = motor angle.")


def set_pose(model: mujoco.MjModel, data: mujoco.MjData, q: np.ndarray) -> None:
    """Put the six arm joints at the angles ``q`` (rad) and make them the actuator targets.

    ``qpos`` is the joint position vector of the whole model; ``jnt_qposadr`` gives the index of each joint in it.
    ``ctrl`` is the actuator target vector. Writing both keeps the PD actuators at rest in the new pose.
    ``mj_forward`` recomputes the positions of all bodies, so the viewer shows the new pose at once.
    """
    for i in range(6):
        j = model.joint(f"joint{i + 1}")
        data.qpos[model.jnt_qposadr[j.id]] = q[i]
        data.ctrl[model.actuator(f"joint{i + 1}").id] = q[i]
    mujoco.mj_forward(model, data)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pose", choices=["home", "zero"], default="home", help="start pose (default: home)")
    ap.add_argument("--list", action="store_true", help="print the joint table and exit (no window)")
    args = ap.parse_args()

    # 1. Load the scene and create the state.
    model = mujoco.MjModel.from_xml_path(str(MODEL_DIR / SCENE))
    data = mujoco.MjData(model)
    # 2. Start pose.
    set_pose(model, data, HOME_QPOS if args.pose == "home" else ZERO_QPOS)
    # 3. Joint table in the terminal.
    print_joint_table(model)
    if args.list:
        return
    # 4. Viewer. On macOS the window must run under mjpython, which gives the main thread to the GUI.
    import time

    from mujoco import viewer

    def on_key(keycode: int) -> None:
        """Keyboard callback of the viewer. Z: zero pose, H: home pose.

        The callback runs in the viewer thread, so the state is changed under the viewer lock. Setting the joints
        and the actuator targets together makes the arm stay in the new pose.
        """
        if keycode in (ord("Z"), ord("z")):
            with v.lock():
                set_pose(model, data, ZERO_QPOS)
            print("pose: zero (folded, gripper forward)")
        elif keycode in (ord("H"), ord("h")):
            with v.lock():
                set_pose(model, data, HOME_QPOS)
            print("pose: home (gripper down, TCP at (0.25, 0, 0.10) m)")

    print("in the viewer: key Z = zero pose, key H = home pose")
    # launch_passive opens the window and returns a handle; this script owns the physics loop below.
    with viewer.launch_passive(model, data, key_callback=on_key) as v:
        v.opt.geomgroup[3] = 0  # hide the collision geoms (group 3); toggle them in the Rendering panel, "Geom groups"
        # Initial camera: look at the arm from the front-left, slightly above the table.
        v.cam.lookat[:] = (0.2, 0.0, 0.15)
        v.cam.distance, v.cam.azimuth, v.cam.elevation = 1.1, 140, -20
        # Physics loop at the model time step (2 ms), in real time. The Control sliders write data.ctrl; each
        # mj_step lets the PD actuators move the joints toward those targets; sync() redraws the window.
        while v.is_running():
            t0 = time.perf_counter()
            mujoco.mj_step(model, data)
            v.sync()
            time.sleep(max(0.0, model.opt.timestep - (time.perf_counter() - t0)))


if __name__ == "__main__":
    main()
