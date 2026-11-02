#!/usr/bin/env bash
set -e
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_SCRIPT="$ROOT_DIR/../../additional_material/visual_yaw_reorientation/run_cube_reorient_simulation.sh"

if [ -f "$TARGET_SCRIPT" ]; then
  exec "$TARGET_SCRIPT" "$@"
else
  echo "Error: Visual yaw reorientation script not found at $TARGET_SCRIPT" >&2
  exit 1
fi
