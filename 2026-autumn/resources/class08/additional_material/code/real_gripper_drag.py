"""Drag the stock reBot B601-RS (with gripper) by hand and watch what the motors report: first power-on check.

SAFETY. Read this before you run the script.

* One person keeps control of the power switch at all times.
* Nobody stays inside the workspace of the arm while the motors are enabled.
* Read the usage notes below before you run the script.
* Normal stop: Ctrl+C. In zero-torque mode the torque is already off, so the arm has no support from the
  motors: hold it and fold it before you press Ctrl+C. In gravity mode, the first Ctrl+C does not stop the
  compensation: fold the arm, then press Enter to switch the torque off. A second Ctrl+C switches the torque
  off immediately. If you close the viewer window, the torque goes off immediately (also in gravity mode).
  The script also switches the torque off and stops when a motor is hotter than 100 C.
* The power switch is the emergency stop only. When you cut the power, the motors give no torque and the
  arm falls.

Usage notes. The program never moves the arm. Two modes:

* ``--mode zero-torque`` (default): the motors are enabled with zero output, then the torque is switched off.
  Move every joint by hand and check that the printed angles and the digital twin (``--viewer``) follow the
  real arm, that the folded pose reads about 0 deg on every joint (within +-2 deg; you read the table, the
  script does not check it), and that no motor reports an error code;
* ``--mode gravity``: gravity compensation only (kp = 0, small damping). The feedforward ramps up from 0 in
  1 s: hold the arm at the start. The arm should feel weightless and stay wherever you leave it. Checks the
  plugin's gravity model and that torque can be applied safely. On Ctrl+C the compensation keeps running
  until you press Enter, so you can fold the arm first.

``--rezero`` (zero-torque mode only) stores the current pose as the motors' zero after an explicit
confirmation (type ``yes``); use it only if the folded pose does not read about 0 deg. Hold the arm in the
folded zero pose (all joints 0 deg, gripper closed) before you confirm.

Examples (from ``additional_material/``, after ``uv sync --group real``)::

    uv run python code/real_gripper_drag.py --can-port can0 --viewer
    uv run python code/real_gripper_drag.py --can-port can0 --mode gravity --viewer
"""

from __future__ import annotations

import argparse
import logging
import os
import select
import sys
import time
from pathlib import Path

if sys.platform.startswith("linux"):
    os.environ.setdefault("MUJOCO_GL", "egl")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # additional_material/, which holds rebot_sim

import numpy as np  # noqa: E402

from rebot_sim.real.gripper_arm import GripperTwin, RealGripperArm, format_table  # noqa: E402

OVERHEAT_C = 100.0  # stop and cut torque above this MOS temperature


def parse_joint_values(text: str | None) -> dict[str, float]:
    """'shoulder_lift=0.7,elbow_flex=0.9' -> {'shoulder_lift': 0.7, 'elbow_flex': 0.9}; motor IDs 1-6 also work."""
    from rebot_sim.real.gripper_arm import ARM_MOTORS

    out: dict[str, float] = {}
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        if name.isdigit():
            name = ARM_MOTORS[int(name) - 1]
        if name not in ARM_MOTORS or not value:
            raise argparse.ArgumentTypeError(f"use joint name or motor ID=value, e.g. shoulder_lift=0.7; got {part!r}")
        out[name] = float(value)
    return out


def parse_joint_fits(text: str | None) -> dict[str, tuple[float, float]]:
    """'shoulder_lift=-0.8:0.2' -> {'shoulder_lift': (-0.8, 0.2)}: extra feedforward a*cos(q) + b*sin(q) (N*m)."""
    from rebot_sim.real.gripper_arm import ARM_MOTORS

    out: dict[str, tuple[float, float]] = {}
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        if name.isdigit():
            name = ARM_MOTORS[int(name) - 1]
        a, sep, b = value.partition(":")
        if name not in ARM_MOTORS or not sep:
            raise argparse.ArgumentTypeError(f"use joint=a:b, e.g. shoulder_lift=-0.8:0.2; got {part!r}")
        out[name] = (float(a), float(b))
    return out


def add_common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--can-port", default="can0", help="SocketCAN interface")
    ap.add_argument("--robot-id", default="rebot_gripper",
                    help="calibration file id (separate from the pusher arm, rebot_pusher)")
    ap.add_argument("--viewer", action="store_true", help="show the digital twin window (model with the gripper)")
    ap.add_argument("--check-gripper-zero", action="store_true",
                    help="run the plugin's gripper zero check at connect (closes the gripper with 0.3 N*m; "
                         "the only part of the connection that applies torque)")
    ap.add_argument("--gravity-joint-scale", type=parse_joint_values, default={},
                    help="gravity feedforward scale per joint, e.g. shoulder_lift=0.7,elbow_flex=0.9 "
                         "(motor IDs also work: 2=0.7)")
    ap.add_argument("--gravity-joint-offset", type=parse_joint_values, default={},
                    help="gravity feedforward offset per joint in N*m, e.g. shoulder_lift=-0.5 "
                         "(a positive value pushes in the positive joint direction)")
    ap.add_argument("--gravity-joint-fit", type=parse_joint_fits, default={},
                    help="feedforward correction a*cos(q)+b*sin(q) per joint in N*m, e.g. shoulder_lift=-0.8:0.2 "
                         "(from the motion test with --gravity-sweep)")


class Display:
    """In-place refresh of the status block (ANSI cursor up).

    Lines are cut to the terminal width so they never wrap (a wrapped line would break the cursor-up count
    and the table would scroll away, e.g. in a narrow IDE terminal).
    """

    def __init__(self) -> None:
        self.n = 0

    def show(self, lines: list[str]) -> None:
        import shutil

        width = max(40, shutil.get_terminal_size((120, 40)).columns - 1)
        if self.n:
            sys.stdout.write(f"\x1b[{self.n}F")
        for line in lines:
            sys.stdout.write(line[:width].ljust(width) + "\n")
        self.n = len(lines)
        sys.stdout.flush()

    def end(self) -> None:
        self.n = 0


def stdin_has_line() -> bool:
    return bool(select.select([sys.stdin], [], [], 0)[0])


def rezero(arm: RealGripperArm) -> None:
    print("The current pose will become the motor zero (this replaces the zero set in Motorbridge Studio).")
    print("First move the arm by hand to the folded zero pose: all joints 0 deg, gripper closed.")
    if input("Write the zero? Type yes and press Enter. Any other input cancels: ").strip().lower() != "yes":
        print("Cancelled")
        return
    arm.set_zero_here()
    time.sleep(0.3)
    snap = arm.read()
    print("Zero written. Current angles (deg):", np.round(snap.pos_deg, 2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--mode", choices=["zero-torque", "gravity"], default="zero-torque")
    ap.add_argument("--damping", type=float, default=0.3, help="joint damping kd in gravity mode (N*m*s/rad)")
    ap.add_argument("--gravity-scale", type=float, default=1.0,
                    help="gravity feedforward scale in gravity mode (< 1 lets the arm sink a little, easier to see)")
    ap.add_argument("--rate", type=float, default=50.0, help="refresh / control rate in Hz")
    ap.add_argument("--rezero", action="store_true",
                    help="zero-torque mode only: after confirmation, store the current pose as the motor zero")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.rezero and args.mode != "zero-torque":
        sys.exit("--rezero works only with --mode zero-torque")

    gravity = args.mode == "gravity"
    arm = RealGripperArm(args.can_port, args.robot_id, gravity_compensation=gravity,
                         check_gripper_zero=args.check_gripper_zero,
                         gravity_scale=args.gravity_joint_scale, gravity_offset=args.gravity_joint_offset,
                         gravity_fit=args.gravity_joint_fit)
    if gravity and (args.gravity_joint_scale or args.gravity_joint_offset or args.gravity_joint_fit):
        print(f"Gravity feedforward correction: scale {args.gravity_joint_scale}, offset {args.gravity_joint_offset} N*m, "
              f"cos/sin terms {args.gravity_joint_fit}")
    twin = viewer = None
    display = Display()
    interrupted = False
    try:
        snap = arm.connect()
        print("Connected. Motors enabled with zero torque. Current angles (deg):", np.round(snap.pos_deg, 1))
        if args.rezero:
            rezero(arm)
        if gravity:
            print("Gravity mode: torque on, gravity compensation only. Hold the arm: the feedforward ramps up "
                  "from 0 to the set value in 1 s.")
            print("Ctrl+C to stop: the compensation continues. Fold the arm, then press Enter to switch the torque off "
                  "(press Ctrl+C again to switch it off now).")
        else:
            arm.disable_torque()
            print("Zero-torque mode: torque is off. You can move the arm by hand. Ctrl+C to stop "
                  "(fold the arm before you stop).")
        if args.viewer:
            import mujoco.viewer

            twin = GripperTwin()
            viewer = mujoco.viewer.launch_passive(twin.model, twin.data, show_left_ui=False)
        print()

        t_start = time.monotonic()
        dt = 1.0 / args.rate
        while viewer is None or viewer.is_running():
            tick = time.perf_counter()
            try:
                snap = arm.read()
                tau = None
                if gravity:
                    ramp = min(1.0, (time.monotonic() - t_start) / 1.0)
                    tau = arm.send_gravity_only(args.gravity_scale * ramp, args.damping)
                if np.nanmax(snap.t_mos) > OVERHEAT_C:
                    arm.disable_torque()
                    display.end()
                    print(f"\nMotor temperature above {OVERHEAT_C:.0f} C: torque is off")
                    break
                tcp = None
                if twin is not None:
                    twin.update(snap)
                    tcp = twin.tcp_pose()[0]
                    viewer.sync()
                lines = format_table(snap, None, tau, tcp)
                if interrupted:
                    lines.append("Ctrl+C received: fold the arm, then press Enter to switch the torque off "
                                 "(press Ctrl+C to switch it off now)")
                    if stdin_has_line():
                        sys.stdin.readline()
                        break
                display.show(lines)
                time.sleep(max(0.0, dt - (time.perf_counter() - tick)))
            except KeyboardInterrupt:
                if not gravity or interrupted:
                    break
                interrupted = True
    except KeyboardInterrupt:
        pass
    finally:
        display.end()
        print("\nTorque off and disconnect...")
        arm.close(return_to_zero=False)
        if viewer is not None:
            from rebot_sim.viewer_utils import close_viewer

            close_viewer(viewer)
        if twin is not None:
            twin.close()


if __name__ == "__main__":
    main()
