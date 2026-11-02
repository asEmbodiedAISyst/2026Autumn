#!/usr/bin/env bash
set -e
BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="/home/oliver/Halwani/mujoco-journey/external/in-hand-rotation-mjlab/.venv/bin/python"

echo "=================================================================="
echo "📷 Calibrating iPhone Overhead Camera to LEAP Palm Frame"
echo "=================================================================="
echo "1. Place the cube flat in the LEAP Hand palm cradle:"
echo "   - Yellow Face ('M', ArUco ID 0) facing UP (+Z)"
echo "   - Red Face ('B', ArUco ID 1) facing THUMB"
echo "   - Green Face ('Z', ArUco ID 2) facing FINGERS"
echo "2. Ensure asMagic is open and streaming on iPhone (10.127.51.69:8000)"
echo "=================================================================="

$PYTHON_BIN "$BUNDLE_DIR/camera/calibrate_camera_to_palm.py" --auto "$@"
