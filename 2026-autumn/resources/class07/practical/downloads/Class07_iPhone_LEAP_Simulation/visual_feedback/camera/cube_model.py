"""Cube geometry and rigid-transform utilities for the ArUco face tracker."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class Face:
    marker_id: int
    name: str
    rotation_cube_marker: np.ndarray
    translation_cube_marker: np.ndarray
    attachment: str

    @property
    def normal_cube(self) -> np.ndarray:
        return self.rotation_cube_marker[:, 2]

    @property
    def center_cube(self) -> np.ndarray:
        return self.translation_cube_marker

    def transform_cube_marker(self) -> np.ndarray:
        transform = np.eye(4, dtype=np.float64)
        transform[:3, :3] = self.rotation_cube_marker
        transform[:3, 3] = self.translation_cube_marker
        return transform


@dataclass(frozen=True)
class CubeModel:
    dictionary_name: str
    cube_size_m: float
    marker_size_m: float
    faces: tuple[Face, ...]

    @property
    def faces_by_id(self) -> dict[int, Face]:
        return {face.marker_id: face for face in self.faces}

    @property
    def faces_by_name(self) -> dict[str, Face]:
        return {face.name: face for face in self.faces}

    def marker_corners(self) -> np.ndarray:
        half = self.marker_size_m / 2.0
        return np.array(
            [
                [-half, half, 0.0],
                [half, half, 0.0],
                [half, -half, 0.0],
                [-half, -half, 0.0],
            ],
            dtype=np.float64,
        )

    def marker_corners_in_cube(self, face: Face) -> np.ndarray:
        corners = self.marker_corners()
        return (face.rotation_cube_marker @ corners.T).T + face.translation_cube_marker


def load_cube_model(path: str | Path) -> CubeModel:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    cube_size_m = float(data["cube_size_m"])
    marker_size_m = float(data["marker_size_m"])
    if cube_size_m <= 0 or marker_size_m <= 0:
        raise ValueError("cube_size_m and marker_size_m must be positive")
    if marker_size_m >= cube_size_m:
        raise ValueError("marker_size_m must be smaller than cube_size_m")

    faces: list[Face] = []
    ids: set[int] = set()
    names: set[str] = set()
    for entry in data["faces"]:
        marker_id = int(entry["id"])
        name = str(entry["name"])
        if marker_id in ids or name in names:
            raise ValueError(f"Duplicate face id/name: {marker_id}/{name}")
        marker_x = np.asarray(entry["marker_x_in_cube"], dtype=np.float64)
        marker_y = np.asarray(entry["marker_y_in_cube"], dtype=np.float64)
        marker_x /= np.linalg.norm(marker_x)
        marker_y /= np.linalg.norm(marker_y)
        if abs(float(np.dot(marker_x, marker_y))) > 1e-8:
            raise ValueError(f"Marker axes for face {name} are not perpendicular")
        normal = np.cross(marker_x, marker_y)
        normal /= np.linalg.norm(normal)
        rotation = np.column_stack((marker_x, marker_y, normal))
        if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-8):
            raise ValueError(f"Invalid marker rotation for face {name}")
        translation = normal * cube_size_m / 2.0
        faces.append(
            Face(
                marker_id=marker_id,
                name=name,
                rotation_cube_marker=rotation,
                translation_cube_marker=translation,
                attachment=str(entry.get("attachment", "")),
            )
        )
        ids.add(marker_id)
        names.add(name)

    return CubeModel(
        dictionary_name=str(data["dictionary"]),
        cube_size_m=cube_size_m,
        marker_size_m=marker_size_m,
        faces=tuple(faces),
    )


def dictionary_from_name(name: str):
    if not hasattr(cv2.aruco, name):
        raise ValueError(f"OpenCV has no ArUco dictionary named {name}")
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


def make_transform(rotation: np.ndarray, translation: np.ndarray) -> np.ndarray:
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = rotation
    transform[:3, 3] = np.asarray(translation, dtype=np.float64).reshape(3)
    return transform


def invert_transform(transform: np.ndarray) -> np.ndarray:
    rotation = transform[:3, :3]
    translation = transform[:3, 3]
    inverse = np.eye(4, dtype=np.float64)
    inverse[:3, :3] = rotation.T
    inverse[:3, 3] = -(rotation.T @ translation)
    return inverse


def rotation_to_quaternion_xyzw(rotation: np.ndarray) -> list[float]:
    # OpenCV Rodrigues -> quaternion via a numerically stable matrix conversion.
    trace = float(np.trace(rotation))
    if trace > 0:
        scale = 2.0 * np.sqrt(trace + 1.0)
        w = 0.25 * scale
        x = (rotation[2, 1] - rotation[1, 2]) / scale
        y = (rotation[0, 2] - rotation[2, 0]) / scale
        z = (rotation[1, 0] - rotation[0, 1]) / scale
    else:
        index = int(np.argmax(np.diag(rotation)))
        if index == 0:
            scale = 2.0 * np.sqrt(1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2])
            x = 0.25 * scale
            y = (rotation[0, 1] + rotation[1, 0]) / scale
            z = (rotation[0, 2] + rotation[2, 0]) / scale
            w = (rotation[2, 1] - rotation[1, 2]) / scale
        elif index == 1:
            scale = 2.0 * np.sqrt(1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2])
            x = (rotation[0, 1] + rotation[1, 0]) / scale
            y = 0.25 * scale
            z = (rotation[1, 2] + rotation[2, 1]) / scale
            w = (rotation[0, 2] - rotation[2, 0]) / scale
        else:
            scale = 2.0 * np.sqrt(1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1])
            x = (rotation[0, 2] + rotation[2, 0]) / scale
            y = (rotation[1, 2] + rotation[2, 1]) / scale
            z = 0.25 * scale
            w = (rotation[1, 0] - rotation[0, 1]) / scale
    quaternion = np.array([x, y, z, w], dtype=np.float64)
    quaternion /= np.linalg.norm(quaternion)
    return quaternion.tolist()
