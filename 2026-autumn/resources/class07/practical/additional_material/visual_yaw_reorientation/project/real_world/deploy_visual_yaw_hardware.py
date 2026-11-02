#!/usr/bin/env python3
"""Unified Real-World LEAP Hand RL Cube Reorientation Deployment Script.

Integrates:
1. iPhone RGB stream via asMagic ARDataSubscriber (default 10.127.51.69:8000).
2. ArUco 6-face cube tracker with subpixel refinement and single-face support.
3. Extrinsic transformation from iPhone optical camera frame to LEAP palm frame.
4. RSL-RL trained policy inference on CPU (57-dim observation -> 16 delta actions).
5. Physical LEAP Hand control over Dynamixel serial bus (/dev/ttyUSB0, 4 MBaud)
   with soft limits, current guards, velocity guards, and stale-pose hold.

Usage:
  # 1. Safe Shadow Mode (no motor torque, verifies camera + policy + encoders):
  python deploy_reorient_hardware.py --iphone-ip 10.127.51.69 --shadow

  # 2. Hardware Deployment Mode (enables motor torque with safety guards):
  python deploy_reorient_hardware.py --iphone-ip 10.127.51.69 --torque
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
from pathlib import Path
import queue
import sys
import threading
import time
from typing import Any, Sequence

import cv2
import numpy as np
import torch

_BUNDLE_DIR = Path(__file__).resolve().parents[2]
_PROJECT_DIR = _BUNDLE_DIR / "project"
_CAMERA_DIR = _BUNDLE_DIR / "camera" / "aruco_cube"

if str(_PROJECT_DIR) not in sys.path:
  sys.path.insert(0, str(_PROJECT_DIR))
if str(_CAMERA_DIR) not in sys.path:
  sys.path.insert(0, str(_CAMERA_DIR))

# Import camera and model components
from aruco_pose import CubePose, CubePoseEstimator
from cube_model import CubeModel, load_cube_model, rotation_to_quaternion_xyzw
from track_cube_faces_asmagic import camera_matrix_from_asmagic
from real_world.bridge_aruco_pose import (
  load_camera_to_palm,
  quaternion_wxyz_from_rotation_matrix,
  rotation_matrix_from_quaternion_wxyz,
)
from real_world.visualizer import draw_annotated_frame, WebVisualizerServer

# Dynamixel SDK
try:
  from dynamixel_sdk import (
    COMM_SUCCESS,
    GroupSyncRead,
    GroupSyncWrite,
    PacketHandler,
    PortHandler,
  )
  HAS_DYNAMIXEL = True
except ImportError:
  HAS_DYNAMIXEL = False

# asmagic
try:
  from asmagic import ARDataSubscriber
  HAS_ASMAGIC = True
except ImportError:
  HAS_ASMAGIC = False

_NUM_JOINTS = 16
_MOTOR_IDS = tuple(range(_NUM_JOINTS))
_PROTOCOL_VERSION = 2.0
_POS_SCALE = 2.0 * np.pi / 4096.0
_VEL_SCALE = 0.229 * 2.0 * np.pi / 60.0

_ADDR_OPERATING_MODE = 11
_ADDR_TORQUE_ENABLE = 64
_ADDR_D_GAIN = 80
_ADDR_I_GAIN = 82
_ADDR_P_GAIN = 84
_ADDR_CURRENT_LIMIT = 102
_ADDR_PROFILE_ACCELERATION = 108
_ADDR_PROFILE_VELOCITY = 112
_ADDR_GOAL_POSITION = 116
_ADDR_PRESENT_CURRENT = 126
_ADDR_PRESENT_VELOCITY = 128
_ADDR_PRESENT_POSITION = 132
_ADDR_PRESENT_TEMPERATURE = 146

# Order mapping:
# Hardware: [if_rot, if_mcp, if_pip, if_dip, mf_rot, mf_mcp, mf_pip, mf_dip, rf_rot, rf_mcp, rf_pip, rf_dip, th_cmc, th_axl, th_mcp, th_ipl]
# Server:   [if_mcp, if_rot, if_pip, if_dip, mf_mcp, mf_rot, mf_pip, mf_dip, rf_mcp, rf_rot, rf_pip, rf_dip, th_cmc, th_axl, th_mcp, th_ipl]
_HW_TO_SERVER = np.array(
  [1, 0, 2, 3, 5, 4, 6, 7, 9, 8, 10, 11, 12, 13, 14, 15],
  dtype=np.int64,
)
_SERVER_TO_HW = np.argsort(_HW_TO_SERVER).astype(np.int64)

# Physical startup grasp pose (Server order) and checkpoint-compatible origin
# for the policy joint observation.
_GRASP_Q_SERVER = np.array(
  [0.1, -0.4, 1.3, 0.0, 0.1, 0.0, 1.3, 0.0, 0.1, 0.4, 1.3, 0.0, 1.45, 1.5, 0.579, 1.37],
  dtype=np.float32,
)
_GRASP_Q_HW = _GRASP_Q_SERVER[_SERVER_TO_HW]

# HOME_KEYFRAME from leap_right_constants.py. Training's joint_pos_rel term
# subtracts this pose even when an episode starts from a cached grasp.
_TRAINING_DEFAULT_Q_SERVER = np.array(
  [0.3, 0.0, 0.3, 0.2, 0.3, 0.0, 0.3, 0.2, 0.3, 0.0, 0.3, 0.2, 0.4, 0.2, 0.3, 0.2],
  dtype=np.float32,
)

# This checkpoint's learned normalizer is centered around its reset grasp,
# despite the nominal HOME_KEYFRAME in the environment configuration.
_POLICY_Q_REFERENCE_SERVER = _GRASP_Q_SERVER.copy()

# Physical right-hand limits from leap_right_hardware_constants.py.
_HARD_LIMIT_LO_SERVER = np.array(
  [-0.261799, -0.523599, -0.261799, -0.261799] * 3
  + [0.0, 0.0, -0.349066, -0.349066],
  dtype=np.float32,
)
_HARD_LIMIT_HI_SERVER = np.array(
  [1.91986, 0.523599, 1.91986, 1.91986] * 3
  + [1.571, 1.571, 1.74533, 1.74533],
  dtype=np.float32,
)

# Match the 0.95 training soft-limit factor, while retaining a 0.01 rad
# physical margin. The intersection is both policy-compatible and safe.
_LIMIT_MID_SERVER = 0.5 * (_HARD_LIMIT_LO_SERVER + _HARD_LIMIT_HI_SERVER)
_LIMIT_HALF_SERVER = 0.5 * (_HARD_LIMIT_HI_SERVER - _HARD_LIMIT_LO_SERVER)
_SOFT_LIMIT_LO_SERVER = np.maximum(
  _LIMIT_MID_SERVER - 0.95 * _LIMIT_HALF_SERVER,
  _HARD_LIMIT_LO_SERVER + 0.01,
)
_SOFT_LIMIT_HI_SERVER = np.minimum(
  _LIMIT_MID_SERVER + 0.95 * _LIMIT_HALF_SERVER,
  _HARD_LIMIT_HI_SERVER - 0.01,
)

# Physical hardware limits (HW order)
_HW_LIMIT_LO = _SOFT_LIMIT_LO_SERVER[_SERVER_TO_HW]
_HW_LIMIT_HI = _SOFT_LIMIT_HI_SERVER[_SERVER_TO_HW]

_ACTION_DELTA_SCALE = 0.041666666666666664  # radians per action step

# Nominal in-hand centroid position error matching Visual Yaw training distribution mean
_NOMINAL_CUBE_POS_ERR = np.array([-0.0327, -0.0128, 0.0549], dtype=np.float32)


def _signed(value: int, size: int) -> int:
  sign_bit = 1 << (8 * size - 1)
  return value - (1 << (8 * size)) if value & sign_bit else value


class DynamixelBus:
  def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 4_000_000):
    if not HAS_DYNAMIXEL:
      raise RuntimeError("dynamixel_sdk is not installed.")
    self.port = PortHandler(port)
    self.packet = PacketHandler(_PROTOCOL_VERSION)
    self.baudrate = int(baudrate)
    self.connected = False
    self.torque_enabled = False

    self.state_reader = GroupSyncRead(
      self.port, self.packet, _ADDR_PRESENT_CURRENT, 10
    )
    self.temperature_reader = GroupSyncRead(
      self.port, self.packet, _ADDR_PRESENT_TEMPERATURE, 1
    )
    for motor_id in _MOTOR_IDS:
      if not self.state_reader.addParam(motor_id):
        raise RuntimeError(f"Could not add motor {motor_id} to state reader")
      if not self.temperature_reader.addParam(motor_id):
        raise RuntimeError(f"Could not add motor {motor_id} to temp reader")

  def connect(self) -> None:
    if not self.port.openPort():
      raise RuntimeError(f"Could not open Dynamixel serial port {self.port.port_name}")
    if not self.port.setBaudRate(self.baudrate):
      self.port.closePort()
      raise RuntimeError(f"Could not set baudrate {self.baudrate}")
    self.connected = True

    missing = []
    for motor_id in _MOTOR_IDS:
      _, comm, error = self.packet.ping(self.port, motor_id)
      if comm != COMM_SUCCESS or error != 0:
        missing.append(motor_id)
    if missing:
      raise RuntimeError(f"Motors ping failed for IDs: {missing}")

  def _check_comm(self, comm: int, context: str) -> None:
    if comm != COMM_SUCCESS:
      raise RuntimeError(f"{context}: {self.packet.getTxRxResult(comm)}")

  def _write_register_all(self, *, address: int, size: int, values: np.ndarray) -> None:
    writer = GroupSyncWrite(self.port, self.packet, address, size)
    for motor_id, value in zip(_MOTOR_IDS, values, strict=True):
      unsigned = int(value) & ((1 << (8 * size)) - 1)
      if not writer.addParam(motor_id, unsigned.to_bytes(size, byteorder="little")):
        raise RuntimeError(f"Could not stage register {address} for motor {motor_id}")
    self._check_comm(writer.txPacket(), f"sync-write address {address}")
    writer.clearParam()

  def _write_byte_verified(self, address: int, value: int) -> None:
    failed = []
    for motor_id in _MOTOR_IDS:
      try:
        comm, error = self.packet.write1ByteTxRx(self.port, motor_id, address, int(value))
      except Exception:
        if address != _ADDR_TORQUE_ENABLE or value != 0:
          raise
        failed.append(motor_id)
        continue
      if comm != COMM_SUCCESS or error != 0:
        failed.append(motor_id)
    if failed:
      raise RuntimeError(f"Register {address} write failed for motors {failed}")

  def read_state(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    success = False
    last_comm = None
    for _ in range(10):
      last_comm = self.state_reader.txRxPacket()
      if last_comm == COMM_SUCCESS:
        success = True
        break
      self.port.clearPort()
      time.sleep(0.002)
    if not success:
      assert last_comm is not None
      self._check_comm(last_comm, "state read")

    q = np.empty(_NUM_JOINTS, dtype=np.float32)
    qd = np.empty(_NUM_JOINTS, dtype=np.float32)
    current = np.empty(_NUM_JOINTS, dtype=np.float32)
    for i, motor_id in enumerate(_MOTOR_IDS):
      if not self.state_reader.isAvailable(motor_id, _ADDR_PRESENT_CURRENT, 10):
        raise RuntimeError(f"State unavailable for motor {motor_id}")
      raw_current = self.state_reader.getData(motor_id, _ADDR_PRESENT_CURRENT, 2)
      raw_velocity = self.state_reader.getData(motor_id, _ADDR_PRESENT_VELOCITY, 4)
      raw_position = self.state_reader.getData(motor_id, _ADDR_PRESENT_POSITION, 4)
      current[i] = float(_signed(raw_current, 2))
      qd[i] = float(_signed(raw_velocity, 4)) * _VEL_SCALE
      q[i] = float(_signed(raw_position, 4)) * _POS_SCALE - np.pi
    return q, qd, current

  def read_temperature(self) -> np.ndarray:
    self.temperature_reader.txRxPacket()
    values = np.empty(_NUM_JOINTS, dtype=np.float32)
    for i, motor_id in enumerate(_MOTOR_IDS):
      if self.temperature_reader.isAvailable(motor_id, _ADDR_PRESENT_TEMPERATURE, 1):
        values[i] = self.temperature_reader.getData(motor_id, _ADDR_PRESENT_TEMPERATURE, 1)
      else:
        values[i] = 0.0
    return values

  def write_position(self, q_hw: np.ndarray) -> None:
    raw = np.rint((np.asarray(q_hw) + np.pi) / _POS_SCALE).astype(np.int64)
    self._write_register_all(address=_ADDR_GOAL_POSITION, size=4, values=raw)

  def configure(
    self,
    *,
    initial_q: np.ndarray,
    kp: int = 400,
    ki: int = 0,
    kd: int = 200,
    mcp_side_gain_scale: float = 0.75,
    current_limit_ma: int = 350,
  ) -> None:
    self.write_position(initial_q)
    self._write_byte_verified(_ADDR_TORQUE_ENABLE, 0)
    self.torque_enabled = False
    self._write_byte_verified(_ADDR_OPERATING_MODE, 5)
    self._write_register_all(
      address=9, size=1, values=np.zeros(_NUM_JOINTS, dtype=np.int64)
    )
    self._write_register_all(
      address=_ADDR_PROFILE_VELOCITY,
      size=4,
      values=np.full(_NUM_JOINTS, 125, dtype=np.int64),
    )
    self._write_register_all(
      address=_ADDR_PROFILE_ACCELERATION,
      size=4,
      values=np.zeros(_NUM_JOINTS, dtype=np.int64),
    )
    p_values = np.full(_NUM_JOINTS, int(kp), dtype=np.int64)
    i_values = np.full(_NUM_JOINTS, int(ki), dtype=np.int64)
    d_values = np.full(_NUM_JOINTS, int(kd), dtype=np.int64)
    mcp_side_ids = [0, 4, 8]
    p_values[mcp_side_ids] = int(round(mcp_side_gain_scale * kp))
    i_values[mcp_side_ids] = int(round(mcp_side_gain_scale * ki))
    d_values[mcp_side_ids] = int(round(mcp_side_gain_scale * kd))
    self._write_register_all(address=_ADDR_P_GAIN, size=2, values=p_values)
    self._write_register_all(address=_ADDR_I_GAIN, size=2, values=i_values)
    self._write_register_all(address=_ADDR_D_GAIN, size=2, values=d_values)
    self._write_register_all(
      address=_ADDR_CURRENT_LIMIT,
      size=2,
      values=np.full(_NUM_JOINTS, current_limit_ma, dtype=np.int64),
    )
    self.write_position(initial_q)
    self._write_byte_verified(_ADDR_TORQUE_ENABLE, 1)
    self.torque_enabled = True

  def disable_torque(self) -> None:
    if self.connected:
      try:
        self._write_byte_verified(_ADDR_TORQUE_ENABLE, 0)
      except Exception as e:
        print(f"Warning disabling torque: {e}")
    self.torque_enabled = False

  def close(self) -> None:
    if self.connected:
      self.disable_torque()
      self.port.closePort()
      self.connected = False


def ramp_joints(
  bus: DynamixelBus,
  start_q: np.ndarray,
  target_q: np.ndarray,
  duration_s: float = 2.0,
  hz: float = 50.0,
  current_abort_ma: float | None = None,
  velocity_abort_rad_s: float | None = None,
) -> None:
  steps = max(1, int(round(duration_s * hz)))
  dt = 1.0 / hz
  for step in range(1, steps + 1):
    t0 = time.monotonic()
    alpha = step / steps
    cmd = (1.0 - alpha) * start_q + alpha * target_q
    bus.write_position(cmd)
    if step % 5 == 0 or step == steps:
      _, qd, current = bus.read_state()
      if current_abort_ma is not None and float(np.max(np.abs(current))) > current_abort_ma:
        raise RuntimeError(
          f"Ramp current guard tripped ({np.max(np.abs(current)):.1f} mA)"
        )
      if velocity_abort_rad_s is not None and float(np.max(np.abs(qd))) > velocity_abort_rad_s:
        raise RuntimeError(
          f"Ramp velocity guard tripped ({np.max(np.abs(qd)):.2f} rad/s)"
        )
    rem = dt - (time.monotonic() - t0)
    if rem > 0:
      time.sleep(rem)


class StandaloneActor(torch.nn.Module):
  """Self-contained PyTorch policy actor for fast CPU inference."""

  def __init__(self, state_dict: dict[str, torch.Tensor]):
    super().__init__()
    self.mean = state_dict["obs_normalizer._mean"].clone()
    self.var = state_dict["obs_normalizer._var"].clone()
    self.std = torch.sqrt(self.var + 1e-8)
    self.eps = 1e-2

    layers = []
    i = 0
    while f"mlp.{i}.weight" in state_dict:
      w = state_dict[f"mlp.{i}.weight"]
      b = state_dict[f"mlp.{i}.bias"]
      out_f, in_f = w.shape
      linear = torch.nn.Linear(in_f, out_f)
      linear.weight.data.copy_(w)
      linear.bias.data.copy_(b)
      layers.append(linear)
      if f"mlp.{i+2}.weight" in state_dict:
        layers.append(torch.nn.ELU())
      i += 2

    self.mlp = torch.nn.Sequential(*layers)
    self.eval()

  @torch.inference_mode()
  def forward(self, obs: torch.Tensor) -> torch.Tensor:
    norm_obs = (obs - self.mean) / (self.std + self.eps)
    return torch.clamp(self.mlp(norm_obs), -1.0, 1.0)


def in_hand_workspace(p: np.ndarray) -> bool:
  """Calibrated hand workspace in LEAP palm body frame for Visual-Yaw task.

  Nominal cube position is approximately [-0.003, 0.031, 0.268] m.
  """
  nominal = np.array([-0.003, 0.031, 0.268], dtype=np.float32)
  dist = float(np.linalg.norm(p - nominal))
  return bool(
    (-0.12 <= p[0] <= 0.12)
    and (-0.08 <= p[1] <= 0.15)
    and (0.16 <= p[2] <= 0.40)
    and (dist <= 0.18)
  )


class CameraTrackerWorker:
  """Threaded receiver and ArUco pose estimator from asMagic iPhone stream."""

  def __init__(
    self,
    iphone_ip: str,
    port: int,
    cube_config_path: Path,
    camera_to_palm_path: Path,
    aruco_detection_scale: float,
    max_reprojection_error_px: float = 25.0,
  ):
    self.iphone_ip = iphone_ip
    self.port = port
    self.max_reprojection_error_px = max_reprojection_error_px
    self.running = True
    self.lock = threading.Lock()

    # Load model and calibration
    self.model = load_cube_model(cube_config_path)
    self.t_palm_camera, self.R_palm_camera = load_camera_to_palm(camera_to_palm_path)

    # Initialize estimator with tuned small-marker params
    self.estimator = CubePoseEstimator(self.model, detection_scale=aruco_detection_scale)

    # Latest tracking state
    self.has_pose = False
    self.in_hand = False
    self.latest_timestamp_s = 0.0
    self.pos_palm = np.zeros(3, dtype=np.float32)
    self.rot_palm = np.eye(3, dtype=np.float32)
    self.quat_palm = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    self.visible_faces: tuple[str, ...] = ()
    self.visible_ids: tuple[int, ...] = ()
    self.reproj_error: float = 0.0
    self.latest_camera_image: np.ndarray | None = None
    self.last_camera_frame_time: float = 0.0
    self.latest_preview: np.ndarray | None = None
    self.telemetry_data: dict[str, Any] = {
      "camera_connected": False,
      "tracking_mode": "CONNECTING...",
      "goal_name": "180° Yaw",
      "goal_angle_deg": 180.0,
      "recording": False,
      "recording_file": None,
    }
    self.recording_path: Path | None = None
    self.record_requested: bool = False
    self.video_writer: cv2.VideoWriter | None = None
    self.video_fps: float = 20.0
    self.frame_count = 0
    standby = self._make_standby(f"Connecting to {self.iphone_ip}:{self.port}...")
    self.latest_annotated: np.ndarray | None = standby
    ret, jpeg = cv2.imencode(".jpg", standby, [cv2.IMWRITE_JPEG_QUALITY, 75])
    self.latest_jpeg: bytes | None = jpeg.tobytes() if ret else None

    self.thread = threading.Thread(target=self._run, daemon=True)
    self.thread.start()

  def _make_standby(self, msg: str) -> np.ndarray:
    return draw_annotated_frame(None, None, [], [], np.eye(3), np.zeros(5), None, False, telemetry=self.telemetry_data)

  def _run(self) -> None:
    if not HAS_ASMAGIC:
      print("Warning: asmagic library not found. Camera tracking disabled.")
      return

    print(f"[Tracker] Connecting to iPhone stream at {self.iphone_ip}:{self.port}...")
    try:
      subscriber = ARDataSubscriber(
        self.iphone_ip, port=self.port, hwm=1, conflate=True, verbose=False
      )
    except Exception as e:
      print(f"[Tracker] Failed to start subscriber: {e}")
      return

    print("[Tracker] Stream subscriber connected and listening.")
    last_frame_time = time.time()
    try:
      while self.running:
        try:
          frame = subscriber.get(timeout=100)
          if frame is None or not frame.has_color_image:
            continue

          last_frame_time = time.time()

          raw_bytes = np.frombuffer(frame.color_bytes, dtype=np.uint8)
          image = cv2.imdecode(raw_bytes, cv2.IMREAD_COLOR)
          if image is None:
            continue

          with self.lock:
            self.latest_camera_image = image
            self.last_camera_frame_time = time.time()

          h, w = image.shape[:2]
          K = camera_matrix_from_asmagic(frame.camera_intrinsics, w, h)
          dist = np.zeros(5, dtype=np.float64)

          corners, ids, _ = self.estimator.detect(image)
          pose: CubePose | None = None
          active_corners: list[np.ndarray] = []
          active_ids: list[int] = []

          # Strictly rely ONLY on marker M (ID 0) for visual tracking and estimation.
          # Under no circumstances should any other marker (IDs 1-5) be used even if detected!
          if 0 in ids:
            m_idx = ids.index(0)
            active_corners = [corners[m_idx]]
            active_ids = [0]
            pose = self.estimator.estimate(active_corners, active_ids, K, dist)
          else:
            pose = None

          ts = time.time()
          p_palm = None
          R_palm = None
          in_hand = False

          if pose is not None and pose.reprojection_error_px <= self.max_reprojection_error_px:
            p_palm = self.R_palm_camera @ pose.translation_camera_cube + self.t_palm_camera
            R_palm = self.R_palm_camera @ pose.rotation_camera_cube
            q_palm = quaternion_wxyz_from_rotation_matrix(R_palm)
            in_hand = in_hand_workspace(p_palm)

            with self.lock:
              self.pos_palm = p_palm.astype(np.float32)
              self.rot_palm = R_palm.astype(np.float32)
              self.quat_palm = q_palm.astype(np.float32)
              self.has_pose = True
              self.in_hand = in_hand
              self.latest_timestamp_s = ts
              self.visible_faces = pose.visible_faces
              self.visible_ids = pose.visible_ids
              self.reproj_error = pose.reprojection_error_px
          else:
            with self.lock:
              self.has_pose = False
              self.in_hand = False
              self.visible_faces = ()
              self.visible_ids = ()

          # Render rich annotated frame with 3D axes, wireframe, and HUD
          with self.lock:
            self.frame_count += 1
            render_telemetry = self.telemetry_data.copy()
            render_telemetry["visible_ids"] = (
              list(pose.visible_ids)
              if pose is not None and pose.reprojection_error_px <= self.max_reprojection_error_px
              else []
            )
            annotated = draw_annotated_frame(
              image,
              pose if (pose is not None and pose.reprojection_error_px <= self.max_reprojection_error_px) else None,
              active_corners,
              active_ids,
              K,
              dist,
              p_palm,
              in_hand,
              telemetry=render_telemetry,
              current_rotation_palm=R_palm,
            )
            self.latest_annotated = annotated
            self.latest_preview = annotated

            # Write frame to MP4 video writer if recording is active
            if self.record_requested:
              if self.video_writer is None and self.recording_path:
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                h_rec, w_rec = annotated.shape[:2]
                self.video_writer = cv2.VideoWriter(str(self.recording_path), fourcc, self.video_fps, (w_rec, h_rec))
                print(f"\n[VideoRecorder] VideoWriter started: {w_rec}x{h_rec} @ {self.video_fps} FPS -> {self.recording_path}")
              if self.video_writer is not None:
                self.video_writer.write(annotated)
            elif self.video_writer is not None:
              self.video_writer.release()
              self.video_writer = None

            ret, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret:
              self.latest_jpeg = jpeg.tobytes()

        except Exception:
          time.sleep(0.01)
    finally:
      if self.video_writer is not None:
        try:
          self.video_writer.release()
          self.video_writer = None
        except Exception:
          pass
      try:
        subscriber.close()
      except Exception:
        pass

  def get_latest_pose(self) -> tuple[bool, float, np.ndarray, np.ndarray, np.ndarray, tuple[str, ...], tuple[int, ...], float, bool]:
    with self.lock:
      return (
        self.has_pose,
        self.latest_timestamp_s,
        self.pos_palm.copy(),
        self.rot_palm.copy(),
        self.quat_palm.copy(),
        self.visible_faces,
        self.visible_ids,
        self.reproj_error,
        self.in_hand,
      )

  def get_annotated_frame(self) -> np.ndarray | None:
    with self.lock:
      return self.latest_annotated.copy() if self.latest_annotated is not None else None

  def get_jpeg(self) -> bytes | None:
    with self.lock:
      return self.latest_jpeg

  def update_telemetry(self, telemetry: dict[str, Any]) -> None:
    with self.lock:
      self.telemetry_data.update(telemetry)
      now = time.time()
      # If no camera frames actively arriving, update live telemetry canvas at 20 Hz
      if self.latest_camera_image is None or (now - self.last_camera_frame_time > 1.2):
        self.telemetry_data["camera_connected"] = False
        canvas = draw_annotated_frame(
          None, None, [], [], np.eye(3), np.zeros(5), None, False, telemetry=self.telemetry_data
        )
        self.latest_annotated = canvas
        self.latest_preview = canvas
        ret, jpeg = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ret:
          self.latest_jpeg = jpeg.tobytes()
      else:
        self.telemetry_data["camera_connected"] = True

  def start_recording(self, output_path: str | Path | None = None) -> Path:
    with self.lock:
      if self.record_requested and self.recording_path:
        return self.recording_path
      if output_path is None or str(output_path) == "auto":
        rec_dir = _PROJECT_DIR / "data/recordings"
        rec_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = rec_dir / f"deployment_{ts}.mp4"
      else:
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
      self.recording_path = output_path
      self.record_requested = True
      self.telemetry_data["recording"] = True
      self.telemetry_data["recording_file"] = output_path.name
      print(f"\n[VideoRecorder] Video recording armed -> {self.recording_path}")
      return self.recording_path

  def stop_recording(self) -> Path | None:
    with self.lock:
      if not self.record_requested and self.video_writer is None:
        return None
      self.record_requested = False
      self.telemetry_data["recording"] = False
      saved = self.recording_path
      if self.video_writer is not None:
        try:
          self.video_writer.release()
          self.video_writer = None
          print(f"\n[VideoRecorder] Recording saved: {saved}")
        except Exception as e:
          print(f"[VideoRecorder] Error closing writer: {e}")
      return saved

  def toggle_recording(self) -> dict[str, Any]:
    with self.lock:
      if self.record_requested:
        saved = self.stop_recording()
        return {
          "recording": False,
          "recording_file": saved.name if saved else None,
          "recording_path": str(saved) if saved else None,
        }
      else:
        path = self.start_recording()
        return {
          "recording": True,
          "recording_file": path.name,
          "recording_path": str(path),
        }

  def get_telemetry_dict(self) -> dict[str, Any]:
    with self.lock:
      d = self.telemetry_data.copy()
      d["has_pose"] = self.has_pose
      d["in_hand"] = self.in_hand
      d["p_palm"] = self.pos_palm.tolist() if self.has_pose else None
      d["visible_faces"] = list(self.visible_faces)
      d["visible_ids"] = list(self.visible_ids) if self.has_pose else []
      d["reproj_error"] = round(self.reproj_error, 2)
      d["recording"] = bool(self.record_requested)
      d["recording_file"] = self.recording_path.name if self.recording_path else None
      return d

  def save_preview(self, path: Path) -> None:
    with self.lock:
      if self.latest_preview is not None:
        cv2.imwrite(str(path), self.latest_preview)

  def stop(self) -> None:
    self.stop_recording()
    self.running = False


class GoalManager:
  """Thread-safe manager for dynamic cube target orientation."""

  _FACE_MAP = {
    "+Z": ([0.0, 0.0, 0.0], "+Z (M / Yellow)"),
    "-Z": ([180.0, 0.0, 0.0], "-Z (I / Orange)"),
    "+X": ([0.0, 90.0, 0.0], "+X (B / Red)"),
    "-X": ([0.0, -90.0, 0.0], "-X (U / Blue)"),
    "+Y": ([-90.0, 0.0, 0.0], "+Y (Z / Green)"),
    "-Y": ([90.0, 0.0, 0.0], "-Y (A / White)"),
    "+90": ([0.0, 0.0, 90.0], "+90° Yaw"),
    "-90": ([0.0, 0.0, -90.0], "-90° Yaw"),
    "180": ([0.0, 0.0, 180.0], "180° Yaw"),
    "0": ([0.0, 0.0, 0.0], "0° Nominal (Yellow UP)"),
    "M": ([0.0, 0.0, 0.0], "+Z (M / Yellow)"),
    "I": ([180.0, 0.0, 0.0], "-Z (I / Orange)"),
    "B": ([0.0, 90.0, 0.0], "+X (B / Red)"),
    "U": ([0.0, -90.0, 0.0], "-X (U / Blue)"),
    "Z": ([-90.0, 0.0, 0.0], "+Y (Z / Green)"),
    "A": ([90.0, 0.0, 0.0], "-Y (A / White)"),
  }

  def __init__(self, init_rpy=(0.0, 0.0, 0.0), init_name="Target"):
    self.lock = threading.Lock()
    self.rpy = [float(x) for x in init_rpy]
    self.name = init_name
    from scipy.spatial.transform import Rotation
    self.rot_cls = Rotation
    self.R_goal = self.rot_cls.from_euler("xyz", self.rpy, degrees=True).as_matrix().astype(np.float32)

  def set_face(self, face_name: str) -> bool:
    key = face_name.strip().upper()
    if key in self._FACE_MAP:
      rpy, label = self._FACE_MAP[key]
      with self.lock:
        self.rpy = list(rpy)
        self.name = label
        self.R_goal = self.rot_cls.from_euler("xyz", self.rpy, degrees=True).as_matrix().astype(np.float32)
      print(f"\n[GoalManager] Target switched to Face {label} (RPY: {self.rpy})")
      return True
    return False

  def set_rpy(self, r: float, p: float, y: float, name: str | None = None) -> None:
    with self.lock:
      self.rpy = [float(r), float(p), float(y)]
      self.name = name or f"RPY [{r:.0f}, {p:.0f}, {y:.0f}]"
      self.R_goal = self.rot_cls.from_euler("xyz", self.rpy, degrees=True).as_matrix().astype(np.float32)
    print(f"\n[GoalManager] Target updated to {self.name}")

  def adjust_yaw(self, delta_deg: float) -> None:
    with self.lock:
      self.rpy[2] = (self.rpy[2] + delta_deg) % 360.0
      if self.rpy[2] > 180.0:
        self.rpy[2] -= 360.0
      elif self.rpy[2] < -180.0:
        self.rpy[2] += 360.0
      self.name = f"RPY [{self.rpy[0]:.0f}, {self.rpy[1]:.0f}, {self.rpy[2]:.0f}]"
      self.R_goal = self.rot_cls.from_euler("xyz", self.rpy, degrees=True).as_matrix().astype(np.float32)
    print(f"\n[GoalManager] Yaw adjusted: {self.name}")

  def set_rotation(self, rotation: np.ndarray, name: str) -> None:
    rotation = np.asarray(rotation, dtype=np.float32).reshape(3, 3)
    with self.lock:
      self.R_goal = rotation.copy()
      self.rpy = self.rot_cls.from_matrix(rotation).as_euler("xyz", degrees=True).tolist()
      self.name = name
    print(f"\n[GoalManager] Target initialized to {name}")

  def set_relative_yaw(self, base_rotation: np.ndarray, yaw_deg: float, name: str | None = None) -> None:
    base_rotation = np.asarray(base_rotation, dtype=np.float32).reshape(3, 3)
    R_yaw = self.rot_cls.from_euler("z", yaw_deg, degrees=True).as_matrix().astype(np.float32)
    R_goal = (R_yaw @ base_rotation).astype(np.float32)
    with self.lock:
      self.R_goal = R_goal.copy()
      self.rpy = self.rot_cls.from_matrix(R_goal).as_euler("xyz", degrees=True).tolist()
      self.name = name or f"{yaw_deg:+.0f} deg Yaw Target"
    print(f"\n[GoalManager] Target set to {self.name} (Relative Yaw: {yaw_deg:+.0f} deg from lock)")

  def get_goal(self) -> tuple[np.ndarray, list[float], str]:
    with self.lock:
      return self.R_goal.copy(), list(self.rpy), self.name


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--iphone-ip", default="10.127.51.69", help="iPhone asMagic streaming IP")
  parser.add_argument("--port", type=int, default=8000, help="asMagic port")
  parser.add_argument("--serial-port", default="/dev/ttyUSB0", help="Dynamixel serial device")
  parser.add_argument("--baudrate", type=int, default=4_000_000, help="Dynamixel baudrate")
  parser.add_argument(
    "--checkpoint",
    default=str(
      _BUNDLE_DIR
      / "checkpoints/visual_yaw_model_4900/model_4900.pt"
    ),
    help="Path to trained policy .pt checkpoint",
  )
  parser.add_argument(
    "--camera-to-palm",
    default=str(_PROJECT_DIR / "real_world/camera_to_palm_iphone.json"),
    help="Calibrated camera-to-palm JSON file",
  )
  parser.add_argument(
    "--cube-config",
    default=str(_CAMERA_DIR / "cube_config.json"),
    help="Path to cube_config.json",
  )
  parser.add_argument(
    "--aruco-detection-scale",
    type=float,
    default=2.0,
    help="Internal image scale for small-marker detection (default: 2.0)",
  )
  parser.add_argument(
    "--shadow",
    action="store_true",
    help="Run without motor torque (evaluates camera tracking + policy in real time)",
  )
  parser.add_argument(
    "--torque",
    action="store_true",
    help="Enable motor torque to actuate the physical hand",
  )
  parser.add_argument(
    "--ramp-test",
    action="store_true",
    help="Only ramp to default grasp pose, hold for 3 seconds, and return safely",
  )
  parser.add_argument(
    "--no-workspace-gate",
    action="store_true",
    help="Disable hand workspace bounding box gating (allow policy to run wherever cube is)",
  )
  parser.add_argument(
    "--gui",
    action="store_true",
    default=bool(os.environ.get("DISPLAY")),
    help="Open live desktop OpenCV window (default: True if DISPLAY is set)",
  )
  parser.add_argument(
    "--no-gui",
    action="store_true",
    help="Disable live desktop OpenCV window",
  )
  parser.add_argument(
    "--web-port",
    type=int,
    default=8080,
    help="Port for live HTTP MJPEG streaming visualizer (default: 8080)",
  )
  parser.add_argument(
    "--no-web",
    action="store_true",
    help="Disable live HTTP web streaming server",
  )
  parser.add_argument("--hz", type=float, default=20.0, help="Policy execution frequency (Hz)")
  parser.add_argument("--duration-s", type=float, default=0.0, help="Run duration in seconds (0 = infinite, default: 0.0)")
  parser.add_argument("--max-pose-age-s", type=float, default=0.35, help="Pose freshness limit")
  parser.add_argument("--max-reprojection-error-px", type=float, default=25.0, help="Max reprojection error for solvePnP in px (default: 25.0)")
  parser.add_argument("--current-limit-ma", type=int, default=450, help="Motor current limit (mA, default: 450)")
  parser.add_argument("--current-abort-ma", type=float, default=650.0, help="Safety abort current (mA, default: 650)")
  parser.add_argument("--velocity-abort-rad-s", type=float, default=5.0, help="Safety abort velocity (rad/s, default: 5.0)")
  parser.add_argument("--temperature-abort-c", type=float, default=65.0, help="Safety abort temperature (C, default: 65)")
  parser.add_argument("--temperature-interval-steps", type=int, default=20, help="Temperature read interval (default: 20 steps)")
  parser.add_argument(
    "--tracking-error-abort-rad",
    type=float,
    default=0.0,
    help="Measured-command error abort threshold (0 = disabled, default: 0.0)",
  )
  parser.add_argument("--kp", type=int, default=600, help="Dynamixel position P gain (default: 600)")
  parser.add_argument("--kd", type=int, default=150, help="Dynamixel position D gain (default: 150)")
  parser.add_argument("--mcp-side-gain-scale", type=float, default=1.0, help="MCP side gain scale (default: 1.0)")
  parser.add_argument(
    "--action-ema-alpha",
    type=float,
    default=0.35,
    help="Action low-pass EMA filter coefficient (default: 0.35, range: 0.05-1.0)",
  )
  parser.add_argument(
    "--policy-gain",
    type=float,
    default=0.5,
    help="Fraction of the trained action delta applied to hardware (default: 0.5)",
  )
  parser.add_argument(
    "--max-command-step-rad",
    type=float,
    default=0.04,
    help="Per-joint command change limit per policy step (default: 0.04 rad)",
  )
  parser.add_argument(
    "--lock-translation-obs",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Lock obs[32:35] to nominal in-hand centroid to focus network purely on rotation and prevent jitter (default: True)",
  )
  parser.add_argument(
    "--force-policy",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Continue policy motion even during marker occlusion so fingers do not stall (default: True)",
  )
  parser.add_argument(
    "--pose-hold-s",
    type=float,
    default=5.0,
    help="Grace period for an occluded pose; continues policy movement during finger manipulation (default: 5.0s)",
  )
  parser.add_argument("--goal-euler-deg", nargs=3, type=float, default=[0.0, 0.0, 0.0], help="Target palm-frame roll pitch yaw (deg)")
  parser.add_argument(
    "--goal-face",
    default=None,
    help="Optional initial face target. By default the first detected pose becomes a hold target.",
  )
  parser.add_argument(
    "--initial-goal-yaw-deg",
    type=float,
    default=180.0,
    help="Initial relative yaw target angle in degrees applied when the cube is locked in hand (default: 180.0)",
  )
  parser.add_argument(
    "--goal-current-on-lock",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Initialize the target relative to the first fresh cube pose (default: True)",
  )
  parser.add_argument("--save-preview-interval-s", type=float, default=2.0, help="Interval to save preview snapshot")
  parser.add_argument(
    "--record-video",
    nargs="?",
    const="auto",
    default=None,
    help="Record annotated visualizer video to an MP4 file (default: project/real_world/data/recordings/deployment_YYYYMMDD_HHMMSS.mp4)",
  )
  parser.add_argument("--output-jsonl", type=Path, default=_PROJECT_DIR / "data/deployment_run.jsonl")
  args = parser.parse_args()

  if not 0.0 < args.policy_gain <= 1.0:
    parser.error("--policy-gain must be in (0, 1]")
  if args.max_command_step_rad <= 0.0:
    parser.error("--max-command-step-rad must be positive")
  if args.pose_hold_s < 0.0:
    parser.error("--pose-hold-s must be non-negative")
  if args.temperature_interval_steps <= 0:
    parser.error("--temperature-interval-steps must be positive")

  if not 1.0 <= args.aruco_detection_scale <= 3.0:
    parser.error("--aruco-detection-scale must be between 1.0 and 3.0")
  if not args.shadow and not args.torque:
    print("Notice: neither --shadow nor --torque was specified. Defaulting to safe SHADOW mode.")
    args.shadow = True

  enable_torque = bool(args.torque) and not bool(args.shadow)
  print("\n" + "=" * 74)
  print(f" 🚀 LEAP HAND IN-HAND REORIENTATION ({'TORQUE ENABLED' if enable_torque else 'SHADOW MODE'})")
  print("=" * 74)
  print(f"  • Hardware Port:    {args.serial_port} @ {args.baudrate} baud")
  initial_goal_label = args.goal_face or "first detected pose (hold)"
  print(f"  • Initial Target:   {initial_goal_label}")
  print(f"  • Policy Fallback:  {'ENABLED after initial ArUco lock' if args.force_policy else 'DISABLED'}")
  print(f"  • Camera Stream:    tcp://{args.iphone_ip}:{args.port}")
  print(f"  • Motor PID:        Kp={args.kp}, Kd={args.kd}, McpScale={args.mcp_side_gain_scale}")
  print(f"  • Max Current:      {args.current_limit_ma} mA (Abort @ {args.current_abort_ma} mA)")
  print(f"  • Anti-jitter EMA:  alpha={args.action_ema_alpha}")
  print(f"  • Policy Authority: {args.policy_gain:.2f} (max step {args.max_command_step_rad:.3f} rad)")
  print("-" * 74)
  print("  🌐 LIVE VISUALIZATION WEB INTERFACE:")
  print(f"     👉 Laptop / Phone:   http://10.127.48.102:{args.web_port}")
  print(f"     👉 Robot Host PC:    http://localhost:{args.web_port}")
  print(f"     👉 Live Video Feed:  http://10.127.48.102:{args.web_port}/stream.mjpg")
  print("=" * 74 + "\n")

  # 1. Load Policy
  print("[1/4] Loading trained RL policy...")
  ckpt_path = Path(args.checkpoint).resolve()
  if not ckpt_path.is_file():
    raise FileNotFoundError(f"Checkpoint not found: {ckpt_path}")
  ckpt_data = torch.load(str(ckpt_path), map_location="cpu")
  actor = StandaloneActor(ckpt_data["actor_state_dict"])
  print("      Policy actor network ready (57 obs -> 16 actions).")

  # 2. Start Camera Tracker
  print("[2/4] Starting iPhone ArUco camera tracker...")
  tracker = CameraTrackerWorker(
    iphone_ip=args.iphone_ip,
    port=args.port,
    cube_config_path=Path(args.cube_config).resolve(),
    camera_to_palm_path=Path(args.camera_to_palm).resolve(),
    aruco_detection_scale=args.aruco_detection_scale,
    max_reprojection_error_px=args.max_reprojection_error_px,
  )
  if args.record_video:
    rec_target = None if args.record_video == "auto" else args.record_video
    tracker.start_recording(rec_target)
  time.sleep(1.0)

  # 3. Connect to LEAP Hand Hardware
  print("[3/4] Connecting to LEAP Hand hardware...")
  bus = DynamixelBus(port=args.serial_port, baudrate=args.baudrate)
  bus.connect()
  # Never inherit an enabled-torque state from an interrupted prior run.
  bus.disable_torque()
  q_init_hw, _, _ = bus.read_state()
  last_temperature_c = bus.read_temperature()
  if float(np.max(last_temperature_c)) >= args.temperature_abort_c:
    raise RuntimeError(
      f"Initial temperature guard tripped ({np.max(last_temperature_c):.1f} C)"
    )
  print("      Hardware connected! Measured joint positions (rad):")
  print("      ", [round(float(x), 2) for x in q_init_hw])

  cmd_server = q_init_hw[_HW_TO_SERVER].copy()
  hardware_armed = False
  if enable_torque:
    print("\n[SAFETY GATE] Torque remains OFF until a fresh configured cube ArUco marker is seen in the hand workspace.")
  else:
    print("      Running in SHADOW mode (motors passive, torque OFF).")

  # Setup Dynamic Goal Manager
  goal_mgr = GoalManager(init_rpy=args.goal_euler_deg)
  goal_initialized = not args.goal_current_on_lock
  if args.goal_face:
    goal_mgr.set_face(args.goal_face)
    goal_initialized = True

  def on_web_set_goal(face: str | None, r: float | None, p: float | None, y: float | None) -> bool:
    nonlocal goal_initialized
    if face is not None:
      changed = goal_mgr.set_face(face)
      goal_initialized = goal_initialized or changed
      return changed
    elif r is not None and p is not None and y is not None:
      goal_mgr.set_rpy(r, p, y)
      goal_initialized = True
      return True
    return False

  # Visualizer and Web streaming setup
  use_gui = bool(args.gui) and not bool(args.no_gui)
  web_server: WebVisualizerServer | None = None
  if not args.no_web:
    web_server = WebVisualizerServer(
      port=args.web_port,
      get_jpeg_func=tracker.get_jpeg,
      get_telemetry_func=tracker.get_telemetry_dict,
      set_goal_func=on_web_set_goal,
      record_toggle_func=tracker.toggle_recording,
    )
    web_server.start()

  # Prepare control state
  last_action_server = np.zeros(_NUM_JOINTS, dtype=np.float32)
  last_valid_R_palm: np.ndarray | None = None
  last_valid_pose_time: float = 0.0
  vision_armed = False
  period = 1.0 / args.hz
  max_steps = int(math.ceil(args.duration_s * args.hz)) if args.duration_s > 0 else 0

  args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
  preview_dir = _PROJECT_DIR / "data/snapshots"
  preview_dir.mkdir(parents=True, exist_ok=True)
  last_preview_save = 0.0

  print("\n[4/4] Starting 20 Hz policy control loop. Press Ctrl+C or 'q' in window to stop.")
  print("      Hotkeys (GUI Window): [1-6] Faces (+Z,+X,-X,+Y,-Y,-Z), [[/]] Yaw -15/+15°, [0] Reset, [q] Quit\n")
  step = 0
  started_time = time.time()

  try:
    with args.output_jsonl.open("w", encoding="utf-8") as log_stream:
      while max_steps == 0 or step < max_steps:
        loop_start = time.monotonic()
        now_wall = time.time()

        # A. Read hardware state
        q_hw, qd_hw, current_hw = bus.read_state()
        q_server = q_hw[_HW_TO_SERVER]
        if step % args.temperature_interval_steps == 0:
          last_temperature_c = bus.read_temperature()

        # Safety checks on hardware
        if bus.torque_enabled:
          max_cur = float(np.max(np.abs(current_hw)))
          max_vel = float(np.max(np.abs(qd_hw)))
          if max_cur > args.current_abort_ma:
            raise RuntimeError(f"Emergency stop: Current guard tripped ({max_cur:.1f} mA > {args.current_abort_ma} mA)")
          if max_vel > args.velocity_abort_rad_s:
            raise RuntimeError(
              f"Emergency stop: Velocity guard tripped ({max_vel:.2f} rad/s > "
              f"{args.velocity_abort_rad_s:.2f} rad/s)"
            )
          max_temp = float(np.max(last_temperature_c))
          if max_temp >= args.temperature_abort_c:
            raise RuntimeError(
              f"Emergency stop: Temperature guard tripped ({max_temp:.1f} C >= "
              f"{args.temperature_abort_c:.1f} C)"
            )
          tracking_error = float(
            np.max(np.abs(q_hw - cmd_server[_SERVER_TO_HW]))
          )
          if (
            args.tracking_error_abort_rad > 0.0
            and hardware_armed
            and step >= 10
            and tracking_error > args.tracking_error_abort_rad
          ):
            raise RuntimeError(
              f"Emergency stop: Tracking error guard tripped ({tracking_error:.3f} rad > "
              f"{args.tracking_error_abort_rad:.3f} rad)"
            )

        # B. Read latest cube tracking state
        has_pose, pose_ts, p_palm, R_palm, q_palm, faces, marker_ids, reproj_err, in_hand = tracker.get_latest_pose()
        pose_age = now_wall - pose_ts if has_pose else 999.0
        pose_valid = has_pose and (pose_age <= args.max_pose_age_s) and (in_hand or args.no_workspace_gate)
        vision_armed = vision_armed or pose_valid
        if pose_valid and not goal_initialized:
          if abs(args.initial_goal_yaw_deg) > 1e-3:
            goal_mgr.set_relative_yaw(
              R_palm,
              args.initial_goal_yaw_deg,
              f"{args.initial_goal_yaw_deg:+.0f} deg Yaw Target",
            )
          else:
            goal_mgr.set_rotation(R_palm, "Current pose (hold)")
          goal_initialized = True

        # Torque configuration and the initial grasp ramp are themselves motion,
        # so they are deferred until a fresh pose from a configured ArUco ID exists.
        just_armed = False
        if enable_torque and not hardware_armed and pose_valid:
          print("\n[SAFETY GATE] Fresh cube ArUco pose acquired. Enabling torque and ramping to grasp...")
          bus.configure(
            initial_q=q_hw,
            kp=args.kp,
            ki=0,
            kd=args.kd,
            mcp_side_gain_scale=args.mcp_side_gain_scale,
            current_limit_ma=args.current_limit_ma,
          )
          ramp_joints(
            bus,
            q_hw,
            _GRASP_Q_HW,
            duration_s=2.5,
            hz=50.0,
            current_abort_ma=args.current_abort_ma,
            velocity_abort_rad_s=args.velocity_abort_rad_s,
          )
          q_settled_hw, _, _ = bus.read_state()
          cmd_server = q_settled_hw[_HW_TO_SERVER].copy()
          hardware_armed = True
          just_armed = True
          print("      Hand armed. Waiting for the next fresh ArUco pose before policy motion.")

          if args.ramp_test:
            print("\n[RAMP TEST] Holding default grasp posture for 3.0 seconds...")
            t_end = time.time() + 3.0
            while time.time() < t_end:
              _, _, cur = bus.read_state()
              print(f"\r[RAMP TEST] Max current: {np.max(np.abs(cur)):.0f} mA", end="", flush=True)
              time.sleep(0.1)
            print("\n[RAMP TEST] Ramping back to the measured startup posture...")
            q_curr_hw, _, _ = bus.read_state()
            ramp_joints(
              bus,
              q_curr_hw,
              q_init_hw,
              duration_s=2.0,
              hz=50.0,
              current_abort_ma=args.current_abort_ma,
              velocity_abort_rad_s=args.velocity_abort_rad_s,
            )
            bus.disable_torque()
            hardware_armed = False
            return

        # C. Read current dynamic target goal
        R_goal_palm, goal_rpy, goal_name = goal_mgr.get_goal()

        # Multi-stage tracking state machine
        active_R_palm: np.ndarray | None = None
        active_p_palm: np.ndarray | None = None

        if just_armed:
          tracking_mode = "ARMED - REFRESHING CUBE"
        elif pose_valid:
          active_R_palm = R_palm
          active_p_palm = p_palm
          last_valid_R_palm = R_palm.copy()
          last_valid_pose_time = now_wall
          tracking_mode = "VISION (CLOSED-LOOP)"
        elif vision_armed and (last_valid_R_palm is not None) and (now_wall - last_valid_pose_time <= args.pose_hold_s):
          active_R_palm = last_valid_R_palm
          active_p_palm = np.array([-0.003, 0.031, 0.268], dtype=np.float32)
          tracking_mode = f"OCCLUSION CONTINUATION ({now_wall - last_valid_pose_time:.1f}s)"
        elif vision_armed and args.force_policy:
          # Autonomous continuation during prolonged occlusion: keep moving fingers through manipulation stroke
          active_R_palm = last_valid_R_palm if last_valid_R_palm is not None else np.eye(3, dtype=np.float32)
          active_p_palm = np.array([-0.003, 0.031, 0.268], dtype=np.float32)
          tracking_mode = "OCCLUDED (AUTONOMOUS CONTINUATION)"
        else:
          tracking_mode = "WAITING FOR CUBE"

        # Construct 57-dim observation
        obs = torch.zeros((1, 57), dtype=torch.float32)
        obs[0, 0:16] = torch.as_tensor(
          q_server - _POLICY_Q_REFERENCE_SERVER, dtype=torch.float32
        )
        obs[0, 16:32] = torch.as_tensor(q_server - cmd_server, dtype=torch.float32)

        goal_angle_deg = 0.0
        policy_ran = False
        raw_action_server = np.zeros(_NUM_JOINTS, dtype=np.float32)
        action_server = np.zeros(_NUM_JOINTS, dtype=np.float32)
        normalized_obs_max = 0.0

        if active_R_palm is not None:
          # Orientation error: R_rel = R_cube @ R_goal.T; take entries [3:9]
          R_rel = active_R_palm @ R_goal_palm.T
          rot_err = R_rel.reshape(9)[3:].astype(np.float32)

          tr = float(np.trace(R_rel))
          cos_val = np.clip((tr - 1.0) / 2.0, -1.0, 1.0)
          goal_angle_deg = float(np.arccos(cos_val) * (180.0 / np.pi))

          if args.lock_translation_obs or active_p_palm is None:
            # Regularize cube translation error to nominal grasp centroid
            obs[0, 32:35] = torch.as_tensor(_NOMINAL_CUBE_POS_ERR, dtype=torch.float32)
          else:
            obs[0, 32:35] = torch.as_tensor(-active_p_palm, dtype=torch.float32)

          obs[0, 35:41] = torch.as_tensor(rot_err, dtype=torch.float32)
          obs[0, 41:57] = torch.as_tensor(last_action_server, dtype=torch.float32)
          normalized_obs = (obs - actor.mean) / (actor.std + actor.eps)
          normalized_obs_max = float(
            torch.max(torch.abs(normalized_obs)).item()
          )

          # Policy forward pass & EMA smoothing
          raw_action_server = actor(obs)[0].cpu().numpy()
          alpha = float(np.clip(args.action_ema_alpha, 0.01, 1.0))
          action_server = alpha * raw_action_server + (1.0 - alpha) * last_action_server
          policy_ran = True

        # E. Integrate delta joint target
        delta_server = action_server * _ACTION_DELTA_SCALE * args.policy_gain
        delta_server = np.clip(
          delta_server, -args.max_command_step_rad, args.max_command_step_rad
        )
        cmd_server = np.clip(cmd_server + delta_server, _SOFT_LIMIT_LO_SERVER, _SOFT_LIMIT_HI_SERVER)
        joint_limit_fraction = float(np.mean(
          (cmd_server <= _SOFT_LIMIT_LO_SERVER + 1e-4)
          | (cmd_server >= _SOFT_LIMIT_HI_SERVER - 1e-4)
        ))
        # Simulation's last_action observation is the raw policy output, not
        # the separately smoothed/scaled hardware command.
        last_action_server = raw_action_server.copy() if policy_ran else np.zeros_like(last_action_server)

        # F. Write commanded joint positions to hardware
        if bus.torque_enabled and policy_ran:
          cmd_hw = cmd_server[_SERVER_TO_HW]
          bus.write_position(cmd_hw)

        action_max = float(np.max(np.abs(action_server)))
        raw_saturation_fraction = (
          float(np.mean(np.abs(raw_action_server) >= 0.99)) if policy_ran else 0.0
        )
        command_step_max = float(np.max(np.abs(delta_server)))

        # Update telemetry shared with visualizer & web stream
        tracker.update_telemetry({
          "step": step,
          "hz": round(1.0 / (time.monotonic() - loop_start + 1e-6), 1),
          "max_current_ma": float(np.max(np.abs(current_hw))),
          "max_temperature_c": float(np.max(last_temperature_c)),
          "current_limit_ma": args.current_limit_ma,
          "current_abort_ma": args.current_abort_ma,
          "torque_enabled": bus.torque_enabled,
          "action_max": action_max,
          "raw_saturation_fraction": raw_saturation_fraction,
          "command_step_max_rad": command_step_max,
          "normalized_obs_max": normalized_obs_max,
          "joint_limit_fraction": joint_limit_fraction,
          "action_applied": [round(float(x), 3) for x in action_server],
          "goal_name": goal_name,
          "goal_rpy": goal_rpy,
          "goal_angle_deg": goal_angle_deg,
          "tracking_mode": tracking_mode,
          "target_rotation_palm": R_goal_palm.tolist(),
          "visible_ids": list(marker_ids) if pose_valid else [],
        })

        # Telemetry & Logging
        log_entry = {
          "step": step,
          "timestamp": now_wall,
          "has_pose": pose_valid,
          "tracking_mode": tracking_mode,
          "in_hand": in_hand,
          "pose_age_s": round(pose_age, 3),
          "p_palm_m": p_palm.tolist() if has_pose else None,
          "visible_faces": list(faces),
          "visible_ids": list(marker_ids),
          "goal_name": goal_name,
          "goal_rpy": goal_rpy,
          "goal_angle_deg": round(goal_angle_deg, 2),
          "policy_ran": policy_ran,
          "action_raw": [round(float(x), 3) for x in raw_action_server] if policy_ran else None,
          "action_applied": [round(float(x), 3) for x in action_server],
          "command_delta_rad": [round(float(x), 5) for x in delta_server],
          "action_server": [round(float(x), 3) for x in action_server],
          "max_current_ma": float(np.max(np.abs(current_hw))),
          "max_temperature_c": float(np.max(last_temperature_c)),
          "tracking_error_rad": float(np.max(np.abs(q_hw - cmd_server[_SERVER_TO_HW]))),
          "raw_saturation_fraction": raw_saturation_fraction,
          "command_step_max_rad": command_step_max,
          "normalized_obs_max": normalized_obs_max,
          "joint_limit_fraction": joint_limit_fraction,
        }
        log_stream.write(json.dumps(log_entry, separators=(",", ":")) + "\n")

        # Live console telemetry (single-line carriage return)
        cur_str = f"Cur:{np.max(np.abs(current_hw)):.0f}mA" if bus.torque_enabled else "Torque:OFF"
        print(
          f"\r[Step {step:04d} | {1.0/(time.monotonic()-loop_start+1e-6):.1f}Hz] Mode:{tracking_mode} | {goal_name} Err:{goal_angle_deg:.1f}° | ActMax:{action_max:.2f} Sat:{100.0*raw_saturation_fraction:.0f}% Step:{command_step_max:.3f} ObsZ:{normalized_obs_max:.1f} Lim:{100.0*joint_limit_fraction:.0f}% | {cur_str}",
          end="",
          flush=True,
        )

        # Periodic snapshot save
        if now_wall - last_preview_save >= args.save_preview_interval_s:
          snap_path = preview_dir / "latest_tracking_preview.jpg"
          tracker.save_preview(snap_path)
          last_preview_save = now_wall

        # Desktop GUI window display with live hotkeys
        if use_gui:
          vis_frame = tracker.get_annotated_frame()
          if vis_frame is not None:
            try:
              cv2.imshow("LEAP Hand - In-Hand Reorientation", vis_frame)
              key = cv2.waitKey(1) & 0xFF
              if key == ord("q"):
                print("\n\n[GUI] 'q' key pressed. Stopping...")
                break
              elif key == ord("1"):
                goal_mgr.set_face("+Z")
                goal_initialized = True
              elif key == ord("2"):
                goal_mgr.set_face("+X")
                goal_initialized = True
              elif key == ord("3"):
                goal_mgr.set_face("-X")
                goal_initialized = True
              elif key == ord("4"):
                goal_mgr.set_face("+Y")
                goal_initialized = True
              elif key == ord("5"):
                goal_mgr.set_face("-Y")
                goal_initialized = True
              elif key == ord("6"):
                goal_mgr.set_face("-Z")
                goal_initialized = True
              elif key == ord("["):
                goal_mgr.adjust_yaw(-15.0)
                goal_initialized = True
              elif key == ord("]"):
                goal_mgr.adjust_yaw(+15.0)
                goal_initialized = True
              elif key == ord("0"):
                goal_mgr.set_rpy(0.0, 0.0, 0.0, "+Z (Reset)")
                goal_initialized = True
            except Exception as e:
              use_gui = False
              print(f"\n[GUI] Desktop window disabled ({e}). Open Web Interface: http://10.127.48.102:8080")

        step += 1
        elapsed = time.monotonic() - loop_start
        if elapsed < period:
          time.sleep(period - elapsed)

  except KeyboardInterrupt:
    print("\n\n[USER STOP] Received KeyboardInterrupt.")
  finally:
    print("\nShutting down safely...")
    if web_server is not None:
      web_server.stop()
    if use_gui:
      try:
        cv2.destroyAllWindows()
      except Exception:
        pass
    if bus.torque_enabled:
      print("Ramping hand back to safe home posture...")
      try:
        q_curr_hw, _, _ = bus.read_state()
        ramp_joints(
          bus,
          q_curr_hw,
          _GRASP_Q_HW,
          duration_s=1.5,
          hz=50.0,
          current_abort_ma=args.current_abort_ma,
          velocity_abort_rad_s=args.velocity_abort_rad_s,
        )
      except Exception as e:
        print(f"Error during ramp down: {e}")
    bus.disable_torque()
    bus.close()
    tracker.stop()
    print("Done. Clean exit complete.")


if __name__ == "__main__":
  main()
