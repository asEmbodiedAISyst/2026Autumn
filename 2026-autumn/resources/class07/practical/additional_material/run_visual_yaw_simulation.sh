#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN=python3

cd "$ROOT_DIR/visual_yaw_reorientation"
"$PYTHON_BIN" project/scripts/play_reorient.py \
  --task Mjlab-Leap-Right-HandCube-MBZUAI-Visual-Yaw \
  --checkpoint-file checkpoints/visual_yaw_model_4900/model_4900.pt \
  --initial-goal current \
  --goal-step-deg 90 \
  --device cpu
