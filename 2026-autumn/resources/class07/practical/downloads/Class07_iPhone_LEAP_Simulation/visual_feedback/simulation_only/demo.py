#!/usr/bin/env python3
"""Recover one declared synthetic cube pose from projected marker corners."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "camera"))

from aruco_pose import CubePoseEstimator  # noqa: E402
from cube_model import load_cube_model, make_transform  # noqa: E402


def rotation_error_deg(left: np.ndarray, right: np.ndarray) -> float:
    delta = left @ right.T
    return float(np.degrees(np.arccos(np.clip((np.trace(delta) - 1.0) / 2.0, -1.0, 1.0))))


def synthetic_recovery(noise_px: float = 0.0, seed: int = 7) -> dict[str, object]:
    cube = load_cube_model(ROOT / "camera" / "cube_config.json")
    estimator = CubePoseEstimator(cube)
    camera = np.asarray([[615.0, 0.0, 320.0], [0.0, 615.0, 240.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    distortion = np.zeros((1, 5), dtype=np.float64)
    rotation, _ = cv2.Rodrigues(np.asarray([0.22, -0.31, 0.13], dtype=np.float64))
    expected = make_transform(rotation, np.asarray([0.025, -0.018, 0.58]))
    face = cube.faces_by_name["+Z"]
    camera_marker = expected @ face.transform_cube_marker()
    rvec, _ = cv2.Rodrigues(camera_marker[:3, :3])
    corners, _ = cv2.projectPoints(cube.marker_corners(), rvec, camera_marker[:3, 3], camera, distortion)
    corners = corners.reshape(4, 2)
    if noise_px:
        corners += np.random.default_rng(seed).normal(0.0, noise_px, corners.shape)
    pose = estimator.estimate([corners], [face.marker_id], camera, distortion)
    if pose is None:
        raise RuntimeError("synthetic pose recovery unexpectedly failed")
    return {
        "marker_id": face.marker_id,
        "noise_std_px": noise_px,
        "translation_error_mm": 1000.0 * float(np.linalg.norm(pose.translation_camera_cube - expected[:3, 3])),
        "rotation_error_deg": rotation_error_deg(pose.rotation_camera_cube, expected[:3, :3]),
        "reprojection_error_px": float(pose.reprojection_error_px),
        "estimated_translation_camera_cube_m": pose.translation_camera_cube.tolist(),
    }


def main() -> None:
    result = {
        "classification": "synthetic correspondence and pose-recovery check; not physical calibration",
        "camera_matrix": [[615.0, 0.0, 320.0], [0.0, 615.0, 240.0], [0.0, 0.0, 1.0]],
        "recovery": synthetic_recovery(),
        "unavailable_gate": "fewer than four corners cannot form this single-marker PnP input",
    }
    output = ROOT / "outputs" / "synthetic_pose_recovery.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
