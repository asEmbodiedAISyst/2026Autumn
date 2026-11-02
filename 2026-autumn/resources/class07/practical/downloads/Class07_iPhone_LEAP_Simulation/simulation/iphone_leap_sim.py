#!/usr/bin/env python3
"""Drive a simulated LEAP Hand from an iPhone asMagic RGB stream."""

from __future__ import annotations

import argparse
import ipaddress
import json
import queue
import threading
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import mujoco
import mujoco.viewer
import numpy as np

from asmagic import ARDataSubscriber
from dex_retargeting.retargeting_config import RetargetingConfig


ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "leap_hand_model" / "right_hand.xml"
LANDMARKER_PATH = ROOT / "hand_landmarker.task"
DEX_PACKAGE = ROOT / "dex_retargeting"
DEX_SOURCE = DEX_PACKAGE / "src" / "dex_retargeting"
DEX_ASSETS = DEX_PACKAGE / "assets" / "robots" / "hands"
RETARGET_CONFIG = DEX_SOURCE / "configs" / "teleop" / "leap_hand_right.yml"

OPERATOR_TO_MANO_RIGHT = np.asarray(
    [[0.0, 0.0, -1.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    dtype=np.float64,
)

HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
)


class AsMagicRGBStream:
    """Receive the newest RGB image without accumulating an old-frame queue."""

    def __init__(self, ip: str, port: int, mirror: bool):
        self.ip = ip
        self.port = port
        self.mirror = mirror
        self.running = True
        self.connected = False
        self.frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=1)
        self.subscriber: ARDataSubscriber | None = None
        self.thread = threading.Thread(target=self._receive, daemon=True)
        self.thread.start()

    def _receive(self) -> None:
        while self.running:
            if self.subscriber is None:
                try:
                    self.subscriber = ARDataSubscriber(
                        self.ip,
                        port=self.port,
                        hwm=1,
                        conflate=True,
                        verbose=False,
                    )
                    self.connected = True
                    print(f"[asMagic] connected to {self.ip}:{self.port}")
                except Exception:
                    time.sleep(0.5)
                    continue
            try:
                packet = self.subscriber.get(timeout=100)
                if packet is None or not packet.has_color_image:
                    continue
                encoded = np.frombuffer(packet.color_bytes, dtype=np.uint8)
                frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                if self.mirror:
                    frame = cv2.flip(frame, 1)
                while not self.frames.empty():
                    try:
                        self.frames.get_nowait()
                    except queue.Empty:
                        break
                self.frames.put_nowait(frame)
            except Exception:
                time.sleep(0.01)

    def get(self, timeout: float = 0.1) -> np.ndarray | None:
        try:
            return self.frames.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self.running = False
        if self.subscriber is not None:
            try:
                self.subscriber.close()
            except Exception:
                pass
        self.thread.join(timeout=1.0)


def estimate_wrist_frame(points: np.ndarray) -> np.ndarray:
    """Estimate the wrist-centred MANO frame from MediaPipe landmarks."""
    reference = points[[0, 5, 9], :]
    x_vector = reference[0] - reference[2]
    centered = reference - np.mean(reference, axis=0, keepdims=True)
    _, _, vh = np.linalg.svd(centered)
    normal = vh[2, :]
    x_axis = x_vector - np.sum(x_vector * normal) * normal
    x_axis /= max(np.linalg.norm(x_axis), 1e-8)
    z_axis = np.cross(x_axis, normal)
    z_axis /= max(np.linalg.norm(z_axis), 1e-8)
    if np.sum(z_axis * (reference[1] - reference[2])) < 0:
        normal = -normal
        z_axis = -z_axis
    return np.stack([x_axis, normal, z_axis], axis=1)


def load_retargeter():
    RetargetingConfig.set_default_urdf_dir(DEX_ASSETS)
    config = RetargetingConfig.load_from_file(RETARGET_CONFIG)
    return config.build()


def retarget_landmarks(retargeter, world_landmarks) -> np.ndarray:
    points = np.asarray(
        [[item.x, item.y, item.z] for item in world_landmarks],
        dtype=np.float64,
    )
    return retarget_points(retargeter, points)


def retarget_points(retargeter, points: np.ndarray) -> np.ndarray:
    """Transform a 21-point human hand and solve its LEAP joint target."""
    points -= points[0:1, :]
    wrist_frame = estimate_wrist_frame(points)
    mano_points = points @ wrist_frame @ OPERATOR_TO_MANO_RIGHT
    indices = retargeter.optimizer.target_link_human_indices
    reference = mano_points[indices[1, :], :] - mano_points[indices[0, :], :]
    return np.asarray(retargeter.retarget(reference), dtype=np.float64)


def retarget_to_sim_indices(retargeter) -> np.ndarray:
    target_ids = [int(name) for name in retargeter.joint_names]
    model_joint_ids = [1, 0, 2, 3, 5, 4, 6, 7, 9, 8, 10, 11, 12, 13, 14, 15]
    return np.asarray([target_ids.index(item) for item in model_joint_ids])


def draw_landmarks(frame: np.ndarray, landmarks) -> None:
    height, width = frame.shape[:2]
    pixels = [(int(item.x * width), int(item.y * height)) for item in landmarks]
    for start, end in HAND_CONNECTIONS:
        cv2.line(frame, pixels[start], pixels[end], (0, 255, 128), 2, cv2.LINE_AA)
    for point in pixels:
        cv2.circle(frame, point, 4, (0, 165, 255), -1, cv2.LINE_AA)


def synthetic_landmarks() -> np.ndarray:
    """Return a finite open-hand landmark set for the package self-check."""
    points = np.zeros((21, 3), dtype=np.float64)
    points[5] = (-0.035, 0.045, 0.0)
    points[9] = (0.0, 0.052, 0.0)
    points[13] = (0.032, 0.047, 0.0)
    points[17] = (0.056, 0.035, 0.0)
    points[4] = (-0.060, 0.020, 0.0)
    points[8] = (-0.040, 0.115, 0.0)
    points[12] = (0.0, 0.125, 0.0)
    points[16] = (0.040, 0.112, 0.0)
    return points


def package_check() -> None:
    required = [MODEL_PATH, LANDMARKER_PATH, RETARGET_CONFIG, DEX_ASSETS]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("missing package assets: " + ", ".join(missing))

    retargeter = load_retargeter()
    points = synthetic_landmarks()
    q_retarget = retarget_points(retargeter, points)
    mapping = retarget_to_sim_indices(retargeter)

    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    data = mujoco.MjData(model)
    data.ctrl[:] = q_retarget[mapping]
    for _ in range(10):
        mujoco.mj_step(model, data)

    base_options = python.BaseOptions(model_asset_path=str(LANDMARKER_PATH))
    options = vision.HandLandmarkerOptions(base_options=base_options, num_hands=1)
    with vision.HandLandmarker.create_from_options(options) as landmarker:
        blank = np.zeros((64, 64, 3), dtype=np.uint8)
        landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=blank))

    result = {
        "status": "pass",
        "mode": "simulation_only",
        "model_actuators": int(model.nu),
        "retargeted_joints": int(q_retarget.size),
        "finite_state": bool(np.isfinite(data.qpos).all()),
        "hand_landmarker_loaded": True,
        "iphone_required_for_live_run": True,
        "motor_interface_included": False,
    }
    if model.nu != 16 or q_retarget.size != 16 or not result["finite_state"]:
        raise RuntimeError(json.dumps(result))
    print(json.dumps(result, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iphone-ip", help="IP displayed by asMagic Data Streaming")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--alpha", type=float, default=0.25)
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument(
        "--mirror",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Mirror the iPhone image before landmark estimation",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate dependencies, assets, retargeting and MuJoCo without an iPhone",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run MuJoCo simulation viewer with animated synthetic hand retargeting without an iPhone",
    )
    args = parser.parse_args()
    if not args.check and not args.demo:
        if not args.iphone_ip:
            parser.error("--iphone-ip is required; copy it from asMagic Data Streaming (or use --demo)")
        try:
            ipaddress.ip_address(args.iphone_ip)
        except ValueError as error:
            parser.error(f"invalid --iphone-ip: {error}")
    if not 0.0 < args.alpha <= 1.0:
        parser.error("--alpha must lie in (0, 1]")
    if args.duration < 0.0:
        parser.error("--duration must be non-negative")
    return args


def run_demo(model: mujoco.MjModel, data: mujoco.MjData, retargeter, mapping: np.ndarray, duration: float = 0.0) -> None:
    """Launch the MuJoCo viewer and animate synthetic hand retargeting without an iPhone."""
    viewer = mujoco.viewer.launch_passive(model, data)
    viewer.cam.distance = 0.45
    viewer.cam.azimuth = 140.0
    viewer.cam.elevation = -20.0
    print("[demo] running standalone MuJoCo simulation viewer with synthetic retargeting")
    print("[demo] press Esc in the viewer or Ctrl+C in terminal to stop")
    start_time = time.monotonic()
    base_points = synthetic_landmarks()
    try:
        while viewer.is_running():
            now = time.monotonic()
            if duration > 0.0 and (now - start_time) >= duration:
                break
            t = now - start_time
            scale = 0.5 + 0.5 * np.sin(2.5 * t)
            points = base_points.copy()
            # Flex fingertips
            points[8, 1] -= 0.045 * scale
            points[8, 2] -= 0.035 * scale
            points[12, 1] -= 0.050 * scale
            points[12, 2] -= 0.040 * scale
            points[16, 1] -= 0.045 * scale
            points[16, 2] -= 0.035 * scale
            points[4, 0] += 0.025 * scale
            points[4, 1] -= 0.020 * scale

            q_retarget = retarget_points(retargeter, points)
            q_target = q_retarget[mapping]
            data.ctrl[:] = np.clip(
                q_target, model.actuator_ctrlrange[:, 0], model.actuator_ctrlrange[:, 1]
            )
            for _ in range(4):
                mujoco.mj_step(model, data)
            viewer.sync()
            time.sleep(0.02)
    finally:
        viewer.close()


def main() -> None:
    args = parse_args()
    if args.check:
        package_check()
        return

    retargeter = load_retargeter()
    mapping = retarget_to_sim_indices(retargeter)
    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    data = mujoco.MjData(model)

    if args.demo:
        run_demo(model, data, retargeter, mapping, args.duration)
        return

    viewer = mujoco.viewer.launch_passive(model, data)
    stream = AsMagicRGBStream(args.iphone_ip, args.port, args.mirror)

    base_options = python.BaseOptions(model_asset_path=str(LANDMARKER_PATH))
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    q_filtered = np.zeros(16, dtype=np.float64)
    started = time.monotonic()
    last_frame_time = started
    window = "asMagic iPhone to simulated LEAP Hand"

    print("[simulation] no motor or serial interface is present in this package")
    print("[simulation] show one right hand to the iPhone; press Q or Esc to stop")
    try:
        with vision.HandLandmarker.create_from_options(options) as landmarker:
            while viewer.is_running():
                if args.duration and time.monotonic() - started >= args.duration:
                    break
                frame = stream.get(timeout=0.1)
                if frame is None:
                    canvas = np.zeros((480, 900, 3), dtype=np.uint8)
                    cv2.putText(
                        canvas,
                        f"Waiting for asMagic AR Data at {args.iphone_ip}:{args.port}",
                        (30, 220),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.75,
                        (0, 180, 255),
                        2,
                    )
                    cv2.imshow(window, canvas)
                    viewer.sync()
                    if cv2.waitKey(10) & 0xFF in (ord("q"), 27):
                        break
                    continue

                last_frame_time = time.monotonic()
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = landmarker.detect(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                )
                tracking = bool(result.hand_world_landmarks and result.hand_landmarks)
                if tracking:
                    q_retarget = retarget_landmarks(
                        retargeter, result.hand_world_landmarks[0]
                    )
                    q_target = q_retarget[mapping]
                    q_filtered = (
                        (1.0 - args.alpha) * q_filtered + args.alpha * q_target
                    )
                    data.ctrl[:] = np.clip(
                        q_filtered, model.actuator_ctrlrange[:, 0], model.actuator_ctrlrange[:, 1]
                    )
                    for _ in range(4):
                        mujoco.mj_step(model, data)
                    draw_landmarks(frame, result.hand_landmarks[0])

                viewer.sync()

                age_ms = 1000.0 * (time.monotonic() - last_frame_time)
                status = "TRACKING" if tracking else "HAND NOT FOUND — SIMULATION HOLDING"
                color = (0, 220, 0) if tracking else (0, 0, 255)
                cv2.rectangle(frame, (0, 0), (frame.shape[1], 52), (20, 20, 20), -1)
                cv2.putText(
                    frame,
                    f"{status} | SIMULATION ONLY | frame age {age_ms:.0f} ms",
                    (15, 34),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.62,
                    color,
                    2,
                )
                cv2.imshow(window, frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
    finally:
        stream.close()
        viewer.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
