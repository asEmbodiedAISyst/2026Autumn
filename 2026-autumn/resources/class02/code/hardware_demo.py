"""Class 02 offline hardware-record audit; Python standard library only.

Run from the package: python code/hardware_demo.py audit
                     python code/hardware_demo.py inspect --row 400
Original source: students branch f7c118edaadc9f33498669736fa9d99160ff629a.
Writes only results/hardware-demo; never connects to or commands hardware.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import statistics

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "xc330-hardware-demo"
TAU = 2 * math.pi


def load():
    with (DATA / "telemetry_events.csv").open(newline="") as stream:
        telemetry = list(csv.DictReader(stream))
    with (DATA / "command_events.csv").open(newline="") as stream:
        commands = list(csv.DictReader(stream))
    return telemetry, commands


def convert(row):
    """Exact model-specific conversions; source columns are already signed."""
    return {
        "position_meas_rad": (int(row["present_position_raw"]) - 2048) * TAU / 4096,
        "velocity_meas_rad_s": int(row["present_velocity_raw"]) * 0.229 * TAU / 60,
        "current_meas_A": int(row["present_current_raw"]) * 0.001,
        "pwm_meas_fraction": int(row["present_pwm_raw"]) * 0.00113,
        "input_voltage_V": int(row["input_voltage_raw"]) * 0.1,
    }


def inspect(row_index):
    rows, _ = load()
    if not 0 <= row_index < len(rows):
        raise ValueError(f"row must be in 0..{len(rows)-1}")
    row = rows[row_index]
    converted = convert(row)
    return {
        "row_index": row_index,
        "time_s_host_receive_end": float(row["t_state_s"]),
        "episode_id": row["episode_id"],
        "raw": {key: int(row[key]) for key in (
            "goal_position_raw", "position_trajectory_raw", "present_position_raw",
            "present_velocity_raw", "present_current_raw", "present_pwm_raw",
            "input_voltage_raw", "temperature_C")},
        "converted": {
            "position_deg_relative_to_2048": math.degrees(converted["position_meas_rad"]),
            "position_rad_relative_to_2048": converted["position_meas_rad"],
            "velocity_rpm": int(row["present_velocity_raw"]) * 0.229,
            "velocity_rad_s": converted["velocity_meas_rad_s"],
            "input_current_mA": converted["current_meas_A"] * 1000,
            "PWM_percent": converted["pwm_meas_fraction"] * 100,
            "input_voltage_V": converted["input_voltage_V"],
            "temperature_C": int(row["temperature_C"]),
        },
        "interpretation": "Encoder/control-table telemetry; no output-torque measurement.",
    }


def audit():
    rows, commands = load()
    manifest = json.loads((DATA / "raw" / "episode.json").read_text())
    before = json.loads((DATA / "raw" / "control_table_before.json").read_text())
    after = json.loads((DATA / "raw" / "control_table_after.json").read_text())
    t = [float(row["t_state_s"]) for row in rows]
    intervals = [b - a for a, b in zip(t, t[1:])]
    if not all(value > 0 for value in intervals):
        raise ValueError("Telemetry time is not strictly increasing")
    errors = {}
    for key in convert(rows[0]):
        error = max(abs(convert(row)[key] - float(row[key])) for row in rows)
        errors[key] = error
        if error > 1e-12:
            raise ValueError(f"Source engineering column differs: {key}: {error}")
    if len(rows) != manifest["telemetry_count"] or len(commands) != manifest["command_count"]:
        raise ValueError("Counts disagree with episode manifest")
    fields = ("id", "model_number", "firmware_version", "operating_mode", "baud_rate",
              "position_p_gain", "position_i_gain", "position_d_gain", "goal_current",
              "current_limit", "pwm_limit", "profile_velocity", "profile_acceleration")
    if any(before[key] != after[key] for key in fields):
        raise ValueError("Critical readback changed")
    if {row["episode_id"] for row in rows + commands} != {manifest["episode_id"]}:
        raise ValueError("Mixed episode identity")
    if {int(row["operating_mode_raw"]) for row in rows} != {before["operating_mode"]}:
        raise ValueError("Mode mismatch")
    if any(int(row["hardware_error_status_raw"]) != 0 for row in rows):
        raise ValueError("Hardware-error record requires separate interpretation")
    tracking = [(int(row["present_position_raw"]) - int(row["goal_position_raw"])) * 360 / 4096
                for row in rows]
    result = {
        "episode": manifest["episode_id"], "date_utc": manifest["start_utc"],
        "fixture": manifest["mechanical_configuration"],
        "external_moving_mass_g": manifest["fixture"]["total_external_moving_mass_g"],
        "controller": manifest["controller_id"],
        "readback": {key: before[key] for key in fields},
        "telemetry_rows": len(rows), "command_rows": len(commands),
        "duration_s": t[-1] - t[0],
        "mean_poll_interval_ms": statistics.mean(intervals) * 1000,
        "median_poll_interval_ms": statistics.median(intervals) * 1000,
        "max_poll_interval_ms": max(intervals) * 1000,
        "achieved_poll_rate_hz": 1 / statistics.mean(intervals),
        "source_conversion_max_abs_error": errors,
        "critical_readback_unchanged": True,
        "position_range_deg_relative_to_2048": [min(float(row["position_meas_rad"]) for row in rows) * 180/math.pi,
                                                max(float(row["position_meas_rad"]) for row in rows) * 180/math.pi],
        "input_voltage_range_V": [min(float(row["input_voltage_V"]) for row in rows),
                                  max(float(row["input_voltage_V"]) for row in rows)],
        "temperature_range_C": [min(int(row["temperature_C"]) for row in rows),
                                 max(int(row["temperature_C"]) for row in rows)],
        "position_tracking_rmse_deg_readback_goal": math.sqrt(statistics.mean(e*e for e in tracking)),
        "observation_boundary": "t_state_s is host receive-end time, not independently measured physical sample time; goal is register readback.",
        "current_semantics": "XC330 input-supply telemetry; not calibrated output torque.",
        "files_sha256": {str(p.relative_to(DATA)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(DATA.rglob("*")) if p.is_file() and p.suffix in (".csv", ".json", ".parquet")},
    }
    out = ROOT / "results" / "hardware-demo"
    out.mkdir(parents=True, exist_ok=True)
    (out / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    (out / "sample-400.json").write_text(json.dumps(inspect(400), indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "inspect"))
    parser.add_argument("--row", type=int, default=400)
    args = parser.parse_args()
    result = audit() if args.action == "audit" else inspect(args.row)
    print(json.dumps(result, indent=2))
