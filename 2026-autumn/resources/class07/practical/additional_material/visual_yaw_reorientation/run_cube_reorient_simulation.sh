#!/usr/bin/env bash
set -e
BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "$PYTHON_BIN" ] && [ -x "$PYTHON_BIN" ]; then
  PY="$PYTHON_BIN"
elif [ -x "/home/oliver/Halwani/mujoco-journey/external/in-hand-rotation-mjlab/.venv/bin/python" ]; then
  PY="/home/oliver/Halwani/mujoco-journey/external/in-hand-rotation-mjlab/.venv/bin/python"
elif [ -x "$BUNDLE_DIR/../../../../class06/practical/downloads/class06-continuous-yaw-standalone/Class06_Continuous_Yaw_Standalone/training_source/project/.venv/bin/python" ]; then
  PY="$BUNDLE_DIR/../../../../class06/practical/downloads/class06-continuous-yaw-standalone/Class06_Continuous_Yaw_Standalone/training_source/project/.venv/bin/python"
else
  PY="python3"
fi

TARGET_YAW="${1:-90}"
shift || true

echo "=================================================================="
echo "🎯 Launching MuJoCo In-Hand Cube Reorientation with Known Target"
echo "Target Yaw: ${TARGET_YAW}° in Palm Frame"
echo "------------------------------------------------------------------"
echo "🎮 Viewer Controls:"
echo "   F8 : +90° Yaw target step"
echo "   F7 : -90° Yaw target step"
echo "   F6 : Reset target to current cube pose"
echo "   F9 : Sample a random target orientation"
echo "   Mouse: Double-click detached target cube, Ctrl+Right-drag to rotate"
echo "   Space: Pause/Resume | Enter: Reset rollout | Esc: Exit"
echo "=================================================================="

LIBGL_DRI3_DISABLE=1 "$PY" "$BUNDLE_DIR/project/scripts/play_reorient.py" \
  --task Mjlab-Leap-Right-HandCube-MBZUAI-Visual-Yaw \
  --checkpoint-file "$BUNDLE_DIR/checkpoints/visual_yaw_model_4900/model_4900.pt" \
  --goal-rpy-palm-deg 0 0 "$TARGET_YAW" \
  --device cpu \
  "$@"
