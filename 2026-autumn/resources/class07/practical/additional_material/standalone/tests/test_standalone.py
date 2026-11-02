from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "camera"))

from aruco_pose import CubePoseEstimator  # noqa: E402
from cube_model import load_cube_model, make_transform  # noqa: E402


def test_cube_model_and_noise_free_pose_recovery() -> None:
    cube = load_cube_model(ROOT / "camera" / "cube_config.json")
    assert {face.marker_id for face in cube.faces} == set(range(6))
    camera = np.asarray([[615.0, 0.0, 320.0], [0.0, 615.0, 240.0], [0.0, 0.0, 1.0]])
    distortion = np.zeros((1, 5))
    rotation, _ = cv2.Rodrigues(np.asarray([0.22, -0.31, 0.13]))
    expected = make_transform(rotation, np.asarray([0.025, -0.018, 0.58]))
    face = cube.faces_by_name["+Z"]
    camera_marker = expected @ face.transform_cube_marker()
    rvec, _ = cv2.Rodrigues(camera_marker[:3, :3])
    corners, _ = cv2.projectPoints(cube.marker_corners(), rvec, camera_marker[:3, 3], camera, distortion)
    pose = CubePoseEstimator(cube).estimate([corners.reshape(4, 2)], [face.marker_id], camera, distortion)
    assert pose is not None
    assert np.allclose(pose.translation_camera_cube, expected[:3, 3], atol=1e-5)


def test_hardware_record_is_jsonl() -> None:
    rows = (ROOT / "data" / "deployment_run.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 310
