#!/usr/bin/env python3
"""One-Click Easy Camera-to-Palm Calibration Tool for LEAP Hand.

Calculates the rigid body extrinsic transform T_palm_camera (translation and rotation)
from the overhead iPhone camera (asMagic) to the LEAP Hand palm coordinate frame.

Method: In-Hand Touchdown Reference
1. The LEAP hand is placed in its nominal grasp/rest posture.
2. The MBZUAI 58 mm cube is seated flatly in the palm cradle with your nominal orientation:
     - Top face: Yellow face ('M', ArUco ID 0) facing UP (+Z)
     - Side face: Red face ('B', ArUco ID 1) facing towards thumb
     - Front face: Green face ('Z', ArUco ID 2) facing towards fingers
3. In palm coordinates, this resting cube pose serves as the zero-yaw cradle reference:
     R_nominal = Eye(3)
     p_nominal = [-0.003, 0.031, 0.268] (from nominal grasp cache centroid)
4. The iPhone camera measures R_camera_cube, p_camera_cube via solvePnP.
5. The calibration is solved algebraically:
     R_palm_camera = R_nominal @ R_camera_cube.T
     t_palm_camera = p_nominal - R_palm_camera @ p_camera_cube
6. 30 frames are averaged to eliminate sensor noise, and the calibrated JSON is written.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
from pathlib import Path
import sys
import time

import cv2
import numpy as np

# Add local path for cube model
_HERE = Path(__file__).resolve().parent
_BUNDLE_ROOT = _HERE.parent
_ARUCO_DIR = _HERE / "aruco_cube"
if str(_ARUCO_DIR) not in sys.path:
  sys.path.insert(0, str(_ARUCO_DIR))

try:
  from aruco_pose import CubePose, CubePoseEstimator
  from cube_model import load_cube_model
except ImportError:
  print("Error: Could not import aruco_pose / cube_model from", _ARUCO_DIR)
  sys.exit(1)

try:
  from asmagic import ARDataSubscriber
  HAS_ASMAGIC = True
except ImportError:
  HAS_ASMAGIC = False


def camera_matrix_from_asmagic(intrinsics: np.ndarray, width: int, height: int) -> np.ndarray:
  """Decode asMagic's column-major intrinsics and scale to image pixels."""
  arr = np.asarray(intrinsics, dtype=np.float64).reshape(-1)
  raw_K = arr.reshape(3, 3, order="F").copy()
  sx = width / 1920.0
  sy = height / 1440.0
  K = np.eye(3, dtype=np.float64)
  K[0, 0] = raw_K[0, 0] * sx
  K[1, 1] = raw_K[1, 1] * sy
  K[0, 2] = raw_K[0, 2] * sx
  K[1, 2] = raw_K[1, 2] * sy
  return K


def rotation_matrix_to_quaternion_wxyz(R: np.ndarray) -> np.ndarray:
  """Convert 3x3 rotation matrix to normalized wxyz quaternion."""
  tr = np.trace(R)
  if tr > 0.0:
    s = 2.0 * np.sqrt(tr + 1.0)
    w = 0.25 * s
    x = (R[2, 1] - R[1, 2]) / s
    y = (R[0, 2] - R[2, 0]) / s
    z = (R[1, 0] - R[0, 1]) / s
  elif (R[0, 0] > R[1, 1]) and (R[0, 0] > R[2, 2]):
    s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
    w = (R[2, 1] - R[1, 2]) / s
    x = 0.25 * s
    y = (R[0, 1] + R[1, 0]) / s
    z = (R[0, 2] + R[2, 0]) / s
  elif R[1, 1] > R[2, 2]:
    s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
    w = (R[0, 2] - R[2, 0]) / s
    x = (R[0, 1] + R[1, 0]) / s
    y = 0.25 * s
    z = (R[1, 2] + R[2, 1]) / s
  else:
    s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
    w = (R[1, 0] - R[0, 1]) / s
    x = (R[0, 2] + R[2, 0]) / s
    y = (R[1, 2] + R[2, 1]) / s
    z = 0.25 * s
  quat = np.array([w, x, y, z], dtype=np.float64)
  quat /= np.linalg.norm(quat)
  return quat


def average_rotations(matrices: list[np.ndarray]) -> np.ndarray:
  """Chordal L2 mean / SVD projection for SO(3) matrices."""
  A = np.zeros((3, 3), dtype=np.float64)
  for R in matrices:
    A += R
  u, _, vh = np.linalg.svd(A)
  R_avg = u @ vh
  if np.linalg.det(R_avg) < 0:
    u[:, -1] *= -1
    R_avg = u @ vh
  return R_avg


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--iphone-ip", default="10.127.51.69", help="iPhone asMagic streaming IP")
  parser.add_argument("--port", type=int, default=8000, help="asMagic port")
  parser.add_argument(
    "--output",
    type=Path,
    default=_BUNDLE_ROOT / "project/real_world/camera_to_palm_iphone.json",
    help="Output JSON file path",
  )
  parser.add_argument(
    "--cube-config",
    type=Path,
    default=_ARUCO_DIR / "cube_config.json",
    help="Path to cube_config.json",
  )
  parser.add_argument(
    "--nominal-pos",
    nargs=3,
    type=float,
    default=[-0.003, 0.031, 0.268],
    help="Nominal in-hand cube position [x, y, z] in palm frame (m)",
  )
  parser.add_argument(
    "--samples",
    type=int,
    default=30,
    help="Number of consecutive valid frames to average",
  )
  parser.add_argument(
    "--auto",
    action="store_true",
    help="Automatically collect samples and calibrate as soon as the cube is detected",
  )
  parser.add_argument(
    "--headless",
    action="store_true",
    help="Run in headless terminal mode without opening an OpenCV GUI window",
  )
  args = parser.parse_args()

  if not HAS_ASMAGIC:
    print("Error: asmagic package not found in this Python environment.")
    sys.exit(1)

  print("\n" + "=" * 70)
  print("📷 EASY CAMERA-TO-PALM CALIBRATION UTILITY")
  print("=" * 70)
  print(f"  • iPhone Camera IP:  {args.iphone_ip}:{args.port}")
  print(f"  • Target Config:     {args.output}")
  print(f"  • Nominal Cube Pose: pos={args.nominal_pos} m, rot=Eye(3)")
  print(f"  • Auto Trigger:      {'ENABLED' if args.auto else 'Press [SPACE] or use --auto'}")
  print("-" * 70)
  print("  Instructions:")
  print("  1. Place the cube flat in the LEAP Hand palm cradle:")
  print("     - Yellow Face ('M', ArUco ID 0) facing UP (+Z)")
  print("     - Red Face ('B', ArUco ID 1) facing THUMB")
  print("     - Green Face ('Z', ArUco ID 2) facing FINGERS")
  print("  2. Ensure the asMagic app is OPEN and STREAMING on the iPhone.")
  print("  3. Calibration will save to camera_to_palm_iphone.json")
  print("=" * 70 + "\n")

  # Load Cube model & estimator
  model = load_cube_model(args.cube_config)
  estimator = CubePoseEstimator(model)

  # Connect to asMagic
  print(f"[Connecting] Subscribing to iPhone at tcp://{args.iphone_ip}:{args.port}...")
  sub = ARDataSubscriber(args.iphone_ip, port=args.port, hwm=1, conflate=True, verbose=False)

  show_gui = not args.headless
  if show_gui:
    try:
      cv2.namedWindow("Camera-to-Palm Calibration", cv2.WINDOW_NORMAL)
      cv2.resizeWindow("Camera-to-Palm Calibration", 960, 720)
    except Exception as e:
      print(f"[Display] GUI window could not be opened ({e}). Falling back to terminal headless mode.")
      show_gui = False

  calibrating = bool(args.auto)
  collected_R_cam_cube: list[np.ndarray] = []
  collected_t_cam_cube: list[np.ndarray] = []

  R_palm_camera_calibrated: np.ndarray | None = None
  t_palm_camera_calibrated: np.ndarray | None = None
  steady_frames = 0

  try:
    while True:
      frame = sub.get(timeout=200)
      if frame is None or not frame.has_color_image:
        if show_gui:
          blank = np.zeros((480, 640, 3), dtype=np.uint8)
          cv2.putText(
            blank,
            f"Waiting for frames from {args.iphone_ip}:{args.port}...",
            (30, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 165, 255),
            2,
          )
          cv2.imshow("Camera-to-Palm Calibration", blank)
          key = cv2.waitKey(20) & 0xFF
          if key in (ord("q"), 27):
            break
        else:
          time.sleep(0.05)
        continue

      raw_bytes = np.frombuffer(frame.color_bytes, dtype=np.uint8)
      img = cv2.imdecode(raw_bytes, cv2.IMREAD_COLOR)
      if img is None:
        continue

      h, w = img.shape[:2]
      K = camera_matrix_from_asmagic(frame.camera_intrinsics, w, h)
      dist = np.zeros(5, dtype=np.float64)

      # Detect cube markers - strictly rely on top marker M (ID 0)
      corners, ids, _ = estimator.detect(img)
      pose: CubePose | None = None
      if 0 in ids:
        m_idx = ids.index(0)
        pose = estimator.estimate([corners[m_idx]], [0], K, dist)

      vis = img.copy()

      # Draw detection
      if pose is not None and pose.reprojection_error_px <= 25.0:
        steady_frames += 1
        cv2.aruco.drawDetectedMarkers(vis, [c.reshape(-1, 1, 2) for c in corners], np.array(ids).reshape(-1, 1))
        rvec, _ = cv2.Rodrigues(pose.rotation_camera_cube)
        tvec = pose.translation_camera_cube
        cv2.drawFrameAxes(vis, K, dist, rvec, tvec, 0.045, 2)

        # Show detected position
        pos_str = f"Cam Pos: [{tvec[0]:.2f}, {tvec[1]:.2f}, {tvec[2]:.2f}] m  |  Err: {pose.reprojection_error_px:.1f}px"
        cv2.putText(vis, pos_str, (16, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 120), 2)

        if args.auto and not calibrating and steady_frames >= 10:
          print("\n[Auto Trigger] Cube detected steadily. Collecting samples...")
          calibrating = True
          collected_R_cam_cube.clear()
          collected_t_cam_cube.clear()

        # Collect calibration samples
        if calibrating:
          collected_R_cam_cube.append(pose.rotation_camera_cube.copy())
          collected_t_cam_cube.append(pose.translation_camera_cube.copy())

          pct = int(len(collected_R_cam_cube) / args.samples * 100)
          cv2.putText(vis, f"COLLECTING SAMPLES: {pct}% ({len(collected_R_cam_cube)}/{args.samples})", (16, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 255), 2)
          if len(collected_R_cam_cube) % 5 == 0 or len(collected_R_cam_cube) == args.samples:
            print(f"\r[Calibrating] Progress: {pct}% ({len(collected_R_cam_cube)}/{args.samples})", end="", flush=True)

          if len(collected_R_cam_cube) >= args.samples:
            print("\n[Solving] Averaging SO(3) rotations and translations...")
            R_cam_cube_avg = average_rotations(collected_R_cam_cube)
            t_cam_cube_avg = np.mean(collected_t_cam_cube, axis=0)

            # Nominal cube in palm frame
            R_palm_cube_nom = np.eye(3, dtype=np.float64)
            p_palm_cube_nom = np.array(args.nominal_pos, dtype=np.float64)

            # Solve: R_palm_camera = R_palm_cube @ R_cam_cube.T
            R_palm_camera = R_palm_cube_nom @ R_cam_cube_avg.T
            # Solve: t_palm_camera = p_palm_cube - R_palm_camera @ t_cam_cube
            t_palm_camera = p_palm_cube_nom - R_palm_camera @ t_cam_cube_avg

            quat_palm_camera_wxyz = rotation_matrix_to_quaternion_wxyz(R_palm_camera)

            R_palm_camera_calibrated = R_palm_camera
            t_palm_camera_calibrated = t_palm_camera

            # Save calibration payload
            payload = {
              "calibrated": True,
              "frame_convention": "p_palm = R_palm_camera @ p_camera + translation_palm_camera_m",
              "note": "Calibrated via in-hand ArUco touchdown reference",
              "calibrated_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "translation_palm_camera_m": [round(float(x), 5) for x in t_palm_camera],
              "quaternion_palm_camera_wxyz": [round(float(x), 5) for x in quat_palm_camera_wxyz],
              "camera_ip": f"{args.iphone_ip}:{args.port}",
              "mean_camera_distance_m": round(float(np.linalg.norm(t_cam_cube_avg)), 4),
            }

            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            # Also update local bundle path if different
            bundle_alt = _BUNDLE_ROOT / "project/real_world/camera_to_palm_iphone.json"
            if bundle_alt != args.output:
              bundle_alt.parent.mkdir(parents=True, exist_ok=True)
              bundle_alt.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            # Save visual verification snapshot
            R_cam_palm = R_palm_camera.T
            t_cam_palm = -R_cam_palm @ t_palm_camera
            rvec_palm, _ = cv2.Rodrigues(R_cam_palm)
            cv2.drawFrameAxes(vis, K, dist, rvec_palm, t_cam_palm, 0.08, 3)
            verification_path = _BUNDLE_ROOT / "camera_calibration_verification.jpg"
            cv2.imwrite(str(verification_path), vis)

            print("\n" + "=" * 70)
            print("✅ CALIBRATION SUCCESSFUL & SAVED!")
            print("=" * 70)
            print(f"  • Saved File:        {args.output}")
            print(f"  • Translation:       {payload['translation_palm_camera_m']} m")
            print(f"  • Quaternion (wxyz): {payload['quaternion_palm_camera_wxyz']}")
            print(f"  • Distance:          {payload['mean_camera_distance_m']} m")
            print(f"  • Verification Img:  {verification_path}")
            print("=" * 70 + "\n")

            calibrating = False
            if args.auto or not show_gui:
              print("Calibration finished. Exiting.")
              break
      else:
        steady_frames = 0
        cv2.putText(vis, "ARUCO MARKER NOT VISIBLE (Ensure ID 0 is in view)", (16, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)

      # Top Banner Instructions
      if not calibrating:
        if R_palm_camera_calibrated is not None:
          cv2.putText(vis, "CALIBRATION SAVED! Press [SPACE] to re-calibrate, [Q] to quit.", (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (50, 255, 50), 2)
          R_cam_palm = R_palm_camera_calibrated.T
          t_cam_palm = -R_cam_palm @ t_palm_camera_calibrated
          rvec_palm, _ = cv2.Rodrigues(R_cam_palm)
          cv2.drawFrameAxes(vis, K, dist, rvec_palm, t_cam_palm, 0.08, 3)
          cv2.putText(vis, "Palm Frame Axes (R=X, G=Y, B=Z)", (16, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        else:
          cv2.putText(vis, "Place cube in palm. Press [SPACE] to capture calibration.", (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

      if show_gui:
        cv2.imshow("Camera-to-Palm Calibration", vis)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
          break
        elif key == ord(" "):
          if pose is not None:
            calibrating = True
            collected_R_cam_cube.clear()
            collected_t_cam_cube.clear()
            print("\n[Calibrating] Collecting 30 sample frames...")
          else:
            print("\n[Warning] Cannot calibrate: ArUco marker is not visible. Adjust cube position.")
      else:
        time.sleep(0.01)

  finally:
    sub.close()
    cv2.destroyAllWindows()
    print("Calibration session ended.")


if __name__ == "__main__":
  main()
