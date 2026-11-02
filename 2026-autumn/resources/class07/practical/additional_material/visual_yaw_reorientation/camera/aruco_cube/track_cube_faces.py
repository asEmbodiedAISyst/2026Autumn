#!/usr/bin/env python3
"""Track a six-marker cube and report every face from an Intel RealSense camera."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pyrealsense2 as rs

from aruco_pose import CubePose, CubePoseEstimator, classify_faces, rotation_project
from cube_model import CubeModel, load_cube_model, rotation_to_quaternion_xyzw


HERE = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=HERE / "cube_config.json")
    parser.add_argument("--width", type=int, default=1280, help="Color width (default: 1280)")
    parser.add_argument("--height", type=int, default=720, help="Color height (default: 720)")
    parser.add_argument("--fps", type=int, default=15, help="Color frame rate (default: 15)")
    parser.add_argument(
        "--roi",
        type=int,
        nargs=4,
        metavar=("X", "Y", "W", "H"),
        default=(450, 280, 340, 300),
        help="LEAP-hand search region at 1280x720 (default: 450 280 340 300)",
    )
    parser.add_argument(
        "--up-calibration",
        type=Path,
        default=HERE / "up_calibration.json",
        help="Saved camera-frame physical-up vector",
    )
    parser.add_argument(
        "--calibrate-up",
        action="store_true",
        help="Place --calibration-face upward, collect samples, save calibration, and exit",
    )
    parser.add_argument("--calibration-face", default="+Z", help="Face physically upward during calibration")
    parser.add_argument("--calibration-samples", type=int, default=60)
    parser.add_argument("--max-reprojection-error", type=float, default=3.0, help="Reject poses above this pixel RMS error")
    parser.add_argument("--position-alpha", type=float, default=0.30, help="Position EMA coefficient")
    parser.add_argument("--rotation-alpha", type=float, default=0.30, help="Rotation EMA coefficient")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--frames", type=int, default=0, help="Stop after N frames; 0 runs continuously")
    parser.add_argument("--print-every", type=int, default=10)
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--save-preview", type=Path)
    return parser.parse_args()


def camera_parameters(intrinsics: rs.intrinsics) -> tuple[np.ndarray, np.ndarray]:
    camera_matrix = np.array(
        [
            [intrinsics.fx, 0.0, intrinsics.ppx],
            [0.0, intrinsics.fy, intrinsics.ppy],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    distortion = np.asarray(intrinsics.coeffs, dtype=np.float64).reshape(1, -1)
    return camera_matrix, distortion


def load_up_vector(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    vector = np.asarray(data["up_camera"], dtype=np.float64)
    norm = np.linalg.norm(vector)
    if vector.shape != (3,) or norm < 1e-8:
        raise ValueError(f"Invalid up vector in {path}")
    return vector / norm


def save_up_vector(path: Path, vector: np.ndarray, face_name: str, samples: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "camera_frame": "realsense_color_optical_x_right_y_down_z_forward",
        "up_camera": vector.tolist(),
        "calibration_face": face_name,
        "samples": samples,
        "created_unix_s": time.time(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def smooth_pose(
    pose: CubePose,
    previous: CubePose | None,
    position_alpha: float,
    rotation_alpha: float,
) -> CubePose:
    if previous is None:
        return pose
    translation = (
        (1.0 - position_alpha) * previous.translation_camera_cube
        + position_alpha * pose.translation_camera_cube
    )
    rotation = rotation_project(
        (1.0 - rotation_alpha) * previous.rotation_camera_cube
        + rotation_alpha * pose.rotation_camera_cube
    )
    return CubePose(
        rotation_camera_cube=rotation,
        translation_camera_cube=translation,
        reprojection_error_px=pose.reprojection_error_px,
        visible_faces=pose.visible_faces,
        visible_ids=pose.visible_ids,
    )


def pose_record(
    pose: CubePose,
    model: CubeModel,
    up_camera: np.ndarray | None,
    frame_number: int,
    camera_timestamp_ms: float,
) -> dict[str, object]:
    face_states, up_face, camera_facing_face = classify_faces(model, pose, up_camera)
    return {
        "host_time_s": time.time(),
        "camera_timestamp_ms": camera_timestamp_ms,
        "frame": frame_number,
        "camera_frame": "realsense_color_optical_x_right_y_down_z_forward",
        "tracking_valid": True,
        "cube_center_m": pose.translation_camera_cube.tolist(),
        "cube_quaternion_xyzw": rotation_to_quaternion_xyzw(pose.rotation_camera_cube),
        "cube_rotation_matrix": pose.rotation_camera_cube.tolist(),
        "visible_marker_ids": list(pose.visible_ids),
        "visible_faces": list(pose.visible_faces),
        "up_face": up_face,
        "camera_facing_face": camera_facing_face,
        "reprojection_error_px": pose.reprojection_error_px,
        "faces": face_states,
    }


def project_camera_point(
    point: np.ndarray,
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
) -> tuple[int, int] | None:
    if point[2] <= 0:
        return None
    image_points, _ = cv2.projectPoints(
        point.reshape(1, 3),
        np.zeros((3, 1)),
        np.zeros((3, 1)),
        camera_matrix,
        distortion,
    )
    pixel = image_points.reshape(2)
    return int(round(pixel[0])), int(round(pixel[1]))


def annotate(
    image: np.ndarray,
    corners: list[np.ndarray],
    ids: list[int],
    pose: CubePose | None,
    model: CubeModel,
    up_camera: np.ndarray | None,
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
    roi: tuple[int, int, int, int] | None,
    calibration_progress: tuple[int, int] | None = None,
) -> np.ndarray:
    output = image.copy()
    if roi:
        x, y, width, height = roi
        cv2.rectangle(output, (x, y), (x + width, y + height), (255, 255, 0), 2)
    if corners:
        draw_corners = [corner.astype(np.float32).reshape(1, 4, 2) for corner in corners]
        cv2.aruco.drawDetectedMarkers(output, draw_corners, np.asarray(ids, dtype=np.int32).reshape(-1, 1))

    if pose is None:
        cv2.putText(output, "No configured cube marker visible", (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (0, 0, 255), 2)
    else:
        record = pose_record(pose, model, up_camera, 0, 0.0)
        rvec, _ = cv2.Rodrigues(pose.rotation_camera_cube)
        cv2.drawFrameAxes(
            output,
            camera_matrix,
            distortion,
            rvec,
            pose.translation_camera_cube.reshape(3, 1),
            model.cube_size_m * 0.75,
            2,
        )
        center = pose.translation_camera_cube
        cv2.putText(
            output,
            f"center x={center[0]:+.3f} y={center[1]:+.3f} z={center[2]:.3f} m",
            (18, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (0, 255, 0),
            2,
        )
        up_text = record["up_face"] if record["up_face"] is not None else "uncalibrated"
        cv2.putText(
            output,
            f"visible={','.join(pose.visible_faces)}  up={up_text}  error={pose.reprojection_error_px:.2f}px",
            (18, 53),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 0),
            2,
        )
        face_states = record["faces"]
        for face_name in pose.visible_faces:
            face_state = face_states[face_name]
            pixel = project_camera_point(
                np.asarray(face_state["center_camera_m"]), camera_matrix, distortion
            )
            if pixel is not None:
                cv2.putText(output, face_name, pixel, cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
    if calibration_progress:
        count, target = calibration_progress
        cv2.putText(
            output,
            f"UP CALIBRATION: {count}/{target} valid samples",
            (18, image.shape[0] - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 0, 255),
            2,
        )
    return output


def main() -> int:
    args = parse_args()
    if (
        args.frames < 0
        or args.print_every < 1
        or args.calibration_samples < 1
        or args.width < 1
        or args.height < 1
        or args.fps < 1
    ):
        raise SystemExit("Invalid frame/print/calibration count")
    if not (0.0 < args.position_alpha <= 1.0 and 0.0 < args.rotation_alpha <= 1.0):
        raise SystemExit("Filter alpha values must be in (0, 1]")

    model = load_cube_model(args.config)
    if args.calibration_face not in model.faces_by_name:
        raise SystemExit(f"Unknown calibration face {args.calibration_face!r}")
    estimator = CubePoseEstimator(model)
    up_camera = None if args.calibrate_up else load_up_vector(args.up_calibration)
    if not args.calibrate_up and up_camera is None:
        print(
            f"Warning: {args.up_calibration} does not exist; up_face will be null until calibration.",
            file=sys.stderr,
        )

    json_file = None
    if args.jsonl:
        args.jsonl.parent.mkdir(parents=True, exist_ok=True)
        json_file = args.jsonl.open("w", encoding="utf-8")
    if args.save_preview:
        args.save_preview.parent.mkdir(parents=True, exist_ok=True)

    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(
        rs.stream.color,
        args.width,
        args.height,
        rs.format.bgr8,
        args.fps,
    )
    profile = pipeline.start(config)
    color_profile = profile.get_stream(rs.stream.color).as_video_stream_profile()
    camera_matrix, distortion = camera_parameters(color_profile.get_intrinsics())

    filtered_pose = None
    latest_preview = None
    valid_poses = 0
    up_samples: list[np.ndarray] = []
    frame_number = 0
    calibration_complete = False

    try:
        for _ in range(15):
            pipeline.wait_for_frames(5000)
        while args.frames == 0 or frame_number < args.frames:
            frame_number += 1
            frames = pipeline.wait_for_frames(5000)
            color_frame = frames.get_color_frame()
            if not color_frame:
                continue
            image = np.asanyarray(color_frame.get_data())
            corners, ids, _ = estimator.detect(image, tuple(args.roi) if args.roi else None)
            raw_pose = estimator.estimate(corners, ids, camera_matrix, distortion)
            if raw_pose is not None and raw_pose.reprojection_error_px > args.max_reprojection_error:
                raw_pose = None

            if raw_pose is not None:
                filtered_pose = smooth_pose(
                    raw_pose,
                    filtered_pose,
                    args.position_alpha,
                    args.rotation_alpha,
                )
                valid_poses += 1

                if args.calibrate_up:
                    face = model.faces_by_name[args.calibration_face]
                    up_samples.append(filtered_pose.rotation_camera_cube @ face.normal_cube)
                    if len(up_samples) >= args.calibration_samples:
                        vector = np.mean(np.asarray(up_samples), axis=0)
                        vector /= np.linalg.norm(vector)
                        save_up_vector(
                            args.up_calibration,
                            vector,
                            args.calibration_face,
                            len(up_samples),
                        )
                        up_camera = vector
                        calibration_complete = True
                else:
                    record = pose_record(
                        filtered_pose,
                        model,
                        up_camera,
                        frame_number,
                        color_frame.get_timestamp(),
                    )
                    if valid_poses % args.print_every == 0:
                        print(json.dumps(record, separators=(",", ":")), flush=True)
                    if json_file is not None:
                        json_file.write(json.dumps(record, separators=(",", ":")) + "\n")
                        json_file.flush()

            latest_preview = annotate(
                image,
                corners,
                ids,
                filtered_pose if raw_pose is not None else None,
                model,
                up_camera,
                camera_matrix,
                distortion,
                tuple(args.roi) if args.roi else None,
                (len(up_samples), args.calibration_samples) if args.calibrate_up else None,
            )
            if not args.headless:
                cv2.imshow("D455 ArUco cube faces - Q/Esc to quit", latest_preview)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
            if calibration_complete:
                break
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()
        if json_file is not None:
            json_file.close()

    if latest_preview is not None and args.save_preview:
        if not cv2.imwrite(str(args.save_preview), latest_preview):
            print(f"Could not save preview to {args.save_preview}", file=sys.stderr)
            return 2
        print(f"Saved preview to {args.save_preview.resolve()}")

    if args.calibrate_up:
        if not calibration_complete:
            print(
                f"Up calibration incomplete: collected {len(up_samples)}/{args.calibration_samples} valid poses.",
                file=sys.stderr,
            )
            return 1
        print(f"Saved camera up calibration to {args.up_calibration.resolve()}")
        print(f"up_camera={up_camera.tolist()}")
        return 0
    if valid_poses == 0:
        print("No configured ArUco cube marker was detected.", file=sys.stderr)
        return 1
    print(f"Tracked {valid_poses} valid cube poses in {frame_number} frames.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
