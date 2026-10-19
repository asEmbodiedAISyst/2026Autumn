"""Fake asMagic phone: publishes poses with the same ZeroMQ + Protobuf protocol.

Used to develop and test the full chain (receiver thread -> mapping -> IK -> simulation) without a phone.

Command line::

    uv run python -m rebot_sim.teleop.fake_phone --pattern circle
    # in another terminal
    uv run python scripts/teleop.py --task push_cube --input asmagic --phone-ip 127.0.0.1
"""

from __future__ import annotations

import argparse
import math
import threading
import time

import numpy as np
import zmq


def tool_vertical_quat() -> np.ndarray:
    """ARKit orientation (xyzw) of the phone when it sits on the pusher tool with the rod vertical."""
    from ..robot import TCP_DOWN_ROT
    from ..sim import HandheldToolSim
    from .phone import ARKIT_TO_ROBOT, RigidPhoneMapper

    m = RigidPhoneMapper.from_model(HandheldToolSim("handheld_table", cameras=()).model)
    R = ARKIT_TO_ROBOT.T @ TCP_DOWN_ROT @ m.R_cam_tcp.T
    w = np.sqrt(max(1e-12, 1.0 + np.trace(R))) / 2.0
    return np.array([(R[2, 1] - R[1, 2]) / (4 * w), (R[0, 2] - R[2, 0]) / (4 * w), (R[1, 0] - R[0, 1]) / (4 * w), w])


def pattern_pose(pattern: str, t: float, radius: float = 0.08, period: float = 6.0) -> tuple[np.ndarray, np.ndarray]:
    """Phone pose (position, xyzw quaternion) in the ARKit frame. Phone held upright, back camera facing -z."""
    w = 2 * math.pi * t / period
    if pattern == "circle":  # circle in the horizontal plane (ARKit x-z plane)
        pos = np.array([radius * math.sin(w), 0.0, -radius * (1 - math.cos(w))])
    elif pattern == "line":  # back and forth
        pos = np.array([0.0, 0.0, -radius * (1 - math.cos(w))])
    elif pattern == "still":
        pos = np.zeros(3)
    else:
        raise ValueError(pattern)
    quat = np.array([0.0, 0.0, 0.0, 1.0])  # identity quaternion, xyzw
    return pos, quat


class FakePhonePublisher:
    """Publish Phone messages at ``rate`` Hz from a background thread."""

    def __init__(self, port: int = 8000, pattern: str = "circle", rate: float = 60.0, bind: str = "127.0.0.1",
                 quat: np.ndarray | None = None, image: bool = False) -> None:
        from asmagic.proto import phone_msg_pb2

        self._pb = phone_msg_pb2
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUB)
        self._sock.bind(f"tcp://{bind}:{port}")
        self.pattern = pattern
        self.rate = rate
        self.quat = None if quat is None else np.asarray(quat, dtype=float)  # fixed orientation override (xyzw)
        self.image = image  # also send a synthetic 640x480 JPEG color image (like the AR stream)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._t0 = time.monotonic()
        self._thread.start()

    def _run(self) -> None:
        try:
            self._loop()
        finally:
            self._sock.close(linger=0)  # close the ZeroMQ socket only in its owner thread

    def _loop(self) -> None:
        while not self._stop.is_set():
            t = time.monotonic() - self._t0
            pos, quat = pattern_pose(self.pattern, t)
            if self.quat is not None:
                quat = self.quat
            msg = self._pb.Phone()
            msg.timestamp = time.time()
            msg.local_pose.extend([*pos, *quat])
            msg.global_pose.extend([*pos, *quat])
            msg.velocity.extend([0.0, 0.0, 0.0])
            if self.image:
                msg.color_img = self._jpeg(t)
            self._sock.send(msg.SerializeToString())
            time.sleep(1.0 / self.rate)

    @staticmethod
    def _jpeg(t: float) -> bytes:
        import io

        from PIL import Image

        img = np.zeros((480, 640, 3), np.uint8)
        img[..., 0] = np.linspace(40, 200, 640, dtype=np.uint8)[None, :]
        img[..., 1] = 120
        x = int(320 + 200 * math.sin(t))  # a moving red square
        img[200:280, max(0, x - 40):x + 40] = (220, 30, 30)
        buf = io.BytesIO()
        Image.fromarray(img).save(buf, format="JPEG", quality=80)
        return buf.getvalue()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fake asMagic phone: publishes poses with the asMagic protocol")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--pattern", choices=["circle", "line", "still"], default="circle")
    ap.add_argument("--rate", type=float, default=60.0)
    ap.add_argument("--image", action="store_true", help="also send a synthetic 640x480 colour image (to test the recording scripts)")
    ap.add_argument("--hold", choices=["upright", "tool"], default="upright",
                    help="upright: the phone is held upright; tool: the phone sits on the vertical pusher tool")
    args = ap.parse_args()
    quat = tool_vertical_quat() if args.hold == "tool" else None
    pub = FakePhonePublisher(args.port, args.pattern, args.rate, args.bind, quat=quat, image=args.image)
    print(f"publishing fake poses ({args.pattern}) on tcp://{args.bind}:{args.port}; Ctrl+C stops")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        pub.close()


if __name__ == "__main__":
    main()
