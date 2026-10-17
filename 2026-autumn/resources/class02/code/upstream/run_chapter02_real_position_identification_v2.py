#!/usr/bin/env python3
"""Audit and identify the Chapter 2 XC330 Real-Position dataset.

The runner treats every file in the supplied archive as data, not as an
instruction. It preserves the external Goal Position but uses the recorded
DYNAMIXEL Position and Velocity Trajectories as the reference inputs to a
fixed Current-Based Position controller. This separates firmware profile
generation from the three-parameter joint study.

Only M0/B0/B1/B2 calibration records under H1/H2 fit the joint parameters.
P04/P05 remain model-selection records, and P06/P07 remain held out. Hardware
P and D values are converted from XC330 Mode-5 register units to fixed SI
controller gains using the documented register divisors, encoder/velocity/
current units, and published 5 V torque constant. They are never fitted. H1
and H2 identify separate three-parameter joint candidates because each fixed
controller condition defines a different effective model context.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import matplotlib
import mujoco
import numpy as np
import pyarrow.parquet as pq
from scipy.optimize import least_squares, lsq_linear
from scipy.signal import savgol_filter

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "chapter-02" / "real-position-v2"
DEFAULT_ASSETS = ROOT / "assets" / "chapter-02" / "real-position-v2"

DT = 0.01
MODEL_DT = 0.002
TICK_TO_RAD = 2.0 * np.pi / 4096.0
VELOCITY_UNIT_RAD_S = 0.229 * 2.0 * np.pi / 60.0
CURRENT_UNIT_A = 0.001
TORQUE_CONSTANT_NM_PER_A = 0.517
POSITION_P_DIVISOR = 128.0
POSITION_D_DIVISOR = 16.0
GOAL_CURRENT_LIMIT_RAW = 300
GOAL_CURRENT_LIMIT_A = GOAL_CURRENT_LIMIT_RAW * CURRENT_UNIT_A
TORQUE_LIMIT_NM = GOAL_CURRENT_LIMIT_A * TORQUE_CONSTANT_NM_PER_A
GRAVITY = 9.81

JOINT_NAMES = ("armature", "damping", "frictionloss")
JOINT_UNITS = ("kg·m²", "N·m·s/rad", "N·m")
JOINT_LOWER = np.array([1.0e-5, 1.0e-4, 1.0e-4])
JOINT_UPPER = np.array([0.020, 0.100, 0.100])
OPTIMIZER_STARTS = (
    np.array([0.0007, 0.009, 0.006]),
    np.array([0.0015, 0.020, 0.015]),
    np.array([0.0080, 0.050, 0.005]),
)

RAW_GAINS = {
    "H1": {"P": 600, "I": 0, "D": 150},
    "H2": {"P": 800, "I": 0, "D": 150},
    "H3": {"P": 600, "I": 0, "D": 220},
    "H4": {"P": 300, "I": 0, "D": 60},
    "H5": {"P": 1200, "I": 0, "D": 320},
}

# Fixed engineering conversion for XC330 Current-Based Position Control
# (Operating Mode 5). The register values remain known inputs. A shared,
# published current-to-torque factor converts the controller output to joint
# torque; it is not fitted from the dynamic identification episodes.
FIXED_CONTROLLER_GAINS = {
    controller_id: (
        TORQUE_CONSTANT_NM_PER_A
        * CURRENT_UNIT_A
        * (RAW_GAINS[controller_id]["P"] / POSITION_P_DIVISOR)
        / TICK_TO_RAD,
        TORQUE_CONSTANT_NM_PER_A
        * CURRENT_UNIT_A
        * (RAW_GAINS[controller_id]["D"] / POSITION_D_DIVISOR)
        / VELOCITY_UNIT_RAD_S,
    )
    for controller_id in ("H1", "H2")
}

MEASURED_PARTS = {
    "link_mass_kg": 0.006,
    "pin_mass_each_kg": 0.004,
    "payload_mass_each_kg": 0.042,
}

# Inertias from the unchanged STL geometry before scaling to measured mass.
SOURCE_MASS_AND_IYY = {
    "link": (0.00910681137570, 3.36940436695e-5),
    "pin": (0.00310826420343, 2.48661128194e-8),
    "payload": (0.0370401701644, 7.75702177862e-6),
}

FIXTURE_RADII_M = {
    "B0": (-0.060, 0.060),
    "B1": (-0.080, 0.080),
    "B2": (-0.100, 0.100),
    "G1": (0.060, 0.100),
}

COLORS = {
    "goal": "#202020",
    "trajectory": "#d99000",
    "hardware": "#2768a8",
    "method1": "#23966f",
    "method2": "#7c55a5",
}


@dataclass(frozen=True)
class Fixture:
    fixture_id: str
    moving_mass_kg: float
    inertia_kg_m2: float
    unsigned_first_moment_kg_m: float
    signed_first_moment_kg_m: float
    maximum_gravity_torque_Nm: float
    radii_m: tuple[float, ...]


@dataclass(frozen=True)
class Episode:
    episode_id: str
    fixture_id: str
    controller_id: str
    profile_id: str
    role: str
    repeat_id: str
    time: np.ndarray
    external_goal: np.ndarray
    controller_trajectory: np.ndarray
    controller_velocity_trajectory: np.ndarray
    position: np.ndarray
    velocity: np.ndarray
    current: np.ndarray
    pwm: np.ndarray
    voltage: np.ndarray
    temperature: np.ndarray


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parquet_array(table, name: str) -> np.ndarray:
    return table.column(name).combine_chunks().to_numpy(zero_copy_only=False)


def zero_order_hold(time: np.ndarray, values: np.ndarray, grid: np.ndarray) -> np.ndarray:
    indices = np.searchsorted(time, grid, side="right") - 1
    return values[np.clip(indices, 0, values.size - 1)]


def fixture_properties() -> dict[str, Fixture]:
    link_mass = MEASURED_PARTS["link_mass_kg"]
    pin_mass = MEASURED_PARTS["pin_mass_each_kg"]
    payload_mass = MEASURED_PARTS["payload_mass_each_kg"]
    link_iyy = SOURCE_MASS_AND_IYY["link"][1] * link_mass / SOURCE_MASS_AND_IYY["link"][0]
    pin_iyy = SOURCE_MASS_AND_IYY["pin"][1] * pin_mass / SOURCE_MASS_AND_IYY["pin"][0]
    payload_iyy = SOURCE_MASS_AND_IYY["payload"][1] * payload_mass / SOURCE_MASS_AND_IYY["payload"][0]
    attached_mass = pin_mass + payload_mass
    fixtures = {
        "M0": Fixture("M0", 0.0, 0.0, 0.0, 0.0, 0.0, ()),
    }
    for fixture_id, radii in FIXTURE_RADII_M.items():
        inertia = link_iyy + sum(
            pin_iyy + payload_iyy + attached_mass * radius**2 for radius in radii
        )
        unsigned_first_moment = sum(attached_mass * radius for radius in radii)
        # The physical G1 locations are +60/+100 mm in the CAD convention. The
        # recorded bench coordinate rests toward negative q with torque off, so
        # the signed MuJoCo first moment is negative in the dataset coordinate.
        signed_first_moment = -unsigned_first_moment if fixture_id == "G1" else 0.0
        fixtures[fixture_id] = Fixture(
            fixture_id,
            link_mass + 2.0 * attached_mass,
            inertia,
            unsigned_first_moment,
            signed_first_moment,
            abs(unsigned_first_moment) * GRAVITY,
            radii,
        )
    return fixtures


def locate_campaign_root(extracted: Path) -> Path:
    candidates = [path for path in extracted.rglob("episodes") if path.is_dir()]
    run_roots = sorted(
        path.parent
        for path in candidates
        if (path.parent / "run.json").exists()
    )
    if len(run_roots) != 5:
        raise ValueError(f"Expected five run roots, found {len(run_roots)}")
    return run_roots[0].parent


def audit_archive(campaign_root: Path) -> tuple[dict, list[Path]]:
    metadata_paths = sorted(campaign_root.glob("*/episodes/*/episode.json"))
    if len(metadata_paths) != 260:
        raise ValueError(f"Expected 260 episode records, found {len(metadata_paths)}")
    roles = Counter()
    fixtures = Counter()
    controllers = Counter()
    profiles = Counter()
    gain_sets: dict[str, set[tuple[int, int, int]]] = defaultdict(set)
    mode_sets: dict[str, set[int]] = defaultdict(set)
    current_limit_sets: dict[str, set[tuple[int, int]]] = defaultdict(set)
    command_schemas = set()
    telemetry_schemas = set()
    failures = 0
    timing_failures = 0
    register_failures = 0
    hardware_error_samples = 0
    torque_disabled_samples = 0
    timing_deltas = []
    ranges = defaultdict(lambda: [np.inf, -np.inf])
    for metadata_path in metadata_paths:
        metadata = read_json(metadata_path)
        episode_dir = metadata_path.parent
        before = read_json(episode_dir / "control_table_before.json")
        command = pq.read_table(episode_dir / "command_events.parquet")
        telemetry = pq.read_table(episode_dir / "telemetry_events.parquet")
        command_schemas.add(tuple(command.schema.names))
        telemetry_schemas.add(tuple(telemetry.schema.names))
        roles[metadata["role"]] += 1
        fixtures[metadata["mechanical_configuration"]] += 1
        controllers[metadata["controller_id"]] += 1
        profiles[metadata["profile_id"]] += 1
        gain_sets[metadata["controller_id"]].add(
            (
                int(before["position_p_gain"]),
                int(before["position_i_gain"]),
                int(before["position_d_gain"]),
            )
        )
        mode_sets[metadata["controller_id"]].add(int(before["operating_mode"]))
        current_limit_sets[metadata["controller_id"]].add(
            (int(before["current_limit"]), int(before["goal_current"]))
        )
        failures += len(metadata.get("failures", []))
        timing_failures += int(not metadata["telemetry_timing_quality"]["passed"])
        register_failures += int(not metadata["critical_registers_match_before_after"])
        t_state = parquet_array(telemetry, "t_state_s").astype(float)
        timing_deltas.append(np.diff(t_state))
        hardware_error_samples += int(
            np.count_nonzero(parquet_array(telemetry, "hardware_error_status_raw"))
        )
        torque_disabled_samples += int(
            np.count_nonzero(parquet_array(telemetry, "torque_enable_raw") != 1)
        )
        for name in (
            "position_meas_rad",
            "velocity_meas_rad_s",
            "current_meas_A",
            "pwm_meas_fraction",
            "input_voltage_V",
            "temperature_C",
        ):
            values = parquet_array(telemetry, name).astype(float)
            ranges[name][0] = min(ranges[name][0], float(np.min(values)))
            ranges[name][1] = max(ranges[name][1], float(np.max(values)))
        for name in ("position_trajectory_raw", "velocity_trajectory_raw"):
            values = parquet_array(telemetry, name).astype(float)
            ranges[name][0] = min(ranges[name][0], float(np.min(values)))
            ranges[name][1] = max(ranges[name][1], float(np.max(values)))
    if len(command_schemas) != 1 or len(telemetry_schemas) != 1:
        raise ValueError("Parquet schema changes were found within the campaign")
    for controller_id, expected in RAW_GAINS.items():
        observed = gain_sets[controller_id]
        expected_tuple = (expected["P"], expected["I"], expected["D"])
        if observed != {expected_tuple}:
            raise ValueError(f"{controller_id} register mismatch: {observed}")
        if mode_sets[controller_id] != {5}:
            raise ValueError(
                f"{controller_id} is not consistently Current-Based Position Mode: "
                f"{mode_sets[controller_id]}"
            )
        if current_limit_sets[controller_id] != {
            (GOAL_CURRENT_LIMIT_RAW, GOAL_CURRENT_LIMIT_RAW)
        }:
            raise ValueError(
                f"{controller_id} current-limit mismatch: "
                f"{current_limit_sets[controller_id]}"
            )
    all_dt = np.concatenate(timing_deltas)
    return {
        "episode_count": len(metadata_paths),
        "role_counts": dict(roles),
        "fixture_counts": dict(fixtures),
        "controller_counts": dict(controllers),
        "profile_counts": dict(profiles),
        "controller_raw_gains": RAW_GAINS,
        "controller_operating_modes": {
            key: sorted(value) for key, value in mode_sets.items()
        },
        "controller_current_limit_and_goal_current_raw": {
            key: [list(item) for item in sorted(value)]
            for key, value in current_limit_sets.items()
        },
        "command_schema": list(next(iter(command_schemas))),
        "telemetry_schema": list(next(iter(telemetry_schemas))),
        "recorded_failure_count": failures,
        "timing_failure_count": timing_failures,
        "critical_register_failure_count": register_failures,
        "hardware_error_sample_count": hardware_error_samples,
        "torque_disabled_sample_count_inside_episode": torque_disabled_samples,
        "telemetry_interval_s": {
            "mean": float(np.mean(all_dt)),
            "median": float(np.median(all_dt)),
            "p99": float(np.quantile(all_dt, 0.99)),
            "maximum": float(np.max(all_dt)),
        },
        "raw_telemetry_ranges": dict(ranges),
    }, metadata_paths


def load_analysis_episodes(metadata_paths: list[Path]) -> list[Episode]:
    episodes = []
    for metadata_path in metadata_paths:
        metadata = read_json(metadata_path)
        if metadata["role"] not in {"calibration", "model_selection", "held_out"}:
            continue
        episode_dir = metadata_path.parent
        command = pq.read_table(episode_dir / "command_events.parquet")
        telemetry = pq.read_table(episode_dir / "telemetry_events.parquet")
        command_time = parquet_array(command, "t_command_s").astype(float)
        state_time = parquet_array(telemetry, "t_state_s").astype(float)
        active = parquet_array(command, "active_profile_sample").astype(bool)
        active_time = command_time[active]
        start = max(float(active_time[0]), float(state_time[0]))
        stop = min(float(active_time[-1]), float(state_time[-1]))
        grid_absolute = np.arange(
            math.ceil(start / DT) * DT,
            math.floor(stop / DT) * DT + DT / 2.0,
            DT,
        )
        grid = grid_absolute - grid_absolute[0]
        external_goal = zero_order_hold(
            command_time,
            parquet_array(command, "position_applied_rad").astype(float),
            grid_absolute,
        )
        position_trajectory = (
            parquet_array(telemetry, "position_trajectory_raw").astype(float) - 2048.0
        ) * TICK_TO_RAD
        velocity_trajectory = (
            parquet_array(telemetry, "velocity_trajectory_raw").astype(float)
            * VELOCITY_UNIT_RAD_S
        )
        episodes.append(
            Episode(
                metadata["episode_id"],
                metadata["mechanical_configuration"],
                metadata["controller_id"],
                metadata["profile_id"],
                metadata["role"],
                metadata.get("repeat_id") or "",
                grid,
                external_goal,
                np.interp(grid_absolute, state_time, position_trajectory),
                np.interp(grid_absolute, state_time, velocity_trajectory),
                np.interp(
                    grid_absolute,
                    state_time,
                    parquet_array(telemetry, "position_meas_rad").astype(float),
                ),
                np.interp(
                    grid_absolute,
                    state_time,
                    parquet_array(telemetry, "velocity_meas_rad_s").astype(float),
                ),
                np.interp(
                    grid_absolute,
                    state_time,
                    parquet_array(telemetry, "current_meas_A").astype(float),
                ),
                np.interp(
                    grid_absolute,
                    state_time,
                    parquet_array(telemetry, "pwm_meas_fraction").astype(float),
                ),
                np.interp(
                    grid_absolute,
                    state_time,
                    parquet_array(telemetry, "input_voltage_V").astype(float),
                ),
                np.interp(
                    grid_absolute,
                    state_time,
                    parquet_array(telemetry, "temperature_C").astype(float),
                ),
            )
        )
    return episodes


def derivative_observability(episodes: list[Episode]) -> dict:
    grouped: dict[tuple[str, str, str], list[Episode]] = defaultdict(list)
    for episode in episodes:
        if episode.role == "calibration":
            grouped[(episode.fixture_id, episode.profile_id, episode.controller_id)].append(episode)

    def mean_trace(group: list[Episode]) -> np.ndarray:
        count = min(len(episode.position) for episode in group)
        return np.mean([episode.position[:count] for episode in group], axis=0)

    comparisons = []
    for left, right, interpretation in (
        ("H1", "H2", "P changes 600 to 800 while D remains 150"),
        ("H1", "H3", "D changes 150 to 220 while P remains 600"),
    ):
        differences = []
        for fixture_id in ("M0", "B0", "B1", "B2"):
            for profile_id in (
                "P01_slow_triangle",
                "P02_multisine",
                "P03_smooth_levels",
            ):
                first = mean_trace(grouped[(fixture_id, profile_id, left)])
                second = mean_trace(grouped[(fixture_id, profile_id, right)])
                count = min(first.size, second.size)
                differences.append(float(np.sqrt(np.mean(np.square(first[:count] - second[:count])))))
        comparisons.append(
            {
                "comparison": f"{left}_vs_{right}",
                "interpretation": interpretation,
                "combination_count": len(differences),
                "mean_output_difference_rmse_rad": float(np.mean(differences)),
                "minimum_output_difference_rmse_rad": float(np.min(differences)),
                "maximum_output_difference_rmse_rad": float(np.max(differences)),
            }
        )
    return {
        "comparisons": comparisons,
        "decision": "Retain H3-H5 as diagnostics only. Convert the recorded H1/H2 P and D values through the fixed XC330 Mode-5 SI mapping; do not fit controller gains or require one joint vector to be shared across H contexts.",
    }


class ReplayEngine:
    def __init__(
        self,
        fixtures: dict[str, Fixture],
        controller_gains: dict[str, tuple[float, float]],
    ):
        self.fixtures = fixtures
        self.controller_gains = controller_gains
        self.models: dict[tuple[str, str], mujoco.MjModel] = {}

    def _make_model(self, fixture_id: str, controller_id: str) -> mujoco.MjModel:
        fixture = self.fixtures[fixture_id]
        mass = max(fixture.moving_mass_kg, 1.0e-6)
        x_com = fixture.signed_first_moment_kg_m / mass
        central_iyy = max(fixture.inertia_kg_m2 - mass * x_com**2, 1.0e-12)
        central_ixx = max(0.55 * central_iyy, 1.0e-12)
        central_izz = max(0.55 * central_iyy, 1.0e-12)
        xml = f"""
<mujoco model="xc330-hardware-effective">
  <compiler angle="radian"/>
  <option timestep="{MODEL_DT}" integrator="implicitfast" gravity="0 0 -9.81"/>
  <worldbody>
    <body name="fixture">
      <joint name="actuator_joint" type="hinge" axis="0 1 0" range="-2 2"
             armature="{OPTIMIZER_STARTS[0][0]}"
             damping="{OPTIMIZER_STARTS[0][1]}"
             frictionloss="{OPTIMIZER_STARTS[0][2]}"/>
      <inertial mass="{mass}" pos="{x_com} 0 0"
                diaginertia="{central_ixx} {central_iyy} {central_izz}"/>
    </body>
  </worldbody>
  <actuator>
    <motor name="mode5_controller_torque" joint="actuator_joint" gear="1"
           ctrllimited="true" ctrlrange="{-TORQUE_LIMIT_NM} {TORQUE_LIMIT_NM}"
           forcelimited="true" forcerange="{-TORQUE_LIMIT_NM} {TORQUE_LIMIT_NM}"/>
  </actuator>
</mujoco>
"""
        return mujoco.MjModel.from_xml_string(xml)

    def replay(
        self,
        episode: Episode,
        joint: np.ndarray,
    ) -> np.ndarray:
        key = (episode.fixture_id, episode.controller_id)
        if key not in self.models:
            self.models[key] = self._make_model(*key)
        model = self.models[key]
        data = mujoco.MjData(model)
        model.dof_armature[0] = float(joint[0])
        model.dof_damping[0] = float(joint[1])
        model.dof_frictionloss[0] = float(joint[2])
        mujoco.mj_setConst(model, data)
        position_reference = episode.controller_trajectory
        velocity_reference = episode.controller_velocity_trajectory
        kp, kv = self.controller_gains[episode.controller_id]
        data.qpos[0] = float(episode.position[0])
        data.qvel[0] = float(episode.velocity[0])
        data.ctrl[0] = float(
            np.clip(
                kp * (position_reference[0] - data.qpos[0])
                + kv * (velocity_reference[0] - data.qvel[0]),
                -TORQUE_LIMIT_NM,
                TORQUE_LIMIT_NM,
            )
        )
        mujoco.mj_forward(model, data)
        output = np.empty(position_reference.size)
        output[0] = data.qpos[0]
        substeps = round(DT / MODEL_DT)
        for index in range(1, position_reference.size):
            for _ in range(substeps):
                data.ctrl[0] = float(
                    np.clip(
                        kp * (position_reference[index - 1] - data.qpos[0])
                        + kv * (velocity_reference[index - 1] - data.qvel[0]),
                        -TORQUE_LIMIT_NM,
                        TORQUE_LIMIT_NM,
                    )
                )
                mujoco.mj_step(model, data)
            output[index] = data.qpos[0]
        return output


def calibration_subset(episodes: list[Episode], controller_id: Optional[str] = None) -> list[Episode]:
    return [
        episode
        for episode in episodes
        if episode.role == "calibration"
        and episode.fixture_id in {"M0", "B0", "B1", "B2"}
        and episode.controller_id in {"H1", "H2"}
        and (controller_id is None or episode.controller_id == controller_id)
    ]


def fit_method1(
    episodes: list[Episode],
    fixtures: dict[str, Fixture],
    gains: dict[str, tuple[float, float]],
    controller_id: Optional[str] = None,
) -> tuple[np.ndarray, dict]:
    blocks_x = []
    blocks_y = []
    windows_by_episode = {}
    for episode in calibration_subset(episodes, controller_id):
        position = savgol_filter(episode.position, 21, 3, mode="interp")
        velocity = savgol_filter(episode.velocity, 21, 3, mode="interp")
        kp, kv = gains[episode.controller_id]
        effort = np.clip(
            kp * (episode.controller_trajectory - position)
            + kv * (episode.controller_velocity_trajectory - velocity),
            -TORQUE_LIMIT_NM,
            TORQUE_LIMIT_NM,
        )
        rows = []
        response = []
        integration_window = 50
        integration_step = 10
        margin = 12
        for start in range(
            margin,
            position.size - integration_window - margin,
            integration_step,
        ):
            end = start + integration_window
            sample = slice(start, end + 1)
            moving = np.abs(velocity[sample]) >= 0.04
            if float(np.mean(moving)) < 0.40:
                continue
            delta_velocity = float(velocity[end] - velocity[start])
            delta_position = float(position[end] - position[start])
            direction_integral = float(
                np.trapezoid(
                    np.where(moving, np.sign(velocity[sample]), 0.0),
                    episode.time[sample],
                )
            )
            effort_integral = float(np.trapezoid(effort[sample], episode.time[sample]))
            rows.append([delta_velocity, delta_position, direction_integral])
            response.append(
                effort_integral
                - fixtures[episode.fixture_id].inertia_kg_m2 * delta_velocity
            )
        design = np.asarray(rows)
        target = np.asarray(response)
        if target.size == 0:
            raise ValueError(f"No qualified Method 1 windows in {episode.episode_id}")
        weight = 1.0 / math.sqrt(target.size)
        blocks_x.append(design * weight)
        blocks_y.append(target * weight)
        windows_by_episode[episode.episode_id] = int(target.size)
    design = np.vstack(blocks_x)
    target = np.concatenate(blocks_y)
    result = lsq_linear(design, target, bounds=(JOINT_LOWER, JOINT_UPPER))
    residual = design @ result.x - target
    scaled = design * np.array([0.001, 0.070, 0.005])
    diagnostics = {
        "solver_success": bool(result.success),
        "weighted_design_rank": int(np.linalg.matrix_rank(design)),
        "scaled_design_condition_number": float(np.linalg.cond(scaled)),
        "qualified_window_count": int(sum(windows_by_episode.values())),
        "parameter_lower_bounds": JOINT_LOWER.tolist(),
        "parameter_upper_bounds": JOINT_UPPER.tolist(),
        "active_bound_mask": result.active_mask.tolist(),
        "integrated_balance_rmse_Nm_s": float(
            np.sqrt(np.sum(np.square(residual)) / len(blocks_y))
        ),
        "windows_by_episode": windows_by_episode,
    }
    return result.x, diagnostics


def method2_residual(
    values: np.ndarray,
    episodes: list[Episode],
    engine: ReplayEngine,
    stride: int = 4,
) -> np.ndarray:
    blocks = []
    for episode in episodes:
        prediction = engine.replay(episode, values)
        retained = np.arange(0, prediction.size, stride)
        blocks.append(
            (prediction[retained] - episode.position[retained])
            / math.sqrt(retained.size)
        )
    return np.concatenate(blocks)


def fit_method2(
    episodes: list[Episode],
    engine: ReplayEngine,
    controller_id: Optional[str] = None,
    multi_start: bool = True,
) -> tuple[np.ndarray, dict]:
    selected = calibration_subset(episodes, controller_id)
    starts = list(OPTIMIZER_STARTS)
    if not multi_start:
        starts = starts[:1]
    runs = []
    for start in starts:
        result = least_squares(
            lambda values: method2_residual(values, selected, engine),
            start,
            bounds=(JOINT_LOWER, JOINT_UPPER),
            max_nfev=60,
            x_scale="jac",
            xtol=1.0e-8,
            ftol=1.0e-8,
            gtol=1.0e-8,
        )
        residual = method2_residual(result.x, selected, engine)
        objective = float(
            np.sqrt(np.sum(np.square(residual)) / len(selected))
        )
        runs.append((objective, result))
    objective, selected_result = min(runs, key=lambda item: item[0])
    diagnostics = {
        "calibration_output_gap_rmse_rad": objective,
        "episode_count": len(selected),
        "sample_stride": 4,
        "solver_success": bool(selected_result.success),
        "solver_message": str(selected_result.message),
        "selected_function_evaluations": int(selected_result.nfev),
        "parameter_lower_bounds": JOINT_LOWER.tolist(),
        "parameter_upper_bounds": JOINT_UPPER.tolist(),
        "active_bound_mask": selected_result.active_mask.tolist(),
        "starts": [start.tolist() for start in starts],
        "runs": [
            {
                "start": start.tolist(),
                "candidate": result.x.tolist(),
                "objective_rmse_rad": score,
                "function_evaluations": int(result.nfev),
                "success": bool(result.success),
            }
            for start, (score, result) in zip(starts, runs)
        ],
    }
    return selected_result.x, diagnostics


def rmse(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def evaluate(
    episodes: list[Episode],
    engine: ReplayEngine,
    candidates: dict[str, dict[str, np.ndarray]],
) -> tuple[list[dict], list[dict], dict[str, dict[str, np.ndarray]]]:
    rows = []
    traces: dict[str, dict[str, np.ndarray]] = defaultdict(dict)
    for candidate_id, values_by_controller in candidates.items():
        for episode in episodes:
            if episode.controller_id not in {"H1", "H2"}:
                continue
            prediction = engine.replay(
                episode, values_by_controller[episode.controller_id]
            )
            traces[candidate_id][episode.episode_id] = prediction
            rows.append(
                {
                    "candidate": candidate_id,
                    "episode_id": episode.episode_id,
                    "split": episode.role,
                    "controller_id": episode.controller_id,
                    "fixture_id": episode.fixture_id,
                    "profile_id": episode.profile_id,
                    "repeat_id": episode.repeat_id,
                    "output_gap_rmse_rad": rmse(prediction - episode.position),
                    "output_gap_mae_rad": float(np.mean(np.abs(prediction - episode.position))),
                    "output_gap_max_abs_rad": float(np.max(np.abs(prediction - episode.position))),
                    "hardware_external_tracking_rmse_rad": rmse(
                        episode.position - episode.external_goal
                    ),
                    "hardware_inner_tracking_rmse_rad": rmse(
                        episode.position - episode.controller_trajectory
                    ),
                }
            )
    aggregate = []
    for controller_id in ("H1", "H2"):
        for candidate_id in candidates:
            for split in ("calibration", "model_selection", "held_out"):
                selected = [
                    row
                    for row in rows
                    if row["candidate"] == candidate_id
                    and row["controller_id"] == controller_id
                    and row["split"] == split
                ]
                gap = float(
                    np.mean([row["output_gap_rmse_rad"] for row in selected])
                )
                aggregate.append(
                    {
                        "controller_id": controller_id,
                        "candidate": candidate_id,
                        "split": split,
                        "episode_count": len(selected),
                        "equal_episode_output_gap_rmse_rad": gap,
                    }
                )
    return rows, aggregate, traces


def repeatability(episodes: list[Episode]) -> list[dict]:
    groups: dict[tuple[str, str, str, str], list[Episode]] = defaultdict(list)
    for episode in episodes:
        if episode.controller_id in {"H1", "H2"}:
            groups[
                (
                    episode.fixture_id,
                    episode.controller_id,
                    episode.profile_id,
                    episode.role,
                )
            ].append(episode)
    rows = []
    for split in ("calibration", "model_selection", "held_out"):
        deviations = []
        for key, group in groups.items():
            if key[3] != split:
                continue
            count = min(episode.position.size for episode in group)
            mean = np.mean([episode.position[:count] for episode in group], axis=0)
            deviations.extend(
                rmse(episode.position[:count] - mean) for episode in group
            )
        rows.append(
            {
                "split": split,
                "repeat_count": len(deviations),
                "mean_repeat_to_combination_mean_rmse_rad": float(np.mean(deviations)),
                "standard_deviation_rad": float(np.std(deviations)),
                "maximum_rmse_rad": float(np.max(deviations)),
            }
        )
    return rows


def fixture_split_metrics(episode_metrics: list[dict]) -> list[dict]:
    rows = []
    keys = sorted(
        {
            (
                row["controller_id"],
                row["candidate"],
                row["split"],
                row["fixture_id"],
            )
            for row in episode_metrics
        }
    )
    for controller_id, candidate, split, fixture_id in keys:
        selected = [
            row
            for row in episode_metrics
            if row["controller_id"] == controller_id
            and row["candidate"] == candidate
            and row["split"] == split
            and row["fixture_id"] == fixture_id
        ]
        rows.append(
            {
                "controller_id": controller_id,
                "candidate": candidate,
                "split": split,
                "fixture_id": fixture_id,
                "episode_count": len(selected),
                "equal_episode_output_gap_rmse_rad": float(
                    np.mean([row["output_gap_rmse_rad"] for row in selected])
                ),
            }
        )
    return rows


def parameter_rows(
    method1: dict[str, np.ndarray],
    method2: dict[str, np.ndarray],
) -> list[dict]:
    rows = []
    for index, (name, unit) in enumerate(zip(JOINT_NAMES, JOINT_UNITS)):
        rows.append(
            {
                "parameter": name,
                "unit": unit,
                "method1_H1": float(method1["H1"][index]),
                "method2_H1": float(method2["H1"][index]),
                "method1_vs_method2_H1_symmetric_difference_percent": float(
                    200.0
                    * abs(method1["H1"][index] - method2["H1"][index])
                    / (abs(method1["H1"][index]) + abs(method2["H1"][index]))
                ),
                "method1_H2": float(method1["H2"][index]),
                "method2_H2": float(method2["H2"][index]),
                "method1_vs_method2_H2_symmetric_difference_percent": float(
                    200.0
                    * abs(method1["H2"][index] - method2["H2"][index])
                    / (abs(method1["H2"][index]) + abs(method2["H2"][index]))
                ),
            }
        )
    return rows


def plot_input_boundaries(episode: Episode, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 8.0), constrained_layout=True)
    axes[0, 0].plot(episode.time, episode.external_goal, "--", color=COLORS["goal"], label="External Goal Position")
    axes[0, 0].plot(episode.time, episode.controller_trajectory, color=COLORS["trajectory"], label="Internal Position Trajectory")
    axes[0, 0].plot(episode.time, episode.position, color=COLORS["hardware"], label="Measured Position")
    axes[0, 0].set(title="Position Boundaries", xlabel="Time (s)", ylabel="Position (rad)")
    axes[0, 1].plot(
        episode.time,
        episode.position - episode.external_goal,
        color=COLORS["goal"],
        label=f"External tracking RMSE {rmse(episode.position - episode.external_goal):.4f} rad",
    )
    axes[0, 1].plot(
        episode.time,
        episode.position - episode.controller_trajectory,
        color=COLORS["trajectory"],
        label=f"Inner tracking RMSE {rmse(episode.position - episode.controller_trajectory):.4f} rad",
    )
    axes[0, 1].axhline(0.0, color="#777777", linewidth=0.8)
    axes[0, 1].set(title="Position Tracking Errors", xlabel="Time (s)", ylabel="Error (rad)")
    axes[1, 0].plot(
        episode.time,
        episode.controller_velocity_trajectory,
        color=COLORS["trajectory"],
        label="Internal Velocity Trajectory",
    )
    axes[1, 0].plot(
        episode.time,
        episode.velocity,
        color=COLORS["hardware"],
        label="Measured Velocity",
    )
    axes[1, 0].set(title="Velocity Boundary", xlabel="Time (s)", ylabel="Velocity (rad/s)")
    velocity_error = episode.velocity - episode.controller_velocity_trajectory
    axes[1, 1].plot(
        episode.time,
        velocity_error,
        color=COLORS["trajectory"],
        label=f"Velocity error RMSE {rmse(velocity_error):.4f} rad/s",
    )
    axes[1, 1].axhline(0.0, color="#777777", linewidth=0.8)
    axes[1, 1].set(title="Velocity Tracking Error", xlabel="Time (s)", ylabel="Error (rad/s)")
    for axis in axes.flat:
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)
    fig.suptitle(f"Hardware Input Contract — {episode.episode_id}")
    fig.savefig(output_dir / "hardware-input-boundaries.png", dpi=180)
    plt.close(fig)


def plot_heldout(
    episode: Episode,
    traces: dict[str, dict[str, np.ndarray]],
    output_dir: Path,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.6), constrained_layout=True)
    axes[0].plot(episode.time, episode.controller_trajectory, "--", color=COLORS["trajectory"], label="Controller Position Trajectory")
    axes[0].plot(episode.time, episode.position, color=COLORS["hardware"], linewidth=2.0, label="Hardware Output")
    for candidate_id, label in (
        ("method1", "Real-Position M1 Candidate"),
        ("method2", "Real-Position M2 Candidate"),
    ):
        prediction = traces[candidate_id][episode.episode_id]
        axes[0].plot(
            episode.time,
            prediction,
            color=COLORS[candidate_id],
            label=f"{label} ({rmse(prediction - episode.position):.4f} rad)",
        )
        axes[1].plot(
            episode.time,
            prediction - episode.position,
            color=COLORS[candidate_id],
            label=f"{label} gap",
        )
    axes[0].set(title="Input and Outputs", xlabel="Time (s)", ylabel="Position (rad)")
    axes[1].set(title="Output-to-Hardware Gap", xlabel="Time (s)", ylabel="Gap (rad)")
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8)
    fig.suptitle(f"Held-Out Replay — {episode.episode_id}")
    fig.savefig(output_dir / "heldout-g1-replay.png", dpi=180)
    plt.close(fig)


def plot_split_metrics(aggregate: list[dict], output_dir: Path) -> None:
    lookup = {
        (row["controller_id"], row["candidate"], row["split"]): row[
            "equal_episode_output_gap_rmse_rad"
        ]
        for row in aggregate
    }
    splits = ("calibration", "model_selection", "held_out")
    x = np.arange(len(splits))
    width = 0.34
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.7), constrained_layout=True)
    for axis, controller_id in zip(axes, ("H1", "H2")):
        for offset, candidate_id, label in (
            (-width / 2.0, "method1", "Real-Position M1 Candidate"),
            (width / 2.0, "method2", "Real-Position M2 Candidate"),
        ):
            axis.bar(
                x + offset,
                [lookup[(controller_id, candidate_id, split)] for split in splits],
                width,
                color=COLORS[candidate_id],
                label=label,
            )
        axis.set_xticks(x, ["Calibration", "Model Selection", "Held Out"])
        axis.set_ylabel("Equal-Episode Output-Gap RMSE (rad)")
        kp, kv = FIXED_CONTROLLER_GAINS[controller_id]
        axis.set_title(f"{controller_id} — fixed $K_p^C$={kp:.3f}, $K_v^C$={kv:.3f}")
        axis.grid(axis="y", alpha=0.25)
        axis.legend(fontsize=8)
    fig.suptitle("Independent Real-Position Behavioral Gaps")
    fig.savefig(output_dir / "split-output-gap.png", dpi=180)
    plt.close(fig)


def plot_parameters(rows: list[dict], output_dir: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 8.0), constrained_layout=True)
    labels = ("Method 1", "Method 2")
    colors = (COLORS["method1"], COLORS["method2"])
    for axis_row, controller_id in zip(axes, ("H1", "H2")):
        for axis, row in zip(axis_row, rows):
            values = (
                row[f"method1_{controller_id}"],
                row[f"method2_{controller_id}"],
            )
            bars = axis.bar(labels, values, color=colors)
            axis.set_title(f"{controller_id} — {row['parameter']}")
            axis.set_ylabel(row["unit"])
            axis.grid(axis="y", alpha=0.25)
            axis.bar_label(
                bars,
                labels=[f"{value:.6g}" for value in values],
                fontsize=8,
            )
    fig.suptitle("Independent Context-Bounded MuJoCo Joint Candidates")
    fig.savefig(output_dir / "parameter-comparison.png", dpi=180)
    plt.close(fig)


def fixture_rows(fixtures: dict[str, Fixture]) -> list[dict]:
    rows = []
    for fixture_id in ("M0", "B0", "B1", "B2", "G1"):
        fixture = fixtures[fixture_id]
        rows.append(
            {
                "fixture_id": fixture_id,
                "payload_center_positions_mm": ", ".join(f"{1000*r:+.0f}" for r in fixture.radii_m) or "none",
                "link_mass_kg": 0.0 if fixture_id == "M0" else MEASURED_PARTS["link_mass_kg"],
                "pin_mass_each_kg": 0.0 if fixture_id == "M0" else MEASURED_PARTS["pin_mass_each_kg"],
                "payload_mass_each_kg": 0.0 if fixture_id == "M0" else MEASURED_PARTS["payload_mass_each_kg"],
                "total_added_moving_mass_kg": fixture.moving_mass_kg,
                "fixture_inertia_kg_m2": fixture.inertia_kg_m2,
                "unsigned_first_moment_kg_m": fixture.unsigned_first_moment_kg_m,
                "signed_MuJoCo_first_moment_kg_m": fixture.signed_first_moment_kg_m,
                "maximum_gravity_torque_Nm": fixture.maximum_gravity_torque_Nm,
            }
        )
    return rows


def write_readme(output: Path, result: dict) -> None:
    held = {
        (row["controller_id"], row["candidate"]): row
        for row in result["aggregate_metrics"]
        if row["split"] == "held_out"
    }
    repeatability_floor = {
        row["split"]: row["mean_repeat_to_combination_mean_rmse_rad"]
        for row in result["repeatability"]
    }["held_out"]
    text = f"""# XC330 Real-Position Identification Results v2

This directory is generated by `scripts/run_chapter02_real_position_identification_v2.py` from the immutable source archive recorded in `result.json`.

The analysis uses H1/H2 M0/B0/B1/B2 active calibration segments, P04/P05 model-selection segments, and all 30 active held-out repeats. External Goal Position is preserved as the application-facing command. The recorded DYNAMIXEL Position Trajectory and Velocity Trajectory drive a fixed Current-Based Position controller in MuJoCo. Post-return and preparation commands are excluded through the recorded `active_profile_sample` flag.

| Controller Context | Identified Model | Held-Out Output-Gap RMSE | Gap / Repeatability Floor |
| --- | --- | ---: | ---: |
| H1: P/D = 600/150 | Real-Position M1 Candidate | {held[('H1', 'method1')]['equal_episode_output_gap_rmse_rad']:.6f} rad | {held[('H1', 'method1')]['equal_episode_output_gap_rmse_rad'] / repeatability_floor:.1f}× |
| H1: P/D = 600/150 | Real-Position M2 Candidate | {held[('H1', 'method2')]['equal_episode_output_gap_rmse_rad']:.6f} rad | {held[('H1', 'method2')]['equal_episode_output_gap_rmse_rad'] / repeatability_floor:.1f}× |
| H2: P/D = 800/150 | Real-Position M1 Candidate | {held[('H2', 'method1')]['equal_episode_output_gap_rmse_rad']:.6f} rad | {held[('H2', 'method1')]['equal_episode_output_gap_rmse_rad'] / repeatability_floor:.1f}× |
| H2: P/D = 800/150 | Real-Position M2 Candidate | {held[('H2', 'method2')]['equal_episode_output_gap_rmse_rad']:.6f} rad | {held[('H2', 'method2')]['equal_episode_output_gap_rmse_rad'] / repeatability_floor:.1f}× |

The hardware register values are not copied numerically. They are converted through a fixed, declared XC330 Mode-5 engineering map using the documented P/D divisors, encoder and velocity units, the 1 mA current unit, and the published 5 V torque/current ratio. This gives H1 $$K_p^C={FIXED_CONTROLLER_GAINS['H1'][0]:.6f}$$ N·m/rad and H2 $$K_p^C={FIXED_CONTROLLER_GAINS['H2'][0]:.6f}$$ N·m/rad, with $$K_v^C={FIXED_CONTROLLER_GAINS['H1'][1]:.6f}$$ N·m·s/rad for both. The controller coefficients and the 0.1551 N·m current-derived effort limit are fixed; none is fitted.

H1 and H2 produce independent context-bounded joint candidates and are never forced to share one vector. There is no nominal model in the Real-Position study and no gap-reduction claim against an arbitrary starting vector. Method 2's starting vectors are optimizer initializations only. Acceptance is based on each identified model's absolute calibration, model-selection, and held-out model-to-hardware gap, with repeatability reported as context rather than as a baseline model.
"""
    (output / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path, help="XC330 hardware episode ZIP")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--quick", action="store_true", help="Use one Method 2 start")
    args = parser.parse_args()
    archive = args.archive.resolve()
    if not archive.exists():
        raise FileNotFoundError(archive)
    args.output.mkdir(parents=True, exist_ok=True)
    args.assets.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phyintel-hardware-v2-") as temporary:
        extracted = Path(temporary)
        with zipfile.ZipFile(archive) as handle:
            handle.extractall(extracted)
        campaign_root = locate_campaign_root(extracted)
        audit, metadata_paths = audit_archive(campaign_root)
        fixtures = fixture_properties()
        episodes = load_analysis_episodes(metadata_paths)
        derivative = derivative_observability(episodes)
        engine = ReplayEngine(fixtures, FIXED_CONTROLLER_GAINS)

        method1 = {}
        method1_diagnostics = {}
        method2 = {}
        method2_diagnostics = {}
        for controller_id in ("H1", "H2"):
            method1[controller_id], method1_diagnostics[controller_id] = fit_method1(
                episodes,
                fixtures,
                FIXED_CONTROLLER_GAINS,
                controller_id,
            )
            method2[controller_id], method2_diagnostics[controller_id] = fit_method2(
                episodes,
                engine,
                controller_id,
                multi_start=not args.quick,
            )
        candidates = {
            "method1": method1,
            "method2": method2,
        }
        episode_metrics, aggregate, traces = evaluate(episodes, engine, candidates)
        fixture_metrics = fixture_split_metrics(episode_metrics)
        repeatability_rows = repeatability(episodes)
        repeatability_by_split = {
            row["split"]: row["mean_repeat_to_combination_mean_rmse_rad"]
            for row in repeatability_rows
        }
        for row in aggregate:
            row["gap_to_repeatability_floor_ratio"] = (
                row["equal_episode_output_gap_rmse_rad"]
                / repeatability_by_split[row["split"]]
            )
        parameters = parameter_rows(method1, method2)

        active_primary = [
            episode for episode in episodes if episode.controller_id in {"H1", "H2"}
        ]
        coverage = Counter((episode.role, episode.controller_id) for episode in active_primary)
        result = {
            "release_id": "xc330-real-position-v2",
            "source_archive": {
                "filename": archive.name,
                "sha256": sha256(archive),
                "size_bytes": archive.stat().st_size,
            },
            "evidence_status": "retrospective preliminary hardware evidence",
            "methodological_decisions": {
                "primary_external_input": "transmitted Goal Position, retained for application-interface tracking",
                "identified_model_input": "recorded DYNAMIXEL Position and Velocity Trajectories, replayed through a fixed torque-limited Mode-5-equivalent controller",
                "excluded_command_phases": "all command records with active_profile_sample=false",
                "controller_gain_treatment": {
                    "policy": "known and fixed; no controller gain identification",
                    "mapping": "declared XC330 Mode-5 engineering conversion from raw P/D registers to SI-scale equivalent controller coefficients",
                    "formula_kp": "Kt * current_unit * (P/128) / position_unit",
                    "formula_kv": "Kt * current_unit * (D/16) / velocity_unit",
                    "position_unit_rad_per_count": TICK_TO_RAD,
                    "velocity_unit_rad_s_per_count": VELOCITY_UNIT_RAD_S,
                    "current_unit_A_per_count": CURRENT_UNIT_A,
                    "torque_constant_Nm_per_A_at_5V": TORQUE_CONSTANT_NM_PER_A,
                    "H1": {"kp": FIXED_CONTROLLER_GAINS["H1"][0], "kv": FIXED_CONTROLLER_GAINS["H1"][1]},
                    "H2": {"kp": FIXED_CONTROLLER_GAINS["H2"][0], "kv": FIXED_CONTROLLER_GAINS["H2"][1]},
                },
                "effort_limit_Nm": TORQUE_LIMIT_NM,
                "effort_limit_mapping": "Goal Current/Current Limit 300 counts * 0.001 A/count * 0.517 N·m/A",
                "effort_limit_qualification": "fixed published 5 V static conversion; not a measured torque trace or an identified parameter",
                "joint_target": JOINT_NAMES,
                "joint_sharing_policy": "none; H1 and H2 identify independent context-bounded three-parameter vectors",
                "nominal_model_policy": "none in the Real-Position study; Method 2 start vectors are numerical optimizer initializations only",
            },
            "fixture_mass_properties": fixture_rows(fixtures),
            "archive_audit": audit,
            "analysis_episode_count": len(episodes),
            "primary_H1_H2_episode_count": len(active_primary),
            "primary_coverage": {
                f"{role}/{controller}": count
                for (role, controller), count in sorted(coverage.items())
            },
            "derivative_observability": derivative,
            "joint_parameters": {
                "method1_H1": dict(zip(JOINT_NAMES, method1["H1"].tolist())),
                "method2_H1": dict(zip(JOINT_NAMES, method2["H1"].tolist())),
                "method1_H2": dict(zip(JOINT_NAMES, method1["H2"].tolist())),
                "method2_H2": dict(zip(JOINT_NAMES, method2["H2"].tolist())),
            },
            "method1_diagnostics": method1_diagnostics,
            "method2_diagnostics": method2_diagnostics,
            "aggregate_metrics": aggregate,
            "fixture_split_metrics": fixture_metrics,
            "repeatability": repeatability_rows,
            "acceptance": {
                "behavioral_test": "evaluate each H/method candidate by its absolute model-to-hardware output gap on calibration, model-selection, and held-out episodes",
                "nominal_baseline": "not used",
                "controller_gain_identification": "not performed",
                "cross_controller_parameter_sharing": "not performed",
                "parameter_interpretation": "controller-context-bounded MuJoCo-equivalent joint parameters",
                "current_decision": "retain Method 2 H1/H2 as promising retrospective balanced-fixture candidates; do not accept G1 transfer or the final chapter-level Sim2Real claim",
                "prospective_final_claim": "not permitted because the trajectory adapter and controller representation were finalized after collection",
            },
        }

        write_json(args.output / "result.json", result)
        write_json(args.output / "archive-audit.json", audit)
        write_json(args.output / "derivative-observability.json", derivative)
        write_csv(args.output / "fixture-mass-properties.csv", fixture_rows(fixtures))
        write_csv(
            args.output / "fixed-controller-conditions.csv",
            [
                {
                    "controller_id": controller_id,
                    "position_p_gain_raw": RAW_GAINS[controller_id]["P"],
                    "position_i_gain_raw": RAW_GAINS[controller_id]["I"],
                    "position_d_gain_raw": RAW_GAINS[controller_id]["D"],
                    "operating_mode": 5,
                    "position_p_divisor": POSITION_P_DIVISOR,
                    "position_d_divisor": POSITION_D_DIVISOR,
                    "position_unit_rad_per_count": TICK_TO_RAD,
                    "velocity_unit_rad_s_per_count": VELOCITY_UNIT_RAD_S,
                    "current_unit_A_per_count": CURRENT_UNIT_A,
                    "published_torque_constant_Nm_per_A_at_5V": TORQUE_CONSTANT_NM_PER_A,
                    "fixed_MuJoCo_kp": FIXED_CONTROLLER_GAINS[controller_id][0],
                    "fixed_MuJoCo_kv": FIXED_CONTROLLER_GAINS[controller_id][1],
                    "current_limit_raw": GOAL_CURRENT_LIMIT_RAW,
                    "fixed_effort_limit_Nm": TORQUE_LIMIT_NM,
                    "mapping_status": "fixed Mode-5 engineering conversion; no gain fitted",
                }
                for controller_id in ("H1", "H2")
            ],
        )
        write_csv(args.output / "joint-parameter-estimates.csv", parameters)
        write_csv(args.output / "episode-metrics.csv", episode_metrics)
        write_csv(args.output / "aggregate-metrics.csv", aggregate)
        write_csv(args.output / "fixture-split-metrics.csv", fixture_metrics)
        write_csv(args.output / "repeatability.csv", repeatability_rows)
        write_readme(args.output, result)

        representative_input = next(
            episode
            for episode in episodes
            if episode.episode_id == "B1__H1__P03_smooth_levels__R01"
        )
        representative_heldout = next(
            episode
            for episode in episodes
            if episode.episode_id == "G1__H1__P06_heldout_composite__R01"
        )
        plot_input_boundaries(representative_input, args.assets)
        plot_heldout(representative_heldout, traces, args.assets)
        plot_split_metrics(aggregate, args.assets)
        plot_parameters(parameters, args.assets)
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
