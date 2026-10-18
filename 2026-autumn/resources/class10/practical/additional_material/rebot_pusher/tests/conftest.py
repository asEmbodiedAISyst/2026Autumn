import os
import sys
from pathlib import Path

if sys.platform.startswith("linux"):  # headless EGL rendering on Linux; macOS uses its default (CGL)
    os.environ.setdefault("MUJOCO_GL", "egl")

# The package is not installed (package = false in pyproject.toml): import rebot_sim from the package root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
