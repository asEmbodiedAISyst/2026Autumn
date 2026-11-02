"""Offline tests for marker detection, cube geometry, and pose fusion."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import cv2
import numpy as np
import trimesh

from aruco_pose import CubePoseEstimator, classify_faces
from cube_model import load_cube_model, make_transform


HERE = Path(__file__).resolve().parent


class ArucoCubeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = load_cube_model(HERE / "cube_config.json")
        cls.estimator = CubePoseEstimator(cls.model)
        cls.camera_matrix = np.array(
            [[615.0, 0.0, 320.0], [0.0, 615.0, 240.0], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
        cls.distortion = np.zeros((1, 5), dtype=np.float64)

    def project_face(
        self,
        face_name: str,
        transform_camera_cube: np.ndarray,
    ) -> tuple[np.ndarray, int]:
        face = self.model.faces_by_name[face_name]
        transform_camera_marker = transform_camera_cube @ face.transform_cube_marker()
        rvec, _ = cv2.Rodrigues(transform_camera_marker[:3, :3])
        corners, _ = cv2.projectPoints(
            self.model.marker_corners(),
            rvec,
            transform_camera_marker[:3, 3],
            self.camera_matrix,
            self.distortion,
        )
        return corners.reshape(4, 2), face.marker_id

    def test_six_right_handed_faces(self) -> None:
        self.assertEqual({face.name for face in self.model.faces}, {"+X", "-X", "+Y", "-Y", "+Z", "-Z"})
        normals = set()
        for face in self.model.faces:
            self.assertAlmostEqual(np.linalg.det(face.rotation_cube_marker), 1.0, places=8)
            self.assertTrue(np.allclose(face.rotation_cube_marker.T @ face.rotation_cube_marker, np.eye(3)))
            self.assertAlmostEqual(np.linalg.norm(face.center_cube), self.model.cube_size_m / 2.0)
            self.assertGreater(np.dot(face.center_cube, face.normal_cube), 0.0)
            normals.add(tuple(np.rint(face.normal_cube).astype(int)))
        self.assertEqual(len(normals), 6)

    def test_all_generated_ids_detect(self) -> None:
        dictionary_id = getattr(cv2.aruco, self.model.dictionary_name)
        dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)
        canvas = np.full((620, 620, 3), 255, dtype=np.uint8)
        for index, face in enumerate(self.model.faces):
            marker = cv2.aruco.generateImageMarker(dictionary, face.marker_id, 140, borderBits=1)
            row, column = divmod(index, 3)
            y, x = 50 + row * 280, 40 + column * 200
            canvas[y : y + 140, x : x + 140] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        _, ids, _ = self.estimator.detect(canvas)
        self.assertEqual(set(ids), {face.marker_id for face in self.model.faces})

    def test_ids_detect_at_expected_1280x720_pixel_size(self) -> None:
        dictionary_id = getattr(cv2.aruco, self.model.dictionary_name)
        dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)
        for face in self.model.faces:
            canvas = np.full((120, 120, 3), 255, dtype=np.uint8)
            marker = cv2.aruco.generateImageMarker(
                dictionary, face.marker_id, 38, borderBits=1
            )
            canvas[41:79, 41:79] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
            canvas = cv2.GaussianBlur(canvas, (3, 3), 0.55)
            _, ids, _ = self.estimator.detect(canvas)
            self.assertIn(face.marker_id, ids)

    def test_single_marker_recovers_cube_pose(self) -> None:
        rotation, _ = cv2.Rodrigues(np.array([0.22, -0.31, 0.13], dtype=np.float64))
        expected = make_transform(rotation, np.array([0.025, -0.018, 0.58]))
        corners, marker_id = self.project_face("+Z", expected)
        pose = self.estimator.estimate(
            [corners], [marker_id], self.camera_matrix, self.distortion
        )
        self.assertIsNotNone(pose)
        assert pose is not None
        self.assertTrue(np.allclose(pose.translation_camera_cube, expected[:3, 3], atol=1e-5))
        self.assertTrue(np.allclose(pose.rotation_camera_cube, expected[:3, :3], atol=1e-5))

    def test_multiple_faces_refine_one_cube_pose(self) -> None:
        rotation, _ = cv2.Rodrigues(np.array([0.28, 0.37, -0.19], dtype=np.float64))
        expected = make_transform(rotation, np.array([-0.04, 0.015, 0.62]))
        projected = [self.project_face(name, expected) for name in ("+Z", "+X", "+Y")]
        pose = self.estimator.estimate(
            [item[0] for item in projected],
            [item[1] for item in projected],
            self.camera_matrix,
            self.distortion,
        )
        self.assertIsNotNone(pose)
        assert pose is not None
        self.assertLess(pose.reprojection_error_px, 1e-5)
        self.assertTrue(np.allclose(pose.translation_camera_cube, expected[:3, 3], atol=1e-5))
        self.assertTrue(np.allclose(pose.rotation_camera_cube, expected[:3, :3], atol=1e-5))

    def test_face_classification(self) -> None:
        marker_id = self.model.faces_by_name["+Z"].marker_id
        from aruco_pose import CubePose

        pose = CubePose(np.eye(3), np.array([0.0, 0.0, 0.5]), 0.0, ("+Z",), (marker_id,))
        states, up_face, camera_facing = classify_faces(
            self.model, pose, np.array([0.0, 0.0, 1.0])
        )
        self.assertEqual(up_face, "+Z")
        self.assertEqual(camera_facing, "-Z")
        self.assertTrue(states["+Z"]["visible"])
        self.assertFalse(states["-Z"]["visible"])

    def test_exported_stls_are_watertight_and_exact_size(self) -> None:
        manifest = json.loads((HERE / "stl" / "manifest.json").read_text())
        body = trimesh.load_mesh(
            HERE / "stl" / manifest["files"]["dual_material_white"]
        )
        inlays = trimesh.load_mesh(
            HERE / "stl" / manifest["files"]["dual_material_black"]
        )
        self.assertTrue(body.is_watertight)
        self.assertTrue(inlays.is_watertight)
        self.assertTrue(np.allclose(body.extents, [62.0, 62.0, 62.0]))
        self.assertTrue(np.allclose(inlays.bounds, body.bounds))
        self.assertAlmostEqual(body.volume + inlays.volume, 62.0**3, places=4)


if __name__ == "__main__":
    unittest.main()
