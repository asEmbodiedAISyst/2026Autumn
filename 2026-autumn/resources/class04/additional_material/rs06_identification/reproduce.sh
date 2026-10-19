#!/usr/bin/env bash
set -euo pipefail

PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$PACKAGE_DIR"
"$PYTHON_BIN" scripts/generate_chapter02_rs06_sim_position_v1.py --refresh-model-sources
"$PYTHON_BIN" scripts/generate_chapter02_rs06_sim_torque_v1.py
"$PYTHON_BIN" scripts/run_chapter02_rs06_sim_position_identification_v1.py
"$PYTHON_BIN" scripts/run_chapter02_rs06_sim_torque_identification_v1.py
"$PYTHON_BIN" scripts/generate_chapter02_rs06_hardware_trajectories.py --controller-id H1 --kp 50 --kd 3.38 --output-dir hardware/trajectory-suites/H1 --overwrite
"$PYTHON_BIN" scripts/generate_chapter02_rs06_hardware_trajectories.py --controller-id H2 --kp 100 --kd 1.95 --output-dir hardware/trajectory-suites/H2 --overwrite
"$PYTHON_BIN" scripts/build_chapter02_rs06_hardware_plan.py
"$PYTHON_BIN" scripts/verify_chapter02_rs06_release.py --write
"$PYTHON_BIN" -m unittest discover -s tests -v
