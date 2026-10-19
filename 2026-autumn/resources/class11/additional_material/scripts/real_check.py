"""First check of the real reBot B601-RS with the pusher tool: calibration, joint directions and tool mounting.

Connects (no zero calibration: the zero set in Motorbridge Studio is stored in the motors), then **disables
torque** so the arm can be moved by hand, and prints the measured joint angles, the pusher-tip (TCP) position computed with the simulation model and
its height above the table. Compare with a ruler: if the printed tip position follows the real tip (within
~1 cm), the calibration, joint directions and tool mounting match the model used for IK and datasets.

Optionally shows the twin in a MuJoCo window (``--viewer``). ``--rezero 6`` re-zeroes only the wrist-roll motor
(after an explicit confirmation) when the tool is mounted at a different roll than the gripper was. Put the
arm back into its folded rest pose before stopping (Ctrl+C): torque stays off on exit.

Example::

    uv run python scripts/real_check.py --can-port can0
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the package root

from rebot_sim.real.arm import ARM_MOTORS, RealArm
from rebot_sim.real.camera import NoCamera
from rebot_sim.real.env import RealToolPushEnv


def parse_ids(text: str) -> list[int]:
    """'6' / '1-3,6' -> motor IDs within 1..6."""
    ids: set[int] = set()
    for part in text.split(","):
        a, _, b = part.strip().partition("-")
        lo, hi = int(a), int(b or a)
        if not 1 <= lo <= hi <= 6:
            raise SystemExit(f"--rezero motor numbers must be between 1 and 6: {part!r}")
        ids.update(range(lo, hi + 1))
    return sorted(ids)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--can-port", default="can0")
    ap.add_argument("--robot-id", default="rebot_pusher")
    ap.add_argument("--viewer", action="store_true", help="show the digital twin in a MuJoCo window")
    ap.add_argument("--rezero", default=None, metavar="IDS",
                    help="after a confirmation, store the current position of these motors (e.g. 6 or 1-6) as their zero; use it when the wrist-roll zero changed with the tool")
    args = ap.parse_args()

    arm = RealArm(args.can_port, args.robot_id)
    env = RealToolPushEnv(arm, NoCamera())
    arm.connect()
    arm.disable_torque()  # torque off; close() will not try to move back to zero
    if args.rezero:
        ids = parse_ids(args.rezero)
        names = [ARM_MOTORS[i - 1] for i in ids]
        print(f"The current position of motors {ids} ({names}) will be stored as zero and replace the zero saved in the motors.")
        print("First move these joints to their zero pose by hand (joint 6: the four screw holes of the flange form a horizontal square and the rod is in a vertical plane); leave the other joints.")
        if input("Store the zero? Type yes and Enter; any other key skips: ").strip().lower() == "yes":
            arm.set_zero(names)
            time.sleep(0.3)
            print("zero stored; current reading (deg):", np.round(np.degrees(arm.read_q()), 2))
        else:
            print("skipped")
    print("Torque is off: the arm can be moved by hand. Ctrl+C stops (put the arm back into its folded pose first).")
    viewer = None
    if args.viewer:
        import mujoco.viewer

        viewer = mujoco.viewer.launch_passive(env.kin.model, env.kin.data, show_left_ui=False)
    try:
        while viewer is None or viewer.is_running():
            p, R = env.tool_pose()
            tilt = np.degrees(np.arccos(np.clip(-R[2, 2], -1, 1)))
            sys.stdout.write(f"\rjoints (deg) {np.round(np.degrees(env.q_meas), 1)} | tip x={p[0] * 100:5.1f} "
                             f"y={p[1] * 100:5.1f} cm, {p[2] * 100:5.1f} cm above the table | tilt {tilt:4.1f} deg".ljust(110))
            sys.stdout.flush()
            if viewer is not None:
                viewer.sync()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print()
    finally:
        env.close()
        if viewer is not None:
            from rebot_sim.viewer_utils import close_viewer

            close_viewer(viewer)


if __name__ == "__main__":
    main()
