#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/oliver/Halwani/mujoco-journey"
VENV="$REPO_DIR/external/in-hand-rotation-mjlab/.venv"

# Clean environment
unset PYTHONPATH ROS_DISTRO ROS_VERSION ROS_PACKAGE_PATH
export PYTHONNOUSERSITE=1
export MUJOCO_GL=egl
export DISPLAY="${DISPLAY:-:1}"

echo "Starting synchronized MBZUAI cube in-hand rotation (Real LEAP Hand + MuJoCo simulation)..."
"$VENV/bin/python" "$REPO_DIR/external/in-hand-rotation-mjlab/scripts/deploy_and_record_side_by_side.py" "$@"
