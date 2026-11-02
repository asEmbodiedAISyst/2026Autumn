"""Tests for the standalone asMagic iPhone cube tracker."""

from __future__ import annotations

import unittest
from pathlib import Path

import cv2
import numpy as np

from aruco_pose import CubePose, CubePoseEstimator
from cube_model import load_cube_model, make_transform
from track_cube_faces_asmagic import (
    RangeStability,
    camera_matrix_from_asmagic,
    camera_to_cube_surface_distance,
    geometric_limits,
)


HERE = Path(__file__).resolve().parent


class AsMagicCubeTrackerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = load_cube_model(HERE / "cube_config.json")
        cls.estimator = CubePoseEstimator(cls.model)
        cls.intrinsics = np.array(
            [
                1390.592529296875,
                0.0,
                0.0,
                0.0,
                1390.592529296875,
                0.0,
                964.8057861328125,
                720.55712890625,
                1.0,
            ]
        )
        cls.camera_matrix = camera_matrix_from_asmagic(
            cls.intrinsics, 640, 480
        )
        cls.distortion = np.zeros((1, 5), dtype=np.float64)

    def test_column_major_intrinsics_scale_to_stream(self) -> None:
        self.assertEqual(self.model.dictionary_name, "DICT_4X4_50")
        self.assertEqual(sorted(self.model.faces_by_id), list(range(6)))
        self.assertAlmostEqual(self.model.marker_size_m, 0.01555)
        expected = np.array(
            [
                [463.5308430989583, 0.0, 321.6019287109375],
                [0.0, 463.5308430989583, 240.18570963541666],
                [0.0, 0.0, 1.0],
            ]
        )
        self.assertTrue(np.allclose(self.camera_matrix, expected))

    def test_portrait_stream_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "landscape"):
            camera_matrix_from_asmagic(self.intrinsics, 480, 640)

    def test_geometric_limits_match_captured_camera(self) -> None:
        limits = geometric_limits(
            self.camera_matrix,
            640,
            480,
            self.model.cube_size_m,
            self.model.marker_size_m,
        )
        self.assertAlmostEqual(limits["marker_only_plane_m"], 0.0150, delta=0.001)
        self.assertAlmostEqual(limits["frontal_cube_center_m"], 0.0851, delta=0.001)
        self.assertAlmostEqual(
            limits["any_orientation_cube_center_m"], 0.1093, delta=0.002
        )

    def test_oriented_cube_surface_distance(self) -> None:
        pose = CubePose(
            rotation_camera_cube=np.eye(3),
            translation_camera_cube=np.array([0.0, 0.0, 0.20]),
            reprojection_error_px=0.0,
            visible_faces=("+Z",),
            visible_ids=(0,),
        )
        distance = camera_to_cube_surface_distance(
            pose, self.model.cube_size_m
        )
        self.assertAlmostEqual(distance, 0.171, places=6)

    def test_stability_requires_stationary_timed_hold(self) -> None:
        stability = RangeStability(
            hold_seconds=1.0,
            required_fraction=0.8,
            min_samples=10,
            max_gap_s=0.2,
            max_mad_m=0.002,
            max_p95_p05_span_m=0.008,
        )
        result = None
        for index in range(11):
            distance = None if index in (2, 7) else 0.10
            result = stability.update(index * 0.1, distance)
            if index < 10:
                self.assertFalse(result.stable)

        assert result is not None
        self.assertTrue(result.stable)
        self.assertAlmostEqual(result.valid_fraction, 9 / 11)
        self.assertAlmostEqual(result.duration_s, 1.0)
        self.assertAlmostEqual(result.median_surface_m, 0.10)
        self.assertAlmostEqual(stability.closest_stable_surface_m, 0.10)

    def test_moving_range_is_not_called_stable(self) -> None:
        stability = RangeStability(
            hold_seconds=1.0,
            required_fraction=0.95,
            min_samples=10,
            max_gap_s=0.2,
            max_mad_m=0.002,
            max_p95_p05_span_m=0.008,
        )
        result = None
        for index, distance in enumerate(np.linspace(0.08, 0.12, 11)):
            result = stability.update(index * 0.1, float(distance))

        assert result is not None
        self.assertFalse(result.stable)
        self.assertIn("distance_mad", result.failure_reasons)
        self.assertIn("distance_span", result.failure_reasons)
        self.assertIsNone(stability.closest_stable_surface_m)

    def test_synthetic_marker_recovers_metric_cube_pose(self) -> None:
        face = self.model.faces_by_name["+Z"]
        expected = make_transform(np.eye(3), np.array([0.0, 0.0, 0.20]))
        transform_camera_marker = expected @ face.transform_cube_marker()
        rvec, _ = cv2.Rodrigues(transform_camera_marker[:3, :3])
        corners, _ = cv2.projectPoints(
            self.model.marker_corners(),
            rvec,
            transform_camera_marker[:3, 3],
            self.camera_matrix,
            self.distortion,
        )
        pose = self.estimator.estimate(
            [corners.reshape(4, 2)],
            [face.marker_id],
            self.camera_matrix,
            self.distortion,
        )
        self.assertIsNotNone(pose)
        assert pose is not None
        self.assertTrue(
            np.allclose(
                pose.translation_camera_cube,
                expected[:3, 3],
                atol=1e-5,
            )
        )


if __name__ == "__main__":
    unittest.main()
