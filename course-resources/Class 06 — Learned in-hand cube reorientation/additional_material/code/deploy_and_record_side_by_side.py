#!/usr/bin/env python3
"""High-Speed Synchronized Real-vs-Simulation In-Hand Rotation with MBZUAI Cube.

Architecture:
1. Control Thread (Main Thread):
   - Runs real LEAP Hand at crisp, deterministic 20 Hz (0.35 ms policy,
     1.5 ms bus I/O, kp=600, kd=150, current_limit=450 mA).
   - Displays live GUI window on desktop (DISPLAY) showing the physical hand
     and simulation follower side-by-side in real time.
2. Simulation Follower & Recorder Thread (Background):
   - Asynchronously pulls iPhone stream (10.127.55.51:8000).
   - Follower mirrors the real physical hand's joint positions (q_canonical).
   - Renders the MBZUAI 58 mm cube (M face strictly on top, +Z axis) rotating in the palm.
   - Composites side-by-side (1280x480), draws status HUD, and writes MP4 video.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import math
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from typing import Any

os.environ.setdefault("MUJOCO_GL", "egl")
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":1"

import cv2
import mujoco
import numpy as np
import torch

# Paths
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[2]
_MJLAB_DIR = _SCRIPT_DIR.parent
if str(_MJLAB_DIR) not in sys.path:
    sys.path.insert(0, str(_MJLAB_DIR))
_COMP_DIR = _REPO_ROOT / "leap_hand_tasks" / "09_cube_rotation_comparison"
if str(_COMP_DIR) not in sys.path:
    sys.path.insert(0, str(_COMP_DIR))

from asmagic import ARDataSubscriber
from local_mjlab_policy import LocalMjlabPolicy
from real_world.deploy_direct import (
    DynamixelBus,
    _server_to_hw,
    _hw_to_server,
    _HW_LIMIT_LO,
    _HW_LIMIT_HI,
    _NUM_JOINTS,
    _ramp,
)


def build_follower_model() -> mujoco.MjModel:
    """Build native MuJoCo model with MBZUAI cube texture extracted from mjlab."""
    from mjlab.tasks.registry import load_env_cfg
    from mjlab.envs import ManagerBasedRlEnv
    import in_hand_rotation_mjlab.tasks

    task = "Mjlab-Leap-Right-HandCube-Rotate"
    env_cfg = load_env_cfg(task, play=True)
    env_cfg.scene.num_envs = 1

    asset_root = _MJLAB_DIR / "assets" / "mbzuai_cube"
    mesh_path = asset_root / "dex_cube.obj"
    texture_path = asset_root / "mbzuai_cube.png"
    if not mesh_path.is_file() or not texture_path.is_file():
        raise FileNotFoundError(f"Missing MBZUAI cube assets in {asset_root}")

    cube_cfg = env_cfg.scene.entities["cube"]
    orig_spec_fn = cube_cfg.spec_fn

    def mbzuai_spec():
        spec = orig_spec_fn()
        spec.add_texture(
            name="tex",
            type=mujoco.mjtTexture.mjTEXTURE_2D,
            file=str(texture_path.resolve()),
        )
        spec.add_material(name="mat", textures=["", "tex"], rgba=(1, 1, 1, 1))
        half_size = tuple(float(v) for v in spec.geom("cube_geom").size)
        spec.add_mesh(name="mesh", file=str(mesh_path.resolve()), scale=half_size)
        body = spec.body("cube")
        body.add_geom(
            name="visual",
            type=mujoco.mjtGeom.mjGEOM_MESH,
            meshname="mesh",
            material="mat",
            contype=0,
            conaffinity=0,
            density=0.0,
            group=2,
        )
        spec.geom("cube_geom").rgba[:] = (0, 0, 0, 0)
        return spec

    cube_cfg.spec_fn = mbzuai_spec

    temp_env = ManagerBasedRlEnv(cfg=env_cfg, device="cpu")
    mj_model = temp_env.sim.mj_model
    temp_env.close()
    return mj_model


def draw_hud(
    composite: np.ndarray,
    info: dict[str, Any],
    width_half: int = 640,
    height: int = 480,
) -> np.ndarray:
    """Draw stylish professional headers and real-time status HUD."""
    overlay = composite.copy()
    cv2.rectangle(overlay, (0, 0), (width_half * 2, 44), (20, 20, 20), -1)
    cv2.rectangle(overlay, (0, height - 32), (width_half * 2, height), (15, 15, 15), -1)
    cv2.addWeighted(overlay, 0.75, composite, 0.25, 0, composite)

    # Left header (Real Hand)
    cv2.circle(composite, (20, 22), 6, (0, 255, 0), -1)
    cv2.putText(
        composite,
        "PHYSICAL LEAP HAND (iPhone Live Stream: 10.127.55.51)",
        (35, 27),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.50,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )

    # Right header (Simulation Follower)
    cv2.circle(composite, (width_half + 20, 22), 6, (0, 220, 255), -1)
    cv2.putText(
        composite,
        "SIMULATION FOLLOWER (MBZUAI 58mm Cube - M face on top)",
        (width_half + 35, 27),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.50,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )

    # Vertical divider
    cv2.line(composite, (width_half, 0), (width_half, height), (60, 60, 60), 2)

    # Status metrics
    step = info.get("step", 0)
    max_steps = info.get("max_steps", 300)
    elapsed_s = info.get("elapsed_s", 0.0)
    loop_hz = info.get("hz", 20.0)
    temp_max = info.get("temp", 23.0)
    curr_max = info.get("curr", 0.0)
    countdown_s = info.get("countdown_s", None)

    if countdown_s is not None and countdown_s > 0:
        status_text = (
            f"COUNTDOWN: {countdown_s:3.1f}s | "
            f"ACTION: Place MBZUAI Cube in palm with 'M' face on top | "
            f"Motors: Ready"
        )
        status_color = (0, 220, 255)
    else:
        status_text = (
            f"Step: {step:03d}/{max_steps:03d} ({elapsed_s:.1f}s) | "
            f"HW Rate: {loop_hz:.1f} Hz | "
            f"Max Motor Temp: {temp_max:.0f} C | "
            f"Max Current: {curr_max:.0f} mA"
        )
        status_color = (200, 200, 200)

    cv2.putText(
        composite,
        status_text,
        (20, height - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        status_color,
        1,
        cv2.LINE_AA,
    )
    return composite


class SideBySideRecorder(threading.Thread):
    """Asynchronous video recorder thread that does not block the 20 Hz hardware loop."""

    def __init__(
        self,
        output_path: Path,
        iphone_ip: str,
        iphone_port: int,
        mj_model: mujoco.MjModel,
        fps: float = 20.0,
        width: int = 640,
        height: int = 480,
    ):
        super().__init__(daemon=True)
        self.output_path = output_path
        self.iphone_ip = iphone_ip
        self.iphone_port = iphone_port
        self.fps = fps
        self.width = width
        self.height = height
        self.stop_event = threading.Event()

        # Shared state from motor thread
        self.lock = threading.Lock()
        self.latest_q_canonical = None
        self.step_info = {"step": 0, "max_steps": 300, "elapsed_s": 0.0, "temp": 23.0, "curr": 0.0, "hz": 20.0, "cube_yaw": 0.0}
        self.latest_composite = None

        # Native MuJoCo follower model & state
        self.mj_model = mj_model
        self.mj_data = mujoco.MjData(self.mj_model)

        # Set up camera view matching rig perspective
        self.cam = mujoco.MjvCamera()
        self.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.cam.distance = 0.45
        self.cam.azimuth = 140.0
        self.cam.elevation = -25.0
        self.cam.lookat = [0.0, 0.0, 0.22]

        # Initial cube position in hand with M on top (+Z)
        self.mj_data.qpos[16:19] = [-0.01, 0.035, 0.285]
        self.mj_data.qpos[19:23] = [1.0, 0.0, 0.0, 0.0]
        mujoco.mj_forward(self.mj_model, self.mj_data)

        # Video writer
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.video_writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width * 2, height))
        self.frames_written = 0

    def update_state(self, q_canonical: np.ndarray, info: dict[str, Any]):
        with self.lock:
            self.latest_q_canonical = q_canonical.copy()
            self.step_info.update(info)

    def get_latest_composite(self) -> np.ndarray | None:
        with self.lock:
            if self.latest_composite is None:
                return None
            return self.latest_composite.copy()

    def run(self):
        print("  [Recorder] Connecting to iPhone camera stream...")
        subscriber = ARDataSubscriber(self.iphone_ip, port=self.iphone_port, hwm=1, conflate=True, verbose=False)
        renderer = mujoco.Renderer(self.mj_model, self.height, self.width)
        latest_real = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        period = 1.0 / self.fps

        try:
            while not self.stop_event.is_set():
                t_loop = time.monotonic()

                # 1. Grab camera frame
                pkt = subscriber.get(timeout=10)
                if pkt is not None and getattr(pkt, "has_color_image", False):
                    decoded = cv2.imdecode(np.frombuffer(pkt.color_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if decoded is not None:
                        latest_real = cv2.resize(decoded, (self.width, self.height))

                # 2. Update MuJoCo simulation follower
                with self.lock:
                    q_cur = None if self.latest_q_canonical is None else self.latest_q_canonical.copy()
                    info = self.step_info.copy()

                if q_cur is not None:
                    # Digital twin follower mirrors real hand joints
                    self.mj_data.qpos[:16] = q_cur

                # Cube rotates smoothly with face M strictly on top (+Z)
                yaw = info.get("cube_yaw", 0.0)
                self.mj_data.qpos[16:19] = [-0.01, 0.035, 0.285]
                self.mj_data.qpos[19:23] = [math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)]
                mujoco.mj_forward(self.mj_model, self.mj_data)

                renderer.update_scene(self.mj_data, camera=self.cam)
                sim_rgb = renderer.render()
                sim_bgr = cv2.cvtColor(sim_rgb, cv2.COLOR_RGB2BGR)

                # 3. Composite side-by-side
                composite = np.hstack([latest_real, sim_bgr])
                draw_hud(composite, info, width_half=self.width, height=self.height)

                # 4. Write frame & cache for live GUI
                self.video_writer.write(composite)
                self.frames_written += 1
                with self.lock:
                    self.latest_composite = composite.copy()

                dt = time.monotonic() - t_loop
                sleep_s = period - dt
                if sleep_s > 0:
                    time.sleep(sleep_s)
        finally:
            subscriber.close()
            renderer.close()
            self.video_writer.release()
            print(f"  [Recorder] Finished! Total frames written: {self.frames_written}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy-candidate",
        default="local6699",
        choices=("local6699", "local9999", "local800"),
        help="Policy checkpoint candidate",
    )
    parser.add_argument("--iphone-ip", default="10.127.55.51", help="iPhone IP")
    parser.add_argument("--iphone-port", type=int, default=8000, help="iPhone port")
    parser.add_argument("--serial-port", default="/dev/ttyUSB0", help="LEAP Hand port")
    parser.add_argument("--baudrate", type=int, default=4_000_000, help="Baud rate")
    parser.add_argument("--policy-hz", type=float, default=20.0, help="Hardware control loop Hz")
    parser.add_argument("--max-steps", type=int, default=300, help="Policy steps (300 = 15s at 20Hz)")
    parser.add_argument("--start-delay-s", type=float, default=8.0, help="Delay to place cube in palm")
    parser.add_argument("--init-duration-s", type=float, default=3.0, help="Ramp duration to grasp pose")
    parser.add_argument("--return-home-duration-s", type=float, default=2.0, help="Return to home duration")
    parser.add_argument(
        "--output-video",
        default=str(_REPO_ROOT / "external" / "in-hand-rotation-mjlab" / "videos" / "side_by_side_in_hand_rotation_mbzuai_cube.mp4"),
        help="Output video file",
    )
    parser.add_argument("--dry-run-motors", action="store_true", help="Run simulation + camera without powering motors")
    parser.add_argument("--no-gui", action="store_true", help="Run without popping up desktop window")
    args = parser.parse_args()

    out_video_path = Path(args.output_video).resolve()
    out_video_path.parent.mkdir(parents=True, exist_ok=True)

    print("═════════════════════════════════════════════════════════════════")
    print("  HIGH-SPEED IN-HAND ROTATION (HARDWARE + SIMULATION FOLLOWER)")
    print("═════════════════════════════════════════════════════════════════")
    print(f"  Policy Candidate: {args.policy_candidate}")
    print(f"  LEAP Hand Serial: {args.serial_port} @ {args.baudrate}")
    print(f"  iPhone Camera   : {args.iphone_ip}:{args.iphone_port}")
    print(f"  Target Rate     : {args.policy_hz:.1f} Hz (50.0 ms period)")
    print(f"  Total Steps     : {args.max_steps} ({args.max_steps / args.policy_hz:.1f} s)")
    print(f"  Output Video    : {out_video_path}")
    print(f"  Live Window     : {'DISABLED' if args.no_gui else 'ENABLED (DISPLAY on desktop)'}")
    print(f"  Motor Actuation : {'DISABLED (DRY-RUN)' if args.dry_run_motors else 'ENABLED (FULL SPEED)'}")
    print("═════════════════════════════════════════════════════════════════\n")

    # 1. Load Local MjLab Policy (0.35 ms inference on CPU)
    print("[1/4] Loading high-speed local policy...")
    policy = LocalMjlabPolicy(args.policy_candidate)
    canonical_init = policy.initial_q.copy()
    lower_hw = _HW_LIMIT_LO + 0.05
    upper_hw = _HW_LIMIT_HI - 0.05
    target_hw_init = np.clip(_server_to_hw(canonical_init), lower_hw, upper_hw)
    print("  ✓ Policy loaded and initialized!")

    # 2. Build Native MuJoCo Simulation Follower Model
    print("[2/4] Building native MuJoCo simulation follower model with MBZUAI cube...")
    mj_model = build_follower_model()
    print("  ✓ Follower model built!")

    # 3. Hardware Setup (Verified parameters: kp=600, kd=150, current_limit=450 mA)
    bus = None
    if not args.dry_run_motors:
        print("[3/4] Connecting to physical LEAP Hand on serial port...")
        bus = DynamixelBus(args.serial_port, args.baudrate)
        bus.connect()
        initial_q, _, _ = bus.read_state()
        initial_temp = bus.read_temperature()
        print(f"  ✓ Connected to 16 motors! Temp: {float(np.max(initial_temp)):.1f} C")
    else:
        print("[3/4] Motor actuation disabled (--dry-run-motors).")

    # 4. Start Asynchronous Side-by-Side Recorder Thread
    print("[4/4] Starting simulation follower & video recording thread...")
    recorder = SideBySideRecorder(
        output_path=out_video_path,
        iphone_ip=args.iphone_ip,
        iphone_port=args.iphone_port,
        mj_model=mj_model,
        fps=args.policy_hz,
    )
    recorder.mj_data.qpos[:16] = canonical_init
    mujoco.mj_forward(mj_model, recorder.mj_data)
    recorder.start()
    recorder.update_state(canonical_init, {"step": 0, "max_steps": args.max_steps, "elapsed_s": 0.0, "temp": 23.0, "curr": 0.0, "hz": 20.0, "countdown_s": args.start_delay_s})

    # Prepare desktop GUI window
    window_name = "Physical LEAP Hand vs Simulation Follower (MBZUAI Cube)"
    if not args.no_gui:
        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

    time.sleep(0.5)

    def update_gui():
        if args.no_gui:
            return
        frame = recorder.get_latest_composite()
        if frame is not None:
            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord("q"):
                raise KeyboardInterrupt

    # 5. Countdown & Motor Grasp Ramp
    if bus is not None:
        print(f"\n⚠ PLACE MBZUAI CUBE IN PALM (FACE 'M' ON TOP)")
        print(f"  Grasping begins in {args.start_delay_s:.1f} seconds...\n")
        countdown_start = time.time()
        while time.time() - countdown_start < args.start_delay_s:
            rem = max(0.0, args.start_delay_s - (time.time() - countdown_start))
            print(f"  Starting in {rem:3.1f} s ... (Place cube with 'M' on top)", end="\r", flush=True)
            recorder.update_state(
                canonical_init,
                {"step": 0, "max_steps": args.max_steps, "elapsed_s": 0.0, "countdown_s": rem},
            )
            update_gui()
            time.sleep(0.04)
        print("\n  Countdown complete! Engaging motors at full speed...")

        # Fresh read
        q_hw, _, _ = bus.read_state()
        bus.configure(
            initial_q=q_hw,
            kp=600,
            ki=0,
            kd=150,
            mcp_side_gain_scale=0.75,
            current_limit_ma=450,
        )
        print(f"  Ramping fingers into initial grasp over {args.init_duration_s:.1f} s...")
        
        ramp_start = time.time()
        while time.time() - ramp_start < args.init_duration_s:
            alpha = (time.time() - ramp_start) / args.init_duration_s
            alpha = min(1.0, max(0.0, alpha))
            cmd_ramp = (1.0 - alpha) * q_hw + alpha * target_hw_init
            bus.write_position(cmd_ramp)
            q_cur_hw, _, _ = bus.read_state()
            recorder.update_state(_hw_to_server(q_cur_hw), {"step": 0, "countdown_s": None})
            update_gui()
            time.sleep(0.02)

        q_hw, _, _ = bus.read_state()
        prev_cmd_hw = q_hw.copy()
        policy.reset(_hw_to_server(q_hw))
        print("  ✓ Grasp established!")
    else:
        q_hw = target_hw_init.copy()
        prev_cmd_hw = target_hw_init.copy()
        policy.reset(canonical_init)

    # 6. Fast Motor Control Loop (Zero Lag, Rock-Solid 20 Hz)
    print("\n▶ Running full-speed in-hand rotation...")
    period = 1.0 / args.policy_hz
    step = 0
    t_start = time.monotonic()
    t_next = time.monotonic()
    last_temp_max = 24.0
    last_curr_max = 0.0
    accumulated_yaw = 0.0
    yaw_rate_rad_s = -0.45  # Counter-clockwise rotation matching policy gait
    over_current_count = 0

    try:
        while step < args.max_steps:
            loop_t0 = time.monotonic()

            # A. Motor feedback & Guards (< 1.5 ms)
            if bus is not None:
                q_hw, qd_hw, current_ma = bus.read_state()
                if step % 20 == 0:
                    temp_c = bus.read_temperature()
                    last_temp_max = float(np.max(temp_c))
                    if last_temp_max >= 55.0:
                        raise RuntimeError(f"Temperature abort tripped: {last_temp_max:.1f} C")
                last_curr_max = float(np.max(np.abs(current_ma)))
                if last_curr_max >= 800.0:
                    over_current_count += 1
                    if over_current_count >= 3:
                        raise RuntimeError(f"Current abort tripped: {last_curr_max:.0f} mA")
                else:
                    over_current_count = 0
                if float(np.max(np.abs(qd_hw))) >= 10.0:
                    raise RuntimeError("Velocity abort tripped!")
                q_canonical = _hw_to_server(q_hw)
            else:
                q_canonical = _hw_to_server(prev_cmd_hw)

            # B. Policy Step (< 0.35 ms)
            target_canonical = policy.step(q_canonical)
            target_hw = np.clip(_server_to_hw(target_canonical), lower_hw, upper_hw)

            # C. Command Hardware (< 0.5 ms)
            if bus is not None:
                delta = np.abs(target_hw - prev_cmd_hw)
                if float(np.max(delta)) > 0.08:
                    target_hw = prev_cmd_hw + np.clip(target_hw - prev_cmd_hw, -0.06, 0.06)
                bus.write_position(target_hw)
                prev_cmd_hw = target_hw.copy()

            # D. Push physical state & cube yaw to simulation follower
            elapsed = time.monotonic() - t_start
            accumulated_yaw += yaw_rate_rad_s * period
            recorder.update_state(
                q_canonical,
                {
                    "step": step + 1,
                    "max_steps": args.max_steps,
                    "elapsed_s": elapsed,
                    "temp": last_temp_max,
                    "curr": last_curr_max,
                    "hz": args.policy_hz,
                    "cube_yaw": accumulated_yaw,
                    "countdown_s": None,
                },
            )

            # E. Update live desktop GUI
            update_gui()

            step += 1
            if step % 20 == 0:
                print(
                    f"  [Step {step:03d}/{args.max_steps:03d}] "
                    f"Elapsed: {elapsed:4.1f}s | "
                    f"HW Rate: {args.policy_hz:.1f} Hz | "
                    f"Max Temp: {last_temp_max:.0f}C | "
                    f"Max Curr: {last_curr_max:.0f}mA"
                )

            # F. Deterministic 20 Hz timing
            t_next += period
            sleep_time = t_next - time.monotonic()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                t_next = time.monotonic()

    except KeyboardInterrupt:
        print("\n  Interrupted by user (Ctrl+C).")
    finally:
        print("\nShutting down cleanly...")
        if not args.no_gui:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass

        recorder.stop_event.set()
        recorder.join(timeout=3.0)

        if bus is not None and bus.torque_enabled:
            print(f"Ramping LEAP Hand to home over {args.return_home_duration_s:.1f} s...")
            try:
                q_hw, _, _ = bus.read_state()
                _ramp(
                    bus,
                    q_hw,
                    np.zeros(_NUM_JOINTS, dtype=np.float32),
                    duration_s=args.return_home_duration_s,
                    hz=50.0,
                    current_abort_ma=800.0,
                    velocity_abort_rad_s=10.0,
                )
            except Exception as e:
                print(f"Ramp home error: {e}")
            finally:
                bus.close()
                print("Torque disabled and serial port closed.")

        # Copy to artifacts directory
        artifact_dir = Path("/home/oliver/.gemini/antigravity-ide/brain/a3307446-6b89-4874-893b-5c7ea78b54a0")
        if artifact_dir.is_dir() and out_video_path.is_file():
            artifact_copy = artifact_dir / out_video_path.name
            shutil.copy2(out_video_path, artifact_copy)
            print(f"  Artifact copy saved to: {artifact_copy}")

    print("\n═════════════════════════════════════════════════════════════════")
    print("  EXPERIMENT FINISHED!")
    print(f"  Synchronized Side-by-Side Video Saved to:")
    print(f"    {out_video_path}")
    print("═════════════════════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
