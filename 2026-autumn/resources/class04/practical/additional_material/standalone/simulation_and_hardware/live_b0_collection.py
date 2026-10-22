#!/usr/bin/env python3
"""Run a guarded B0 XC330 collection while a local MuJoCo twin follows it live."""
from __future__ import annotations

import argparse
import csv
import math
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

import mujoco
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hardware_runtime"))
from xc330_io import DynamixelBus, snapshot  # noqa: E402

TICKS_PER_RAD = 4096.0 / (2.0 * math.pi)
MODEL = ROOT / "platform_models" / "AsBrainBox-Platform---XC330-B0" / "AsBrainBox-Platform---XC330-B0_actuated_mujoco_compatible.xml"
XC330_BODY = "1DOF-B0_1__XC330-M288-T_1"
H2_PROFILES = ("P01_slow_triangle", "P02_multisine", "P03_smooth_levels")


@dataclass(frozen=True)
class Profile:
    name: str
    time_s: np.ndarray
    goal_raw: np.ndarray

    @property
    def duration_s(self) -> float:
        return float(self.time_s[-1])


def verified_bus(cfg: dict[str, object]) -> DynamixelBus:
    bus = DynamixelBus(str(cfg["serial_port"]), int(cfg["baud_rate_bps"]))
    row = snapshot(bus, int(cfg["motor_id"]))
    for name in ("model_number", "firmware_version", "operating_mode"):
        expected = int(cfg[f"expected_{name}"] if name != "operating_mode" else cfg[name])
        if int(row[name]) != expected:
            bus.close()
            raise RuntimeError(f"preflight {name}: expected {expected}, got {row[name]}")
    # XC330 input_voltage is reported in tenths of volts. 45–55 means 4.5–5.5 V.
    if not 45 <= int(row["input_voltage"]) <= 55 or int(row["temperature"]) >= 49:
        bus.close()
        raise RuntimeError(f"unsafe start telemetry: {row}")
    return bus


def h2_profiles() -> list[Profile]:
    """Load the exact locally embedded V5 B0/H2/P01–P03/R01 command records."""
    root = ROOT / "data" / "v5_h2_calibration"
    profiles: list[Profile] = []
    for name in H2_PROFILES:
        path = root / name / "command_events.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"Missing embedded V5 command record: {path}")
        frame = pd.read_parquet(path)
        t = frame.t_command_s.to_numpy(dtype=float)
        raw = frame.goal_position_raw_requested.to_numpy(dtype=float)
        if len(t) < 2 or np.any(np.diff(t) < 0):
            raise RuntimeError(f"Invalid V5 command timestamps in {path}")
        profiles.append(Profile(name, t - t[0], raw))
    return profiles


def demo_profile(initial: int, seconds: float) -> Profile:
    """The short classroom sine remains available for a fast supervised check."""
    if seconds <= 0:
        raise ValueError("--seconds must be greater than zero")
    t = np.linspace(0.0, seconds, max(2, int(seconds / .02) + 1))
    raw = initial + .35 * TICKS_PER_RAD * np.sin(2.0 * math.pi * .18 * t)
    return Profile("demo_sine", t, raw)


def configure_collection(bus: DynamixelBus, motor: int, cfg: dict[str, object], initial: int, *, h2: bool) -> None:
    bus.write(motor, "torque_enable", 0)
    bus.write(motor, "operating_mode", int(cfg["operating_mode"]))
    # V5 H2 used P=800, I=0, D=150. Keep the shorter demo deliberately gentler.
    bus.write(motor, "position_p_gain", 800 if h2 else 600)
    bus.write(motor, "position_i_gain", 0)
    bus.write(motor, "position_d_gain", 150)
    bus.write(motor, "profile_acceleration", 32)
    bus.write(motor, "profile_velocity", 125)
    bus.write(motor, "goal_position", initial)
    bus.write(motor, "torque_enable", 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "hardware.example.toml")
    parser.add_argument("--enable-motion", action="store_true", help="required before torque is enabled")
    parser.add_argument("--protocol", choices=("demo", "h2_calibration"), default="demo", help="demo: 8-second sine; h2_calibration: V5 H2 P01/P02/P03, R01 exactly once")
    parser.add_argument("--seconds", type=float, default=8.0, help="only for --protocol demo (default: 8)")
    parser.add_argument("--no-viewer", action="store_true", help="headless troubleshooting only; default shows the live MuJoCo twin")
    args = parser.parse_args()
    cfg = tomllib.loads(args.config.read_text())

    if args.protocol == "h2_calibration":
        planned = h2_profiles()
        summary = ", ".join(f"{p.name} ({p.duration_s:.2f}s)" for p in planned)
        print(f"Selected embedded V5 H2 protocol, one repeat: {summary}; total {sum(p.duration_s for p in planned):.2f}s")
    else:
        planned = []
    if not args.enable_motion:
        print("Dry run. No serial port opened and no torque enabled.")
        print(f"protocol={args.protocol}; config={cfg}")
        print("Run again with --enable-motion only after clearing the fixture.")
        return

    bus = verified_bus(cfg)
    motor = int(cfg["motor_id"])
    rows: list[dict[str, float | str]] = []
    sim_model = mujoco.MjModel.from_xml_path(str(MODEL))
    sim_data = mujoco.MjData(sim_model)
    sim_body = mujoco.mj_name2id(sim_model, mujoco.mjtObj.mjOBJ_BODY, XC330_BODY)
    if sim_body < 0:
        bus.close()
        raise RuntimeError(f"Could not find {XC330_BODY} in the local B0 MJCF")
    window = None
    if not args.no_viewer:
        from mujoco import viewer
        window = viewer.launch_passive(sim_model, sim_data)
        window.cam.distance = .32; window.cam.azimuth = 140; window.cam.elevation = -18
    try:
        initial = bus.read(motor, "present_position")
        if args.protocol == "demo":
            planned = [demo_profile(initial, args.seconds)]
        sim_data.qpos[0] = (initial - 2048) / TICKS_PER_RAD
        mujoco.mj_forward(sim_model, sim_data)
        configure_collection(bus, motor, cfg, initial, h2=args.protocol == "h2_calibration")
        global_start = time.monotonic()
        for profile in planned:
            profile_start = time.monotonic()
            print(f"Running {profile.name}: {profile.duration_s:.2f}s")
            while True:
                profile_elapsed = time.monotonic() - profile_start
                if profile_elapsed >= profile.duration_s or (window is not None and not window.is_running()):
                    break
                requested = float(np.interp(profile_elapsed, profile.time_s, profile.goal_raw))
                goal = int(round(requested))
                goal = max(int(cfg["goal_min_raw"]), min(int(cfg["goal_max_raw"]), goal))
                bus.write(motor, "goal_position", goal)
                global_elapsed = time.monotonic() - global_start
                sim_target = (goal - 2048) / TICKS_PER_RAD
                while sim_data.time < global_elapsed:
                    sim_data.ctrl[0] = sim_target
                    mujoco.mj_step(sim_model, sim_data)
                if window:
                    window.cam.lookat[:] = sim_data.xpos[sim_body]
                    window.sync()
                rows.append({
                    "time_s": global_elapsed,
                    "protocol": args.protocol,
                    "profile": profile.name,
                    "profile_time_s": profile_elapsed,
                    "goal_position_raw": goal,
                    "present_position_raw": bus.read(motor, "present_position"),
                    "present_velocity_raw": bus.read(motor, "present_velocity"),
                    "present_current_raw": bus.read(motor, "present_current"),
                    "simulation_position_rad": float(sim_data.qpos[0]),
                })
                time.sleep(.02)
            if window is not None and not window.is_running():
                print("MuJoCo viewer was closed; stopping the physical collection safely.")
                break
    finally:
        try:
            bus.torque_disable(motor)
        finally:
            bus.close()
            if window:
                window.close()
    output_name = "live_b0_h2_calibration_R01.csv" if args.protocol == "h2_calibration" else "live_b0_collection.csv"
    output = ROOT / "outputs" / output_name
    output.parent.mkdir(exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        fields = list(rows[0]) if rows else ["time_s", "protocol", "profile"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    print(f"Saved {len(rows)} guarded physical + MuJoCo-twin samples to {output}")


if __name__ == "__main__":
    main()
