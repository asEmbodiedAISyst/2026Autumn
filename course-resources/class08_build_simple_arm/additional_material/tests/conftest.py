import os
import sys
from pathlib import Path

if sys.platform.startswith("linux"):  # headless EGL rendering on Linux; macOS uses its default (CGL)
    os.environ.setdefault("MUJOCO_GL", "egl")

ROOT = Path(__file__).resolve().parents[1]  # additional_material/
sys.path.insert(0, str(ROOT / "code"))  # real_gripper_drag, real_gripper_motion_test
sys.path.insert(0, str(ROOT))  # rebot_sim
