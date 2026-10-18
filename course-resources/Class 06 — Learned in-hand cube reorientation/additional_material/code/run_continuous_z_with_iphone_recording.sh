#!/usr/bin/env bash
# Single supported physical deployment entrypoint for this package.
set -euo pipefail

CLASS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUNDLE_ROOT="${CLASS_ROOT}/../external/CONTINUOUS_Z_ROTATION_DEPLOYMENT_BUNDLE_20261014"

exec bash "${BUNDLE_ROOT}/hardware_runtime/run_60s_with_iphone_video.sh" "$@"
