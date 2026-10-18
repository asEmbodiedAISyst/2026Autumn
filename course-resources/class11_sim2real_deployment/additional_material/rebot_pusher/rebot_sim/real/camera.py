"""Policy camera backends: the robot-mounted iPhone (asMagic color stream) or the simulated phone camera."""

from __future__ import annotations

import time

import numpy as np


def to_rgb(img: np.ndarray | None, size: tuple[int, int] = (480, 640)) -> np.ndarray | None:
    """asMagic color image -> (H, W, 3) uint8 at the dataset size."""
    if img is None:
        return None
    if img.shape[:2] != size:
        from PIL import Image

        img = np.asarray(Image.fromarray(img).resize((size[1], size[0])))
    return np.ascontiguousarray(img[..., :3], dtype=np.uint8)


class AsmagicCamera:
    """Color images of the iPhone on the robot tool (asMagic AR page). The pose in the stream is not used."""

    def __init__(self, ip: str, port: int = 8000, image_size: tuple[int, int] = (480, 640)) -> None:
        from ..teleop.phone import AsmagicFrameReader

        self.reader = AsmagicFrameReader(ip, port)
        self.image_size = image_size
        self.address = self.reader.address

    def wait(self, timeout: float = 5.0) -> bool:
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            f = self.reader.latest()
            if f is not None and f.image is not None:
                return True
            time.sleep(0.05)
        return False

    def read(self) -> tuple[np.ndarray | None, float]:
        """Latest image and its age (s); (None, inf) if the stream stalled."""
        f = self.reader.latest(max_age=0.5)
        if f is None or f.image is None:
            return None, float("inf")
        return to_rgb(f.image, self.image_size), time.monotonic() - f.recv_time

    @property
    def rate_hz(self) -> float:
        return self.reader.rate_hz

    def close(self) -> None:
        self.reader.close()


class NoCamera:
    """No policy camera (arm checks and teleoperation tests before the phone is mounted): every image is None."""

    address = "none"
    rate_hz = 0.0

    def wait(self, timeout: float = 5.0) -> bool:
        return True

    def read(self) -> tuple[np.ndarray | None, float]:
        return None, float("inf")

    def close(self) -> None:
        pass


class SimCamera:
    """The phone camera of a :class:`rebot_sim.real.arm.SimArm` (for testing without hardware)."""

    def __init__(self, sim_arm) -> None:
        self.sim = sim_arm.sim
        self.address = "sim"
        self.rate_hz = float(sim_arm.fps)

    def wait(self, timeout: float = 5.0) -> bool:
        return True

    def read(self) -> tuple[np.ndarray | None, float]:
        return self.sim.render("phone"), 0.0

    def close(self) -> None:
        pass
