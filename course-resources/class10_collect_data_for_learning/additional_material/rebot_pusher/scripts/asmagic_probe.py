"""Inspect the asMagic phone pose stream: connection, rate, pose format and axis directions.

Run this before using a phone for the first time; move the phone as prompted and check that the
coordinate mapping is as expected.

Example::

    uv run python scripts/asmagic_probe.py --phone-ip 192.168.1.100
    uv run python scripts/asmagic_probe.py --scan 10.42.0.0/24     # find the phone on the computer's hotspot
"""

from __future__ import annotations

import argparse
import ipaddress
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the package root
from rebot_sim.teleop.phone import ARKIT_TO_ROBOT, AsmagicPoseReader


def parse_intrinsics(k: np.ndarray) -> tuple[float, float, float, float] | None:
    """(fx, fy, cx, cy) from asMagic's camera_intrinsics (3x3 in either storage order, or 4 values)."""
    k = np.asarray(k, dtype=float).ravel()
    if k.size == 4:
        return tuple(k)
    if k.size != 9:
        return None
    K = k.reshape(3, 3)
    if abs(K[2, 0]) > abs(K[0, 2]):  # column-major (ARKit simd_float3x3): principal point in the last row
        K = K.T
    return K[0, 0], K[1, 1], K[0, 2], K[1, 2]


def scan(cidr: str, port: int, timeout: float = 0.3) -> list[str]:
    """Hosts in ``cidr`` with ``port`` open (the asMagic app listens on 8000): finds the phone on a hotspot."""
    def probe(ip: str) -> str | None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return ip if s.connect_ex((ip, port)) == 0 else None

    hosts = [str(h) for h in ipaddress.ip_network(cidr, strict=False).hosts()] or [cidr.split("/")[0]]
    with ThreadPoolExecutor(64) as pool:
        return [ip for ip in pool.map(probe, hosts) if ip]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phone-ip", default=None)
    ap.add_argument("--phone-port", type=int, default=8000)
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--scan", default=None, metavar="CIDR",
                    help="search this subnet for a phone that runs asMagic (e.g. the computer hotspot 10.42.0.0/24), then probe the first phone found")
    args = ap.parse_args()
    if args.scan:
        found = scan(args.scan, args.phone_port)
        print(f"devices in {args.scan} with port {args.phone_port} open: {found or 'none'}")
        if not found:
            return
        args.phone_ip = found[0]
    if not args.phone_ip:
        ap.error("give --phone-ip or --scan")

    from asmagic import ARDataSubscriber

    # First look at one raw frame
    sub = ARDataSubscriber(args.phone_ip, port=args.phone_port)
    frame = sub.get(timeout=3000)
    sub.close()
    if frame is None:
        print(f"no data within 3 s: check the phone IP ({args.phone_ip}), the network and that the app is on the AR page")
        return
    print(f"timestamp={frame.timestamp:.3f}")
    print(f"local_pose length={len(frame.local_pose)} values={np.round(frame.local_pose, 4)}")
    print(f"global_pose length={len(frame.global_pose)}")
    print(f"velocity={np.round(frame.velocity, 4)}  colour image={frame.has_color_image} depth image={frame.has_depth_image}")
    print(f"camera_intrinsics={np.round(frame.camera_intrinsics, 2)}")
    k = parse_intrinsics(frame.camera_intrinsics)
    if k is not None and k[1] > 0:
        fx, fy, cx, cy = k
        # 2*cy is the image height the intrinsics refer to, so this is independent of the stream resolution
        print(f"  fx={fx:.1f} fy={fy:.1f} cx={cx:.1f} cy={cy:.1f} -> vertical field of view fovy = {np.degrees(2 * np.arctan(cy / fy)):.1f} deg"
              " (phone in landscape; compare with fovy=54.4 of the camera in model/rebot_b601_rs_mjcf/tool_pusher.xml)")

    reader = AsmagicPoseReader(args.phone_ip, args.phone_port)
    print("\nMove the phone 10 cm forward, then 10 cm left, then 10 cm up: the robot-frame displacement must be +x, +y and +z")
    print("(this assumes that you face the direction of the back camera; the teleoperation aligns the heading when it engages)\n")
    time.sleep(0.5)
    p0 = None
    t_end = time.monotonic() + args.duration
    try:
        while time.monotonic() < t_end:
            p = reader.latest()
            if p is None:
                print("\rwaiting for data...".ljust(100), end="")
                time.sleep(0.1)
                continue
            if p0 is None:
                p0 = p
            d_ark = p.pos - p0.pos
            d_robot = ARKIT_TO_ROBOT @ d_ark
            rpy = Rotation.from_matrix(p.rot).as_euler("xyz", degrees=True)
            print(
                f"\rrate {reader.rate_hz:5.1f} Hz | ARKit displacement {np.round(d_ark, 3)} | robot-frame displacement {np.round(d_robot, 3)}"
                f" | rpy {np.round(rpy, 0)}".ljust(120),
                end="",
            )
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        reader.close()
        print()


if __name__ == "__main__":
    main()
