#!/usr/bin/env python3
"""Reproduce the V5 model-to-hardware comparison from the milestone packages."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import shutil
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mujoco
from mujoco import rollout
import numpy as np
import pandas as pd
import pyarrow
import scipy
from scipy.optimize import least_squares


INPUT_PACKAGE = Path(__file__).resolve().parents[1]
# A separate output root makes the hardware refit reproducible without deleting
# the published Class 04 package while a new candidate is being evaluated.
PACKAGE = Path(os.environ.get("CLASS04_REPLAY_OUTPUT", str(INPUT_PACKAGE))).resolve()
RAW_LOGS = INPUT_PACKAGE / "raw_data" / "asbrain_logs"
EPISODE_INDEX = INPUT_PACKAGE / "data" / "EPISODES_USED.csv"
TEMPLATE_MODELS = INPUT_PACKAGE / "models" / "Synthetic_Baseline" / "H1"
TEMPLATE_ASSETS = INPUT_PACKAGE / "models" / "assets"

MODELS = PACKAGE / "01_Models"
HARDWARE = PACKAGE / "02_Hardware_Data"
METHOD = PACKAGE / "03_Method"
RESULTS = PACKAGE / "04_Results"
PLOTS = PACKAGE / "05_Plots"
CONCLUSIONS = PACKAGE / "07_Conclusions"
VALIDATION = PACKAGE / "08_Validation"

TIME_ZONE = ZoneInfo("Asia/Dubai")
PREPARED_BY = "Mohamad Halwani"
PHYSICS_TIMESTEP_S = 0.002
FIT_SAMPLE_STRIDE = 5
POSITION_RESOLUTION_RAD = 2.0 * math.pi / 4096.0
VELOCITY_RESOLUTION_RAD_S = 0.229 * 2.0 * math.pi / 60.0
EFFORT_LIMIT_NM = 0.1551

PARAMETER_NAMES = (
    "armature_kg_m2",
    "damping_Nm_s_per_rad",
    "frictionloss_Nm",
)
LOWER = np.array([0.0002, 0.003, 0.002], dtype=float)
UPPER = np.array([0.010, 0.150, 0.050], dtype=float)
STARTS = {
    "S1_nominal": np.array([0.0007, 0.009, 0.006], dtype=float),
    "S2_low": np.array([0.0003, 0.005, 0.003], dtype=float),
    "S3_middle": np.array([0.0051, 0.0765, 0.026], dtype=float),
    "S4_high": np.array([0.0085, 0.130, 0.044], dtype=float),
}
CONTROLLERS = {
    "H1": {
        "position_p_gain_raw": 600,
        "position_i_gain_raw": 0,
        "position_d_gain_raw": 150,
        "kp_Nm_per_rad": 1.579836,
        "kv_Nm_s_per_rad": 0.202115,
    },
    "H2": {
        "position_p_gain_raw": 800,
        "position_i_gain_raw": 0,
        "position_d_gain_raw": 150,
        "kp_Nm_per_rad": 2.106448,
        "kv_Nm_s_per_rad": 0.202115,
    },
}
EXPECTED_COUNTS = {
    "calibration": {"H1": 36, "H2": 36},
    "model_selection": {"H1": 12, "H2": 12},
    "held_out": {"H1": 15, "H2": 15},
}
FIXTURES = ("M0", "B0", "B1", "B2", "G1")


@dataclass(frozen=True)
class Episode:
    episode_id: str
    split: str
    fixture_id: str
    controller_id: str
    profile_id: str
    repetition: str
    source_directory: str
    time_s: np.ndarray
    external_command_rad: np.ndarray
    inner_position_reference_rad: np.ndarray
    inner_velocity_reference_rad_s: np.ndarray
    hardware_position_rad: np.ndarray
    hardware_velocity_rad_s: np.ndarray
    hardware_current_A: np.ndarray
    hardware_pwm_fraction: np.ndarray
    hardware_temperature_C: np.ndarray


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def reset_generated_directories() -> None:
    python_cache = PACKAGE / "06_Reproduction" / "__pycache__"
    if python_cache.exists():
        shutil.rmtree(python_cache)
    for directory in (MODELS, HARDWARE, METHOD, RESULTS, PLOTS, CONCLUSIONS, VALIDATION):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)


def normalized(theta: np.ndarray) -> np.ndarray:
    return (theta - LOWER) / (UPPER - LOWER)


def physical(unit_vector: np.ndarray) -> np.ndarray:
    return LOWER + np.asarray(unit_vector, dtype=float) * (UPPER - LOWER)


def load_baseline_parameters() -> np.ndarray:
    result_path = INPUT_PACKAGE / "data" / "physical_parameter_sets.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    values = result["synthetic_baseline"]
    return np.array([float(values[name]) for name in PARAMETER_NAMES], dtype=float)


def selected_index_rows() -> pd.DataFrame:
    rows = pd.read_csv(EPISODE_INDEX)
    rows = rows[
        rows["role"].isin(EXPECTED_COUNTS)
        & rows["controller_id"].isin(CONTROLLERS)
    ].copy()
    rows.sort_values(
        ["role", "controller_id", "mechanical_configuration", "profile_id", "repeat_id"],
        inplace=True,
    )
    actual = {
        split: {
            controller: int(
                ((rows["role"] == split) & (rows["controller_id"] == controller)).sum()
            )
            for controller in CONTROLLERS
        }
        for split in EXPECTED_COUNTS
    }
    if actual != EXPECTED_COUNTS:
        raise ValueError(f"episode matrix mismatch: expected {EXPECTED_COUNTS}, got {actual}")
    return rows


def load_episode(row: pd.Series) -> Episode:
    source_parts = Path(str(row["package_log_directory"])).parts
    try:
        relative_parts = source_parts[source_parts.index("Original") + 1 :]
    except ValueError as exc:
        raise ValueError("raw-log path lacks Original marker") from exc
    episode_dir = RAW_LOGS.joinpath(*relative_parts).resolve()
    if not episode_dir.is_relative_to(RAW_LOGS.resolve()):
        raise ValueError(f"episode path escaped accepted raw-log root: {episode_dir}")

    command_path = episode_dir / "command_events.parquet"
    telemetry_path = episode_dir / "telemetry_events.parquet"
    command = pd.read_parquet(
        command_path,
        columns=[
            "host_write_request_ns",
            "active_profile_sample",
            "position_applied_rad",
        ],
    )
    telemetry = pd.read_parquet(
        telemetry_path,
        columns=[
            "host_rx_end_ns",
            "position_meas_rad",
            "velocity_meas_rad_s",
            "position_trajectory_raw",
            "velocity_trajectory_raw",
            "current_meas_A",
            "pwm_meas_fraction",
            "temperature_C",
        ],
    )

    active_command = command[command["active_profile_sample"].astype(bool)].copy()
    active_command.sort_values("host_write_request_ns", inplace=True)
    if active_command.empty:
        raise ValueError(f"{row['episode_id']}: no active command samples")

    start_ns = int(active_command["host_write_request_ns"].iloc[0])
    stop_ns = int(active_command["host_write_request_ns"].iloc[-1])
    telemetry = telemetry[
        (telemetry["host_rx_end_ns"] >= start_ns)
        & (telemetry["host_rx_end_ns"] <= stop_ns)
    ].copy()
    telemetry.sort_values("host_rx_end_ns", inplace=True)
    telemetry.drop_duplicates("host_rx_end_ns", keep="last", inplace=True)
    if len(telemetry) < 100:
        raise ValueError(f"{row['episode_id']}: too few active telemetry samples")

    host_ns = telemetry["host_rx_end_ns"].to_numpy(dtype=np.int64)
    if np.any(np.diff(host_ns) <= 0):
        raise ValueError(f"{row['episode_id']}: non-increasing telemetry timestamps")
    time_s = (host_ns - host_ns[0]).astype(float) * 1e-9

    command_ns = active_command["host_write_request_ns"].to_numpy(dtype=np.int64)
    command_index = np.searchsorted(command_ns, host_ns, side="right") - 1
    command_index = np.clip(command_index, 0, len(active_command) - 1)
    external_command = active_command["position_applied_rad"].to_numpy(dtype=float)[
        command_index
    ]

    arrays = {
        "external_command_rad": external_command,
        "inner_position_reference_rad": (
            telemetry["position_trajectory_raw"].to_numpy(dtype=float) - 2048.0
        )
        * POSITION_RESOLUTION_RAD,
        "inner_velocity_reference_rad_s": telemetry[
            "velocity_trajectory_raw"
        ].to_numpy(dtype=float)
        * VELOCITY_RESOLUTION_RAD_S,
        "hardware_position_rad": telemetry["position_meas_rad"].to_numpy(dtype=float),
        "hardware_velocity_rad_s": telemetry["velocity_meas_rad_s"].to_numpy(
            dtype=float
        ),
        "hardware_current_A": telemetry["current_meas_A"].to_numpy(dtype=float),
        "hardware_pwm_fraction": telemetry["pwm_meas_fraction"].to_numpy(dtype=float),
        "hardware_temperature_C": telemetry["temperature_C"].to_numpy(dtype=float),
    }
    if not all(np.all(np.isfinite(value)) for value in arrays.values()):
        raise ValueError(f"{row['episode_id']}: non-finite active data")

    return Episode(
        episode_id=str(row["episode_id"]),
        split=str(row["role"]),
        fixture_id=str(row["mechanical_configuration"]),
        controller_id=str(row["controller_id"]),
        profile_id=str(row["profile_id"]),
        repetition=str(row["repeat_id"]),
        source_directory=str(episode_dir.relative_to(INPUT_PACKAGE)),
        time_s=time_s,
        **arrays,
    )


def load_split(rows: pd.DataFrame, split: str) -> list[Episode]:
    selected = rows[rows["role"] == split]
    episodes = [load_episode(row) for _, row in selected.iterrows()]
    print(f"loaded {len(episodes)} {split} hardware episodes", flush=True)
    return episodes


class HardwareReplayer:
    def __init__(self) -> None:
        self.models: dict[str, mujoco.MjModel] = {}
        self.data: dict[str, mujoco.MjData] = {}
        self.sensor_addresses: dict[str, tuple[int, int, int]] = {}
        for fixture in FIXTURES:
            model_path = (
                TEMPLATE_MODELS / f"{fixture}.xml"
            )
            model = mujoco.MjModel.from_xml_path(str(model_path))
            data = mujoco.MjData(model)
            addresses = []
            for sensor_name in ("q", "qdot", "tau_actuator"):
                sensor_id = mujoco.mj_name2id(
                    model, mujoco.mjtObj.mjOBJ_SENSOR, sensor_name
                )
                if sensor_id < 0:
                    raise ValueError(f"{fixture}: missing sensor {sensor_name}")
                addresses.append(int(model.sensor_adr[sensor_id]))
            self.models[fixture] = model
            self.data[fixture] = data
            self.sensor_addresses[fixture] = tuple(addresses)

    def simulate(
        self, episode: Episode, theta: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        model = self.models[episode.fixture_id]
        data = self.data[episode.fixture_id]
        controller = CONTROLLERS[episode.controller_id]
        kp = float(controller["kp_Nm_per_rad"])
        kv = float(controller["kv_Nm_s_per_rad"])

        model.opt.timestep = PHYSICS_TIMESTEP_S
        model.dof_armature[0] = float(theta[0])
        model.dof_damping[0] = float(theta[1])
        model.dof_frictionloss[0] = float(theta[2])
        actuator_id = 0
        model.actuator_gainprm[actuator_id] = 0.0
        model.actuator_gainprm[actuator_id, 0] = 1.0
        model.actuator_biasprm[actuator_id] = 0.0
        model.actuator_biasprm[actuator_id, 1] = -kp
        model.actuator_biasprm[actuator_id, 2] = -kv
        model.actuator_ctrllimited[actuator_id] = 0
        model.actuator_forcelimited[actuator_id] = 1
        model.actuator_forcerange[actuator_id] = (-EFFORT_LIMIT_NM, EFFORT_LIMIT_NM)

        mujoco.mj_resetData(model, data)
        data.qpos[0] = float(episode.hardware_position_rad[0])
        data.qvel[0] = float(episode.hardware_velocity_rad_s[0])
        mujoco.mj_forward(model, data)

        step_count = int(math.ceil(float(episode.time_s[-1]) / PHYSICS_TIMESTEP_S))
        physics_time_before = np.arange(step_count, dtype=float) * PHYSICS_TIMESTEP_S
        q_reference_before = np.interp(
            physics_time_before,
            episode.time_s,
            episode.inner_position_reference_rad,
        )
        v_reference_before = np.interp(
            physics_time_before,
            episode.time_s,
            episode.inner_velocity_reference_rad_s,
        )
        control = (kp * q_reference_before + kv * v_reference_before)[:, None]

        state_size = mujoco.mj_stateSize(
            model, mujoco.mjtState.mjSTATE_FULLPHYSICS
        )
        initial_state = np.empty(state_size, dtype=float)
        mujoco.mj_getState(
            model,
            data,
            initial_state,
            mujoco.mjtState.mjSTATE_FULLPHYSICS,
        )
        _, sensor_data = rollout.rollout(model, data, initial_state, control)
        sensor_data = np.asarray(sensor_data).reshape(step_count, model.nsensordata)
        q_address, v_address, _ = self.sensor_addresses[episode.fixture_id]

        physics_time = np.arange(step_count + 1, dtype=float) * PHYSICS_TIMESTEP_S
        q_grid = np.concatenate(
            ([episode.hardware_position_rad[0]], sensor_data[:, q_address])
        )
        v_grid = np.concatenate(
            ([episode.hardware_velocity_rad_s[0]], sensor_data[:, v_address])
        )
        q_prediction = np.interp(episode.time_s, physics_time, q_grid)

        q_reference_grid = np.interp(
            physics_time, episode.time_s, episode.inner_position_reference_rad
        )
        v_reference_grid = np.interp(
            physics_time, episode.time_s, episode.inner_velocity_reference_rad_s
        )
        raw_torque = kp * (q_reference_grid - q_grid) + kv * (
            v_reference_grid - v_grid
        )
        torque_grid = np.clip(raw_torque, -EFFORT_LIMIT_NM, EFFORT_LIMIT_NM)
        torque = np.interp(episode.time_s, physics_time, torque_grid)
        saturation = (
            np.interp(
                episode.time_s,
                physics_time,
                (np.abs(raw_torque) >= EFFORT_LIMIT_NM).astype(float),
            )
            >= 0.5
        )
        if not (
            np.all(np.isfinite(q_prediction))
            and np.all(np.isfinite(torque))
            and np.max(np.abs(q_prediction)) < 2.0
        ):
            raise FloatingPointError(f"{episode.episode_id}: unstable simulation")
        return q_prediction, torque, saturation


def episode_rmse(
    replayer: HardwareReplayer, episodes: list[Episode], theta: np.ndarray
) -> float:
    values = []
    for episode in episodes:
        prediction, _, _ = replayer.simulate(episode, theta)
        values.append(
            float(
                np.sqrt(
                    np.mean((prediction - episode.hardware_position_rad) ** 2)
                )
            )
        )
    return float(np.mean(values))


def fit_one_controller(
    replayer: HardwareReplayer,
    calibration: list[Episode],
    controller_id: str,
) -> list[dict]:
    episodes = [episode for episode in calibration if episode.controller_id == controller_id]
    if len(episodes) != EXPECTED_COUNTS["calibration"][controller_id]:
        raise ValueError(f"{controller_id}: calibration count mismatch")

    cache: dict[tuple[float, ...], np.ndarray] = {}

    def objective(unit_vector: np.ndarray) -> np.ndarray:
        key = tuple(np.round(unit_vector, 12))
        if key in cache:
            return cache[key]
        theta = physical(unit_vector)
        residuals = []
        for episode in episodes:
            prediction, _, _ = replayer.simulate(episode, theta)
            sample = slice(None, None, FIT_SAMPLE_STRIDE)
            error = (
                prediction[sample] - episode.hardware_position_rad[sample]
            )
            residuals.append(100.0 * error / math.sqrt(len(error)))
        value = np.concatenate(residuals)
        cache[key] = value
        return value

    candidates = []
    for start_id, theta_start in STARTS.items():
        started = time.perf_counter()
        fit = least_squares(
            objective,
            normalized(theta_start),
            bounds=(np.zeros(3), np.ones(3)),
            method="trf",
            loss="linear",
            diff_step=0.0005,
            max_nfev=100,
            ftol=1e-8,
            xtol=1e-8,
            gtol=1e-8,
        )
        theta = physical(fit.x)
        row = {
            "controller_id": controller_id,
            "start_id": start_id,
            "success": bool(fit.success),
            "status": int(fit.status),
            "message": str(fit.message).replace("\n", " "),
            "nfev": int(fit.nfev),
            "njev": int(fit.njev) if fit.njev is not None else None,
            "cost": float(fit.cost),
            "optimality": float(fit.optimality),
            "elapsed_s": float(time.perf_counter() - started),
            "calibration_mean_episode_rmse_rad": episode_rmse(
                replayer, episodes, theta
            ),
        }
        row.update({name: float(value) for name, value in zip(PARAMETER_NAMES, theta)})
        candidates.append(row)
        print(
            f"{controller_id} {start_id}: "
            f"RMSE={row['calibration_mean_episode_rmse_rad']:.6g} rad, "
            f"nfev={row['nfev']}",
            flush=True,
        )
    return candidates


def choose_candidates(
    replayer: HardwareReplayer,
    model_selection: list[Episode],
    candidates: list[dict],
) -> dict[str, dict]:
    selected: dict[str, dict] = {}
    for controller_id in CONTROLLERS:
        episodes = [
            episode
            for episode in model_selection
            if episode.controller_id == controller_id
        ]
        if len(episodes) != EXPECTED_COUNTS["model_selection"][controller_id]:
            raise ValueError(f"{controller_id}: model-selection count mismatch")
        valid = []
        for row in candidates:
            if row["controller_id"] != controller_id:
                continue
            theta = np.array([row[name] for name in PARAMETER_NAMES], dtype=float)
            row["model_selection_mean_episode_rmse_rad"] = episode_rmse(
                replayer, episodes, theta
            )
            if row["success"] and np.isfinite(
                row["model_selection_mean_episode_rmse_rad"]
            ):
                valid.append(row)
        if not valid:
            raise RuntimeError(f"{controller_id}: no successful fit candidate")
        winner = min(
            valid, key=lambda item: item["model_selection_mean_episode_rmse_rad"]
        )
        winner["selected"] = True
        selected[controller_id] = {
            "start_id": winner["start_id"],
            **{name: winner[name] for name in PARAMETER_NAMES},
            "calibration_mean_episode_rmse_rad": winner[
                "calibration_mean_episode_rmse_rad"
            ],
            "model_selection_mean_episode_rmse_rad": winner[
                "model_selection_mean_episode_rmse_rad"
            ],
        }
        for row in candidates:
            row.setdefault("selected", False)
        print(
            f"selected {controller_id} {winner['start_id']} on model-selection RMSE "
            f"{winner['model_selection_mean_episode_rmse_rad']:.6g} rad",
            flush=True,
        )
    return selected


def metric_row(
    episode: Episode,
    model_name: str,
    prediction: np.ndarray,
    torque: np.ndarray,
    saturation: np.ndarray,
) -> dict:
    error = prediction - episode.hardware_position_rad
    sample_count = len(error)
    sse = float(np.sum(error**2))
    centered = episode.hardware_position_rad - np.mean(episode.hardware_position_rad)
    denominator = float(np.sum(centered**2))
    response_range = float(np.ptp(episode.hardware_position_rad))
    return {
        "episode_id": episode.episode_id,
        "split": episode.split,
        "fixture_id": episode.fixture_id,
        "controller_id": episode.controller_id,
        "profile_id": episode.profile_id,
        "repetition": episode.repetition,
        "model": model_name,
        "sample_count": sample_count,
        "duration_s": float(episode.time_s[-1]),
        "position_rmse_rad": float(math.sqrt(sse / sample_count)),
        "position_mae_rad": float(np.mean(np.abs(error))),
        "position_peak_abs_error_rad": float(np.max(np.abs(error))),
        "position_bias_rad": float(np.mean(error)),
        "position_r2": float(1.0 - sse / denominator)
        if denominator > 0
        else float("nan"),
        "position_nrmse_by_range": float(math.sqrt(sse / sample_count) / response_range)
        if response_range > 0
        else float("nan"),
        "sse_rad2": sse,
        "simulated_effort_peak_Nm": float(np.max(np.abs(torque))),
        "simulated_effort_saturation_fraction": float(np.mean(saturation)),
        "hardware_inner_tracking_rmse_rad": float(
            np.sqrt(
                np.mean(
                    (
                        episode.inner_position_reference_rad
                        - episode.hardware_position_rad
                    )
                    ** 2
                )
            )
        ),
        "hardware_peak_abs_current_A": float(
            np.max(np.abs(episode.hardware_current_A))
        ),
        "hardware_peak_abs_pwm_fraction": float(
            np.max(np.abs(episode.hardware_pwm_fraction))
        ),
        "hardware_max_temperature_C": float(
            np.max(episode.hardware_temperature_C)
        ),
    }


def evaluate_all(
    replayer: HardwareReplayer,
    episodes: list[Episode],
    baseline: np.ndarray,
    selected: dict[str, dict],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    metric_rows = []
    prediction_frames = []
    by_episode: dict[str, pd.DataFrame] = {}
    for number, episode in enumerate(episodes, start=1):
        fitted = np.array(
            [selected[episode.controller_id][name] for name in PARAMETER_NAMES],
            dtype=float,
        )
        baseline_q, baseline_tau, baseline_sat = replayer.simulate(episode, baseline)
        fitted_q, fitted_tau, fitted_sat = replayer.simulate(episode, fitted)
        metric_rows.extend(
            [
                metric_row(
                    episode, "synthetic_baseline", baseline_q, baseline_tau, baseline_sat
                ),
                metric_row(
                    episode, "hardware_fitted", fitted_q, fitted_tau, fitted_sat
                ),
            ]
        )
        frame = pd.DataFrame(
            {
                "episode_id": episode.episode_id,
                "split": episode.split,
                "fixture_id": episode.fixture_id,
                "controller_id": episode.controller_id,
                "profile_id": episode.profile_id,
                "repetition": episode.repetition,
                "sample_index": np.arange(len(episode.time_s), dtype=int),
                "time_s": episode.time_s,
                "external_position_command_rad": episode.external_command_rad,
                "recorded_inner_position_reference_rad": episode.inner_position_reference_rad,
                "recorded_inner_velocity_reference_rad_s": episode.inner_velocity_reference_rad_s,
                "hardware_position_rad": episode.hardware_position_rad,
                "hardware_velocity_rad_s": episode.hardware_velocity_rad_s,
                "synthetic_baseline_position_rad": baseline_q,
                "hardware_fitted_position_rad": fitted_q,
                "synthetic_baseline_effort_Nm": baseline_tau,
                "hardware_fitted_effort_Nm": fitted_tau,
                "synthetic_baseline_saturated": baseline_sat,
                "hardware_fitted_saturated": fitted_sat,
                "hardware_current_A": episode.hardware_current_A,
                "hardware_pwm_fraction": episode.hardware_pwm_fraction,
                "hardware_temperature_C": episode.hardware_temperature_C,
            }
        )
        prediction_frames.append(frame)
        by_episode[episode.episode_id] = frame
        if number % 20 == 0 or number == len(episodes):
            print(f"evaluated {number}/{len(episodes)} episodes", flush=True)
    return (
        pd.DataFrame(metric_rows),
        pd.concat(prediction_frames, ignore_index=True),
        by_episode,
    )


def summarize_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    keys = ["split", "fixture_id", "controller_id", "model"]
    for values, group in metrics.groupby(keys, sort=True):
        sample_total = int(group["sample_count"].sum())
        rows.append(
            {
                **dict(zip(keys, values)),
                "episode_count": int(len(group)),
                "sample_count": sample_total,
                "mean_episode_position_rmse_rad": float(
                    group["position_rmse_rad"].mean()
                ),
                "median_episode_position_rmse_rad": float(
                    group["position_rmse_rad"].median()
                ),
                "worst_episode_position_rmse_rad": float(
                    group["position_rmse_rad"].max()
                ),
                "pooled_position_rmse_rad": float(
                    math.sqrt(group["sse_rad2"].sum() / sample_total)
                ),
                "mean_position_mae_rad": float(group["position_mae_rad"].mean()),
                "mean_simulated_saturation_fraction": float(
                    group["simulated_effort_saturation_fraction"].mean()
                ),
            }
        )
    return pd.DataFrame(rows)


def paired_held_out(metrics: pd.DataFrame) -> pd.DataFrame:
    held = metrics[metrics["split"] == "held_out"].copy()
    index_columns = [
        "episode_id",
        "split",
        "fixture_id",
        "controller_id",
        "profile_id",
        "repetition",
        "sample_count",
        "duration_s",
    ]
    fields = [
        "position_rmse_rad",
        "position_mae_rad",
        "position_peak_abs_error_rad",
        "position_bias_rad",
        "position_r2",
        "position_nrmse_by_range",
        "simulated_effort_saturation_fraction",
    ]
    wide = held.pivot(index=index_columns, columns="model", values=fields)
    wide.columns = [f"{field}__{model}" for field, model in wide.columns]
    wide.reset_index(inplace=True)
    baseline = wide["position_rmse_rad__synthetic_baseline"]
    fitted = wide["position_rmse_rad__hardware_fitted"]
    wide["rmse_reduction_percent"] = 100.0 * (baseline - fitted) / baseline
    return wide


def create_models(
    baseline: np.ndarray, selected: dict[str, dict]
) -> list[dict]:
    assets = MODELS / "assets"
    assets.mkdir(parents=True)
    for source in sorted(TEMPLATE_ASSETS.glob("*.stl")):
        shutil.copy2(source, assets / source.name)

    model_records = []
    scopes = {
        "Synthetic_Baseline": {
            "H1": baseline,
            "H2": baseline,
        },
        "Hardware_Fitted": {
            controller: np.array(
                [selected[controller][name] for name in PARAMETER_NAMES], dtype=float
            )
            for controller in CONTROLLERS
        },
    }
    for scope, controller_values in scopes.items():
        for controller_id, theta in controller_values.items():
            controller = CONTROLLERS[controller_id]
            kp = float(controller["kp_Nm_per_rad"])
            kv = float(controller["kv_Nm_s_per_rad"])
            for fixture in FIXTURES:
                source = TEMPLATE_MODELS / f"{fixture}.xml"
                tree = ET.parse(source)
                root = tree.getroot()
                root.set("model", f"{scope.lower()}-{controller_id}-{fixture}")
                joint = root.find(".//joint[@name='actuator_joint']")
                if joint is None:
                    raise ValueError(f"{fixture}: actuator_joint not found")
                joint.set("armature", f"{theta[0]:.16g}")
                joint.set("damping", f"{theta[1]:.16g}")
                joint.set("frictionloss", f"{theta[2]:.16g}")
                for mesh in root.findall("./asset/mesh"):
                    mesh.set("file", f"../../assets/{Path(mesh.get('file', '')).name}")
                actuator = root.find("actuator")
                if actuator is None:
                    actuator = ET.SubElement(root, "actuator")
                actuator.clear()
                ET.SubElement(
                    actuator,
                    "general",
                    {
                        "name": "xc330_replay",
                        "joint": "actuator_joint",
                        "gear": "1",
                        "gainprm": "1",
                        "biastype": "affine",
                        "biasprm": f"0 {-kp:.16g} {-kv:.16g}",
                        "ctrllimited": "false",
                        "forcelimited": "true",
                        "forcerange": f"{-EFFORT_LIMIT_NM:.16g} {EFFORT_LIMIT_NM:.16g}",
                    },
                )
                sensor = root.find("sensor")
                if sensor is None:
                    sensor = ET.SubElement(root, "sensor")
                sensor.clear()
                ET.SubElement(
                    sensor,
                    "jointpos",
                    {"name": "q", "joint": "actuator_joint"},
                )
                ET.SubElement(
                    sensor,
                    "jointvel",
                    {"name": "qdot", "joint": "actuator_joint"},
                )
                ET.SubElement(
                    sensor,
                    "actuatorfrc",
                    {"name": "tau_actuator", "actuator": "xc330_replay"},
                )
                destination = MODELS / scope / controller_id / f"{fixture}.xml"
                destination.parent.mkdir(parents=True, exist_ok=True)
                ET.indent(tree, space="  ")
                tree.write(destination, encoding="utf-8", xml_declaration=False)
                model_records.append(
                    {
                        "scope": scope,
                        "controller_id": controller_id,
                        "fixture_id": fixture,
                        "path": str(destination.relative_to(PACKAGE)),
                        **{
                            name: float(value)
                            for name, value in zip(PARAMETER_NAMES, theta)
                        },
                    }
                )
    write_json(
        MODELS / "controller_conditions.json",
        {
            "controller_formula": "tau = clip(Kp*(q_trajectory-q) + Kv*(qdot_trajectory-qdot), -0.1551, +0.1551)",
            "controllers": CONTROLLERS,
            "physics_timestep_s": PHYSICS_TIMESTEP_S,
            "effort_limit_Nm": EFFORT_LIMIT_NM,
        },
    )
    write_json(
        MODELS / "physical_parameter_sets.json",
        {
            "synthetic_baseline": dict(zip(PARAMETER_NAMES, map(float, baseline))),
            "hardware_fitted": {
                controller: {
                    name: float(selected[controller][name])
                    for name in PARAMETER_NAMES
                }
                for controller in CONTROLLERS
            },
        },
    )
    return model_records


def plot_panel(
    episode_ids: list[str],
    by_episode: dict[str, pd.DataFrame],
    destination: Path,
    title: str,
) -> None:
    columns = 2
    rows = int(math.ceil(len(episode_ids) / columns))
    fig, axes = plt.subplots(rows, columns, figsize=(13, 3.2 * rows), squeeze=False)
    for axis, episode_id in zip(axes.flat, episode_ids):
        frame = by_episode[episode_id]
        axis.plot(
            frame["time_s"],
            frame["hardware_position_rad"],
            color="black",
            linewidth=1.2,
            label="hardware",
        )
        axis.plot(
            frame["time_s"],
            frame["hardware_fitted_position_rad"],
            color="#1769aa",
            linewidth=1.0,
            label="hardware-fitted simulation",
        )
        axis.plot(
            frame["time_s"],
            frame["synthetic_baseline_position_rad"],
            color="#d97706",
            linewidth=0.9,
            linestyle="--",
            label="synthetic baseline",
        )
        axis.plot(
            frame["time_s"],
            frame["recorded_inner_position_reference_rad"],
            color="#777777",
            linewidth=0.7,
            alpha=0.65,
            label="recorded inner reference",
        )
        axis.set_title(episode_id, fontsize=9)
        axis.set_xlabel("time (s)")
        axis.set_ylabel("position (rad)")
        axis.grid(alpha=0.2)
    for axis in axes.flat[len(episode_ids) :]:
        axis.set_visible(False)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, fontsize=9)
    fig.suptitle(title, fontsize=14)
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    fig.savefig(destination, dpi=170)
    plt.close(fig)


def create_plots(
    metrics: pd.DataFrame,
    held_out: pd.DataFrame,
    by_episode: dict[str, pd.DataFrame],
) -> None:
    calibration_ids = [
        f"{fixture}__{controller}__P02_multisine__R01"
        for fixture in ("M0", "B0", "B1", "B2")
        for controller in ("H1", "H2")
    ]
    selection_ids = [
        f"{fixture}__{controller}__{profile}__R01"
        for fixture in ("B0", "B2")
        for controller in ("H1", "H2")
        for profile in ("P04_chirp", "P05_wide_sine")
    ]
    held_out_ids = [
        "B1__H1__P06_heldout_composite__R01",
        "B1__H2__P06_heldout_composite__R01",
        "G1__H1__P06_heldout_composite__R01",
        "G1__H2__P06_heldout_composite__R01",
        "G1__H1__P07_heldout_sine_hold__R01",
        "G1__H2__P07_heldout_sine_hold__R01",
    ]
    plot_panel(
        calibration_ids,
        by_episode,
        PLOTS / "calibration_paired_examples.png",
        "Calibration examples: simulation and hardware",
    )
    plot_panel(
        selection_ids,
        by_episode,
        PLOTS / "model_selection_paired_examples.png",
        "Model-selection examples: simulation and hardware",
    )
    plot_panel(
        held_out_ids,
        by_episode,
        PLOTS / "held_out_paired_examples.png",
        "Held-out examples: simulation and hardware",
    )

    worst_ids = (
        held_out.sort_values(
            "position_rmse_rad__hardware_fitted", ascending=False
        )["episode_id"]
        .head(5)
        .tolist()
    )
    plot_panel(
        worst_ids,
        by_episode,
        PLOTS / "largest_held_out_errors.png",
        "Five largest held-out fitted errors",
    )

    grouped = (
        metrics.groupby(["split", "controller_id", "model"], sort=True)[
            "position_rmse_rad"
        ]
        .mean()
        .reset_index()
    )
    labels = [
        ("calibration", "H1"),
        ("calibration", "H2"),
        ("model_selection", "H1"),
        ("model_selection", "H2"),
        ("held_out", "H1"),
        ("held_out", "H2"),
    ]
    x = np.arange(len(labels), dtype=float)
    fig, axis = plt.subplots(figsize=(11, 5.2))
    for offset, (model, color, label) in enumerate(
        (
            ("synthetic_baseline", "#d97706", "synthetic baseline"),
            ("hardware_fitted", "#1769aa", "hardware-fitted simulation"),
        )
    ):
        values = []
        for split, controller in labels:
            match = grouped[
                (grouped["split"] == split)
                & (grouped["controller_id"] == controller)
                & (grouped["model"] == model)
            ]
            values.append(float(match["position_rmse_rad"].iloc[0]))
        axis.bar(x + (offset - 0.5) * 0.36, values, width=0.36, color=color, label=label)
    axis.set_xticks(x, [f"{split}\n{controller}" for split, controller in labels])
    axis.set_ylabel("mean episode position RMSE (rad)")
    axis.set_title("Simulation-to-hardware error by split and controller")
    axis.grid(axis="y", alpha=0.2)
    axis.legend()
    fig.tight_layout()
    fig.savefig(PLOTS / "rmse_summary.png", dpi=180)
    plt.close(fig)


def validate_models(model_records: list[dict]) -> tuple[list[dict], dict]:
    records = []
    for record in model_records:
        path = PACKAGE / record["path"]
        model = mujoco.MjModel.from_xml_path(str(path))
        joint_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_JOINT, "actuator_joint"
        )
        actuator_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, "xc330_replay"
        )
        body_id = int(model.jnt_bodyid[joint_id])
        expected_mass = 0.000001 if record["fixture_id"] == "M0" else 0.110
        checks = {
            "loads": True,
            "one_dof_one_actuator": (model.nq, model.nv, model.nu) == (1, 1, 1),
            "joint_axis": bool(
                np.allclose(model.jnt_axis[joint_id], [0.0, -1.0, 0.0], atol=1e-12)
            ),
            "moving_mass": bool(
                np.isclose(
                    model.body_subtreemass[body_id], expected_mass, atol=1e-12
                )
            ),
            "armature": bool(
                np.isclose(
                    model.dof_armature[0], record["armature_kg_m2"], atol=1e-14
                )
            ),
            "damping": bool(
                np.isclose(
                    model.dof_damping[0],
                    record["damping_Nm_s_per_rad"],
                    atol=1e-14,
                )
            ),
            "frictionloss": bool(
                np.isclose(
                    model.dof_frictionloss[0],
                    record["frictionloss_Nm"],
                    atol=1e-14,
                )
            ),
            "effort_limit": bool(
                np.allclose(
                    model.actuator_forcerange[actuator_id],
                    [-EFFORT_LIMIT_NM, EFFORT_LIMIT_NM],
                    atol=1e-14,
                )
            ),
            "physics_step": bool(
                np.isclose(model.opt.timestep, PHYSICS_TIMESTEP_S, atol=1e-15)
            ),
        }
        records.append(
            {
                **record,
                "moving_body_mass_kg": float(model.body_subtreemass[body_id]),
                "checks": checks,
                "passed": all(checks.values()),
            }
        )
    summary = {
        "model_count": len(records),
        "all_models_passed": all(record["passed"] for record in records),
        "loaded_fixture_mass_kg": 0.110,
        "m0_numeric_placeholder_mass_kg": 0.000001,
    }
    return records, summary


def overall_split_table(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for values, group in metrics.groupby(
        ["split", "controller_id", "model"], sort=True
    ):
        split, controller, model = values
        total = int(group["sample_count"].sum())
        rows.append(
            {
                "split": split,
                "controller_id": controller,
                "model": model,
                "episode_count": int(len(group)),
                "mean_episode_position_rmse_rad": float(
                    group["position_rmse_rad"].mean()
                ),
                "median_episode_position_rmse_rad": float(
                    group["position_rmse_rad"].median()
                ),
                "pooled_position_rmse_rad": float(
                    math.sqrt(group["sse_rad2"].sum() / total)
                ),
            }
        )
    return pd.DataFrame(rows)


def value_from_overall(
    overall: pd.DataFrame, split: str, controller: str, model: str
) -> float:
    row = overall[
        (overall["split"] == split)
        & (overall["controller_id"] == controller)
        & (overall["model"] == model)
    ]
    return float(row["mean_episode_position_rmse_rad"].iloc[0])


def percentage_reduction(baseline: float, fitted: float) -> float:
    return 100.0 * (baseline - fitted) / baseline


def write_documentation(
    timestamp: datetime,
    baseline: np.ndarray,
    selected: dict[str, dict],
    candidates: list[dict],
    metrics: pd.DataFrame,
    summary: pd.DataFrame,
    overall: pd.DataFrame,
    held_out: pd.DataFrame,
    poor: pd.DataFrame,
    validation_summary: dict,
) -> None:
    held_fitted = metrics[
        (metrics["split"] == "held_out") & (metrics["model"] == "hardware_fitted")
    ]
    held_baseline = metrics[
        (metrics["split"] == "held_out")
        & (metrics["model"] == "synthetic_baseline")
    ]
    held_fitted_mean = float(held_fitted["position_rmse_rad"].mean())
    held_baseline_mean = float(held_baseline["position_rmse_rad"].mean())
    held_reduction = percentage_reduction(held_baseline_mean, held_fitted_mean)

    fixture_lines = []
    for fixture in ("B1", "G1"):
        fitted_value = float(
            held_fitted[held_fitted["fixture_id"] == fixture]["position_rmse_rad"].mean()
        )
        baseline_value = float(
            held_baseline[held_baseline["fixture_id"] == fixture][
                "position_rmse_rad"
            ].mean()
        )
        fixture_lines.append(
            (
                fixture,
                baseline_value,
                fitted_value,
                percentage_reduction(baseline_value, fitted_value),
            )
        )

    note = f"""MILESTONE:
Sim2Real

DATE AND TIME:
{timestamp.strftime('%d-%b-%Y %H:%M:%S')}

TIME ZONE:
Asia/Dubai (UTC+04:00)

PREPARED BY:
{PREPARED_BY}

PROJECT INTENTION:
Compare the 1-DOF MuJoCo model with the accepted XC330 hardware records, identify an effective joint model from calibration runs, and check it on data kept out of fitting.

WHAT IS AVAILABLE NOW:
The package compares hardware data with two simulations: a model fitted only to generated MuJoCo data and a model fitted to hardware. It includes 72 fitting, 24 model-selection and 30 held-out episodes, with paired plots and summary tables.

WHAT IS PLANNED OR ASSUMED:
The recorded Position and Velocity Trajectory registers are used as controller references. H1 and H2 use the fixed gains from Claim2Design. The 0.1551 N m effort limit is treated as a joint torque limit.

WHAT CHANGED SINCE THE PREVIOUS MILESTONE:
The hardware logs were replayed in MuJoCo. P01-P03 were used for fitting, P04-P05 for selection and P06-P07 for the final check.

IMPORTANT DECISIONS:
The main metric is mean position RMSE per episode. H1 and H2 are fitted separately while controller gains, geometry, measured masses, timing, gravity and effort limit stay fixed. Current and PWM are supporting signals, not output-torque measurements.

KNOWN PROBLEMS OR UNCERTAINTIES:
All selected values remain inside the widened declared bounds. H3-H5 are not simulated because their fixed Kp/Kv mappings are not available.
The model uses CAD geometry and internal mass distribution.
Output torque, command delay, compliance, backlash and temperature effects were not measured. The fitted parameters are effective closed-loop values, not isolated motor constants.

FILES INCLUDED:
The folders contain the models, compared hardware data, method, results, plots, reproduction script, conclusions and validation checks.

WHAT SHOULD HAPPEN NEXT:
Measure output torque or calibrate the current-to-joint-torque relationship, then repeat the test with a new dataset.
"""
    write_text(PACKAGE / "00_Milestone_Note.txt", note)

    readme = """# Sim2Real

This package compares the hardware episodes with two MuJoCo models: one fitted only to generated simulation data and one fitted to hardware data for H1 and H2.

| Requested item | Where to find it |
|---|---|
| Simulation/model and hardware results | 01_Models, 02_Hardware_Data/paired_simulation_hardware_samples.csv.gz, and 04_Results |
| Primary metric | 03_Method/PRIMARY_METRIC.md |
| Paired plots | 05_Plots |
| Configuration and controller summary | 04_Results/summary_by_configuration_controller.csv |
| Held-out results | 04_Results/held_out_results.csv |
| Poor-agreement cases | 04_Results/poor_agreement_cases.csv and 05_Plots/largest_held_out_errors.png |
| Transfer conclusion | 07_Conclusions/WHAT_TRANSFERRED_AND_WHAT_DID_NOT.md |
| Limitations and alternatives | 07_Conclusions/LIMITATIONS_AND_ALTERNATIVE_EXPLANATIONS.md |
| Ideal-agreement assumptions | 07_Conclusions/IDEAL_AGREEMENT_ASSUMPTIONS.md |
| Recommended next step | 07_Conclusions/RECOMMENDED_NEXT_STEP.md |
| Reproduction and checks | 06_Reproduction and 08_Validation |

The raw Parquet logs remain in the preceding Model2Prototype milestone. This ZIP carries their episode index and the aligned columns used in the comparison, avoiding a second full copy of the acquisition package.
"""
    write_text(PACKAGE / "README.md", readme)

    write_text(
        METHOD / "PRIMARY_METRIC.md",
        """# Primary comparison metric

The primary metric is position RMSE in radians for each episode:

RMSE = sqrt(mean((simulated position - measured hardware position)^2))

Only telemetry samples inside the active command profile are scored. Every episode contributes one RMSE value, and reported means give equal weight to episodes rather than giving longer records more influence.

This was chosen because joint position is the directly comparable output available in both MuJoCo and the XC330 log. Present Current is input-current telemetry, not an independently calibrated output-torque measurement.

MAE, peak absolute error, bias, R-squared, range-normalized RMSE, simulated effort saturation, and the hardware inner-reference tracking error are included as supporting quantities.
""",
    )

    method = f"""# Fit and evaluation method

## Data boundary

The accepted episode list provides 72 calibration records, 24 model-selection records, and 30 held-out records. Numeric held-out Parquet data is loaded only after both calibration fits and the model-selection choice are complete.

H1 and H2 are handled separately. H3-H5 remain listed as hardware diagnostics, but are not replayed because fixed engineering Kp/Kv values are not available for those settings.

## Signals and alignment

The active interval begins at the first command row marked active_profile_sample and ends at the last such row. Telemetry is aligned with the command stream using host_rx_end_ns and host_write_request_ns. Duplicate telemetry timestamps, if present, retain the last row.

Position Trajectory is converted with 2*pi/4096 rad per count. Velocity Trajectory is converted with 0.229 rpm per count. Both recorded inner references are linearly interpolated onto the 0.002 s MuJoCo physics grid. External goal positions are retained in the paired archive for context, but they are not substituted for the recorded inner trajectory.

Each rollout starts once from the first measured active-profile position and velocity. No later measured state is injected.

## Controller replay

The controller is:

tau = clip(Kp*(q_trajectory-q) + Kv*(qdot_trajectory-qdot), -0.1551, +0.1551) N m

H1 uses Kp={CONTROLLERS['H1']['kp_Nm_per_rad']:.6f} N m/rad and Kv={CONTROLLERS['H1']['kv_Nm_s_per_rad']:.6f} N m s/rad.

H2 uses Kp={CONTROLLERS['H2']['kp_Nm_per_rad']:.6f} N m/rad and Kv={CONTROLLERS['H2']['kv_Nm_s_per_rad']:.6f} N m s/rad.

The corresponding hardware P/I/D registers are H1 = 600/0/150 and H2 = 800/0/150. Controller gains and effort scaling are fixed rather than fitted.

## Parameters and selection

Only effective armature, joint damping, and friction loss are fitted. Bounds are:

| Parameter | Lower | Upper |
|---|---:|---:|
| armature (kg m^2) | {LOWER[0]:.6g} | {UPPER[0]:.6g} |
| damping (N m s/rad) | {LOWER[1]:.6g} | {UPPER[1]:.6g} |
| friction loss (N m) | {LOWER[2]:.6g} | {UPPER[2]:.6g} |

The objective uses every fifth active telemetry sample and divides each episode residual by the square root of its sample count. Four bounded starts are fitted on P01-P03. P04-P05 selects the successful candidate with the smallest mean episode position RMSE. That choice is frozen before P06-P07 is opened.

The baseline parameters were fitted only to generated MuJoCo data for the 110 g fixture. No hardware data were used for that baseline.
"""
    write_text(METHOD / "FIT_AND_EVALUATION_METHOD.md", method)

    write_text(
        HARDWARE / "HARDWARE_DATA_NOTE.md",
        """# Hardware data used

The analysis reads the accepted motor logs listed in EPISODES_USED.csv. For every episode it uses:

- command_events.parquet: active-profile flag, host write time, and applied goal position;
- telemetry_events.parquet: host receive time, measured position and velocity, Position Trajectory, Velocity Trajectory, Present Current, Present PWM, and temperature.

The full raw files are in 4_Model2Prototype/06_Raw_asBrain_Box_Logs/Original. The paired sample archive here contains the aligned columns and both model predictions. Safety pilots, preparation records, and H3-H5 diagnostic runs are not fitted or scored.
""",
    )

    parameters_lines = [
        "# Model parameter sets",
        "",
        "The simulation-only baseline is shared across controllers. H1 and H2 have separate hardware fits.",
        "",
        "| Model | Controller | Armature (kg m^2) | Damping (N m s/rad) | Friction loss (N m) |",
        "|---|---|---:|---:|---:|",
        f"| simulation-only baseline | shared | {baseline[0]:.12g} | {baseline[1]:.12g} | {baseline[2]:.12g} |",
    ]
    for controller in ("H1", "H2"):
        values = selected[controller]
        parameters_lines.append(
            f"| hardware fit | {controller} | {values['armature_kg_m2']:.12g} | "
            f"{values['damping_Nm_s_per_rad']:.12g} | "
            f"{values['frictionloss_Nm']:.12g} |"
        )
    parameters_lines.extend(
        [
            "",
            "All selected values remain inside the widened declared bounds. They remain effective parameters under the fixed replay assumptions, not independently measured XC330 motor constants.",
        ]
    )
    write_text(RESULTS / "PARAMETER_SUMMARY.md", "\n".join(parameters_lines))

    comparison_lines = [
        "# Main comparison",
        "",
        f"Across the 30 held-out episodes, the simulation-only baseline RMSE is {held_baseline_mean:.6f} rad and the hardware-fitted RMSE is {held_fitted_mean:.6f} rad. This is a {held_reduction:.1f}% reduction.",
        "",
        "| Held-out configuration | Baseline mean RMSE (rad) | Fitted mean RMSE (rad) | Reduction |",
        "|---|---:|---:|---:|",
    ]
    for fixture, base_value, fit_value, reduction in fixture_lines:
        comparison_lines.append(
            f"| {fixture} | {base_value:.6f} | {fit_value:.6f} | {reduction:.1f}% |"
        )
    comparison_lines.extend(
        [
            "",
            "The complete configuration/controller table is summary_by_configuration_controller.csv. Held-out episode pairs are in held_out_results.csv.",
            "",
            "The fitted comparison improves position prediction, but the lower RMSE does not establish the selected effective terms as physical estimates.",
        ]
    )
    write_text(RESULTS / "RESULTS_OVERVIEW.md", "\n".join(comparison_lines))

    h1_base = value_from_overall(overall, "held_out", "H1", "synthetic_baseline")
    h1_fit = value_from_overall(overall, "held_out", "H1", "hardware_fitted")
    h2_base = value_from_overall(overall, "held_out", "H2", "synthetic_baseline")
    h2_fit = value_from_overall(overall, "held_out", "H2", "hardware_fitted")
    b1 = next(item for item in fixture_lines if item[0] == "B1")
    g1 = next(item for item in fixture_lines if item[0] == "G1")
    transfer = f"""# What transferred and what did not

The recorded trajectories, fixture geometry and rigid-joint model follow the main hardware motion for both controller settings. On held-out data, the H1 RMSE falls from {h1_base:.6f} rad with the simulation-only baseline to {h1_fit:.6f} rad after hardware fitting. H2 falls from {h2_base:.6f} rad to {h2_fit:.6f} rad.

B1 is the cleanest held-out check of balanced-fixture transfer: its mean RMSE changes from {b1[1]:.6f} rad to {b1[2]:.6f} rad. G1 is the gravity-unbalanced check: its mean changes from {g1[1]:.6f} rad to {g1[2]:.6f} rad. The larger of those two fitted errors marks the condition where the current model transfers less well.

What did not transfer as a measured quantity is output torque. The replay effort is calculated from fixed controller gains and clipped at the stated limit; it is not checked against a torque sensor. All selected values remain inside the widened declared bounds, but the present data and assumptions still do not uniquely identify physical terms. The H1 and H2 fits do not establish controller-independent motor constants. Differences between their fitted values can contain controller mapping error, timing error, and unmodelled mechanics.

The five largest held-out fitted errors are listed separately. They are called poor-agreement cases only in the relative sense: no external pass/fail threshold was supplied.
"""
    write_text(CONCLUSIONS / "WHAT_TRANSFERRED_AND_WHAT_DID_NOT.md", transfer)

    write_text(
        CONCLUSIONS / "LIMITATIONS_AND_ALTERNATIVE_EXPLANATIONS.md",
        """# Limitations and alternative explanations

- Output torque was not measured. The fixed Kp/Kv and effort-limit interpretation may be inaccurate even if position looks reasonable.
- Position and velocity trajectory registers were sampled at about 200 Hz, while the internal controller runs faster. Linear interpolation cannot recover unrecorded inner-loop detail.
- Host timestamps include USB and software timing. A separate command-to-actuation delay was not measured or fitted.
- The rigid MJCF has no shaft compliance, printed-part flex, backlash, joint play, fastener looseness, cable force, or fixture-base motion.
- Damping plus Coulomb friction is a small loss model. Stiction, Stribeck behaviour, direction asymmetry, and speed dependence are not represented.
- The model uses CAD dimensions and internal mass distribution. It uses the measured 22 g link, two 44 g payload assemblies and the recorded payload positions.
- Temperature dependence is not modelled. The campaign covers one motor and one collection day.
- Present Current and Present PWM can show operating severity, but neither proves output torque.
- M0 uses a 0.000001 kg numerical moving-body placeholder required by the MJCF. It is not a physical payload.
- H3-H5 remain unevaluated because their fixed replay gains are not available.
- All selected values remain inside the widened declared bounds. They remain effective replay parameters rather than well-localized physical estimates.

Several mechanisms can produce similar position errors. A fitted damping change may actually compensate for torque scale, latency, compliance, or trajectory interpolation. A good position trace therefore does not uniquely validate the three fitted physical terms.
""",
    )

    write_text(
        CONCLUSIONS / "IDEAL_AGREEMENT_ASSUMPTIONS.md",
        """# Assumptions needed for ideal agreement

Ideal simulation-to-hardware agreement would require all of the following:

- the MJCF geometry, joint axis, payload locations, masses, inertia tensors, and centres of mass match the assembled fixture;
- encoder zero and model zero refer to the same physical pose;
- recorded Position Trajectory and Velocity Trajectory values are time-aligned inner references with no missing dynamics;
- the fixed H1/H2 Kp and Kv values reproduce the hardware controller at the output joint;
- the 0.1551 N m limit is the correct symmetric output-joint torque limit;
- command, telemetry, and actuation timing share a known clock and delay;
- damping and Coulomb friction adequately describe all losses;
- the motor, link, pins, printed payloads, mount, and wiring behave as rigid bodies;
- supply voltage, temperature, and controller state do not change the dynamics;
- measurement quantization and communication jitter are the only observation errors.

The mass totals, nominal payload positions, register settings, encoder resolution, and recorded rates are available. Output torque, exact delay, individual centres of mass, compliance, backlash, cable force, and temperature dependence remain unmeasured or untested. Several assumptions needed for ideal agreement are therefore unrealistic for the present model.
""",
    )

    write_text(
        CONCLUSIONS / "RECOMMENDED_NEXT_STEP.md",
        """# Recommended next step

Calibrate the current-to-output-torque relationship with an independent fixture and verify the H1/H2 replay gains against that measurement. Record controller trajectory registers and torque-calibration data on the same clock.

After fixing that mapping, collect a new calibration set and a new held-out set using the same M0, B0, B1, B2, and G1 configurations. Keep the current 30 held-out episodes as reported results; do not move them into the next fit.
""",
    )

    write_text(
        PACKAGE / "PACKAGE_CONTENTS.txt",
        """00_Milestone_Note.txt
    State of the Sim2Real milestone and the decision it supports.

01_Models
    Loadable synthetic-baseline and hardware-fitted MJCFs for H1 and H2, mesh assets, controller conditions, and parameter sets.

02_Hardware_Data
    Compared episode list, data note, and the aligned simulation/hardware sample archive.

03_Method
    Primary metric and the exact fit, alignment, controller, split, and replay method.

04_Results
    Fitted parameters, optimizer candidates, per-episode metrics, held-out results, poor-agreement cases, and grouped summaries.

05_Plots
    Paired time histories and RMSE summaries.

06_Reproduction
    Reproduction script, environment versions, and run instructions.

07_Conclusions
    Transfer conclusion, limitations, ideal-agreement assumptions, and recommended next step.

08_Validation
    Machine-readable checks, file inventory, and SHA-256 manifest.
""",
    )

    write_text(
        PACKAGE / "06_Reproduction" / "requirements.txt",
        f"""mujoco=={mujoco.__version__}
numpy=={np.__version__}
scipy=={scipy.__version__}
pandas=={pd.__version__}
pyarrow=={pyarrow.__version__}
matplotlib=={matplotlib.__version__}
""",
    )
    write_text(
        PACKAGE / "06_Reproduction" / "RUN_INSTRUCTIONS.txt",
        """Run from the 5_Sim2Real folder:

python 06_Reproduction/run_sim2real.py

The script reads only the numbered milestone folders beside this package. It rebuilds folders 01-05, 07, and 08. It does not write to the Model2Prototype raw-log folder.
""",
    )

    candidate_spread = {}
    for controller in CONTROLLERS:
        subset = [row for row in candidates if row["controller_id"] == controller]
        candidate_spread[controller] = {
            name: float(max(row[name] for row in subset) - min(row[name] for row in subset))
            for name in PARAMETER_NAMES
        }
    upper_bound_status = {
        controller: {
            name: bool(
                np.isclose(
                    selected[controller][name],
                    UPPER[index],
                    rtol=0,
                    atol=1e-10 * (UPPER[index] - LOWER[index]),
                )
            )
            for index, name in enumerate(PARAMETER_NAMES)
        }
        for controller in CONTROLLERS
    }
    write_text(
        RESULTS / "FIT_RELIABILITY_NOTE.md",
        f"""# Fit reliability note

All four starts are reported in optimizer_candidates.csv. Model selection, rather than calibration cost, chooses the retained candidate.

The fitted parameter spread across successful starts is:

| Controller | Armature spread (kg m^2) | Damping spread (N m s/rad) | Friction spread (N m) |
|---|---:|---:|---:|
| H1 | {candidate_spread['H1']['armature_kg_m2']:.6g} | {candidate_spread['H1']['damping_Nm_s_per_rad']:.6g} | {candidate_spread['H1']['frictionloss_Nm']:.6g} |
| H2 | {candidate_spread['H2']['armature_kg_m2']:.6g} | {candidate_spread['H2']['damping_Nm_s_per_rad']:.6g} | {candidate_spread['H2']['frictionloss_Nm']:.6g} |

The widened bounds place all selected values inside their declared intervals. The remaining multi-start spread and the closed-loop measurement boundary still do not establish tightly identified physical motor constants.

Position-only closed-loop data can trade physical loss terms against an inaccurate torque scale or timing model. The fitted models can be compared as effective predictors, but the selected effective terms should not be reported as measured motor constants.
""",
    )


def write_file_inventory() -> None:
    rows = []
    for path in sorted(PACKAGE.rglob("*")):
        if path.is_file() and path.name not in {
            "FILE_INVENTORY.csv",
            "FILE_MANIFEST.sha256",
        }:
            rows.append(
                {
                    "relative_path": str(path.relative_to(PACKAGE)),
                    "size_bytes": path.stat().st_size,
                }
            )
    pd.DataFrame(rows).to_csv(VALIDATION / "FILE_INVENTORY.csv", index=False)


def write_manifest() -> None:
    destination = VALIDATION / "FILE_MANIFEST.sha256"
    lines = []
    for path in sorted(PACKAGE.rglob("*")):
        if path.is_file() and path != destination:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  ./{path.relative_to(PACKAGE)}")
    write_text(destination, "\n".join(lines))


def main() -> None:
    reset_generated_directories()
    timestamp = datetime.now(TIME_ZONE)
    stage_order = ["episode_index_loaded"]
    rows = selected_index_rows()

    used_columns = [
        "episode_id",
        "role",
        "mechanical_configuration",
        "controller_id",
        "profile_id",
        "repeat_id",
        "package_log_directory",
        "command_samples",
        "telemetry_samples",
        "tracking_rmse_rad_active",
        "maximum_abs_current_A",
        "maximum_abs_pwm_fraction",
        "maximum_temperature_C",
        "achieved_telemetry_rate_hz",
    ]
    rows[used_columns].to_csv(HARDWARE / "EPISODES_USED.csv", index=False)

    replayer = HardwareReplayer()
    baseline = load_baseline_parameters()
    calibration = load_split(rows, "calibration")
    stage_order.append("calibration_numeric_loaded")
    candidates = []
    for controller in CONTROLLERS:
        candidates.extend(
            fit_one_controller(replayer, calibration, controller)
        )
    stage_order.append("calibration_fits_complete")

    model_selection = load_split(rows, "model_selection")
    stage_order.append("model_selection_numeric_loaded")
    selected = choose_candidates(replayer, model_selection, candidates)
    stage_order.append("candidates_selected_and_frozen")
    write_json(
        RESULTS / "FROZEN_SELECTION_BEFORE_HELD_OUT.json",
        {
            "frozen_at": datetime.now(TIME_ZONE).isoformat(),
            "selection_rule": "smallest mean episode position RMSE on model_selection among successful calibration fits",
            "selected": selected,
            "held_out_numeric_loaded": False,
        },
    )

    held_out_episodes = load_split(rows, "held_out")
    stage_order.append("held_out_numeric_loaded")
    all_episodes = calibration + model_selection + held_out_episodes
    metrics, predictions, by_episode = evaluate_all(
        replayer, all_episodes, baseline, selected
    )
    stage_order.append("held_out_scored")

    summary = summarize_metrics(metrics)
    overall = overall_split_table(metrics)
    held_out = paired_held_out(metrics)
    poor = held_out.sort_values(
        "position_rmse_rad__hardware_fitted", ascending=False
    ).head(5).copy()
    poor.insert(
        len(poor.columns),
        "case_definition",
        "five largest fitted RMSE values among the 30 held-out episodes; relative review list, not a supplied pass/fail threshold",
    )

    metrics.drop(columns=["sse_rad2"]).to_csv(
        RESULTS / "episode_metrics.csv", index=False, float_format="%.12g"
    )
    summary.to_csv(
        RESULTS / "summary_by_configuration_controller.csv",
        index=False,
        float_format="%.12g",
    )
    overall.to_csv(
        RESULTS / "summary_by_split_controller.csv",
        index=False,
        float_format="%.12g",
    )
    held_out.to_csv(
        RESULTS / "held_out_results.csv", index=False, float_format="%.12g"
    )
    poor.to_csv(
        RESULTS / "poor_agreement_cases.csv", index=False, float_format="%.12g"
    )
    pd.DataFrame(candidates).to_csv(
        RESULTS / "optimizer_candidates.csv", index=False, float_format="%.12g"
    )
    parameter_rows = [
        {
            "model": "synthetic_baseline",
            "controller_id": "shared",
            **dict(zip(PARAMETER_NAMES, map(float, baseline))),
        }
    ]
    for controller in CONTROLLERS:
        parameter_rows.append(
            {
                "model": "hardware_fitted",
                "controller_id": controller,
                **{
                    name: float(selected[controller][name])
                    for name in PARAMETER_NAMES
                },
            }
        )
    pd.DataFrame(parameter_rows).to_csv(
        RESULTS / "fitted_parameters.csv", index=False, float_format="%.12g"
    )
    predictions.to_csv(
        HARDWARE / "paired_simulation_hardware_samples.csv.gz",
        index=False,
        float_format="%.10g",
        compression={"method": "gzip", "compresslevel": 6, "mtime": 0},
    )

    controller_rows = []
    for controller, values in CONTROLLERS.items():
        controller_rows.append(
            {
                "controller_id": controller,
                "hardware_position_p_gain_raw": values["position_p_gain_raw"],
                "hardware_position_i_gain_raw": values["position_i_gain_raw"],
                "hardware_position_d_gain_raw": values["position_d_gain_raw"],
                "fixed_replay_kp_Nm_per_rad": values["kp_Nm_per_rad"],
                "fixed_replay_kv_Nm_s_per_rad": values["kv_Nm_s_per_rad"],
                "sim2real_status": "fitted_and_evaluated",
            }
        )
    for controller, gains in (
        ("H3", (600, 0, 220)),
        ("H4", (300, 0, 60)),
        ("H5", (1200, 0, 320)),
    ):
        controller_rows.append(
            {
                "controller_id": controller,
                "hardware_position_p_gain_raw": gains[0],
                "hardware_position_i_gain_raw": gains[1],
                "hardware_position_d_gain_raw": gains[2],
                "fixed_replay_kp_Nm_per_rad": "not available",
                "fixed_replay_kv_Nm_s_per_rad": "not available",
                "sim2real_status": "not evaluated; fixed replay mapping not available",
            }
        )
    pd.DataFrame(controller_rows).to_csv(
        RESULTS / "controller_setting_summary.csv", index=False
    )

    model_records = create_models(baseline, selected)
    model_validation, model_validation_summary = validate_models(model_records)
    create_plots(metrics, held_out, by_episode)
    write_documentation(
        timestamp,
        baseline,
        selected,
        candidates,
        metrics,
        summary,
        overall,
        held_out,
        poor,
        model_validation_summary,
    )

    result = {
        "schema_version": "v5-sim2real-1",
        "run_time_asia_dubai": timestamp.isoformat(),
        "prepared_by": PREPARED_BY,
        "software": {
            "python": platform.python_version(),
            "mujoco": mujoco.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "pandas": pd.__version__,
            "pyarrow": pyarrow.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "fixture_mass_basis": {
            "link_mass_kg": 0.022,
            "complete_payload_mass_each_kg": 0.044,
            "loaded_fixture_total_kg": 0.110,
        },
        "data_counts": {
            split: {
                controller: EXPECTED_COUNTS[split][controller]
                for controller in CONTROLLERS
            }
            for split in EXPECTED_COUNTS
        },
        "stage_order": stage_order,
        "primary_metric": "equal-weight mean per-episode active-profile position RMSE in radians",
        "synthetic_baseline_parameters": dict(
            zip(PARAMETER_NAMES, map(float, baseline))
        ),
        "hardware_fitted_parameters": selected,
        "selected_parameter_active_upper_bounds": {
            controller: {
                name: bool(
                    np.isclose(
                        selected[controller][name],
                        UPPER[index],
                        rtol=0,
                        atol=1e-10 * (UPPER[index] - LOWER[index]),
                    )
                )
                for index, name in enumerate(PARAMETER_NAMES)
            }
            for controller in CONTROLLERS
        },
        "parameter_interpretation": "effective position-prediction fit; all selected values remain inside the widened declared bounds",
        "held_out_mean_episode_rmse_rad": {
            model: float(
                metrics[
                    (metrics["split"] == "held_out") & (metrics["model"] == model)
                ]["position_rmse_rad"].mean()
            )
            for model in ("synthetic_baseline", "hardware_fitted")
        },
        "poor_case_definition": "five largest fitted RMSE values among held-out episodes; relative review list only",
        "model_validation": model_validation_summary,
    }
    write_json(RESULTS / "result.json", result)

    checks = {
        "episode_matrix_exact": len(all_episodes) == 126,
        "calibration_count_exact": len(calibration) == 72,
        "model_selection_count_exact": len(model_selection) == 24,
        "held_out_count_exact": len(held_out_episodes) == 30,
        "fit_controllers_exact": sorted(selected) == ["H1", "H2"],
        "held_out_loaded_after_freeze": stage_order.index(
            "held_out_numeric_loaded"
        )
        > stage_order.index("candidates_selected_and_frozen"),
        "all_predictions_finite": bool(
            np.all(
                np.isfinite(
                    predictions[
                        [
                            "hardware_position_rad",
                            "synthetic_baseline_position_rad",
                            "hardware_fitted_position_rad",
                        ]
                    ].to_numpy()
                )
            )
        ),
        "all_generated_models_pass": model_validation_summary["all_models_passed"],
        "generated_model_count_20": model_validation_summary["model_count"] == 20,
        "all_optimizer_candidates_successful": all(
            bool(row["success"]) for row in candidates
        ),
        "expected_optimizer_candidate_count_8": len(candidates) == 8,
    }
    validation = {
        "passed": all(checks.values()),
        "checks": checks,
        "stage_order": stage_order,
        "model_checks": model_validation,
        "notes": {
            "h3_h4_h5": "not evaluated because fixed engineering replay gains are not available",
            "current_and_pwm": "descriptive only; not output torque",
            "held_out_policy": "numeric held-out logs loaded only after candidate parameters were selected and written",
            "active_parameter_bounds": "all selected values remain inside the widened declared bounds",
        },
    }
    write_json(VALIDATION / "validation_report.json", validation)
    if not validation["passed"]:
        raise RuntimeError("validation failed; inspect 08_Validation/validation_report.json")

    write_file_inventory()
    write_manifest()
    print(
        json.dumps(
            {
                "passed": True,
                "selected": selected,
                "held_out_mean_episode_rmse_rad": result[
                    "held_out_mean_episode_rmse_rad"
                ],
                "output": str(PACKAGE),
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
