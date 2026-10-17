"""Fake asMagic phone: publishes phone poses with the same protocol as the asMagic app (Class 09).

Use it to try ``teleop_rebot_rs_sim.py`` without an iPhone, or to test the network path with a known motion. It
publishes ``Phone`` Protobuf messages over ZeroMQ PUB on ``tcp://<bind>:<port>``, 60 times per second.

    uv run python code/fake_phone.py                     # terminal 1: circle, radius 8 cm, period 6 s
    uv run python code/fake_phone.py --pattern line      # back and forth along the camera direction
    uv run python code/fake_phone.py --pattern tilt      # still, rotating about the top axis by +-20 degrees
    uv run python code/fake_phone.py --pattern still     # no motion (tests the hold behaviour)
    uv run python code/teleop_rebot_rs_sim.py --phone-ip 127.0.0.1   # terminal 2

The pose is given in the iPhone frame of the asMagic app (``teleop_common.EE_TF_IPHONE``: x along the long side
towards the top, y towards the left edge, z out of the screen; the camera looks along -z). The circle
lies in the plane of the right and the top direction, so the gripper draws a circle in the plane of its side and
finger directions (horizontal when the gripper points down). ``local_pose`` = [tx, ty, tz, qx, qy, qz, qw] in metres, quaternion in x-y-z-w order;
``--matrix`` sends the pose as a 4x4 matrix (16 values, row-major) instead.
"""

from __future__ import annotations

import argparse
import math
import time

import numpy as np
import zmq
from asmagic.proto import phone_msg_pb2

from teleop_common import EE_TF_IPHONE, rotvec_to_matrix


def pattern_pose(pattern: str, t: float, ee_tf_iphone: np.ndarray, radius: float = 0.08, period: float = 6.0):
    """Phone position (m) and rotation matrix at time ``t`` in the iPhone frame. The phone directions come from
    ee_tf_iphone: right = the phone axis that maps to ee -x, top = to ee y, camera = to ee z."""
    right, top, camera = -ee_tf_iphone.T[0], ee_tf_iphone.T[1], ee_tf_iphone.T[2]
    w = 2 * math.pi * t / period
    pos, rot = np.zeros(3), np.eye(3)
    if pattern == "circle":  # in the plane of the right and the top direction
        pos = radius * math.sin(w) * right + radius * (1 - math.cos(w)) * top
    elif pattern == "line":  # back and forth along the camera direction
        pos = radius * (1 - math.cos(w)) * camera
    elif pattern == "tilt":  # rotation about the top axis, +-20 degrees
        rot = rotvec_to_matrix(math.radians(20.0) * math.sin(w) * top)
    return pos, rot


def matrix_to_quat_xyzw(R: np.ndarray) -> list[float]:
    w = math.sqrt(max(0.0, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
    x = math.copysign(math.sqrt(max(0.0, 1 + R[0, 0] - R[1, 1] - R[2, 2])) / 2, R[2, 1] - R[1, 2])
    y = math.copysign(math.sqrt(max(0.0, 1 - R[0, 0] + R[1, 1] - R[2, 2])) / 2, R[0, 2] - R[2, 0])
    z = math.copysign(math.sqrt(max(0.0, 1 - R[0, 0] - R[1, 1] + R[2, 2])) / 2, R[1, 0] - R[0, 1])
    return [x, y, z, w]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pattern", choices=["circle", "line", "tilt", "still"], default="circle")
    ap.add_argument("--matrix", action="store_true", help="send the pose as a 4x4 matrix (16 values) instead of 7")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--bind", default="127.0.0.1", help="interface to publish on (0.0.0.0 for other computers)")
    ap.add_argument("--rate", type=float, default=60.0, help="messages per second")
    args = ap.parse_args()

    sock = zmq.Context.instance().socket(zmq.PUB)
    sock.bind(f"tcp://{args.bind}:{args.port}")
    print(f"publishing '{args.pattern}' poses on tcp://{args.bind}:{args.port} at {args.rate:.0f} Hz; Ctrl+C stops")
    t0 = time.monotonic()
    try:
        while True:
            t = time.monotonic() - t0
            pos, rot = pattern_pose(args.pattern, t, EE_TF_IPHONE)
            msg = phone_msg_pb2.Phone()
            msg.timestamp = time.time()
            if args.matrix:
                T = np.eye(4)
                T[:3, :3], T[:3, 3] = rot, pos
                msg.local_pose.extend(T.flatten().tolist())
            else:
                msg.local_pose.extend([*pos.tolist(), *matrix_to_quat_xyzw(rot)])
            msg.global_pose.extend(msg.local_pose)
            msg.velocity.extend([0.0, 0.0, 0.0])
            sock.send(msg.SerializeToString())
            time.sleep(1.0 / args.rate)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close(linger=0)


if __name__ == "__main__":
    main()
