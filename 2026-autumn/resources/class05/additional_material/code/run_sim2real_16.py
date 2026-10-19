#!/usr/bin/env python3
"""Fit and evaluate 32 independent XC330/MuJoCo replay models.

This is a software-only reproduction.  It reads accepted episode CSV files and
generated MJCF files; it never opens a serial port or camera stream.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import shutil
import time
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


PACKAGE = Path(__file__).resolve().parents[1]
MILESTONES_16 = PACKAGE.parent
V5 = PACKAGE.parents[2]
DESIGN2DATA = MILESTONES_16 / "2_Design2Data"
DATA2MODEL = MILESTONES_16 / "3_Data2Model"
MODEL2PROTOTYPE = MILESTONES_16 / "4_Model2Prototype"
RAW_PACKAGE = MODEL2PROTOTYPE / "06_Raw_asBrain_Box_Logs"
G1_CANONICAL = V5 / "hardware_experiment/g1_16_motors/data/G1_16_complete/episodes"

MODELS_OUT = PACKAGE / "01_Models"
HARDWARE_OUT = PACKAGE / "02_Hardware_Data"
METHOD_OUT = PACKAGE / "03_Method"
RESULTS_OUT = PACKAGE / "04_Results"
PLOTS_OUT = PACKAGE / "05_Plots"
CONCLUSIONS_OUT = PACKAGE / "07_Conclusions"
VALIDATION_OUT = PACKAGE / "08_Validation"

TZ = ZoneInfo("Asia/Dubai")
DT = 0.002
FIT_STRIDE = 5
POSITION_UNIT = 2.0 * math.pi / 4096.0
VELOCITY_UNIT = 0.229 * 2.0 * math.pi / 60.0
CURRENT_UNIT_A = 0.001
EFFORT_LIMIT_NM = 0.1551
FIXTURES = ("M0", "B0", "B1", "B2", "G1")
PARAMETERS = ("armature_kg_m2", "damping_Nm_s_per_rad", "frictionloss_Nm")
LOWER = np.array([0.0002, 0.003, 0.002], dtype=float)
UPPER = np.array([0.010, 0.150, 0.050], dtype=float)
STARTS = {
    "S1_low": np.array([0.0020, 0.030, 0.010]),
    "S2_middle": np.array([0.0040, 0.060, 0.020]),
}
CONTROLLERS = {
    "H1": {"kp": 1.579836, "kv": 0.202115, "p_raw": 600, "i_raw": 0, "d_raw": 150},
    "H2": {"kp": 2.106448, "kv": 0.202115, "p_raw": 800, "i_raw": 0, "d_raw": 150},
}
EXCLUDED = {
    "B0_16__H2__P05_wide_sine__R03": "excluded campaign entry",
}
EXPECTED_SIMULTANEOUS = {
    "calibration": {"H1": 36, "H2": 36},
    "model_selection": {"H1": 12, "H2": 11},
    "held_out": {"H1": 15, "H2": 15},
}


@dataclass(frozen=True)
class Episode:
    episode_id: str
    simultaneous_episode_id: str
    motor_id: int
    split: str
    fixture_id: str
    controller_id: str
    profile_id: str
    repeat_id: str
    source_directory: str
    time_s: np.ndarray
    external_command_rad: np.ndarray
    qref_rad: np.ndarray
    vref_rad_s: np.ndarray
    q_rad: np.ndarray
    v_rad_s: np.ndarray
    current_A: np.ndarray
    pwm_fraction: np.ndarray
    temperature_C: np.ndarray


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def relative_to_v5(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(V5.resolve()))
    except ValueError:
        return str(path.resolve())


def reset_outputs() -> None:
    for directory in (
        MODELS_OUT,
        HARDWARE_OUT,
        METHOD_OUT,
        RESULTS_OUT,
        PLOTS_OUT,
        CONCLUSIONS_OUT,
        VALIDATION_OUT,
    ):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)


def split_for_profile(profile: str) -> str:
    code = profile.split("_", 1)[0]
    if code in {"P01", "P02", "P03"}:
        return "calibration"
    if code in {"P04", "P05"}:
        return "model_selection"
    if code in {"P06", "P07"}:
        return "held_out"
    raise ValueError(f"unrecognized profile: {profile}")


def episode_path(fixture: str, name: str) -> Path:
    packaged = RAW_PACKAGE / f"{fixture}_16_complete" / name
    if (packaged / "telemetry.csv").is_file():
        return packaged
    if fixture == "G1":
        canonical = G1_CANONICAL / name
        if (canonical / "telemetry.csv").is_file():
            return canonical
    raise FileNotFoundError(f"accepted episode files not found for {name}")


def build_episode_index() -> pd.DataFrame:
    rows: list[dict] = []
    for fixture in FIXTURES:
        root = RAW_PACKAGE / f"{fixture}_16_complete"
        names = sorted(path.name for path in root.iterdir())
        for name in names:
            if "PILOT" in name or name in EXCLUDED:
                continue
            parts = name.split("__")
            if len(parts) != 4 or parts[1] not in CONTROLLERS or not parts[2].startswith("P"):
                continue
            if fixture == "B1" and parts[2].startswith("P06_") and parts[3] not in {
                "R01", "R02", "R03", "R04", "R05"
            }:
                continue
            path = episode_path(fixture, name)
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            if manifest.get("status") != "complete":
                continue
            split = split_for_profile(parts[2])
            rows.append(
                {
                    "simultaneous_episode_id": name,
                    "split": split,
                    "fixture_id": fixture,
                    "controller_id": parts[1],
                    "profile_id": parts[2],
                    "repeat_id": parts[3],
                    "motor_count": 16,
                    "source_directory": relative_to_v5(path),
                    "path": str(path),
                }
            )
    frame = pd.DataFrame(rows).sort_values(
        ["split", "controller_id", "fixture_id", "profile_id", "repeat_id"]
    ).reset_index(drop=True)
    observed = {
        split: {
            controller: int(
                ((frame["split"] == split) & (frame["controller_id"] == controller)).sum()
            )
            for controller in CONTROLLERS
        }
        for split in EXPECTED_SIMULTANEOUS
    }
    if observed != EXPECTED_SIMULTANEOUS:
        raise ValueError(f"episode matrix mismatch: {observed} != {EXPECTED_SIMULTANEOUS}")
    if any(name in set(frame["simultaneous_episode_id"]) for name in EXCLUDED):
        raise ValueError("an excluded entry reached the analysis index")
    if len(frame) != 125:
        raise ValueError(f"expected 125 simultaneous science episodes, found {len(frame)}")
    return frame


def load_episode_row(row: pd.Series) -> list[Episode]:
    directory = Path(row["path"])
    telemetry = pd.read_csv(directory / "telemetry.csv")
    command = pd.read_csv(directory / "commands.csv")
    telemetry = telemetry[(telemetry["phase"] == "active") & (telemetry["telemetry_valid"] == 1)].copy()
    command = command[command["phase"] == "active"].copy()
    result: list[Episode] = []
    for motor_id in range(16):
        measured = telemetry[telemetry["motor_id"] == motor_id].copy()
        measured.sort_values("host_rx_end_ns", inplace=True)
        measured.drop_duplicates("host_rx_end_ns", keep="last", inplace=True)
        commanded = command[command["motor_id"] == motor_id].copy()
        commanded.sort_values("host_write_request_ns", inplace=True)
        if len(measured) < 50 or commanded.empty:
            raise ValueError(f"{row['simultaneous_episode_id']} motor {motor_id}: insufficient active data")
        host_ns = measured["host_rx_end_ns"].to_numpy(dtype=np.int64)
        if np.any(np.diff(host_ns) <= 0):
            raise ValueError(f"{row['simultaneous_episode_id']} motor {motor_id}: timestamps not increasing")
        command_ns = commanded["host_write_request_ns"].to_numpy(dtype=np.int64)
        indices = np.clip(np.searchsorted(command_ns, host_ns, side="right") - 1, 0, len(commanded) - 1)
        q_ticks = measured["present_position"].to_numpy(dtype=float)
        qref_ticks = measured["position_trajectory"].to_numpy(dtype=float)
        result.append(
            Episode(
                episode_id=f"{row['simultaneous_episode_id']}__M{motor_id:02d}",
                simultaneous_episode_id=str(row["simultaneous_episode_id"]),
                motor_id=motor_id,
                split=str(row["split"]),
                fixture_id=str(row["fixture_id"]),
                controller_id=str(row["controller_id"]),
                profile_id=str(row["profile_id"]),
                repeat_id=str(row["repeat_id"]),
                source_directory=str(row["source_directory"]),
                time_s=(host_ns - host_ns[0]).astype(float) * 1e-9,
                external_command_rad=commanded["position_cmd_rad"].to_numpy(dtype=float)[indices],
                qref_rad=(qref_ticks - 2048.0) * POSITION_UNIT,
                vref_rad_s=measured["velocity_trajectory"].to_numpy(dtype=float) * VELOCITY_UNIT,
                q_rad=(q_ticks - 2048.0) * POSITION_UNIT,
                v_rad_s=measured["present_velocity"].to_numpy(dtype=float) * VELOCITY_UNIT,
                current_A=measured["present_current"].to_numpy(dtype=float) * CURRENT_UNIT_A,
                pwm_fraction=measured["present_pwm"].to_numpy(dtype=float) / 885.0,
                temperature_C=measured["temperature"].to_numpy(dtype=float),
            )
        )
    return result


def load_split(index: pd.DataFrame, split: str) -> list[Episode]:
    result: list[Episode] = []
    for _, row in index[index["split"] == split].iterrows():
        result.extend(load_episode_row(row))
    expected = sum(EXPECTED_SIMULTANEOUS[split].values()) * 16
    if len(result) != expected:
        raise ValueError(f"{split}: expected {expected} motor records, found {len(result)}")
    print(f"loaded {len(result)} {split} motor records", flush=True)
    return result


def source_model_path(fixture: str) -> Path:
    path = DESIGN2DATA / f"models/simulation/nominal/C1/{fixture}.xml"
    if not path.is_file():
        raise FileNotFoundError(f"generated 113 g nominal model is missing: {path}")
    return path


def load_baseline() -> np.ndarray:
    path = DATA2MODEL / "results/result.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    values = result["primary_parameters"]
    theta = np.array([float(values[name]) for name in PARAMETERS])
    if np.any(theta < LOWER) or np.any(theta > UPPER):
        raise ValueError(f"synthetic baseline outside declared bounds: {theta}")
    return theta


def physical(unit: np.ndarray) -> np.ndarray:
    return LOWER + np.asarray(unit, dtype=float) * (UPPER - LOWER)


def normalized(theta: np.ndarray) -> np.ndarray:
    return (np.asarray(theta, dtype=float) - LOWER) / (UPPER - LOWER)


class HardwareReplayer:
    """Batched MuJoCo replay using recorded inner references."""

    def __init__(self, nthread: int = 8) -> None:
        self.nthread = nthread
        self.runner = rollout.Rollout(nthread=nthread)
        self.models: dict[tuple[str, str], mujoco.MjModel] = {}
        self.data: dict[tuple[str, str], list[mujoco.MjData]] = {}
        self.sensor_addresses: dict[tuple[str, str], tuple[int, int]] = {}
        for fixture in FIXTURES:
            for controller_id, gains in CONTROLLERS.items():
                model = mujoco.MjModel.from_xml_path(str(source_model_path(fixture)))
                data = [mujoco.MjData(model) for _ in range(nthread)]
                actuator_id = 0
                model.actuator_gaintype[actuator_id] = mujoco.mjtGain.mjGAIN_FIXED
                model.actuator_biastype[actuator_id] = mujoco.mjtBias.mjBIAS_AFFINE
                model.actuator_gainprm[actuator_id] = 0.0
                model.actuator_gainprm[actuator_id, 0] = 1.0
                model.actuator_biasprm[actuator_id] = 0.0
                model.actuator_biasprm[actuator_id, 1] = -float(gains["kp"])
                model.actuator_biasprm[actuator_id, 2] = -float(gains["kv"])
                model.actuator_ctrllimited[actuator_id] = 0
                model.actuator_forcelimited[actuator_id] = 1
                model.actuator_forcerange[actuator_id] = (-EFFORT_LIMIT_NM, EFFORT_LIMIT_NM)
                qid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SENSOR, "q")
                vid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SENSOR, "qdot")
                key = (fixture, controller_id)
                self.models[key] = model
                self.data[key] = data
                self.sensor_addresses[key] = (int(model.sensor_adr[qid]), int(model.sensor_adr[vid]))

    def close(self) -> None:
        self.runner.close()

    def simulate_many(
        self, episodes: list[Episode], theta: np.ndarray
    ) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
        output: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        for fixture in FIXTURES:
            group = [episode for episode in episodes if episode.fixture_id == fixture]
            if not group:
                continue
            controller_id = group[0].controller_id
            if any(episode.controller_id != controller_id for episode in group):
                raise ValueError("simulate_many requires one controller at a time")
            key = (fixture, controller_id)
            model = self.models[key]
            data_pool = self.data[key]
            data = data_pool[0]
            model.dof_armature[0] = float(theta[0])
            model.dof_damping[0] = float(theta[1])
            model.dof_frictionloss[0] = float(theta[2])
            mujoco.mj_setConst(model, data)
            nstep = max(int(math.ceil(float(ep.time_s[-1]) / DT)) + 1 for ep in group)
            state_size = mujoco.mj_stateSize(model, mujoco.mjtState.mjSTATE_FULLPHYSICS)
            initial = np.empty((len(group), state_size), dtype=float)
            controls = np.empty((len(group), nstep, model.nu), dtype=float)
            grid = np.arange(nstep, dtype=float) * DT
            gains = CONTROLLERS[controller_id]
            for index, episode in enumerate(group):
                mujoco.mj_resetData(model, data)
                data.qpos[0] = float(episode.q_rad[0])
                data.qvel[0] = float(episode.v_rad_s[0])
                mujoco.mj_forward(model, data)
                mujoco.mj_getState(model, data, initial[index], mujoco.mjtState.mjSTATE_FULLPHYSICS)
                qref = np.interp(grid, episode.time_s, episode.qref_rad)
                vref = np.interp(grid, episode.time_s, episode.vref_rad_s)
                controls[index, :, 0] = gains["kp"] * qref + gains["kv"] * vref
            _, sensors = self.runner.rollout(model, data_pool, initial, controls)
            sensors = np.asarray(sensors)
            q_address, v_address = self.sensor_addresses[key]
            for index, episode in enumerate(group):
                q_grid = sensors[index, :, q_address]
                v_grid = sensors[index, :, v_address]
                if not np.isclose(q_grid[0], episode.q_rad[0], atol=1e-12):
                    raise RuntimeError("rollout sensor phase is not pre-step as expected")
                qref_grid = np.interp(grid, episode.time_s, episode.qref_rad)
                vref_grid = np.interp(grid, episode.time_s, episode.vref_rad_s)
                raw = gains["kp"] * (qref_grid - q_grid) + gains["kv"] * (vref_grid - v_grid)
                torque_grid = np.clip(raw, -EFFORT_LIMIT_NM, EFFORT_LIMIT_NM)
                prediction = np.interp(episode.time_s, grid, q_grid)
                torque = np.interp(episode.time_s, grid, torque_grid)
                saturation = np.interp(
                    episode.time_s, grid, (np.abs(raw) >= EFFORT_LIMIT_NM).astype(float)
                ) >= 0.5
                if not np.all(np.isfinite(prediction)) or np.max(np.abs(prediction)) >= 2.0:
                    raise FloatingPointError(f"unstable replay: {episode.episode_id}")
                output[episode.episode_id] = (prediction, torque, saturation)
        if len(output) != len(episodes):
            raise RuntimeError("not every episode was simulated")
        return output


def mean_episode_rmse(
    replayer: HardwareReplayer, episodes: list[Episode], theta: np.ndarray
) -> float:
    predictions = replayer.simulate_many(episodes, theta)
    return float(
        np.mean(
            [
                np.sqrt(np.mean((predictions[ep.episode_id][0] - ep.q_rad) ** 2))
                for ep in episodes
            ]
        )
    )


def fit_pair(
    replayer: HardwareReplayer,
    calibration: list[Episode],
    controller_id: str,
    motor_id: int,
) -> list[dict]:
    episodes = [
        ep for ep in calibration if ep.controller_id == controller_id and ep.motor_id == motor_id
    ]
    if len(episodes) != 36:
        raise ValueError(f"{controller_id} M{motor_id:02d}: expected 36 calibration episodes")
    cache: dict[tuple[float, ...], np.ndarray] = {}

    def objective(unit: np.ndarray) -> np.ndarray:
        key = tuple(np.round(unit, 12))
        if key not in cache:
            predictions = replayer.simulate_many(episodes, physical(unit))
            residuals = []
            for episode in episodes:
                error = predictions[episode.episode_id][0][::FIT_STRIDE] - episode.q_rad[::FIT_STRIDE]
                residuals.append(100.0 * error / math.sqrt(len(error)))
            cache[key] = np.concatenate(residuals)
        return cache[key]

    rows: list[dict] = []
    for start_id, theta_start in STARTS.items():
        started = time.perf_counter()
        fit = least_squares(
            objective,
            normalized(theta_start),
            bounds=(np.zeros(3), np.ones(3)),
            method="trf",
            loss="linear",
            diff_step=0.0005,
            max_nfev=70,
            ftol=1e-8,
            xtol=1e-8,
            gtol=1e-8,
        )
        theta = physical(fit.x)
        singular = np.linalg.svd(np.asarray(fit.jac), compute_uv=False)
        row = {
            "controller_id": controller_id,
            "motor_id": motor_id,
            "start_id": start_id,
            "success": bool(fit.success),
            "status": int(fit.status),
            "message": str(fit.message).replace("\n", " "),
            "nfev": int(fit.nfev),
            "cost": float(fit.cost),
            "optimality": float(fit.optimality),
            "elapsed_s": float(time.perf_counter() - started),
            "calibration_mean_episode_rmse_rad": mean_episode_rmse(replayer, episodes, theta),
            "jacobian_largest_singular_value": float(singular[0]),
            "jacobian_smallest_singular_value": float(singular[-1]),
            "jacobian_condition_number": float(singular[0] / singular[-1]) if singular[-1] > 0 else float("inf"),
        }
        row.update(dict(zip(PARAMETERS, map(float, theta))))
        rows.append(row)
        print(
            f"fit {controller_id} M{motor_id:02d} {start_id}: "
            f"RMSE={row['calibration_mean_episode_rmse_rad']:.6f} rad, nfev={fit.nfev}",
            flush=True,
        )
    return rows


def select_candidates(
    replayer: HardwareReplayer,
    model_selection: list[Episode],
    candidates: list[dict],
) -> dict[str, dict[str, dict]]:
    selected: dict[str, dict[str, dict]] = {controller: {} for controller in CONTROLLERS}
    for controller_id in CONTROLLERS:
        for motor_id in range(16):
            episodes = [
                ep
                for ep in model_selection
                if ep.controller_id == controller_id and ep.motor_id == motor_id
            ]
            expected = EXPECTED_SIMULTANEOUS["model_selection"][controller_id]
            if len(episodes) != expected:
                raise ValueError(f"{controller_id} M{motor_id:02d}: expected {expected} selection episodes")
            valid = []
            for row in candidates:
                if row["controller_id"] != controller_id or row["motor_id"] != motor_id:
                    continue
                theta = np.array([row[name] for name in PARAMETERS])
                row["model_selection_mean_episode_rmse_rad"] = mean_episode_rmse(
                    replayer, episodes, theta
                )
                row["selected"] = False
                if row["success"] and np.isfinite(row["model_selection_mean_episode_rmse_rad"]):
                    valid.append(row)
            if not valid:
                raise RuntimeError(f"no successful fit for {controller_id} M{motor_id:02d}")
            winner = min(valid, key=lambda row: row["model_selection_mean_episode_rmse_rad"])
            winner["selected"] = True
            selected[controller_id][str(motor_id)] = {
                "start_id": winner["start_id"],
                **{name: float(winner[name]) for name in PARAMETERS},
                "calibration_mean_episode_rmse_rad": float(
                    winner["calibration_mean_episode_rmse_rad"]
                ),
                "model_selection_mean_episode_rmse_rad": float(
                    winner["model_selection_mean_episode_rmse_rad"]
                ),
            }
            print(
                f"selected {controller_id} M{motor_id:02d} {winner['start_id']} "
                f"({winner['model_selection_mean_episode_rmse_rad']:.6f} rad)",
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
    error = prediction - episode.q_rad
    sse = float(np.sum(error**2))
    centered = episode.q_rad - float(np.mean(episode.q_rad))
    denominator = float(np.sum(centered**2))
    return {
        "episode_id": episode.episode_id,
        "simultaneous_episode_id": episode.simultaneous_episode_id,
        "motor_id": episode.motor_id,
        "split": episode.split,
        "fixture_id": episode.fixture_id,
        "controller_id": episode.controller_id,
        "profile_id": episode.profile_id,
        "repeat_id": episode.repeat_id,
        "model": model_name,
        "sample_count": len(error),
        "duration_s": float(episode.time_s[-1]),
        "position_rmse_rad": float(np.sqrt(np.mean(error**2))),
        "position_rmse_deg": float(np.degrees(np.sqrt(np.mean(error**2)))),
        "position_mae_rad": float(np.mean(np.abs(error))),
        "position_peak_abs_error_rad": float(np.max(np.abs(error))),
        "position_bias_rad": float(np.mean(error)),
        "position_r2": float(1.0 - sse / denominator) if denominator > 0 else float("nan"),
        "sse_rad2": sse,
        "simulated_effort_peak_Nm": float(np.max(np.abs(torque))),
        "simulated_effort_saturation_fraction": float(np.mean(saturation)),
        "hardware_inner_tracking_rmse_rad": float(
            np.sqrt(np.mean((episode.qref_rad - episode.q_rad) ** 2))
        ),
        "hardware_peak_abs_current_A": float(np.max(np.abs(episode.current_A))),
        "hardware_peak_abs_pwm_fraction": float(np.max(np.abs(episode.pwm_fraction))),
        "hardware_max_temperature_C": float(np.max(episode.temperature_C)),
    }


def evaluate(
    replayer: HardwareReplayer,
    episodes: list[Episode],
    baseline: np.ndarray,
    selected: dict[str, dict[str, dict]],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    metrics: list[dict] = []
    frames: list[pd.DataFrame] = []
    by_episode: dict[str, pd.DataFrame] = {}
    pair_number = 0
    for controller_id in CONTROLLERS:
        for motor_id in range(16):
            pair_number += 1
            pair = [
                ep
                for ep in episodes
                if ep.controller_id == controller_id and ep.motor_id == motor_id
            ]
            baseline_prediction = replayer.simulate_many(pair, baseline)
            theta = np.array(
                [selected[controller_id][str(motor_id)][name] for name in PARAMETERS]
            )
            fitted_prediction = replayer.simulate_many(pair, theta)
            for episode in pair:
                bq, bt, bs = baseline_prediction[episode.episode_id]
                fq, ft, fs = fitted_prediction[episode.episode_id]
                metrics.append(metric_row(episode, "synthetic_baseline", bq, bt, bs))
                metrics.append(metric_row(episode, "hardware_fitted", fq, ft, fs))
                frame = pd.DataFrame(
                    {
                        "episode_id": episode.episode_id,
                        "simultaneous_episode_id": episode.simultaneous_episode_id,
                        "motor_id": episode.motor_id,
                        "split": episode.split,
                        "fixture_id": episode.fixture_id,
                        "controller_id": episode.controller_id,
                        "profile_id": episode.profile_id,
                        "repeat_id": episode.repeat_id,
                        "sample_index": np.arange(len(episode.time_s)),
                        "time_s": episode.time_s,
                        "external_position_command_rad": episode.external_command_rad,
                        "recorded_inner_position_reference_rad": episode.qref_rad,
                        "recorded_inner_velocity_reference_rad_s": episode.vref_rad_s,
                        "hardware_position_rad": episode.q_rad,
                        "hardware_velocity_rad_s": episode.v_rad_s,
                        "synthetic_baseline_position_rad": bq,
                        "hardware_fitted_position_rad": fq,
                        "synthetic_baseline_effort_Nm": bt,
                        "hardware_fitted_effort_Nm": ft,
                        "synthetic_baseline_saturated": bs,
                        "hardware_fitted_saturated": fs,
                        "hardware_current_A": episode.current_A,
                        "hardware_pwm_fraction": episode.pwm_fraction,
                        "hardware_temperature_C": episode.temperature_C,
                    }
                )
                frames.append(frame)
                by_episode[episode.episode_id] = frame
            print(f"evaluated motor/controller pair {pair_number}/32", flush=True)
    return pd.DataFrame(metrics), pd.concat(frames, ignore_index=True), by_episode


def grouped_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    keys = ["split", "fixture_id", "controller_id", "model"]
    for values, group in metrics.groupby(keys, sort=True):
        samples = int(group["sample_count"].sum())
        rows.append(
            {
                **dict(zip(keys, values)),
                "motor_episode_count": len(group),
                "simultaneous_episode_count": group["simultaneous_episode_id"].nunique(),
                "motor_count": group["motor_id"].nunique(),
                "mean_episode_position_rmse_rad": float(group["position_rmse_rad"].mean()),
                "mean_episode_position_rmse_deg": float(group["position_rmse_deg"].mean()),
                "median_episode_position_rmse_rad": float(group["position_rmse_rad"].median()),
                "worst_episode_position_rmse_rad": float(group["position_rmse_rad"].max()),
                "pooled_position_rmse_rad": float(math.sqrt(group["sse_rad2"].sum() / samples)),
                "mean_simulated_saturation_fraction": float(
                    group["simulated_effort_saturation_fraction"].mean()
                ),
            }
        )
    return pd.DataFrame(rows)


def held_out_pairs(metrics: pd.DataFrame) -> pd.DataFrame:
    held = metrics[metrics["split"] == "held_out"].copy()
    index = [
        "episode_id",
        "simultaneous_episode_id",
        "motor_id",
        "fixture_id",
        "controller_id",
        "profile_id",
        "repeat_id",
        "sample_count",
        "duration_s",
    ]
    fields = [
        "position_rmse_rad",
        "position_rmse_deg",
        "position_mae_rad",
        "position_peak_abs_error_rad",
        "position_bias_rad",
        "position_r2",
        "simulated_effort_saturation_fraction",
    ]
    wide = held.pivot(index=index, columns="model", values=fields)
    wide.columns = [f"{field}__{model}" for field, model in wide.columns]
    wide.reset_index(inplace=True)
    baseline = wide["position_rmse_rad__synthetic_baseline"]
    fitted = wide["position_rmse_rad__hardware_fitted"]
    wide["rmse_reduction_percent"] = 100.0 * (baseline - fitted) / baseline
    return wide


def plot_panel(
    episode_ids: list[str], by_episode: dict[str, pd.DataFrame], path: Path, title: str
) -> None:
    episode_ids = [episode_id for episode_id in episode_ids if episode_id in by_episode]
    columns = 2
    rows = math.ceil(len(episode_ids) / columns)
    figure, axes = plt.subplots(rows, columns, figsize=(13, 3.2 * rows), squeeze=False)
    for axis, episode_id in zip(axes.flat, episode_ids):
        frame = by_episode[episode_id]
        axis.plot(frame["time_s"], frame["hardware_position_rad"], "k", lw=1.2, label="hardware")
        axis.plot(
            frame["time_s"],
            frame["hardware_fitted_position_rad"],
            color="#1769aa",
            lw=1.0,
            label="hardware-fitted simulation",
        )
        axis.plot(
            frame["time_s"],
            frame["synthetic_baseline_position_rad"],
            color="#d97706",
            lw=0.9,
            ls="--",
            label="113 g synthetic baseline",
        )
        axis.plot(
            frame["time_s"],
            frame["recorded_inner_position_reference_rad"],
            color="#777777",
            lw=0.7,
            alpha=0.6,
            label="recorded inner reference",
        )
        axis.set_title(episode_id, fontsize=8)
        axis.set_xlabel("time (s)")
        axis.set_ylabel("position (rad)")
        axis.grid(alpha=0.2)
    for axis in axes.flat[len(episode_ids) :]:
        axis.set_visible(False)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=4, fontsize=8)
    figure.suptitle(title)
    figure.tight_layout(rect=(0, 0.05, 1, 0.97))
    figure.savefig(path, dpi=170)
    plt.close(figure)


def create_plots(
    metrics: pd.DataFrame, held: pd.DataFrame, by_episode: dict[str, pd.DataFrame]
) -> None:
    worst = held.nlargest(6, "position_rmse_rad__hardware_fitted")["episode_id"].tolist()
    plot_panel(worst, by_episode, PLOTS_OUT / "largest_held_out_errors.png", "Largest held-out fitted errors")
    examples = []
    for fixture, controller in (("B1", "H1"), ("B1", "H2"), ("G1", "H1"), ("G1", "H2")):
        subset = held[(held["fixture_id"] == fixture) & (held["controller_id"] == controller)]
        target = float(subset["position_rmse_rad__hardware_fitted"].median())
        examples.append(
            subset.iloc[
                np.argmin(np.abs(subset["position_rmse_rad__hardware_fitted"].to_numpy() - target))
            ]["episode_id"]
        )
    plot_panel(examples, by_episode, PLOTS_OUT / "held_out_paired_examples.png", "Held-out simulation versus hardware")

    means = (
        metrics.groupby(["split", "controller_id", "model"])["position_rmse_rad"]
        .mean()
        .reset_index()
    )
    labels = [(split, controller) for split in ("calibration", "model_selection", "held_out") for controller in CONTROLLERS]
    x = np.arange(len(labels), dtype=float)
    figure, axis = plt.subplots(figsize=(11, 5.2))
    for offset, (model, color, label) in enumerate(
        (("synthetic_baseline", "#d97706", "113 g synthetic baseline"), ("hardware_fitted", "#1769aa", "hardware fitted"))
    ):
        values = [
            float(
                means[
                    (means["split"] == split)
                    & (means["controller_id"] == controller)
                    & (means["model"] == model)
                ]["position_rmse_rad"].iloc[0]
            )
            for split, controller in labels
        ]
        axis.bar(x + (offset - 0.5) * 0.36, values, width=0.36, color=color, label=label)
    axis.set_xticks(x, [f"{split}\n{controller}" for split, controller in labels])
    axis.set_ylabel("mean per-motor episode position RMSE (rad)")
    axis.set_title("Simulation-to-hardware error")
    axis.grid(axis="y", alpha=0.2)
    axis.legend()
    figure.tight_layout()
    figure.savefig(PLOTS_OUT / "rmse_summary.png", dpi=180)
    plt.close(figure)

    fitted = metrics[metrics["model"] == "hardware_fitted"]
    heat = fitted.groupby(["controller_id", "motor_id"])["position_rmse_rad"].mean().unstack()
    figure, axis = plt.subplots(figsize=(12, 2.8))
    image = axis.imshow(heat.to_numpy(), aspect="auto", cmap="viridis")
    axis.set_yticks(range(len(heat.index)), heat.index)
    axis.set_xticks(range(16), [str(i) for i in range(16)])
    axis.set_xlabel("motor ID")
    axis.set_title("Mean fitted RMSE by controller and motor")
    figure.colorbar(image, ax=axis, label="rad")
    figure.tight_layout()
    figure.savefig(PLOTS_OUT / "motor_controller_rmse_heatmap.png", dpi=180)
    plt.close(figure)


def rollout_phase_check() -> dict:
    xml = """<mujoco><option timestep='.002' gravity='0 0 0'/><worldbody><body>
    <joint name='j' type='hinge' damping='0'/><geom type='sphere' size='.01' mass='1'/>
    </body></worldbody><sensor><jointpos name='q' joint='j'/><jointvel name='v' joint='j'/></sensor></mujoco>"""
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    data.qpos[0], data.qvel[0] = 1.0, 2.0
    mujoco.mj_forward(model, data)
    size = mujoco.mj_stateSize(model, mujoco.mjtState.mjSTATE_FULLPHYSICS)
    initial = np.empty(size)
    mujoco.mj_getState(model, data, initial, mujoco.mjtState.mjSTATE_FULLPHYSICS)
    state, sensor = rollout.rollout(model, data, initial, np.zeros((3, 0)))
    sensor = np.asarray(sensor).reshape(3, 2)
    state = np.asarray(state).reshape(3, size)
    checks = {
        "first_sensor_is_initial_t0": bool(np.isclose(sensor[0, 0], 1.0)),
        "second_sensor_is_t_plus_dt": bool(np.isclose(sensor[1, 0], 1.004)),
        "first_returned_state_is_post_step": bool(np.isclose(state[0, 1], 1.004)),
    }
    return {"passed": all(checks.values()), "checks": checks, "sensor_q": sensor[:, 0].tolist(), "state_q": state[:, 1].tolist()}


def validate_source_models() -> dict:
    records = []
    for fixture in FIXTURES:
        path = source_model_path(fixture)
        model = mujoco.MjModel.from_xml_path(str(path))
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "actuator_joint")
        body_id = int(model.jnt_bodyid[joint_id])
        moving_mass = float(model.body_subtreemass[body_id])
        expected = 0.000001 if fixture == "M0" else 0.113
        checks = {
            "one_dof": (model.nq, model.nv, model.nu) == (1, 1, 1),
            "physics_step_0p002_s": bool(np.isclose(model.opt.timestep, DT)),
            "joint_axis": bool(np.allclose(model.jnt_axis[joint_id], [0.0, -1.0, 0.0])),
            "moving_mass": bool(np.isclose(moving_mass, expected, atol=1e-12)),
        }
        records.append(
            {
                "fixture_id": fixture,
                "source": relative_to_v5(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "moving_mass_kg": moving_mass,
                "checks": checks,
                "passed": all(checks.values()),
            }
        )
    return {"passed": all(record["passed"] for record in records), "records": records}


def write_models_and_parameters(
    baseline: np.ndarray, selected: dict[str, dict[str, dict]]
) -> pd.DataFrame:
    source_destination = MODELS_OUT / "Design2Data_models"
    shutil.copytree(DESIGN2DATA / "models", source_destination)
    rows = [
        {
            "model": "synthetic_baseline",
            "controller_id": "shared",
            "motor_id": "shared",
            **dict(zip(PARAMETERS, map(float, baseline))),
        }
    ]
    for controller_id in CONTROLLERS:
        for motor_id in range(16):
            values = selected[controller_id][str(motor_id)]
            rows.append(
                {
                    "model": "hardware_fitted",
                    "controller_id": controller_id,
                    "motor_id": motor_id,
                    **{name: float(values[name]) for name in PARAMETERS},
                }
            )
    frame = pd.DataFrame(rows)
    frame.to_csv(MODELS_OUT / "model_parameters.csv", index=False, float_format="%.12g")
    write_json(
        MODELS_OUT / "MODEL_REPLAY_DEFINITION.json",
        {
            "source_model_set": "Design2Data_models/simulation/nominal/C1",
            "fixture_models": {fixture: f"Design2Data_models/simulation/nominal/C1/{fixture}.xml" for fixture in FIXTURES},
            "physical_parameters": "model_parameters.csv",
            "controller_gains_fixed": CONTROLLERS,
            "effort_limit_Nm": EFFORT_LIMIT_NM,
            "control_law": "clip(kp*(qref-q)+kv*(vref-v), -effort_limit, +effort_limit)",
            "qref_and_vref": "recorded Position Trajectory and Velocity Trajectory registers",
        },
    )
    return frame


def write_documents(
    baseline: np.ndarray,
    selected: dict[str, dict[str, dict]],
    metrics: pd.DataFrame,
    held: pd.DataFrame,
    summary: pd.DataFrame,
    timestamp: datetime,
) -> None:
    held_metrics = metrics[metrics["split"] == "held_out"]
    baseline_mean = float(
        held_metrics[held_metrics["model"] == "synthetic_baseline"]["position_rmse_rad"].mean()
    )
    fitted_mean = float(
        held_metrics[held_metrics["model"] == "hardware_fitted"]["position_rmse_rad"].mean()
    )
    reduction = 100.0 * (baseline_mean - fitted_mean) / baseline_mean
    fixture_lines = []
    for fixture in ("B1", "G1"):
        subset = held_metrics[held_metrics["fixture_id"] == fixture]
        base = float(subset[subset["model"] == "synthetic_baseline"]["position_rmse_rad"].mean())
        fitted = float(subset[subset["model"] == "hardware_fitted"]["position_rmse_rad"].mean())
        fixture_lines.append((fixture, base, fitted, 100.0 * (base - fitted) / base))
    write_text(
        METHOD_OUT / "FIT_AND_EVALUATION_METHOD.md",
        f"""# Fit and evaluation method

- Unit of analysis: one motor in one simultaneous episode.
- Calibration: 72 simultaneous episodes, 1,152 motor records.
- Model selection: 23 genuine simultaneous episodes, 368 motor records.
- Held out: 30 simultaneous episodes, 480 motor records.
- Total: 2,000 motor records. Pilots and B0 H2 P05 R03 are excluded.

Each motor and controller is fitted independently, giving 32 fits. A fit shares armature, damping, and friction loss across M0, B0, B1, and B2 calibration records for that motor/controller. H1 uses kp={CONTROLLERS['H1']['kp']:.6f} and kv={CONTROLLERS['H1']['kv']:.6f}; H2 uses kp={CONTROLLERS['H2']['kp']:.6f} and kv={CONTROLLERS['H2']['kv']:.6f}. The symmetric effort limit is {EFFORT_LIMIT_NM:.4f} N m.

The selected values are also applied to ten combined 16-actuator scenes. Each scene runs all IDs on one 2 ms MuJoCo clock. The fixtures remain mechanically independent, so the combined scene reproduces the one-DOF dynamics while showing the recorded rack arrangement.

Position is `(tick - 2048) * 2*pi/4096`. Velocity is `raw * 0.229 rpm`. Current is recorded here using 1 mA/count. The replay uses the recorded Position Trajectory and Velocity Trajectory registers. The measured position and velocity set the initial state once; later measured states are not injected.

Two bounded starts are fitted to P01-P03. A successful candidate is selected by equal-weight mean per-episode position RMSE on genuine P04-P05 records. The choice is frozen before P06-P07 numeric logs are loaded. The primary metric is equal-weight mean active-profile position RMSE per motor episode.

MuJoCo rollout sensors were checked to be pre-step: the first sensor row is t=0. The replay therefore does not prepend a duplicate state or shift predictions by 2 ms.
""",
    )
    write_text(
        HARDWARE_OUT / "HARDWARE_DATA_NOTE.md",
        """# Hardware data used

EPISODES_USED.csv lists the 125 accepted simultaneous science episodes. The paired Parquet file contains 2,000 per-motor active-profile records aligned with both simulations. Raw CSV logs and media remain unchanged in Model2Prototype.

The camera records are supporting evidence. No camera-to-angle calibration was available, so ArUco detections are not reported as an angle ground truth in this analysis.
""",
    )
    result_lines = [
        "# Results overview",
        "",
        f"Held-out mean per-motor episode RMSE was {baseline_mean:.6f} rad ({math.degrees(baseline_mean):.3f} deg) for the 113 g synthetic baseline and {fitted_mean:.6f} rad ({math.degrees(fitted_mean):.3f} deg) after hardware fitting. The change is {reduction:.1f}%.",
        "",
        "| Held-out fixture | Baseline RMSE (rad) | Fitted RMSE (rad) | Change |",
        "|---|---:|---:|---:|",
    ]
    result_lines.extend(
        f"| {fixture} | {base:.6f} | {fitted:.6f} | {change:.1f}% |"
        for fixture, base, fitted, change in fixture_lines
    )
    result_lines.extend(
        [
            "",
            "Detailed results are in episode_metrics.csv, held_out_results.csv, summary_by_configuration_controller.csv, and fitted_parameters.csv.",
        ]
    )
    write_text(RESULTS_OUT / "RESULTS_OVERVIEW.md", "\n".join(result_lines))

    fitted_only = metrics[(metrics["split"] == "held_out") & (metrics["model"] == "hardware_fitted")]
    worst_fixture = (
        fitted_only.groupby("fixture_id")["position_rmse_rad"].mean().sort_values(ascending=False).index[0]
    )
    friction_bound_fits = []
    for controller_id in CONTROLLERS:
        for motor_id in range(16):
            values = selected[controller_id][str(motor_id)]
            if np.isclose(
                values["frictionloss_Nm"], UPPER[2], atol=1e-6 * (UPPER[2] - LOWER[2])
            ):
                friction_bound_fits.append(f"{controller_id}/M{motor_id:02d}")
    friction_bound_text = ", ".join(friction_bound_fits) if friction_bound_fits else "none"
    write_text(
        CONCLUSIONS_OUT / "CONCLUSION_AND_LIMITATIONS.md",
        f"""# Conclusion and limitations

The hardware-fitted models changed held-out mean RMSE from {baseline_mean:.6f} to {fitted_mean:.6f} rad. Of the two held-out fixture families, {worst_fixture} has the larger fitted mean error. Per-motor and per-controller variation remains visible in the heatmap and parameter table.

These are effective closed-loop parameters, not isolated motor constants. No selected parameter reaches its declared upper fit bound.

Output torque was not measured. The result assumes the fixed H1/H2 engineering gains and a symmetric {EFFORT_LIMIT_NM:.4f} N m joint-effort limit. Command delay, compliance, backlash, cable forces, temperature dependence, and supply-voltage dependence were not identified. CAD inertia distribution may differ from each assembled fixture. Current and PWM are supporting telemetry, not calibrated output torque. ArUco video is not used as an angle measurement because no camera-to-joint calibration was recorded.

Ideal agreement would require correct geometry, masses, inertia, encoder zero, gravity phase, controller gains, effort scale, timing, rigid mechanics, and loss model for every motor. Several of those assumptions remain unmeasured or simplified.
""",
    )
    write_text(
        CONCLUSIONS_OUT / "RECOMMENDED_NEXT_STEP.md",
        """# Recommended next step

Measure output-joint torque and command-to-motion delay on the same clock, then collect a new calibration and held-out set. Keep the present held-out records outside the next fit.
""",
    )
    write_text(
        PACKAGE / "README.md",
        """# 16-motor Sim2Real

This folder contains 32 independent fits: one for each motor ID 0-15 under H1 and H2. It includes the 113 g source models, exact episode list, method, fitted parameters, paired hardware/simulation samples, plots, held-out results, conclusions, reproduction code, and validation report.
""",
    )
    write_json(
        RESULTS_OUT / "analysis_timestamp.json",
        {"date_time": timestamp.isoformat(), "time_zone": "Asia/Dubai"},
    )


def write_inventory_and_manifest() -> None:
    inventory = []
    manifest_path = VALIDATION_OUT / "FILE_MANIFEST.sha256"
    inventory_path = VALIDATION_OUT / "FILE_INVENTORY.csv"
    for path in sorted(PACKAGE.rglob("*")):
        if path.is_file() and path not in {manifest_path, inventory_path}:
            inventory.append({"relative_path": str(path.relative_to(PACKAGE)), "size_bytes": path.stat().st_size})
    pd.DataFrame(inventory).to_csv(inventory_path, index=False)
    lines = []
    for path in sorted(PACKAGE.rglob("*")):
        if path.is_file() and path != manifest_path:
            lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  ./{path.relative_to(PACKAGE)}")
    write_text(manifest_path, "\n".join(lines))


def main() -> None:
    timestamp = datetime.now(TZ)
    index = build_episode_index()
    baseline = load_baseline()
    reset_outputs()
    index.drop(columns=["path"]).to_csv(HARDWARE_OUT / "EPISODES_USED.csv", index=False)
    pd.DataFrame(
        [{"simultaneous_episode_id": name, "reason": reason} for name, reason in EXCLUDED.items()]
    ).to_csv(VALIDATION_OUT / "EXCLUDED_ENTRIES.csv", index=False)

    stage_order = ["episode_metadata_indexed"]
    phase_check = rollout_phase_check()
    if not phase_check["passed"]:
        raise RuntimeError("MuJoCo rollout phase validation failed")
    write_json(VALIDATION_OUT / "ROLLOUT_TIMESTAMP_PHASE_CHECK.json", phase_check)
    model_validation = validate_source_models()
    if not model_validation["passed"]:
        raise RuntimeError("113 g source model validation failed")
    write_json(VALIDATION_OUT / "SOURCE_MODEL_VALIDATION.json", model_validation)

    replayer = HardwareReplayer(nthread=8)
    try:
        calibration = load_split(index, "calibration")
        stage_order.append("calibration_numeric_loaded")
        candidates: list[dict] = []
        for controller_id in CONTROLLERS:
            for motor_id in range(16):
                candidates.extend(fit_pair(replayer, calibration, controller_id, motor_id))
        stage_order.append("calibration_fits_complete")

        model_selection = load_split(index, "model_selection")
        stage_order.append("model_selection_numeric_loaded")
        selected = select_candidates(replayer, model_selection, candidates)
        stage_order.append("selection_frozen")
        write_json(
            RESULTS_OUT / "FROZEN_SELECTION_BEFORE_HELD_OUT.json",
            {
                "frozen_at": datetime.now(TZ).isoformat(),
                "selection_rule": "minimum genuine model-selection mean per-episode RMSE among successful candidates",
                "selected": selected,
                "held_out_numeric_loaded": False,
            },
        )

        held_out = load_split(index, "held_out")
        stage_order.append("held_out_numeric_loaded")
        all_episodes = calibration + model_selection + held_out
        if len(all_episodes) != 2000:
            raise ValueError(f"expected 2000 motor records, found {len(all_episodes)}")
        metrics, paired_samples, by_episode = evaluate(replayer, all_episodes, baseline, selected)
        stage_order.append("held_out_scored")
    finally:
        replayer.close()

    summary = grouped_summary(metrics)
    held = held_out_pairs(metrics)
    poor = held.nlargest(10, "position_rmse_rad__hardware_fitted").copy()
    poor["case_definition"] = "ten largest fitted held-out RMSE values; review list, not a pass/fail threshold"

    metrics.drop(columns=["sse_rad2"]).to_csv(
        RESULTS_OUT / "episode_metrics.csv", index=False, float_format="%.12g"
    )
    summary.to_csv(
        RESULTS_OUT / "summary_by_configuration_controller.csv", index=False, float_format="%.12g"
    )
    split_summary = (
        metrics.groupby(["split", "controller_id", "model"], as_index=False)
        .agg(
            motor_episode_count=("episode_id", "count"),
            mean_episode_position_rmse_rad=("position_rmse_rad", "mean"),
            mean_episode_position_rmse_deg=("position_rmse_deg", "mean"),
            median_episode_position_rmse_rad=("position_rmse_rad", "median"),
        )
    )
    split_summary.to_csv(RESULTS_OUT / "summary_by_split_controller.csv", index=False, float_format="%.12g")
    held.to_csv(RESULTS_OUT / "held_out_results.csv", index=False, float_format="%.12g")
    poor.to_csv(RESULTS_OUT / "poor_agreement_cases.csv", index=False, float_format="%.12g")
    pd.DataFrame(candidates).to_csv(
        RESULTS_OUT / "optimizer_candidates.csv", index=False, float_format="%.12g"
    )
    parameters = write_models_and_parameters(baseline, selected)
    parameters.to_csv(RESULTS_OUT / "fitted_parameters.csv", index=False, float_format="%.12g")
    paired_samples.to_parquet(
        HARDWARE_OUT / "paired_simulation_hardware_samples.parquet",
        index=False,
        compression="zstd",
    )
    create_plots(metrics, held, by_episode)
    write_documents(baseline, selected, metrics, held, summary, timestamp)

    held_metric = metrics[metrics["split"] == "held_out"]
    held_means = {
        model: float(held_metric[held_metric["model"] == model]["position_rmse_rad"].mean())
        for model in ("synthetic_baseline", "hardware_fitted")
    }
    selected_count = sum(len(value) for value in selected.values())
    finite_columns = ["position_rmse_rad", "position_mae_rad", "position_peak_abs_error_rad"]
    checks = {
        "simultaneous_science_episode_count_125": len(index) == 125,
        "motor_record_count_2000": metrics["episode_id"].nunique() == 2000,
        "metric_row_count_4000": len(metrics) == 4000,
        "calibration_simultaneous_count_72": int((index["split"] == "calibration").sum()) == 72,
        "model_selection_simultaneous_count_23": int((index["split"] == "model_selection").sum()) == 23,
        "held_out_simultaneous_count_30": int((index["split"] == "held_out").sum()) == 30,
        "excluded_entries_absent": not any(name in set(index["simultaneous_episode_id"]) for name in EXCLUDED),
        "thirty_two_frozen_fits": selected_count == 32,
        "four_candidates_per_fit": len(candidates) == 128,
        "every_fit_has_successful_candidate": all(
            any(row["success"] for row in candidates if row["controller_id"] == controller and row["motor_id"] == motor)
            for controller in CONTROLLERS for motor in range(16)
        ),
        "held_out_loaded_after_selection_freeze": stage_order.index("held_out_numeric_loaded") > stage_order.index("selection_frozen"),
        "all_primary_metrics_finite": bool(np.isfinite(metrics[finite_columns].to_numpy()).all()),
        "rollout_phase_check_passed": phase_check["passed"],
        "source_models_passed_113g_check": model_validation["passed"],
    }
    result = {
        "schema_version": "v5-16motor-sim2real-1",
        "run_time_asia_dubai": timestamp.isoformat(),
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
            "link_mass_kg": 0.025,
            "pin_mass_each_kg": 0.004,
            "payload_mass_each_kg": 0.040,
            "loaded_fixture_total_kg": 0.113,
        },
        "counts": {
            "simultaneous_science_episodes": 125,
            "motor_records": 2000,
            "fits": 32,
            "candidates": 128,
            "by_split_and_controller": EXPECTED_SIMULTANEOUS,
        },
        "stage_order": stage_order,
        "primary_metric": "equal-weight mean per-motor episode active-profile position RMSE in radians",
        "synthetic_baseline_parameters": dict(zip(PARAMETERS, map(float, baseline))),
        "held_out_mean_episode_rmse_rad": held_means,
        "selected_parameters": selected,
        "validation_passed": all(checks.values()),
    }
    write_json(RESULTS_OUT / "result.json", result)
    write_json(
        VALIDATION_OUT / "validation_report.json",
        {
            "passed": all(checks.values()),
            "checks": checks,
            "stage_order": stage_order,
            "notes": {
                "vision": "not converted to angle; no camera-to-joint calibration was recorded",
                "torque": "simulated from fixed gains and effort limit; not measured",
                "current_unit_A_per_count": CURRENT_UNIT_A,
            },
        },
    )
    write_text(
        Path(__file__).parent / "requirements.txt",
        f"mujoco=={mujoco.__version__}\nnumpy=={np.__version__}\nscipy=={scipy.__version__}\npandas=={pd.__version__}\npyarrow=={pyarrow.__version__}\nmatplotlib=={matplotlib.__version__}",
    )
    write_text(
        Path(__file__).parent / "RUN_INSTRUCTIONS.txt",
        "Run with ../../../.venv/bin/python 06_Reproduction/run_sim2real_16.py from 5_Sim2Real. The script reads accepted CSV logs and generated models only; it does not access hardware.",
    )
    write_inventory_and_manifest()
    print(json.dumps({"passed": all(checks.values()), "held_out_mean_rmse_rad": held_means, "output": str(PACKAGE)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
