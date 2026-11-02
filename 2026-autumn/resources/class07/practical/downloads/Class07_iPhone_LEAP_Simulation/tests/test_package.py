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
    assert (ROOT / "visual_feedback" / "simulation_only" / "demo.py").is_file()


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
    assert '"motor_interface_included": false' in result.stdout


def test_stale_feedback_finishes_with_larger_yaw_error() -> None:
    activity = ROOT / "visual_feedback" / "simulation_only" / "activity.py"
    result = subprocess.run(
        [
            sys.executable,
            str(activity),
            "--latency-ms",
            "150",
            "--drop-every",
            "5",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    fresh = report["fresh"]
    stale = report["intervention"]
    assert stale["delay_steps"] == 3
    assert stale["dropped_packets"] == 16
    assert stale["final_abs_goal_error_deg"] > fresh["final_abs_goal_error_deg"]
