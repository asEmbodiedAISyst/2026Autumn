"""First powered motion test of the stock reBot B601-RS (with gripper): one joint at a time, small and slow.

SAFETY. Read this before you run the script.

* One person keeps control of the power switch at all times.
* Nobody stays inside the workspace of the arm while the motors are enabled.
* Read the usage notes below before you run the script.
* Normal stop: let the test finish. At the end the arm returns to the folded zero pose in two stages
  (first joints 1, 4, 5, 6, then joints 2 and 3) at ``--speed``, then the torque goes off. With
  ``--no-return-zero`` the arm holds its pose until you press Enter, then the torque goes off.
  Ctrl+C during the test stops the motion: the arm holds its last target (no return to zero) until you press
  Enter, then the torque goes off. Fold or hold the arm before you press Enter: without torque it has no
  support. A second Ctrl+C switches the torque off immediately. Before the position hold starts, the motors
  give zero torque and Ctrl+C switches the torque off at once.
* When a joint lags its target by more than ``--abort-error`` deg, the script switches the torque off
  immediately (no hold, no return to zero) and the arm can fall.
* The power switch is the emergency stop only. When you cut the power, the motors give no torque and the
  arm falls.

Usage notes. Run ``code/real_gripper_drag.py`` first (angles, directions and zero pose checked with torque
off). Then:

1. the motors are enabled with soft MIT gains and gravity compensation, holding the current pose;
2. for every selected joint (default 1-6, one at a time, Enter before each): +A, back, -A, back, at
   ``--speed`` deg/s. Excursions outside the soft joint limits are skipped. Every control cycle checks the
   tracking error and cuts torque when a joint lags by more than ``--abort-error`` deg (collision, wrong
   direction, too little stiffness);
3. a summary per joint (worst tracking error, peak torque, temperature);
4. the arm returns to the folded zero pose in two stages (base/wrist, then shoulder/elbow) at ``--speed``
   and torque is switched off. ``--no-return-zero`` keeps the pose and waits for Enter before releasing.

Start with the arm in (or near) the folded zero pose so that +-A stays clear of the table. The results go to
a JSON file (``--log``, relative to the folder you run the script from). Examples (from
``additional_material/``, after ``uv sync --group real``)::

    uv run python code/real_gripper_motion_test.py --can-port can0 --viewer
    uv run python code/real_gripper_motion_test.py --joints 1,4,5,6 --amplitude 5 --speed 3
    uv run python code/real_gripper_motion_test.py --kp-scale 2 --gripper      # stiffer, also open/close the gripper
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.platform.startswith("linux"):
    os.environ.setdefault("MUJOCO_GL", "egl")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # additional_material/, which holds rebot_sim

import numpy as np  # noqa: E402

from rebot_sim.real.gripper_arm import (  # noqa: E402
    ARM_MOTORS,
    GRIPPER_MOTOR,
    MOTOR_NAMES,
    GripperTwin,
    RealGripperArm,
    TrackingError,
    format_table,
)
from rebot_sim.robot import MOTOR_LIMITS_DEG  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from real_gripper_drag import Display, add_common_args  # noqa: E402

CHECKLIST = """The motors will now get power for a small motion test. Make sure that:
  - the power switch / emergency stop is within reach;
  - the base is fixed, there are no hands and no objects in the workspace, and the joints cannot catch the cables;
  - the arm is in (or near) the folded zero pose, and you checked angles and directions with real_gripper_drag.py.
Press Enter to continue, Ctrl+C to cancel..."""


def parse_joints(text: str) -> list[int]:
    """'1,3-5' -> [0, 2, 3, 4] (motor indexes)."""
    out: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        a, _, b = part.partition("-")
        lo, hi = int(a), int(b or a)
        if not 1 <= lo <= hi <= 6:
            raise argparse.ArgumentTypeError(f"joint numbers must be 1 to 6: {part!r}")
        out.extend(range(lo - 1, hi))
    return sorted(set(out))


RESULTS: dict = {}  # everything worth keeping, written to --log at the end


def report_gravity_error(arm: RealGripperArm, snap) -> None:
    """Hold phase: the position error times kp is the torque the model feedforward got wrong.

    At rest the motor output equals the real gravity torque (plus friction): output = ff + kp * (target - pos).
    So ``kp * err`` is the model error, and ``(ff + kp * err) / ff`` the scale that would cancel it.
    """
    ff = arm.gravity_torques()
    kp = np.array([arm.mit_kp[m] for m in ARM_MOTORS])
    err_rad = np.radians(arm.target[:6] - snap.pos_deg[:6])
    model_err = kp * err_rad  # N*m the controller had to add on top of the feedforward
    print(f"{'joint':<16}{'model ff Nm':>12}{'motor tq Nm':>12}{'ff error Nm':>12}  suggested --gravity-joint-scale")
    print("(\"motor tq\" is the value in the RobStride feedback frame. On the arm it read ~0 with a feedforward of "
          "6.8 N*m, so use it as a hint only. Static friction hides feedforward errors below 0.5 N*m as 0.)")
    hints = []
    for i, name in enumerate(ARM_MOTORS):
        hint = ""
        if abs(ff[i]) > 0.3:
            scale = (ff[i] + model_err[i]) / ff[i]
            hint = f"{name}={scale:.2f}"
            if abs(model_err[i]) > 0.3:
                hints.append(hint)
        print(f"{name:<16}{ff[i]:>12.2f}{snap.torque[i]:>12.2f}{model_err[i]:>+12.2f}  {hint}")
    RESULTS["hold"] = {"pose_deg": [float(x) for x in snap.pos_deg], "feedforward_nm": [float(x) for x in ff],
                       "measured_torque_nm": [float(x) for x in snap.torque], "model_error_nm": [float(x) for x in model_err]}
    if arm.gravity_compensation:
        if hints:
            print(f"Joints with a feedforward error above 0.3 N*m. Try: --gravity-joint-scale {','.join(hints)} "
                  f"(static friction makes the estimate too small; adjust as necessary)\n")
        else:
            print("The gravity feedforward agrees with the measurement (error < 0.3 N*m).\n")
    else:
        print()


def gravity_sweep(arm: RealGripperArm, angles: list[float], speed: float, start: np.ndarray, on_step, display,
                  elbow_deg: float | None = None, approach_deg: float = 4.0) -> None:
    """Hold shoulder_lift at several angles, measure the feedforward error there and fit a*cos(q) + b*sin(q).

    A centre of mass of the upper arm that sits elsewhere than in the URDF adds exactly such a term to the
    shoulder torque, so the fit corrects the drift in every pose (not only where it was measured). Static
    friction hides errors below ~0.5 N*m and biases a single measurement, so every angle is approached from
    below and from above (``approach_deg``) and the two errors are averaged. ``elbow_deg`` first bends the
    elbow so that the shoulder can sweep far (with the elbow at 60 deg the gripper stays >= 19 cm above the
    table up to shoulder 90 deg); the span of the measured angles decides how well ``b`` is determined.
    """
    j2, j3 = MOTOR_NAMES.index("shoulder_lift"), MOTOR_NAMES.index("elbow_flex")
    kp2 = arm.mit_kp["shoulder_lift"]
    lo, hi = MOTOR_LIMITS_DEG["shoulder_lift"]
    twin = GripperTwin()

    def clear(pose: np.ndarray) -> bool:
        twin.update(type("S", (), {"pos_deg": pose})())
        return twin.tcp_pose()[0][2] >= 0.03

    def measure() -> float:
        """Hold the current target 1.5 s, return kp * mean position error of the second half (N*m)."""
        errs = []
        for _ in range(int(1.5 * arm.fps)):
            time.sleep(1.0 / arm.fps)
            snap = arm.read()
            on_step(snap, arm.target)
            arm.check_tracking(snap, arm.target)
            errs.append(np.radians(arm.target[j2] - snap.pos_deg[j2]))
        return kp2 * float(np.mean(errs[len(errs) // 2:]))

    samples: list[tuple[float, float]] = []
    try:
        base = arm.target.copy()
        if elbow_deg is not None:
            pose = base.copy()
            pose[j3] = elbow_deg
            if not clear(pose):
                print(f"With the elbow at {elbow_deg:+.0f} deg the gripper in the model is less than 3 cm above "
                      f"the table: sweep cancelled")
                return
            input(f"\nEnter: first move elbow_flex to {elbow_deg:+.0f} deg ({speed:.0f} deg/s), so that the "
                  f"shoulder can sweep to larger angles...")
            arm.move_to(pose, speed, on_step)
            display.end()
            base = arm.target.copy()
        print(f"\nGravity sweep: hold shoulder_lift at {angles} deg in turn ({speed:.0f} deg/s). Each angle is "
              f"approached once from below and once from above; the result is the mean.")
        for ang in angles:
            if not lo <= ang <= hi:
                print(f"  {ang:+.0f} deg: outside the soft limits, skipped")
                continue
            probe = base.copy()
            probe[j2] = ang
            if not clear(probe):
                print(f"  {ang:+.0f} deg: the gripper in the model is less than 3 cm above the table, skipped")
                continue
            input(f"  Enter: move to shoulder_lift={ang:+.0f} deg and measure (about 10 s)...")
            errs = []
            for side in (-1.0, +1.0):
                pre = probe.copy()
                pre[j2] = float(np.clip(ang + side * approach_deg, lo, hi))
                if pre[j2] != ang and clear(pre):
                    arm.move_to(pre, speed, on_step)
                arm.move_to(probe, speed, on_step)
                errs.append(measure())
            display.end()
            e = float(np.mean(errs))
            samples.append((math.radians(float(arm.last.pos_deg[j2])), e))
            ff = arm.gravity_torques()[j2]
            RESULTS.setdefault("gravity_sweep", []).append({"target_deg": ang, "measured_deg": float(arm.last.pos_deg[j2]),
                                                             "elbow_deg": float(arm.last.pos_deg[j3]), "feedforward_nm": float(ff),
                                                             "model_error_from_below_nm": errs[0], "model_error_from_above_nm": errs[-1],
                                                             "model_error_nm": e})
            print(f"\n  {ang:+.0f} deg: model feedforward {ff:+.2f} N*m, feedforward error from below {errs[0]:+.2f} / "
                  f"from above {errs[-1]:+.2f} -> mean {e:+.2f} N*m "
                  f"(positive = the arm needs more torque forward; the difference of the two is about 2x static friction)")
        if len(samples) >= 2:
            q = np.array([s_[0] for s_ in samples]); y = np.array([s_[1] for s_ in samples])
            A = np.c_[np.cos(q), np.sin(q)]
            (a, b), *_ = np.linalg.lstsq(A, y, rcond=None)
            resid = y - A @ np.array([a, b])
            span = float(np.degrees(q.max() - q.min()))
            RESULTS["gravity_fit"] = {"shoulder_lift": [float(a), float(b)], "max_residual_nm": float(np.abs(resid).max()),
                                      "span_deg": span, "mean_error_nm": float(y.mean())}
            print(f"\nFit a*cos(q2)+b*sin(q2): a={a:+.2f} b={b:+.2f} N*m, residual {np.abs(resid).max():.2f} N*m, "
                  f"angle span {span:.0f} deg")
            if span < 45:
                print(f"The angle span is less than 45 deg, so b is not reliable. Use only a constant offset: "
                      f"--gravity-joint-offset shoulder_lift={y.mean():.2f} "
                      f"(next time add --gravity-sweep-elbow 60 and sweep to 75-90 deg)\n")
            else:
                print(f"Next time, add this to both scripts: --gravity-joint-fit shoulder_lift={a:.2f}:{b:.2f}\n")
        elif len(samples) == 1:
            print(f"\nOnly one valid angle: no fit is possible. You can use a constant offset first: "
                  f"--gravity-joint-offset shoulder_lift={samples[0][1]:.2f}\n")
        input("Enter: go back to the pose before the sweep...")
        back = base.copy()
        back[j2] = start[j2]
        arm.move_to(back, speed, on_step)  # shoulder first, then the elbow (reverse order of the way out)
        arm.move_to(start, speed, on_step)
        display.end()
    finally:
        twin.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--joints", default="1-6", help="joints to test (motor IDs), e.g. 1,4-6")
    ap.add_argument("--amplitude", type=float, default=10.0, help="motion +-A of each joint (deg)")
    ap.add_argument("--speed", type=float, default=5.0, help="joint speed (deg/s), also for the return to zero")
    ap.add_argument("--kp-scale", type=float, default=1.0,
                    help="MIT stiffness multiplier (1 = soft setting, about 1/3 of the plugin default)")
    ap.add_argument("--no-gravity", action="store_true",
                    help="no gravity feedforward (with the soft stiffness the arm sinks a little)")
    ap.add_argument("--abort-error", type=float, default=15.0,
                    help="switch the torque off immediately when the tracking error is larger than this (deg)")
    ap.add_argument("--max-step-deg", type=float, default=5.0,
                    help="largest change of one joint per control cycle in the driver (deg)")
    ap.add_argument("--gripper", action="store_true",
                    help="at the end, test the gripper: motor +30 deg (about 5-6 mm), then back")
    ap.add_argument("--gravity-sweep", default=None, metavar="ANGLES",
                    help="calibrate the gravity feedforward of joint 2: hold shoulder_lift at these angles in turn "
                         "(deg, e.g. 0,15,30,45,60,75), approach each angle from both sides and use the mean, fit "
                         "a*cos+b*sin and print --gravity-joint-fit. Angles where the gripper is less than 3 cm above "
                         "the table are skipped")
    ap.add_argument("--gravity-sweep-elbow", type=float, default=None, metavar="DEG",
                    help="before the sweep, move elbow_flex to this angle (recommended: 60), so that the shoulder can "
                         "sweep to 75-90 deg without a table contact; with a span below 45 deg b is not reliable")
    ap.add_argument("--no-return-zero", action="store_true",
                    help="no return to zero at the end: hold the pose, switch the torque off after Enter")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation before the start")
    ap.add_argument("--log", default="outputs/real_gripper/motion_test_{time}.json",
                    help="result file (hold report, sweep samples and fit, results per joint); "
                         "{time} becomes a time stamp")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    joints = parse_joints(args.joints)

    if not args.yes:
        input(CHECKLIST)

    arm = RealGripperArm(args.can_port, args.robot_id, max_step_deg=args.max_step_deg, kp_scale=args.kp_scale,
                         gravity_compensation=not args.no_gravity, check_gripper_zero=args.check_gripper_zero,
                         abort_error_deg=args.abort_error,
                         gravity_scale=args.gravity_joint_scale, gravity_offset=args.gravity_joint_offset,
                         gravity_fit=args.gravity_joint_fit)
    twin = viewer = None
    display = Display()
    results: list[tuple[str, float, float, float]] = []
    peak_torque = np.zeros(len(MOTOR_NAMES))
    held = False

    def on_step(snap, target) -> None:
        nonlocal peak_torque
        peak_torque = np.maximum(peak_torque, np.abs(snap.torque))
        tcp = None
        if twin is not None:
            twin.update(snap)
            tcp = twin.tcp_pose()[0]
            viewer.sync()
        display.show(format_table(snap, target, arm.gravity_torques(), tcp))

    def release() -> None:
        """Torque off after the user confirms (the arm loses its support)."""
        print("Press Enter to switch the torque off (the arm loses its support at its current position: "
              "hold it or fold it first)...")
        try:
            while True:  # keep holding while waiting
                arm.read()
                arm.command(arm.target)
                time.sleep(0.05)
                if select_stdin():
                    break
        except KeyboardInterrupt:
            pass

    def select_stdin() -> bool:
        import select

        if select.select([sys.stdin], [], [], 0)[0]:
            sys.stdin.readline()
            return True
        return False

    try:
        snap = arm.connect()
        print(f"Connected. Stiffness kp={ {m: round(v, 1) for m, v in arm.mit_kp.items()} }, "
              f"gravity compensation {'on' if arm.gravity_compensation else 'off'}")
        print("Current angles (deg):", np.round(snap.pos_deg, 1))
        if args.viewer:
            import mujoco.viewer

            twin = GripperTwin()
            viewer = mujoco.viewer.launch_passive(twin.model, twin.data, show_left_ui=False)

        input("Enter: enable position hold (the arm stays in the current pose; the hold error shows after 1 s)...")
        start = arm.hold().pos_deg.copy()
        held = True
        for _ in range(int(1.0 * arm.fps)):
            time.sleep(1.0 / arm.fps)
            snap = arm.read()
            on_step(snap, arm.target)
            arm.check_tracking(snap, arm.target)
        display.end()
        err = np.abs(arm.target[:6] - snap.pos_deg[:6])
        print(f"\nHold error (deg): {np.round(err, 1)} (with correct gravity compensation it is less than 3 deg; "
              f"if the arm clearly sinks, the feedforward is too small or the stiffness is too low)")
        report_gravity_error(arm, snap)

        if args.gravity_sweep:
            gravity_sweep(arm, [float(a) for a in args.gravity_sweep.split(",")], args.speed, start, on_step, display,
                          elbow_deg=args.gravity_sweep_elbow)

        for j in joints:
            name = MOTOR_NAMES[j]
            lo, hi = MOTOR_LIMITS_DEG[name]
            plan = [d for d in (+args.amplitude, -args.amplitude) if lo <= start[j] + d <= hi]
            skipped = [d for d in (+args.amplitude, -args.amplitude) if d not in plan]
            msg = f"J{j + 1} {name}: from {start[j]:+.1f} deg do {' / '.join(f'{d:+.0f} deg' for d in plan)}"
            if skipped:
                msg += (f" ({' / '.join(f'{d:+.0f} deg' for d in skipped)} outside the soft limits "
                        f"[{lo:.0f}, {hi:.0f}], skipped)")
            input(msg + ". Enter to start, Ctrl+C to stop...")
            worst = 0.0
            t0 = time.monotonic()
            for d in plan:
                target = arm.target.copy()
                target[j] = start[j] + d
                worst = max(worst, arm.move_to(target, args.speed, on_step))
                target[j] = start[j]
                worst = max(worst, arm.move_to(target, args.speed, on_step))
            display.end()
            temp = arm.last.t_mos[j]
            results.append((name, worst, peak_torque[j], temp))
            RESULTS.setdefault("joints", []).append({"joint": name, "amplitude_deg": args.amplitude, "speed_deg_s": args.speed,
                                                     "worst_tracking_error_deg": float(worst), "peak_torque_nm": float(peak_torque[j]),
                                                     "t_mos_c": float(temp)})
            print(f"\nJ{j + 1} {name} done ({time.monotonic() - t0:.0f} s): largest tracking error {worst:.1f} deg, "
                  f"peak torque {peak_torque[j]:.2f} N*m, temperature {temp:.0f} C\n")

        if args.gripper:
            g = MOTOR_NAMES.index(GRIPPER_MOTOR)
            input(f"Gripper: motor from {start[g]:+.0f} deg to {start[g] + 30:+.0f} deg (about 5-6 mm) and back. "
                  f"Enter to start...")
            arm.gripper_active = True  # only now is the gripper position-controlled (plugin impedance)
            target = arm.target.copy()
            target[g] = start[g] + 30.0
            arm.move_to(target, 20.0, on_step)
            target[g] = start[g]
            arm.move_to(target, 20.0, on_step)
            arm.gripper_active = False
            display.end()
            print(f"\nGripper done: measured {arm.last.pos_deg[g]:+.1f} deg, peak torque {peak_torque[g]:.2f} N*m\n")
            RESULTS["gripper"] = {"final_deg": float(arm.last.pos_deg[g]), "peak_torque_nm": float(peak_torque[g])}

        if results:
            print(f"{'joint':<16}{'max err deg':>12}{'peak tq Nm':>12}{'temp C':>8}")
            for name, worst, tq, temp in results:
                print(f"{name:<16}{worst:>12.1f}{tq:>12.2f}{temp:>8.0f}")
            print("Pass criteria: error clearly below --abort-error, smooth torque, no temperature increase. "
                  "When all joints pass, you can increase --kp-scale or go on to teleoperation.")

        if args.no_return_zero:
            release()
        else:
            print(f"\nReturn to the folded zero pose in two stages ({args.speed:.0f} deg/s): "
                  f"first J1/J4/J5/J6, then J2/J3...")
            arm.return_to_zero(args.speed, on_step)
            display.end()
            print("\nAt the zero pose. Torque off.")
    except TrackingError as e:
        display.end()
        print(f"\nAborted: {e}")
        held = False
    except KeyboardInterrupt:
        display.end()
        print("\nInterrupted")
        if held and arm.is_connected and arm.target is not None:
            release()
    finally:
        arm.close(return_to_zero=False)
        if viewer is not None:
            from rebot_sim.viewer_utils import close_viewer

            close_viewer(viewer)
        if twin is not None:
            twin.close()
        if RESULTS and args.log:
            RESULTS["args"] = {k: (v if isinstance(v, (int, float, str, bool, type(None), list)) else str(v)) for k, v in vars(args).items()}
            RESULTS["kp"] = arm.mit_kp
            path = Path(args.log.replace("{time}", datetime.now().strftime("%Y%m%d_%H%M%S")))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2))
            print(f"Results written to {path}")


if __name__ == "__main__":
    main()
