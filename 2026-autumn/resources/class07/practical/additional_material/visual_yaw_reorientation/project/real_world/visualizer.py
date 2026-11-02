#!/usr/bin/env python3
"""Live Visualization and Interactive Web Streaming Server for LEAP Hand RL Deployment."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import socketserver
import threading
import time
from typing import Any, Callable, Sequence
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np


def draw_cube_wireframe(
  img: np.ndarray,
  K: np.ndarray,
  dist: np.ndarray,
  rvec: np.ndarray,
  tvec: np.ndarray,
  size: float = 0.058,
  color_bottom: tuple[int, int, int] = (0, 220, 255),
  color_top: tuple[int, int, int] = (0, 255, 180),
  color_pillar: tuple[int, int, int] = (255, 200, 0),
) -> None:
  """Project and draw 3D cube bounding box edges on the camera frame."""
  h = size / 2.0
  box_3d = np.array(
    [
      [-h, -h, -h],
      [h, -h, -h],
      [h, h, -h],
      [-h, h, -h],
      [-h, -h, h],
      [h, -h, h],
      [h, h, h],
      [-h, h, h],
    ],
    dtype=np.float32,
  )
  pts_2d, _ = cv2.projectPoints(box_3d, rvec, tvec, K, dist)
  pts = np.int32(pts_2d.reshape(-1, 2))

  # Bottom face
  for i in range(4):
    cv2.line(img, tuple(pts[i]), tuple(pts[(i + 1) % 4]), color_bottom, 2)
  # Top face
  for i in range(4):
    cv2.line(img, tuple(pts[i + 4]), tuple(pts[((i + 1) % 4) + 4]), color_top, 2)
  # Vertical pillars
  for i in range(4):
    cv2.line(img, tuple(pts[i]), tuple(pts[i + 4]), color_pillar, 2)


_POSE_CUBE_VERTICES = np.array(
  [
    [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
    [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
  ],
  dtype=np.float32,
)
_POSE_CUBE_EDGES = (
  (0, 1), (1, 2), (2, 3), (3, 0),
  (4, 5), (5, 6), (6, 7), (7, 4),
  (0, 4), (1, 5), (2, 6), (3, 7),
)


def _draw_orientation_cube(
  canvas: np.ndarray,
  rotation: np.ndarray,
  center: tuple[int, int],
  color: tuple[int, int, int],
) -> None:
  """Draw an orthographic cube and body axes for a palm-frame rotation."""
  rotation = np.asarray(rotation, dtype=np.float32).reshape(3, 3)
  # Fixed isometric observer in the palm frame; both cubes share this view.
  view = np.array(
    [[0.82, -0.57, 0.0], [0.32, 0.46, -0.83]], dtype=np.float32
  )
  points = (view @ (rotation @ _POSE_CUBE_VERTICES.T)).T * 30.0
  points[:, 0] += center[0]
  points[:, 1] += center[1]
  points_i = np.rint(points).astype(np.int32)
  for start, end in _POSE_CUBE_EDGES:
    cv2.line(canvas, tuple(points_i[start]), tuple(points_i[end]), color, 2, cv2.LINE_AA)

  origin = np.asarray(center, dtype=np.float32)
  axis_colors = ((70, 70, 255), (70, 230, 90), (255, 170, 40))
  for axis, axis_color in zip(np.eye(3, dtype=np.float32), axis_colors):
    endpoint = origin + view @ (rotation @ axis) * 48.0
    cv2.arrowedLine(
      canvas,
      tuple(np.rint(origin).astype(int)),
      tuple(np.rint(endpoint).astype(int)),
      axis_color,
      2,
      cv2.LINE_AA,
      tipLength=0.18,
    )


def draw_pose_comparison_panel(
  height: int,
  current_rotation_palm: np.ndarray | None,
  target_rotation_palm: np.ndarray | None,
  visible_ids: Sequence[int] = (),
) -> np.ndarray:
  """Create a side field comparing ArUco-measured and requested cube poses in robot palm frame."""
  width = 300
  panel = np.full((height, width, 3), (20, 22, 28), dtype=np.uint8)
  cv2.putText(panel, "ROBOT PALM FRAME", (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (245, 245, 245), 2)
  cv2.putText(panel, "RL Policy Coordinate System", (16, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (90, 200, 255), 1)
  cv2.line(panel, (16, 58), (width - 16, 58), (55, 62, 76), 1)

  current_y = min(150, max(120, height // 3))
  target_y = min(height - 90, max(current_y + 145, (2 * height) // 3 + 5))
  cv2.putText(panel, "CURRENT (Palm Frame R_palm)", (16, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (150, 215, 255), 1)
  if current_rotation_palm is not None:
    _draw_orientation_cube(panel, current_rotation_palm, (width // 2, current_y), (0, 220, 255))
    ids_text = ", ".join(str(int(marker_id)) for marker_id in visible_ids)
    cv2.putText(panel, f"Marker IDs: {ids_text or '-'}", (18, current_y + 62), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (190, 195, 205), 1)
  else:
    cv2.putText(panel, "NO CUBE MARKER", (52, current_y), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (70, 80, 255), 2)
    cv2.putText(panel, "Control is inhibited", (69, current_y + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (150, 160, 180), 1)

  divider_y = (current_y + target_y) // 2
  cv2.line(panel, (16, divider_y), (width - 16, divider_y), (55, 62, 76), 1)
  cv2.putText(panel, "TARGET (Palm Frame R_goal)", (16, divider_y + 23), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (160, 255, 190), 1)
  if target_rotation_palm is not None:
    _draw_orientation_cube(panel, target_rotation_palm, (width // 2, target_y), (80, 230, 120))
  else:
    cv2.putText(panel, "NO TARGET", (84, target_y), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (120, 130, 150), 2)

  cv2.putText(panel, "X:Thumb(Red) Y:Fingers(Grn) Z:Up(Blu)", (10, height - 22), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180, 190, 205), 1)
  cv2.putText(panel, "(Camera image = Camera Optical Frame)", (10, height - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (120, 130, 145), 1)
  return panel


def draw_telemetry_canvas(
  telemetry: dict[str, Any] | None = None,
  w: int = 640,
  h: int = 480,
) -> np.ndarray:
  """Draw a sleek, high-tech real-time status canvas when camera is in standby."""
  canvas = np.full((h, w, 3), 20, dtype=np.uint8)
  t = telemetry or {}

  # Top Bar
  cv2.rectangle(canvas, (0, 0), (w, 54), (16, 18, 24), -1)
  cv2.putText(
    canvas,
    "LEAP Hand: Cube Reorientation",
    (14, 34),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.52,
    (255, 255, 255),
    2,
  )

  # Status Badge
  mode = t.get("tracking_mode", "STANDBY")
  if "CLOSED-LOOP" in mode:
    badge_bg, badge_text = (30, 140, 50), "VISION ACTIVE (CLOSED-LOOP)"
  elif "OCCLUSION CONTINUATION" in mode or "HELD" in mode:
    badge_bg, badge_text = (0, 140, 220), mode
  elif "AUTONOMOUS" in mode or "OCCLUDED" in mode:
    badge_bg, badge_text = (160, 90, 20), mode
  else:
    badge_bg, badge_text = (30, 30, 180), mode

  cv2.rectangle(canvas, (w - 330, 14), (w - 12, 42), badge_bg, -1)
  cv2.putText(
    canvas,
    badge_text,
    (w - 322, 33),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.41,
    (255, 255, 255),
    1,
  )

  # Camera Status Box
  cv2.rectangle(canvas, (20, 68), (w - 20, 142), (28, 32, 42), -1)
  cv2.rectangle(canvas, (20, 68), (w - 20, 142), (45, 55, 75), 1)
  cv2.putText(
    canvas,
    "CAMERA STREAM (asMagic iPhone App)",
    (32, 90),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.48,
    (100, 200, 255),
    1,
  )
  cam_connected = t.get("camera_connected", False)
  if cam_connected:
    cv2.putText(
      canvas,
      "Status: CONNECTED & STREAMING",
      (32, 114),
      cv2.FONT_HERSHEY_SIMPLEX,
      0.50,
      (50, 220, 80),
      1,
    )
  else:
    cv2.putText(
      canvas,
      "Status: WAITING FOR FRAMES (tcp://10.127.51.69:8000)",
      (32, 114),
      cv2.FONT_HERSHEY_SIMPLEX,
      0.48,
      (0, 165, 255),
      1,
    )
    cv2.putText(
      canvas,
      "Action: Open asMagic app on iPhone and unlock screen.",
      (32, 132),
      cv2.FONT_HERSHEY_SIMPLEX,
      0.40,
      (180, 180, 180),
      1,
    )

  # Control & Target Box
  cv2.rectangle(canvas, (20, 155), (w - 20, 260), (28, 32, 42), -1)
  cv2.rectangle(canvas, (20, 155), (w - 20, 260), (45, 55, 75), 1)
  cv2.putText(
    canvas,
    "TARGET ORIENTATION & GOAL TRACKING",
    (32, 178),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.48,
    (100, 200, 255),
    1,
  )
  goal_name = t.get("goal_name", "+X (B / Red)")
  goal_err = t.get("goal_angle_deg", 90.0)
  cv2.putText(
    canvas,
    f"Target Face: {goal_name}",
    (32, 210),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.65,
    (255, 255, 255),
    2,
  )
  cv2.putText(
    canvas,
    f"Geodesic Orientation Error: {goal_err:.1f} deg",
    (32, 242),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.58,
    (0, 220, 255),
    1,
  )

  # Motor & Hardware Telemetry
  cv2.rectangle(canvas, (20, 272), (w - 20, 368), (28, 32, 42), -1)
  cv2.rectangle(canvas, (20, 272), (w - 20, 368), (45, 55, 75), 1)
  cv2.putText(
    canvas,
    "ROBOT HAND TELEMETRY",
    (32, 294),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.48,
    (100, 200, 255),
    1,
  )

  step = t.get("step", 0)
  hz = t.get("hz", 20.0)
  cur = t.get("max_current_ma", 0.0)
  act_max = t.get("action_max", 0.0)
  torque = "ON (Active)" if t.get("torque_enabled") else "OFF (Shadow)"

  info1 = f"Step: {step:04d}   Rate: {hz:.1f} Hz   Torque: {torque}"
  current_limit = t.get("current_limit_ma", 350)
  temperature = t.get("max_temperature_c", 0.0)
  info2 = f"Max Current: {cur:.0f}/{current_limit:.0f} mA   Temp: {temperature:.0f} C   Action Max: {act_max:.2f}"
  cv2.putText(canvas, info1, (32, 322), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (220, 220, 220), 1)
  cv2.putText(canvas, info2, (32, 348), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (220, 220, 220), 1)

  # 16 Joint Action Visualizer mini-bars
  actions = t.get("action_applied", [])
  if len(actions) == 16:
    bar_y_center = 405
    bar_w = 26
    spacing = 36
    start_x = 35
    for i, a in enumerate(actions):
      bx = start_x + i * spacing
      bar_h = int(np.clip(a, -1.0, 1.0) * 16)
      col = (0, 220, 100) if bar_h >= 0 else (50, 100, 255)
      cv2.rectangle(canvas, (bx, bar_y_center), (bx + bar_w, bar_y_center - bar_h), col, -1)
      cv2.rectangle(
        canvas, (bx, bar_y_center - 16), (bx + bar_w, bar_y_center + 16), (60, 70, 90), 1
      )

  # Bottom Footer
  cv2.rectangle(canvas, (0, h - 34), (w, h), (16, 18, 24), -1)
  footer = "Dashboard: http://10.127.48.102:8080   |   Hotkeys: [1-6] Target Faces, [q] Quit"
  cv2.putText(canvas, footer, (14, h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (160, 170, 185), 1)

  return canvas


def draw_annotated_frame(
  image: np.ndarray | None,
  pose: Any | None,
  corners: Sequence[np.ndarray],
  ids: Sequence[int],
  K: np.ndarray,
  dist: np.ndarray,
  p_palm: np.ndarray | None,
  in_hand: bool,
  telemetry: dict[str, Any] | None = None,
  current_rotation_palm: np.ndarray | None = None,
) -> np.ndarray:
  """Render high-fidelity tracking HUD, 3D axes, goal target, or standby telemetry canvas."""
  telemetry = telemetry or {}
  target_value = telemetry.get("target_rotation_palm")
  target_rotation = None if target_value is None else np.asarray(target_value, dtype=np.float32)
  visible_ids = telemetry.get("visible_ids", [])
  if image is None:
    canvas = draw_telemetry_canvas(telemetry)
    panel = draw_pose_comparison_panel(canvas.shape[0], None, target_rotation, visible_ids)
    return np.hstack((canvas, panel))

  vis = image.copy()
  h, w = vis.shape[:2]

  # Top HUD Bar (dark semi-transparent banner)
  overlay = vis.copy()
  cv2.rectangle(overlay, (0, 0), (w, 54), (18, 19, 24), -1)
  cv2.rectangle(overlay, (0, h - 36), (w, h), (18, 19, 24), -1)
  cv2.addWeighted(overlay, 0.72, vis, 0.28, 0, vis)

  if (telemetry or {}).get("recording"):
    cv2.circle(vis, (w - 75, 34), 6, (0, 0, 255), -1)
    cv2.putText(vis, "REC", (w - 64, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 0, 255), 2)

  if pose is not None and len(ids) > 0:
    # 1. Detected ArUco Marker outline
    cv2.aruco.drawDetectedMarkers(
      vis, [c.reshape(-1, 1, 2) for c in corners], np.array(ids).reshape(-1, 1)
    )

    # 2. 3D coordinate axes at cube origin
    rvec, _ = cv2.Rodrigues(pose.rotation_camera_cube)
    tvec = pose.translation_camera_cube
    cv2.drawFrameAxes(vis, K, dist, rvec, tvec, 0.045, 2)

    # 3. 3D Cube Wireframe
    draw_cube_wireframe(vis, K, dist, rvec, tvec, size=0.058)

    # 4. Status Badge
    if in_hand:
      badge_text = "IN HAND (ACTIVE)"
      badge_color = (40, 220, 70)  # Bright green
    else:
      badge_text = "OUT OF PALM / TABLE"
      badge_color = (0, 165, 255)  # Orange

    cv2.putText(vis, badge_text, (12, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.65, badge_color, 2)

    if p_palm is not None:
      pos_str = f"Palm: [{p_palm[0]:+.2f}, {p_palm[1]:+.2f}, {p_palm[2]:+.2f}] m"
      cv2.putText(vis, pos_str, (240, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2)

    err_str = f"Err: {pose.reprojection_error_px:.2f}px"
    cv2.putText(vis, err_str, (w - 130, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1)
  else:
    # Check if policy is running in autonomous reorientation fallback
    mode = (telemetry or {}).get("tracking_mode", "SEARCHING")
    if "AUTONOMOUS" in mode:
      cv2.putText(
        vis,
        "AUTONOMOUS REORIENTATION (R=I)",
        (12, 36),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 200, 0),
        2,
      )
    else:
      cv2.putText(
        vis,
        "SEARCHING FOR CUBE (ARUCO IDs 0-5)",
        (12, 36),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 0, 255),
        2,
      )

  # Bottom Telemetry Bar
  if telemetry:
    torque_str = "TORQUE: ON" if telemetry.get("torque_enabled") else "TORQUE: OFF (SHADOW)"
    cur_str = f"MaxCur: {telemetry.get('max_current_ma', 0):.0f} mA"
    rate_str = f"{telemetry.get('hz', 20.0):.1f} Hz"
    goal_name = telemetry.get("goal_name", "Target")
    goal_err = telemetry.get("goal_angle_deg", 0.0)
    bot_text = f"{torque_str}  |  {cur_str}  |  {rate_str}  |  Goal: {goal_name} (Err: {goal_err:.1f} deg)"
    cv2.putText(vis, bot_text, (12, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (220, 220, 220), 1)

  panel = draw_pose_comparison_panel(
    vis.shape[0], current_rotation_palm, target_rotation, visible_ids
  )
  return np.hstack((vis, panel))


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LEAP Hand — Live Reorientation Monitor</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: #0f1115;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      padding: 20px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 12px;
      border-bottom: 1px solid #1f242d;
    }
    h1 { font-size: 1.4rem; font-weight: 600; color: #f8fafc; }
    .badge {
      display: inline-block;
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }
    .badge-inhand { background: #064e3b; color: #34d399; border: 1px solid #059669; }
    .badge-out { background: #451a03; color: #fb923c; border: 1px solid #d97706; }
    .badge-lost { background: #450a0a; color: #f87171; border: 1px solid #dc2626; }
    .main-grid {
      display: grid;
      grid-template-columns: 2fr 1.2fr;
      gap: 20px;
    }
    @media (max-width: 960px) {
      .main-grid { grid-template-columns: 1fr; }
    }
    .video-card {
      background: #17191e;
      border: 1px solid #262b36;
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    .video-container {
      width: 100%;
      background: #000;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 400px;
    }
    .video-container img {
      width: 100%;
      height: auto;
      display: block;
    }
    .stats-card {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .card {
      background: #17191e;
      border: 1px solid #262b36;
      border-radius: 10px;
      padding: 16px;
    }
    .card-title {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: #94a3b8;
      margin-bottom: 8px;
    }
    .card-value {
      font-size: 1.25rem;
      font-weight: 600;
      color: #f1f5f9;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    .subtext {
      font-size: 0.8rem;
      color: #64748b;
      margin-top: 4px;
    }
    .btn-group {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-top: 10px;
    }
    button {
      background: #242b38;
      color: #e2e8f0;
      border: 1px solid #3b4252;
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 0.82rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s, border-color 0.15s;
    }
    button:hover {
      background: #333d4f;
      border-color: #60a5fa;
    }
    button:active {
      background: #1d232e;
    }
    .btn-primary {
      background: #1e3a5f;
      border-color: #2563eb;
      color: #93c5fd;
    }
    .slider-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 8px;
      font-size: 0.82rem;
    }
    .slider-row input[type="range"] {
      flex: 1;
      margin: 0 10px;
    }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>LEAP Hand — In-Hand Cube Reorientation</h1>
      <div class="subtext">Live iPhone stream (asMagic) + ArUco 6D pose + RSL-RL Policy</div>
    </div>
    <div id="statusBadge" class="badge badge-lost">SEARCHING</div>
  </div>

  <div class="main-grid">
    <div class="video-card">
      <div class="video-container">
        <img src="/stream.mjpg" alt="Live Hand Camera Stream" />
      </div>
    </div>

    <div class="stats-card">
      <!-- Target Goal Control Card -->
      <div class="card" style="border-color: #3b82f6;">
        <div class="card-title" style="color: #60a5fa;">Target Goal Orientation</div>
        <div class="card-value" id="valGoal">Target: +Z (M)</div>
        <div class="subtext" id="valGoalAngle" style="color: #facc15;">Geodesic Error: 0.0 deg</div>

        <div style="margin-top: 12px; font-size: 0.75rem; color: #94a3b8; text-transform: uppercase;">Preset Face Targets:</div>
        <div class="btn-group">
          <button onclick="setFace('+Z')">+Z (M / Yellow)</button>
          <button onclick="setFace('+X')">+X (B / Red)</button>
          <button onclick="setFace('+Y')">+Y (Z / Green)</button>
          <button onclick="setFace('-X')">-X (U / Blue)</button>
          <button onclick="setFace('-Y')">-Y (A / White)</button>
          <button onclick="setFace('-Z')">-Z (I / Orange)</button>
        </div>

        <div style="margin-top: 12px; font-size: 0.75rem; color: #94a3b8; text-transform: uppercase;">Visual Yaw Discrete Goals (90° Steps):</div>
        <div class="btn-group" style="grid-template-columns: repeat(4, 1fr); margin-top: 8px;">
          <button style="background: #1e3a8a; border-color: #3b82f6; font-weight: 600;" onclick="adjustYaw(-90)">-90° (F7)</button>
          <button style="background: #1e3a8a; border-color: #3b82f6; font-weight: 600;" onclick="adjustYaw(+90)">+90° (F8)</button>
          <button style="background: #1e3a8a; border-color: #3b82f6; font-weight: 600;" onclick="adjustYaw(180)">180°</button>
          <button style="background: #374151; border-color: #6b7280;" onclick="setFace('+Z')">Reset 0° (F6)</button>
        </div>

        <div style="margin-top: 12px; font-size: 0.75rem; color: #94a3b8; text-transform: uppercase;">Fine Relative Yaw Rotation:</div>
        <div class="btn-group" style="grid-template-columns: repeat(4, 1fr); margin-top: 8px;">
          <button onclick="adjustYaw(-15)">-15 deg</button>
          <button onclick="adjustYaw(+15)">+15 deg</button>
          <button onclick="adjustYaw(-30)">-30 deg</button>
          <button onclick="adjustYaw(+30)">+30 deg</button>
        </div>

        <div style="margin-top: 14px; font-size: 0.75rem; color: #94a3b8; text-transform: uppercase;">Manual Euler Angles (RPY):</div>
        <div class="slider-row">
          <span>R</span>
          <input type="range" id="sliderR" min="-180" max="180" value="0" oninput="onSliderChange()">
          <span id="labelR">0 deg</span>
        </div>
        <div class="slider-row">
          <span>P</span>
          <input type="range" id="sliderP" min="-180" max="180" value="0" oninput="onSliderChange()">
          <span id="labelP">0 deg</span>
        </div>
        <div class="slider-row">
          <span>Y</span>
          <input type="range" id="sliderY" min="-180" max="180" value="0" oninput="onSliderChange()">
          <span id="labelY">0 deg</span>
        </div>
      </div>

      <!-- Video Recording Card -->
      <div class="card" style="border-color: #ef4444;">
        <div class="card-title" style="color: #f87171;">Visualizer Video Recording</div>
        <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 8px;">
          <button id="btnRecord" style="background: #991b1b; border: 1px solid #ef4444; color: white; padding: 10px 16px; border-radius: 6px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 8px;" onclick="toggleRecord()">
            <span id="recDot" style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #f87171;"></span>
            <span id="recText">Start Video Recording</span>
          </button>
          <div id="recDuration" style="font-family: monospace; font-size: 1.05rem; font-weight: 700; color: #fca5a5;">00:00</div>
        </div>
        <div class="subtext" id="recStatus" style="margin-top: 8px;">Records full composite feed (camera + 3D palm comparison + HUD) to MP4.</div>
      </div>

      <!-- Real-time Stats Cards -->
      <div class="card">
        <div class="card-title">Cube Palm Position</div>
        <div class="card-value" id="valPos">[0.00, 0.00, 0.00] m</div>
        <div class="subtext" id="valPosSub">ArUco-only calibrated palm frame</div>
      </div>

      <div class="card">
        <div class="card-title">Pose Detection Source</div>
        <div class="card-value" id="valMarkers">No marker</div>
        <div class="subtext">Configured cube ArUco IDs 0–5 only</div>
      </div>

      <div class="card">
        <div class="card-title">Motor Current & Health</div>
        <div class="card-value" id="valCurrent">0 mA</div>
        <div class="subtext" id="valHealth">Temperature: 0 C</div>
      </div>

      <div class="card">
        <div class="card-title">Policy Loop Frequency</div>
        <div class="card-value" id="valRate">20.0 Hz</div>
        <div class="subtext" id="valStep">Step: 0000</div>
      </div>
    </div>
  </div>

  <script>
    let currentR = 0, currentP = 0, currentY = 0;
    let isRecording = false;
    let recStartTime = null;
    let recTimer = null;

    async function toggleRecord() {
      try {
        const res = await fetch('/toggle_record');
        const data = await res.json();
        updateRecState(data.recording, data.recording_file);
      } catch (e) {}
    }

    function updateRecState(rec, filename) {
      isRecording = Boolean(rec);
      const btn = document.getElementById('btnRecord');
      const text = document.getElementById('recText');
      const status = document.getElementById('recStatus');
      const dot = document.getElementById('recDot');
      if (isRecording) {
        btn.style.background = '#dc2626';
        text.innerText = 'Stop Recording';
        status.innerHTML = `<span style="color: #fca5a5;">Recording active: <b>${filename || 'video.mp4'}</b></span>`;
        dot.style.background = '#ffffff';
        if (!recStartTime) {
          recStartTime = Date.now();
          recTimer = setInterval(() => {
            const sec = Math.floor((Date.now() - recStartTime) / 1000);
            const m = String(Math.floor(sec / 60)).padStart(2, '0');
            const s = String(sec % 60).padStart(2, '0');
            document.getElementById('recDuration').innerText = `${m}:${s}`;
          }, 1000);
        }
      } else {
        btn.style.background = '#991b1b';
        text.innerText = 'Start Video Recording';
        dot.style.background = '#f87171';
        if (filename) {
          status.innerHTML = `<span style="color: #4ade80;">Saved video: <b>${filename}</b></span>`;
        } else {
          status.innerText = 'Records full composite feed (camera + 3D palm comparison + HUD) to MP4.';
        }
        if (recTimer) {
          clearInterval(recTimer);
          recTimer = null;
          recStartTime = null;
          document.getElementById('recDuration').innerText = '00:00';
        }
      }
    }

    async function setFace(face) {
      try {
        await fetch(`/set_goal?face=${encodeURIComponent(face)}`);
      } catch (e) {}
    }

    async function adjustYaw(deltaDeg) {
      currentY = (currentY + deltaDeg) % 360;
      if (currentY > 180) currentY -= 360;
      if (currentY < -180) currentY += 360;
      document.getElementById('sliderY').value = currentY;
      document.getElementById('labelY').innerText = `${currentY} deg`;
      try {
        await fetch(`/set_goal?r=${currentR}&p=${currentP}&y=${currentY}`);
      } catch (e) {}
    }

    async function onSliderChange() {
      currentR = parseInt(document.getElementById('sliderR').value);
      currentP = parseInt(document.getElementById('sliderP').value);
      currentY = parseInt(document.getElementById('sliderY').value);
      document.getElementById('labelR').innerText = `${currentR} deg`;
      document.getElementById('labelP').innerText = `${currentP} deg`;
      document.getElementById('labelY').innerText = `${currentY} deg`;
      try {
        await fetch(`/set_goal?r=${currentR}&p=${currentP}&y=${currentY}`);
      } catch (e) {}
    }

    async function updateTelemetry() {
      try {
        const res = await fetch('/telemetry.json');
        if (res.ok) {
          const data = await res.json();
          const badge = document.getElementById('statusBadge');
          const mode = data.tracking_mode || '';
          if (data.has_pose && data.in_hand) {
            badge.className = 'badge badge-inhand';
            badge.innerText = 'VISION (IN HAND)';
          } else if (mode.includes('OCCLUSION') || mode.includes('HELD')) {
            badge.className = 'badge';
            badge.style.background = '#d97706';
            badge.style.color = '#ffffff';
            badge.style.border = '1px solid #f59e0b';
            badge.innerText = mode;
          } else if (mode.includes('AUTONOMOUS') || mode.includes('OCCLUDED')) {
            badge.className = 'badge';
            badge.style.background = '#0c4a6e';
            badge.style.color = '#38bdf8';
            badge.style.border = '1px solid #0284c7';
            badge.innerText = mode;
          } else if (data.has_pose) {
            badge.className = 'badge badge-out';
            badge.innerText = 'OUT OF PALM / TABLE';
          } else {
            badge.className = 'badge badge-lost';
            badge.innerText = 'WAITING FOR CAMERA';
          }

          if (data.p_palm) {
            document.getElementById('valPos').innerText =
              `[${data.p_palm[0].toFixed(2)}, ${data.p_palm[1].toFixed(2)}, ${data.p_palm[2].toFixed(2)}] m`;
          } else {
            document.getElementById('valPos').innerText = 'No pose';
          }
          const markerIds = data.visible_ids || [];
          document.getElementById('valMarkers').innerText = markerIds.length ? `ArUco IDs: ${markerIds.join(', ')}` : 'No marker';

          document.getElementById('valCurrent').innerText = `${Math.round(data.max_current_ma || 0)} mA`;
          document.getElementById('valHealth').innerText =
            `Limit: ${Math.round(data.current_limit_ma || 350)} mA · Temperature: ${Math.round(data.max_temperature_c || 0)} C · Command step: ${(data.command_step_max_rad || 0).toFixed(3)} rad`;
          document.getElementById('valRate').innerText = `${(data.hz || 20.0).toFixed(1)} Hz`;
          document.getElementById('valStep').innerText =
            `Step: ${String(data.step || 0).padStart(4, '0')} · ObsZ: ${(data.normalized_obs_max || 0).toFixed(1)} · Joint limits: ${Math.round(100 * (data.joint_limit_fraction || 0))}%`;

          if (data.goal_name) {
            document.getElementById('valGoal').innerText = `Target: ${data.goal_name}`;
          }
          if (data.goal_rpy && data.goal_rpy.length === 3) {
            currentR = Math.round(data.goal_rpy[0]);
            currentP = Math.round(data.goal_rpy[1]);
            currentY = Math.round(data.goal_rpy[2]);
            document.getElementById('sliderR').value = currentR;
            document.getElementById('sliderP').value = currentP;
            document.getElementById('sliderY').value = currentY;
            document.getElementById('labelR').innerText = `${currentR} deg`;
            document.getElementById('labelP').innerText = `${currentP} deg`;
            document.getElementById('labelY').innerText = `${currentY} deg`;
          }
          if (data.goal_angle_deg !== undefined) {
            document.getElementById('valGoalAngle').innerText = `Geodesic Error: ${data.goal_angle_deg.toFixed(1)} deg`;
          }
          if (data.recording !== undefined && data.recording !== isRecording) {
            updateRecState(data.recording, data.recording_file);
          }
        }
      } catch (e) {}
    }
    setInterval(updateTelemetry, 250);
  </script>
</body>
</html>
"""


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
  daemon_threads = True
  allow_reuse_address = True


class WebVisualizerServer:
  """Embedded Web Streaming Server providing /stream.mjpg, dashboard, and /set_goal API."""

  def __init__(
    self,
    host: str = "0.0.0.0",
    port: int = 8080,
    get_jpeg_func: Callable[[], bytes | None] | None = None,
    get_telemetry_func: Callable[[], dict[str, Any]] | None = None,
    set_goal_func: Callable[[str | None, float | None, float | None, float | None], bool] | None = None,
    record_toggle_func: Callable[[], dict[str, Any]] | None = None,
  ):
    self.host = host
    self.port = port
    self.get_jpeg = get_jpeg_func or (lambda: None)
    self.get_telemetry = get_telemetry_func or (lambda: {})
    self.set_goal = set_goal_func or (lambda f, r, p, y: False)
    self.record_toggle = record_toggle_func or (lambda: {"recording": False})
    self.running = False
    self.server: _ThreadedHTTPServer | None = None
    self.thread: threading.Thread | None = None

  def start(self) -> None:
    handler_class = self._make_handler()
    try:
      self.server = _ThreadedHTTPServer((self.host, self.port), handler_class)
      self.running = True
      self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
      self.thread.start()
      print("\n" + "=" * 72)
      print("🌐 LIVE VISUALIZATION WEB INTERFACE ACTIVE:")
      print(f"   👉 Laptop / Phone Browser:  http://10.127.48.102:{self.port}")
      print(f"   👉 Robot Brain Host:        http://localhost:{self.port}")
      print(f"   👉 MJPEG Video Feed:        http://10.127.48.102:{self.port}/stream.mjpg")
      print("=" * 72 + "\n")
    except Exception as e:
      print(f"[WebVisualizer] Could not start HTTP server on port {self.port}: {e}")

  def stop(self) -> None:
    self.running = False
    if self.server:
      try:
        self.server.shutdown()
        self.server.server_close()
      except Exception:
        pass

  def _make_handler(self) -> type[BaseHTTPRequestHandler]:
    vis_server = self

    class _Handler(BaseHTTPRequestHandler):
      def log_message(self, format: str, *args: Any) -> None:
        pass

      def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
          self.send_response(200)
          self.send_header("Content-Type", "text/html; charset=utf-8")
          self.end_headers()
          self.wfile.write(_DASHBOARD_HTML.encode("utf-8"))
        elif path == "/stream.mjpg":
          self.send_response(200)
          self.send_header("Age", "0")
          self.send_header("Cache-Control", "no-cache, private")
          self.send_header("Pragma", "no-cache")
          self.send_header(
            "Content-Type", "multipart/x-mixed-replace; boundary=FRAME"
          )
          self.end_headers()
          try:
            while vis_server.running:
              jpeg_data = vis_server.get_jpeg()
              if jpeg_data:
                self.wfile.write(b"--FRAME\r\n")
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg_data)))
                self.end_headers()
                self.wfile.write(jpeg_data + b"\r\n")
              time.sleep(0.04)  # ~25 fps
          except (ConnectionResetError, BrokenPipeError):
            pass
        elif path == "/telemetry.json":
          self.send_response(200)
          self.send_header("Content-Type", "application/json")
          self.send_header("Cache-Control", "no-cache")
          self.end_headers()
          telemetry = vis_server.get_telemetry()
          self.wfile.write(json.dumps(telemetry).encode("utf-8"))
        elif path == "/set_goal":
          query = parse_qs(parsed.query)
          face = query.get("face", [None])[0]
          r = float(query["r"][0]) if "r" in query else None
          p = float(query["p"][0]) if "p" in query else None
          y = float(query["y"][0]) if "y" in query else None

          ok = vis_server.set_goal(face, r, p, y)
          self.send_response(200 if ok else 400)
          self.send_header("Content-Type", "application/json")
          self.end_headers()
          self.wfile.write(json.dumps({"success": ok}).encode("utf-8"))
        elif path == "/toggle_record":
          res = vis_server.record_toggle()
          self.send_response(200)
          self.send_header("Content-Type", "application/json")
          self.send_header("Cache-Control", "no-cache")
          self.end_headers()
          self.wfile.write(json.dumps(res).encode("utf-8"))
        else:
          self.send_error(404)

    return _Handler
