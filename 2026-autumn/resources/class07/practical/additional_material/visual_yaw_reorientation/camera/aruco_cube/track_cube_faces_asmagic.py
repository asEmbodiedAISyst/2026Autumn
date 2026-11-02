#!/usr/bin/env python3
"""Track the six-face ArUco cube from the standalone asMagic iPhone stream."""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
import time
from typing import Sequence

import cv2
import numpy as np

from aruco_pose import CubePose, CubePoseEstimator, rotation_project
from cube_model import CubeModel, load_cube_model, rotation_to_quaternion_xyzw


HERE = Path(__file__).resolve().parent
CAMERA_FRAME = "iphone_color_optical_x_right_y_down_z_forward"


@dataclass(frozen=True)
class StabilityResult:
    """Quality metrics for one rolling, capture-time-based hold."""

    sample_count: int
    duration_s: float
    valid_fraction: float
    max_gap_s: float
    median_surface_m: float | None
    mad_m: float | None
    p95_p05_span_m: float | None
    stable: bool
    failure_reasons: tuple[str, ...]


class RangeStability:
    """Track the closest low-motion distance over continuous timed holds."""

    def __init__(
        self,
        hold_seconds: float,
        required_fraction: float,
        min_samples: int,
        max_gap_s: float,
        max_mad_m: float,
        max_p95_p05_span_m: float,
    ) -> None:
        self.values: deque[tuple[float, float | None]] = deque()
        self.hold_seconds = hold_seconds
        self.required_fraction = required_fraction
        self.min_samples = min_samples
        self.max_gap_s = max_gap_s
        self.max_mad_m = max_mad_m
        self.max_p95_p05_span_m = max_p95_p05_span_m
        self.closest_stable_surface_m: float | None = None

    def update(
        self,
        timestamp_s: float,
        surface_distance_m: float | None,
    ) -> StabilityResult:
        if not math.isfinite(timestamp_s):
            raise ValueError("frame timestamp must be finite")
        if surface_distance_m is not None and (
            not math.isfinite(surface_distance_m) or surface_distance_m < 0.0
        ):
            raise ValueError("surface distance must be finite and non-negative")

        timestamp_reset = bool(
            self.values and timestamp_s <= self.values[-1][0]
        )
        if timestamp_reset:
            self.values.clear()
        self.values.append((timestamp_s, surface_distance_m))

        cutoff = timestamp_s - self.hold_seconds
        # Retain one sample on or before the cutoff so the measured interval
        # demonstrably covers the requested hold duration.
        while len(self.values) >= 2 and self.values[1][0] <= cutoff:
            self.values.popleft()

        timestamps = np.asarray(
            [sample_timestamp for sample_timestamp, _ in self.values],
            dtype=np.float64,
        )
        valid = np.asarray(
            [value for _, value in self.values if value is not None],
            dtype=np.float64,
        )
        sample_count = len(self.values)
        duration_s = (
            float(timestamps[-1] - timestamps[0])
            if sample_count >= 2
            else 0.0
        )
        max_observed_gap_s = (
            float(np.max(np.diff(timestamps)))
            if sample_count >= 2
            else 0.0
        )
        valid_fraction = len(valid) / sample_count

        median_surface_m: float | None = None
        mad_m: float | None = None
        robust_span_m: float | None = None
        if len(valid):
            median_surface_m = float(np.median(valid))
            mad_m = float(np.median(np.abs(valid - median_surface_m)))
            p05, p95 = np.percentile(valid, [5.0, 95.0])
            robust_span_m = float(p95 - p05)

        reasons: list[str] = []
        if timestamp_reset:
            reasons.append("timestamp_reset")
        if duration_s + 1e-9 < self.hold_seconds:
            reasons.append("hold_duration")
        if sample_count < self.min_samples:
            reasons.append("sample_count")
        if valid_fraction < self.required_fraction:
            reasons.append("valid_fraction")
        if max_observed_gap_s > self.max_gap_s:
            reasons.append("sample_gap")
        if mad_m is None:
            reasons.append("no_valid_pose")
        elif mad_m > self.max_mad_m:
            reasons.append("distance_mad")
        if robust_span_m is not None and robust_span_m > self.max_p95_p05_span_m:
            reasons.append("distance_span")

        stable = not reasons
        if stable and median_surface_m is not None and (
            self.closest_stable_surface_m is None
            or median_surface_m < self.closest_stable_surface_m
        ):
            self.closest_stable_surface_m = median_surface_m

        return StabilityResult(
            sample_count=sample_count,
            duration_s=duration_s,
            valid_fraction=valid_fraction,
            max_gap_s=max_observed_gap_s,
            median_surface_m=median_surface_m,
            mad_m=mad_m,
            p95_p05_span_m=robust_span_m,
            stable=stable,
            failure_reasons=tuple(reasons),
        )


def camera_matrix_from_asmagic(
    intrinsics: object,
    image_width: int,
    image_height: int,
    reference_width: int = 1920,
    reference_height: int = 1440,
) -> np.ndarray:
    """Convert asMagic's column-major intrinsics to the streamed image size."""

    values = np.asarray(intrinsics, dtype=np.float64).reshape(-1)
    if values.shape != (9,) or not np.all(np.isfinite(values)):
        raise ValueError(
            f"asMagic camera_intrinsics must contain nine finite values; got {values.shape}"
        )
    if image_width < 1 or image_height < 1:
        raise ValueError("image dimensions must be positive")
    if reference_width < 1 or reference_height < 1:
        raise ValueError("intrinsics reference dimensions must be positive")
    image_aspect = image_width / image_height
    reference_aspect = reference_width / reference_height
    if not math.isclose(image_aspect, reference_aspect, rel_tol=0.02):
        raise ValueError(
            "unexpected asMagic image aspect ratio; keep the iPhone in "
            f"landscape ({image_width}x{image_height} received, "
            f"{reference_width}x{reference_height} intrinsics reference)"
        )

    # asMagic documents [fx, 0, 0, 0, fy, 0, cx, cy, 1], column-major.
    camera_matrix = values.reshape(3, 3, order="F")
    camera_matrix = camera_matrix.copy()
    scale_x = image_width / reference_width
    scale_y = image_height / reference_height
    camera_matrix[0, 0] *= scale_x
    camera_matrix[0, 2] *= scale_x
    camera_matrix[1, 1] *= scale_y
    camera_matrix[1, 2] *= scale_y

    if (
        camera_matrix[0, 0] <= 0
        or camera_matrix[1, 1] <= 0
        or abs(camera_matrix[2, 2] - 1.0) > 1e-6
    ):
        raise ValueError(f"invalid scaled camera matrix: {camera_matrix.tolist()}")
    return camera_matrix


def geometric_limits(
    camera_matrix: np.ndarray,
    image_width: int,
    image_height: int,
    cube_size_m: float,
    marker_size_m: float,
    total_margin_fraction: float = 0.0,
) -> dict[str, float]:
    """Return centered pinhole crop limits; these are not focus guarantees."""

    if not (0.0 <= total_margin_fraction < 1.0):
        raise ValueError("total margin fraction must be in [0, 1)")
    fx = float(camera_matrix[0, 0])
    fy = float(camera_matrix[1, 1])
    cx = float(camera_matrix[0, 2])
    cy = float(camera_matrix[1, 2])
    usable = 1.0 - total_margin_fraction
    margin_x = min(cx, image_width - cx) * usable
    margin_y = min(cy, image_height - cy) * usable
    if margin_x <= 0 or margin_y <= 0:
        raise ValueError("camera principal point lies outside the image")

    cube_half = cube_size_m / 2.0
    marker_half = marker_size_m / 2.0
    frontal_surface_m = max(
        fx * cube_half / margin_x,
        fy * cube_half / margin_y,
    )
    marker_plane_m = max(
        fx * marker_half / margin_x,
        fy * marker_half / margin_y,
    )

    half_angle_x = math.atan(margin_x / fx)
    half_angle_y = math.atan(margin_y / fy)
    limiting_half_angle = min(half_angle_x, half_angle_y)
    bounding_radius = math.sqrt(3.0) * cube_half
    any_orientation_center_m = bounding_radius / math.sin(limiting_half_angle)

    return {
        "marker_only_plane_m": marker_plane_m,
        "frontal_nearest_surface_m": frontal_surface_m,
        "frontal_cube_center_m": frontal_surface_m + cube_half,
        "any_orientation_cube_center_m": any_orientation_center_m,
        "any_orientation_nearest_sphere_surface_m": (
            any_orientation_center_m - bounding_radius
        ),
        "horizontal_fov_deg": math.degrees(2.0 * math.atan(image_width / (2.0 * fx))),
        "vertical_fov_deg": math.degrees(2.0 * math.atan(image_height / (2.0 * fy))),
    }


def camera_to_cube_surface_distance(pose: CubePose, cube_size_m: float) -> float:
    """Model-box distance from the camera optical center to the oriented cube."""

    camera_origin_cube = (
        pose.rotation_camera_cube.T @ (-pose.translation_camera_cube)
    )
    outside = np.maximum(np.abs(camera_origin_cube) - cube_size_m / 2.0, 0.0)
    return float(np.linalg.norm(outside))


def mean_marker_edge_px(
    corners: list[np.ndarray],
    ids: list[int],
    model: CubeModel,
) -> float | None:
    lengths: list[float] = []
    for marker_corners, marker_id in zip(corners, ids):
        if marker_id not in model.faces_by_id:
            continue
        points = np.asarray(marker_corners, dtype=np.float64).reshape(4, 2)
        edges = np.roll(points, -1, axis=0) - points
        lengths.extend(np.linalg.norm(edges, axis=1).tolist())
    return float(np.mean(lengths)) if lengths else None


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
    *,
    frame_number: int,
    iphone_timestamp_s: float,
    host_timestamp_s: float,
    camera_matrix: np.ndarray,
    pose: CubePose | None,
    raw_surface_distance_m: float | None,
    marker_edge_px: float | None,
    detected_marker_ids: list[int],
    raw_reprojection_error_px: float | None,
    stability: StabilityResult,
    closest_stable_surface_m: float | None,
    rejection_reason: str | None,
    cube_size_m: float,
) -> dict[str, object]:
    record: dict[str, object] = {
        "frame": frame_number,
        "iphone_timestamp_s": iphone_timestamp_s,
        "host_timestamp_s": host_timestamp_s,
        "camera_frame": CAMERA_FRAME,
        "camera_matrix": camera_matrix.tolist(),
        "distortion_assumption": "zero_coefficients_not_provided_by_asmagic",
        "tracking_valid": pose is not None,
        "rejection_reason": rejection_reason,
        "detected_marker_ids": detected_marker_ids,
        "mean_configured_marker_edge_px": marker_edge_px,
        "raw_reprojection_error_px": raw_reprojection_error_px,
        "rolling_valid_fraction": stability.valid_fraction,
        "stability_sample_count": stability.sample_count,
        "stability_duration_s": stability.duration_s,
        "stability_max_gap_s": stability.max_gap_s,
        "stability_mad_m": stability.mad_m,
        "stability_p95_p05_span_m": stability.p95_p05_span_m,
        "stability_failure_reasons": list(stability.failure_reasons),
        "stable_window": stability.stable,
        "stable_window_median_surface_m": (
            stability.median_surface_m if stability.stable else None
        ),
        "closest_stable_surface_m": closest_stable_surface_m,
    }
    if pose is None:
        return record

    surface_distance_m = camera_to_cube_surface_distance(pose, cube_size_m)
    record.update(
        {
            "pose_is_temporally_filtered": True,
            "cube_center_m": pose.translation_camera_cube.tolist(),
            "cube_center_distance_m": float(
                np.linalg.norm(pose.translation_camera_cube)
            ),
            "cube_center_z_m": float(pose.translation_camera_cube[2]),
            "camera_to_cube_surface_m": surface_distance_m,
            "raw_camera_to_cube_surface_m": raw_surface_distance_m,
            "cube_quaternion_xyzw": rotation_to_quaternion_xyzw(
                pose.rotation_camera_cube
            ),
            "cube_rotation_matrix": pose.rotation_camera_cube.tolist(),
            "visible_marker_ids": list(pose.visible_ids),
            "visible_faces": list(pose.visible_faces),
            "reprojection_error_px": raw_reprojection_error_px,
        }
    )
    return record


def annotate(
    image: np.ndarray,
    corners: list[np.ndarray],
    ids: list[int],
    pose: CubePose | None,
    camera_matrix: np.ndarray,
    distortion: np.ndarray,
    cube_size_m: float,
    marker_edge_px: float | None,
    stability: StabilityResult,
    closest_stable_surface_m: float | None,
    roi: tuple[int, int, int, int] | None,
) -> np.ndarray:
    output = image.copy()
    if roi:
        x, y, width, height = roi
        cv2.rectangle(output, (x, y), (x + width, y + height), (255, 255, 0), 2)

    if corners:
        draw_corners = [
            np.asarray(corner, dtype=np.float32).reshape(1, 4, 2)
            for corner in corners
        ]
        cv2.aruco.drawDetectedMarkers(
            output,
            draw_corners,
            np.asarray(ids, dtype=np.int32).reshape(-1, 1),
        )

    if pose is None:
        cv2.putText(
            output,
            "No configured cube marker visible",
            (14, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (0, 0, 255),
            2,
        )
    else:
        rvec, _ = cv2.Rodrigues(pose.rotation_camera_cube)
        cv2.drawFrameAxes(
            output,
            camera_matrix,
            distortion,
            rvec,
            pose.translation_camera_cube.reshape(3, 1),
            cube_size_m * 0.75,
            2,
        )
        center_distance = float(np.linalg.norm(pose.translation_camera_cube))
        surface_distance = camera_to_cube_surface_distance(pose, cube_size_m)
        cv2.putText(
            output,
            (
                f"center={center_distance * 100:.1f}cm "
                f"surface={surface_distance * 100:.1f}cm "
                f"z={pose.translation_camera_cube[2] * 100:.1f}cm"
            ),
            (14, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.54,
            (0, 255, 0),
            2,
        )
        marker_text = (
            f"ids={list(pose.visible_ids)} edge={marker_edge_px:.1f}px "
            f"err={pose.reprojection_error_px:.2f}px"
            if marker_edge_px is not None
            else (
                f"ids={list(pose.visible_ids)} "
                f"err={pose.reprojection_error_px:.2f}px"
            )
        )
        cv2.putText(
            output,
            marker_text,
            (14, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            (0, 255, 0),
            2,
        )

    stable_median = stability.median_surface_m if stability.stable else None
    stable_text = (
        f"stable {stable_median * 100:.1f}cm"
        if stable_median is not None
        else "not stable"
    )
    closest_text = (
        f"closest={closest_stable_surface_m * 100:.1f}cm"
        if closest_stable_surface_m is not None
        else "closest=--"
    )
    span_text = (
        f"span={stability.p95_p05_span_m * 100:.2f}cm"
        if stability.p95_p05_span_m is not None
        else "span=--"
    )
    color = (0, 220, 0) if stability.stable else (0, 180, 255)
    cv2.putText(
        output,
        (
            f"hold={stability.duration_s:.1f}s n={stability.sample_count} "
            f"valid={stability.valid_fraction * 100:.0f}% {span_text}"
        ),
        (14, image.shape[0] - 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        color,
        2,
    )
    cv2.putText(
        output,
        f"{stable_text} {closest_text}",
        (14, image.shape[0] - 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        color,
        2,
    )
    return output


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iphone-ip", required=True)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--config", type=Path, default=HERE / "cube_config.json")
    parser.add_argument(
        "--roi",
        type=int,
        nargs=4,
        metavar=("X", "Y", "W", "H"),
        help="optional iPhone-frame search region; default searches the full image",
    )
    parser.add_argument("--max-reprojection-error", type=float, default=3.0)
    parser.add_argument("--position-alpha", type=float, default=0.30)
    parser.add_argument("--rotation-alpha", type=float, default=0.30)
    parser.add_argument(
        "--stability-min-samples",
        "--stability-window",
        dest="stability_min_samples",
        type=int,
        default=30,
        help="minimum samples in a stationary hold (old --stability-window alias supported)",
    )
    parser.add_argument("--stability-fraction", type=float, default=0.95)
    parser.add_argument("--stability-hold-seconds", type=float, default=2.0)
    parser.add_argument("--stability-max-gap-seconds", type=float, default=0.25)
    parser.add_argument(
        "--stability-max-mad-cm",
        type=float,
        default=0.20,
        help="maximum median absolute range deviation during a stable hold",
    )
    parser.add_argument(
        "--stability-max-span-cm",
        type=float,
        default=0.80,
        help="maximum 5th-to-95th percentile range span during a stable hold",
    )
    parser.add_argument(
        "--framing-margin",
        type=float,
        default=0.30,
        help="total image margin used for the printed geometric bound",
    )
    parser.add_argument("--intrinsics-reference-width", type=int, default=1920)
    parser.add_argument("--intrinsics-reference-height", type=int, default=1440)
    parser.add_argument("--poll-timeout-ms", type=int, default=100)
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--frames", type=int, default=0)
    parser.add_argument("--print-every", type=int, default=10)
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--save-preview", type=Path)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    if not (1 <= args.port <= 65535):
        parser.error("--port must be in [1, 65535]")
    if args.frames < 0:
        parser.error("--frames must be zero or positive")
    if not math.isfinite(args.duration) or args.duration < 0:
        parser.error("--duration must be a finite value that is zero or positive")
    if args.print_every < 1 or args.stability_min_samples < 1:
        parser.error("--print-every and --stability-min-samples must be positive")
    if not (0.0 < args.stability_fraction <= 1.0):
        parser.error("--stability-fraction must be in (0, 1]")
    positive_stability_values = (
        args.stability_hold_seconds,
        args.stability_max_gap_seconds,
        args.stability_max_mad_cm,
        args.stability_max_span_cm,
    )
    if any(
        not math.isfinite(value) or value <= 0.0
        for value in positive_stability_values
    ):
        parser.error("stability duration, gap, MAD, and span limits must be positive")
    if not (0.0 <= args.framing_margin < 1.0):
        parser.error("--framing-margin must be in [0, 1)")
    if args.max_reprojection_error <= 0:
        parser.error("--max-reprojection-error must be positive")
    if not (0.0 < args.position_alpha <= 1.0):
        parser.error("--position-alpha must be in (0, 1]")
    if not (0.0 < args.rotation_alpha <= 1.0):
        parser.error("--rotation-alpha must be in (0, 1]")
    if args.poll_timeout_ms < 1:
        parser.error("--poll-timeout-ms must be positive")
    if (
        args.intrinsics_reference_width < 1
        or args.intrinsics_reference_height < 1
    ):
        parser.error("intrinsics reference dimensions must be positive")
    if args.roi is not None and (args.roi[2] < 1 or args.roi[3] < 1):
        parser.error("ROI width and height must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        from asmagic import ARDataSubscriber
    except ImportError:
        print(
            "asmagic is not installed. Run: python -m pip install -r requirements_asmagic.txt",
            file=sys.stderr,
        )
        return 2

    model = load_cube_model(args.config)
    estimator = CubePoseEstimator(model)
    stability = RangeStability(
        hold_seconds=args.stability_hold_seconds,
        required_fraction=args.stability_fraction,
        min_samples=args.stability_min_samples,
        max_gap_s=args.stability_max_gap_seconds,
        max_mad_m=args.stability_max_mad_cm / 100.0,
        max_p95_p05_span_m=args.stability_max_span_cm / 100.0,
    )
    distortion = np.zeros((1, 5), dtype=np.float64)
    roi = tuple(args.roi) if args.roi is not None else None

    json_file = None
    if args.jsonl:
        args.jsonl.parent.mkdir(parents=True, exist_ok=True)
        json_file = args.jsonl.open("w", encoding="utf-8")
    if args.save_preview:
        args.save_preview.parent.mkdir(parents=True, exist_ok=True)

    subscriber = None
    latest_preview = None
    filtered_pose: CubePose | None = None
    frames = 0
    valid_poses = 0
    first_limits_printed = False
    started_monotonic = time.monotonic()
    stop_reason = "completed"

    try:
        subscriber = ARDataSubscriber(
            args.iphone_ip,
            port=args.port,
            hwm=1,
            conflate=True,
            verbose=args.verbose,
        )
        print(
            "Tracking asMagic RGB. Press q or Esc in the preview window to stop.",
            flush=True,
        )

        while args.frames == 0 or frames < args.frames:
            if args.duration > 0 and time.monotonic() - started_monotonic >= args.duration:
                stop_reason = "duration"
                break

            frame = subscriber.get(timeout=args.poll_timeout_ms)
            if frame is None:
                if not args.headless:
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), 27):
                        stop_reason = "user"
                        break
                continue
            frames += 1

            iphone_timestamp_s = float(frame.timestamp)
            if not frame.has_color_image:
                stability.update(iphone_timestamp_s, None)
                filtered_pose = None
                continue
            encoded = np.frombuffer(frame.color_bytes, dtype=np.uint8)
            image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            if image is None:
                stability.update(iphone_timestamp_s, None)
                filtered_pose = None
                continue

            height, width = image.shape[:2]
            camera_matrix = camera_matrix_from_asmagic(
                frame.camera_intrinsics,
                width,
                height,
                args.intrinsics_reference_width,
                args.intrinsics_reference_height,
            )
            if not first_limits_printed:
                crop = geometric_limits(
                    camera_matrix,
                    width,
                    height,
                    model.cube_size_m,
                    model.marker_size_m,
                    0.0,
                )
                working = geometric_limits(
                    camera_matrix,
                    width,
                    height,
                    model.cube_size_m,
                    model.marker_size_m,
                    args.framing_margin,
                )
                print(
                    (
                        f"Camera {width}x{height}, "
                        f"FOV={crop['horizontal_fov_deg']:.1f}x"
                        f"{crop['vertical_fov_deg']:.1f} deg"
                    ),
                    flush=True,
                )
                print(
                    (
                        "Ideal crop limits: marker plane="
                        f"{crop['marker_only_plane_m'] * 100:.1f}cm, "
                        "frontal cube center="
                        f"{crop['frontal_cube_center_m'] * 100:.1f}cm, "
                        "any-orientation center="
                        f"{crop['any_orientation_cube_center_m'] * 100:.1f}cm"
                    ),
                    flush=True,
                )
                print(
                    (
                        f"With {args.framing_margin * 100:.0f}% total margin: "
                        "frontal cube center="
                        f"{working['frontal_cube_center_m'] * 100:.1f}cm, "
                        "any-orientation center="
                        f"{working['any_orientation_cube_center_m'] * 100:.1f}cm"
                    ),
                    flush=True,
                )
                first_limits_printed = True

            corners, ids, _ = estimator.detect(image, roi)
            candidate_pose = estimator.estimate(
                corners, ids, camera_matrix, distortion
            )
            raw_reprojection_error_px = (
                None
                if candidate_pose is None
                else candidate_pose.reprojection_error_px
            )
            raw_pose = candidate_pose
            rejection_reason = None
            if (
                raw_pose is not None
                and raw_pose.reprojection_error_px > args.max_reprojection_error
            ):
                rejection_reason = "reprojection_error"
                raw_pose = None
            elif raw_pose is None:
                rejection_reason = "no_configured_marker"

            marker_edge_px = mean_marker_edge_px(corners, ids, model)
            raw_surface_distance_m = (
                None
                if raw_pose is None
                else camera_to_cube_surface_distance(raw_pose, model.cube_size_m)
            )
            stability_result = stability.update(
                iphone_timestamp_s, raw_surface_distance_m
            )

            display_pose = None
            if raw_pose is not None:
                filtered_pose = smooth_pose(
                    raw_pose,
                    filtered_pose,
                    args.position_alpha,
                    args.rotation_alpha,
                )
                display_pose = filtered_pose
                valid_poses += 1
            else:
                # Never blend a newly reacquired pose with stale pre-loss state.
                filtered_pose = None

            record = pose_record(
                frame_number=frames,
                iphone_timestamp_s=iphone_timestamp_s,
                host_timestamp_s=time.time(),
                camera_matrix=camera_matrix,
                pose=display_pose,
                raw_surface_distance_m=raw_surface_distance_m,
                marker_edge_px=marker_edge_px,
                detected_marker_ids=ids,
                raw_reprojection_error_px=raw_reprojection_error_px,
                stability=stability_result,
                closest_stable_surface_m=stability.closest_stable_surface_m,
                rejection_reason=rejection_reason,
                cube_size_m=model.cube_size_m,
            )
            if json_file is not None:
                json_file.write(json.dumps(record, separators=(",", ":")) + "\n")
                json_file.flush()
            if display_pose is not None and valid_poses % args.print_every == 0:
                print(json.dumps(record, separators=(",", ":")), flush=True)

            latest_preview = annotate(
                image,
                corners,
                ids,
                display_pose,
                camera_matrix,
                distortion,
                model.cube_size_m,
                marker_edge_px,
                stability_result,
                stability.closest_stable_surface_m,
                roi,
            )
            if not args.headless:
                cv2.imshow("asMagic iPhone ArUco cube pose - Q/Esc to quit", latest_preview)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    stop_reason = "user"
                    break
    except KeyboardInterrupt:
        stop_reason = "keyboard_interrupt"
    finally:
        if subscriber is not None:
            subscriber.close()
        if json_file is not None:
            json_file.close()
        cv2.destroyAllWindows()

    if latest_preview is not None and args.save_preview:
        if not cv2.imwrite(str(args.save_preview), latest_preview):
            print(f"Could not save preview to {args.save_preview}", file=sys.stderr)
            return 2
        print(f"Saved preview to {args.save_preview.resolve()}")

    ratio = valid_poses / frames if frames else 0.0
    print(
        f"Stopped ({stop_reason}): {valid_poses}/{frames} valid poses "
        f"({ratio * 100:.1f}%)."
    )
    if stability.closest_stable_surface_m is None:
        print(
            "No stationary nearest distance measured. Keep one complete marker "
            f"visible and still for at least {args.stability_hold_seconds:.1f}s "
            f"and {args.stability_min_samples} samples."
        )
    else:
        print(
            "Closest stable camera-to-cube surface distance: "
            f"{stability.closest_stable_surface_m * 100:.1f} cm "
            f"({args.stability_fraction * 100:.0f}% valid, "
            f"{args.stability_hold_seconds:.1f}s stationary hold)."
        )

    return 0 if valid_poses else 1


if __name__ == "__main__":
    raise SystemExit(main())
