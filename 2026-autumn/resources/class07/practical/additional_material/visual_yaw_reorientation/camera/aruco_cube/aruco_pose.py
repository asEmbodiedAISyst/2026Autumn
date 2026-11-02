"""ArUco detection and multi-face cube pose estimation."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from cube_model import CubeModel, Face, invert_transform, make_transform


@dataclass(frozen=True)
class MarkerObservation:
    marker_id: int
    corners: np.ndarray
    face: Face
    reprojection_error_px: float
    transform_camera_cube: np.ndarray


@dataclass(frozen=True)
class CubePose:
    rotation_camera_cube: np.ndarray
    translation_camera_cube: np.ndarray
    reprojection_error_px: float
    visible_faces: tuple[str, ...]
    visible_ids: tuple[int, ...]

    def transform_camera_cube(self) -> np.ndarray:
        return make_transform(self.rotation_camera_cube, self.translation_camera_cube)


def rotation_project(matrix: np.ndarray) -> np.ndarray:
    u, _, vh = np.linalg.svd(matrix)
    rotation = u @ vh
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vh
    return rotation


def quaternion_wxyz_from_rotation(R: np.ndarray) -> np.ndarray:
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
    q = np.array([w, x, y, z], dtype=np.float64)
    norm = np.linalg.norm(q)
    return q / (norm + 1e-12)


def rotation_from_quaternion_wxyz(q: np.ndarray) -> np.ndarray:
    w, x, y, z = q
    return np.array([
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
        [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
        [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
    ], dtype=np.float64)


def quat_slerp(q0: np.ndarray, q1: np.ndarray, fraction: float) -> np.ndarray:
    dot = float(np.dot(q0, q1))
    if dot < 0.0:
        q1 = -q1
        dot = -dot
    if dot > 0.9995:
        result = q0 + fraction * (q1 - q0)
        return result / (np.linalg.norm(result) + 1e-12)
    theta_0 = np.arccos(np.clip(dot, -1.0, 1.0))
    sin_theta_0 = np.sin(theta_0)
    theta = theta_0 * fraction
    sin_theta = np.sin(theta)
    s0 = np.cos(theta) - dot * sin_theta / sin_theta_0
    s1 = sin_theta / sin_theta_0
    result = (s0 * q0) + (s1 * q1)
    return result / (np.linalg.norm(result) + 1e-12)


class CubePoseEstimator:
    def __init__(self, model: CubeModel, detection_scale: float = 1.0, smooth_pose: bool = True):
        self.model = model
        self.detection_scale = float(max(0.5, detection_scale))
        self.smooth_pose = smooth_pose
        self.last_rotation_camera_marker: dict[int, np.ndarray] = {}
        self.last_pose_t: np.ndarray | None = None
        self.last_pose_q: np.ndarray | None = None

        dictionary_id = getattr(cv2.aruco, model.dictionary_name)
        dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)
        parameters = cv2.aruco.DetectorParameters()
        parameters.adaptiveThreshWinSizeMin = 3
        parameters.adaptiveThreshWinSizeMax = 35
        parameters.adaptiveThreshWinSizeStep = 4
        parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        parameters.cornerRefinementWinSize = 3
        parameters.cornerRefinementMaxIterations = 40
        parameters.cornerRefinementMinAccuracy = 0.01
        parameters.minMarkerPerimeterRate = 0.015
        self.detector = cv2.aruco.ArucoDetector(dictionary, parameters)

    def reset_tracking(self) -> None:
        """Reset temporal state when tracking is re-initialized."""
        self.last_rotation_camera_marker.clear()
        self.last_pose_t = None
        self.last_pose_q = None

    def detect(
        self,
        image: np.ndarray,
        roi: tuple[int, int, int, int] | None = None,
    ) -> tuple[list[np.ndarray], list[int], list[np.ndarray]]:
        height, width = image.shape[:2]
        offset = np.zeros(2, dtype=np.float32)
        search_image = image
        if roi:
            x, y, roi_width, roi_height = roi
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(width, x + roi_width), min(height, y + roi_height)
            if x1 <= x0 or y1 <= y0:
                return [], [], []
            search_image = image[y0:y1, x0:x1]
            offset[:] = (x0, y0)

        gray = cv2.cvtColor(search_image, cv2.COLOR_BGR2GRAY)
        scale = self.detection_scale
        if scale != 1.0:
            gray_proc = cv2.resize(gray, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
        else:
            gray_proc = gray
        corners, ids, rejected = self.detector.detectMarkers(gray_proc)
        detected = [np.asarray(corner, dtype=np.float64).reshape(4, 2) / scale + offset for corner in corners]
        rejected_full = [np.asarray(corner, dtype=np.float64).reshape(4, 2) / scale + offset for corner in rejected]
        id_list = [] if ids is None else [int(value) for value in ids.reshape(-1)]
        return detected, id_list, rejected_full

    @staticmethod
    def _reprojection_error(
        object_points: np.ndarray,
        image_points: np.ndarray,
        rotation: np.ndarray,
        translation: np.ndarray,
        camera_matrix: np.ndarray,
        distortion: np.ndarray,
    ) -> float:
        rvec, _ = cv2.Rodrigues(rotation)
        projected, _ = cv2.projectPoints(
            object_points,
            rvec,
            translation.reshape(3, 1),
            camera_matrix,
            distortion,
        )
        residual = projected.reshape(-1, 2) - image_points.reshape(-1, 2)
        return float(np.sqrt(np.mean(np.sum(residual * residual, axis=1))))

    def _single_marker_observation(
        self,
        marker_id: int,
        corners: np.ndarray,
        camera_matrix: np.ndarray,
        distortion: np.ndarray,
    ) -> MarkerObservation | None:
        face = self.model.faces_by_id.get(marker_id)
        if face is None:
            return None
        marker_points = self.model.marker_corners()

        # solvePnPGeneric with SOLVEPNP_IPPE_SQUARE gives both planar solutions and their errors
        num_sol, rvecs, tvecs, errors = cv2.solvePnPGeneric(
            marker_points,
            corners,
            camera_matrix,
            distortion,
            flags=cv2.SOLVEPNP_IPPE_SQUARE,
        )
        if num_sol == 0 or rvecs is None or len(rvecs) == 0:
            return None

        # Disambiguate between the two IPPE solutions using temporal continuity
        best_idx = 0
        if num_sol > 1 and marker_id in self.last_rotation_camera_marker:
            prev_R = self.last_rotation_camera_marker[marker_id]
            err0 = float(errors[0][0])
            err1 = float(errors[1][0])
            # Only consider continuity if both solutions have close reprojection errors (<0.6px)
            if abs(err0 - err1) < 0.6:
                R0, _ = cv2.Rodrigues(rvecs[0])
                R1, _ = cv2.Rodrigues(rvecs[1])
                diff0 = float(np.arccos(np.clip((np.trace(R0.T @ prev_R) - 1.0) / 2.0, -1.0, 1.0)))
                diff1 = float(np.arccos(np.clip((np.trace(R1.T @ prev_R) - 1.0) / 2.0, -1.0, 1.0)))
                if diff1 < diff0:
                    best_idx = 1
            else:
                best_idx = 0 if err0 <= err1 else 1
        elif num_sol > 1:
            err0 = float(errors[0][0])
            err1 = float(errors[1][0])
            best_idx = 0 if err0 <= err1 else 1

        rvec = rvecs[best_idx]
        tvec = tvecs[best_idx]
        rotation_camera_marker, _ = cv2.Rodrigues(rvec)
        self.last_rotation_camera_marker[marker_id] = rotation_camera_marker

        transform_camera_marker = make_transform(rotation_camera_marker, tvec)
        transform_camera_cube = transform_camera_marker @ invert_transform(face.transform_cube_marker())
        error = (
            float(errors[best_idx][0])
            if (errors is not None and len(errors) > best_idx)
            else self._reprojection_error(
                marker_points,
                corners,
                rotation_camera_marker,
                np.asarray(tvec).reshape(3),
                camera_matrix,
                distortion,
            )
        )
        return MarkerObservation(marker_id, corners, face, error, transform_camera_cube)

    def estimate(
        self,
        corners: list[np.ndarray],
        ids: list[int],
        camera_matrix: np.ndarray,
        distortion: np.ndarray,
    ) -> CubePose | None:
        observations = [
            observation
            for marker_id, marker_corners in zip(ids, corners)
            if (
                observation := self._single_marker_observation(
                    marker_id, marker_corners, camera_matrix, distortion
                )
            )
            is not None
        ]
        if not observations:
            return None

        seed = min(observations, key=lambda item: item.reprojection_error_px)
        rotation = seed.transform_camera_cube[:3, :3]
        translation = seed.transform_camera_cube[:3, 3]

        object_points = np.concatenate(
            [self.model.marker_corners_in_cube(item.face) for item in observations], axis=0
        ).astype(np.float64)
        image_points = np.concatenate([item.corners for item in observations], axis=0).astype(np.float64)

        if len(observations) > 1:
            rvec, _ = cv2.Rodrigues(rotation)
            tvec = translation.reshape(3, 1).copy()
            success, rvec, tvec = cv2.solvePnP(
                object_points,
                image_points,
                camera_matrix,
                distortion,
                rvec,
                tvec,
                useExtrinsicGuess=True,
                flags=cv2.SOLVEPNP_ITERATIVE,
            )
            if success:
                rvec, tvec = cv2.solvePnPRefineLM(
                    object_points,
                    image_points,
                    camera_matrix,
                    distortion,
                    rvec,
                    tvec,
                )
                rotation, _ = cv2.Rodrigues(rvec)
                translation = np.asarray(tvec).reshape(3)

        error = self._reprojection_error(
            object_points,
            image_points,
            rotation,
            translation,
            camera_matrix,
            distortion,
        )
        ordered = sorted(observations, key=lambda item: item.marker_id)
        R_cube = rotation_project(rotation)
        t_cube = translation.copy()

        if self.smooth_pose:
            q_curr = quaternion_wxyz_from_rotation(R_cube)
            if self.last_pose_q is not None and self.last_pose_t is not None:
                t_cube = 0.7 * t_cube + 0.3 * self.last_pose_t
                q_curr = quat_slerp(self.last_pose_q, q_curr, 0.7)
                R_cube = rotation_from_quaternion_wxyz(q_curr)
            self.last_pose_t = t_cube.copy()
            self.last_pose_q = q_curr.copy()

        return CubePose(
            rotation_camera_cube=R_cube,
            translation_camera_cube=t_cube,
            reprojection_error_px=error,
            visible_faces=tuple(item.face.name for item in ordered),
            visible_ids=tuple(item.marker_id for item in ordered),
        )


def classify_faces(
    model: CubeModel,
    pose: CubePose,
    up_camera: np.ndarray | None,
) -> tuple[dict[str, dict[str, object]], str | None, str]:
    rotation = pose.rotation_camera_cube
    translation = pose.translation_camera_cube
    camera_direction = -translation / np.linalg.norm(translation)
    visible = set(pose.visible_faces)
    states: dict[str, dict[str, object]] = {}
    for face in model.faces:
        normal_camera = rotation @ face.normal_cube
        center_camera = rotation @ face.center_cube + translation
        states[face.name] = {
            "marker_id": face.marker_id,
            "visible": face.name in visible,
            "center_camera_m": center_camera.tolist(),
            "normal_camera": normal_camera.tolist(),
            "up_alignment": None if up_camera is None else float(np.dot(normal_camera, up_camera)),
            "camera_facing_score": float(np.dot(normal_camera, camera_direction)),
        }
    camera_facing_face = max(states, key=lambda name: float(states[name]["camera_facing_score"]))
    up_face = None
    if up_camera is not None:
        up_face = max(states, key=lambda name: float(states[name]["up_alignment"]))
    return states, up_face, camera_facing_face
