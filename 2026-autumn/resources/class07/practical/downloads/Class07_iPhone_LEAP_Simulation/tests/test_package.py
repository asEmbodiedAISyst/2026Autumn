from pathlib import Path

import json
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "simulation" / "iphone_leap_sim.py"


def test_required_assets_are_packaged() -> None:
    assert SCRIPT.is_file()
    assert (ROOT / "simulation" / "hand_landmarker.task").is_file()
    assert (ROOT / "simulation" / "leap_hand_model" / "right_hand.xml").is_file()
    assert (ROOT / "simulation" / "dex_retargeting" / "pyproject.toml").is_file()
    assert (ROOT / "run_cube_reorient_simulation.sh").is_file()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'asmagic==1.0.1' in pyproject


def test_student_launcher_contains_no_motor_interface() -> None:
    source = SCRIPT.read_text(encoding="utf-8").lower()
    assert "dynamixel" not in source
    assert "serial-port" not in source
    assert "write_position" not in source


def test_simulation_and_retargeting_self_check() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert '"status": "pass"' in result.stdout
    assert '"model_actuators": 16' in result.stdout
    assert '"retargeted_joints": 16' in result.stdout
    assert '"asmagic_version": "1.0.1"' in result.stdout
    assert '"hevc_decoder": "PyAV ' in result.stdout
    assert '"motor_interface_included": false' in result.stdout


def test_current_asmagic_stream_api_is_used() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert ".receive(timeout=" in source
    assert "packet.color_array" in source
    assert "cv2.imdecode" not in source
    assert '"--check-stream"' in source


def test_reorient_simulation_launcher_is_executable() -> None:
    launcher = ROOT / "run_cube_reorient_simulation.sh"
    assert launcher.is_file()
    assert (launcher.stat().st_mode & 0o111) != 0

