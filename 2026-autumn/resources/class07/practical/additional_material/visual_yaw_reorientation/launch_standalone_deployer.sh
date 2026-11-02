#!/usr/bin/env bash
set -e
BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="/home/oliver/Halwani/mujoco-journey/external/in-hand-rotation-mjlab/.venv/bin/python"

echo "=================================================================="
echo "🚀 Launching Unified Standalone Visual Yaw Deployment"
echo "🌐 Web Dashboard: http://10.127.48.102:8080"
echo "=================================================================="

$PYTHON_BIN "$BUNDLE_DIR/project/real_world/deploy_visual_yaw_hardware.py" "$@"
