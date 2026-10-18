#!/usr/bin/env python3
"""Run the Sim-Position identification study for Chapter 2.

Both methods consume the same hardware-shaped analysis view: timestamped
applied position, measured position and velocity, validity/saturation flags,
fixed controller metadata, and a matched fixture model. MuJoCo true state,
generalized force, and disclosed source parameters are never exposed to
either Sim-Position fitter. Both methods identify only the three declared
MuJoCo-equivalent joint parameters. Source parameters are read only after
fitting so that the simulation exercise can be graded.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib
import mujoco
import numpy as np
from scipy.optimize import least_squares, lsq_linear
from scipy.signal import savgol_filter

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "data" / "chapter-02" / "releases" / "rs06-sim-data-v1"
IDENTIFICATION_CONTRACT_PATH = PACKAGE / "identification-contract.json"
RESULT_DIR = PACKAGE / "sim-position-results-v1"
PLOT_DIR = ROOT / "assets" / "chapter-02" / "rs06-sim-position-results-v1"
JOINT_NAMES = ("armature", "damping", "frictionloss")
JOINT_UNITS = ("kg·m²", "N·m·s/rad", "N·m")
JOINT_LOWER = np.array([0.0002, 0.00001, 0.001], dtype=float)
JOINT_UPPER = np.array([0.0080, 0.05000, 0.200], dtype=float)
METHOD2_JOINT_STARTS = (
    np.array([0.0005, 0.0001, 0.012], dtype=float),
    np.array([0.0020, 0.0020, 0.080], dtype=float),
)
METHOD2_SAMPLE_STRIDE = 2
METHOD2_MAX_NFEV = 40
COLORS = {
    "input": "#202020",
    "source": "#2768a8",
    "nominal_model": "#d04a35",
    "sim_position_m1": "#23966f",
    "sim_position_m2": "#7c55a5",
}
CANDIDATE_FOR_METHOD = {
    "method1": "sim_position_m1",
    "method2": "sim_position_m2",
}
CANDIDATE_DISPLAY = {
    "nominal_model": "Nominal Model",
    "sim_position_m1": "Sim-Position M1 Candidate",
    "sim_position_m2": "Sim-Position M2 Candidate",
}


@dataclass(frozen=True)
class Episode:
    episode_id: str
    split: str
    controller_id: str
    fixture_id: str
    profile_id: str
    # Only logical, hardware-realistic fields are admitted here.
    values: dict[str, np.ndarray]


@dataclass(frozen=True)
class Candidate:
    joint: np.ndarray


@dataclass(frozen=True)
class Fit:
    method_id: str
    candidate: Candidate
    calibration_objective: float
    selection_score: float
    diagnostics: dict


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_episodes() -> tuple[dict, dict, dict, list[Episode]]:
    contract = read_json(PACKAGE / "experiment-contract.json")
    manifest = read_json(PACKAGE / "sim-position-manifest.json")
    identification = read_json(IDENTIFICATION_CONTRACT_PATH)
    if identification["release_id"] != contract["release_id"]:
        raise ValueError("identification contract and experiment release IDs differ")
    archive = np.load(PACKAGE / identification["archive_file"], allow_pickle=False)
    field_map = identification["field_map"]
    missing = [source for source in field_map.values() if source not in archive.files]
    if missing:
        raise KeyError(f"Mapped analysis fields are absent from the archive: {missing}")
    episodes = []
    for metadata in manifest["episodes"]:
        sample_slice = slice(int(metadata["start"]), int(metadata["stop"]))
        # This projection is an implementation guard: fitting code cannot read
        # MuJoCo generation-audit arrays even though the simulation archive retains them.
        values = {
            logical: archive[source][sample_slice].copy()
            for logical, source in field_map.items()
        }
        episodes.append(
            Episode(
                episode_id=metadata["episode_id"],
                split=metadata["split"],
                controller_id=metadata["controller_id"],
                fixture_id=metadata["fixture_id"],
                profile_id=metadata["profile_id"],
                values=values,
            )
        )
    return contract, manifest, identification, episodes


def signal(episode: Episode, logical_name: str) -> np.ndarray:
    if logical_name not in episode.values:
        raise KeyError(
            f"Episode {episode.episode_id!r} has no admitted logical field "
            f"{logical_name!r}"
        )
    return episode.values[logical_name]


def rmse(error: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(error))))


def mae(error: np.ndarray) -> float:
    return float(np.mean(np.abs(error)))


def subset(episodes: Iterable[Episode], split: str) -> list[Episode]:
    return [episode for episode in episodes if episode.split == split]


def model_path(identification: dict, controller_id: str, fixture_id: str) -> Path:
    return (
        PACKAGE
        / identification["candidate_model_tree"]
        / controller_id
        / f"{fixture_id}.xml"
    )


def controller_gains(
    candidate: Candidate, controller_id: str, identification: dict
) -> tuple[float, float]:
    coordinate = identification["controller_mapping"]["coordinates"][controller_id]
    return (
        float(coordinate.get("kp_Nm_per_rad", coordinate.get("normalized_P"))),
        float(coordinate.get("kv_Nm_s_per_rad", coordinate.get("normalized_D"))),
    )


def initial_candidate(contract: dict, identification: dict) -> Candidate:
    return Candidate(
        joint=np.array(
            [contract["nominal_model"][name] for name in JOINT_NAMES], dtype=float
        )
    )


class ReplayEngine:
    """Replay a candidate using the same recorded-input boundary for both methods."""

    def __init__(self, contract: dict, identification: dict):
        self.identification = identification
        # Store only the sensor resolution needed for candidate output. The
        # replay object passed to the fitters does not retain source-model
        # parameters from the experiment contract.
        self.position_resolution_rad = float(
            contract["simulation"]["sensor_emulation"]["position_resolution_rad"]
        )
        self.models: dict[tuple[str, str], mujoco.MjModel] = {}

    def model(self, episode: Episode, candidate: Candidate) -> mujoco.MjModel:
        key = (episode.controller_id, episode.fixture_id)
        if key not in self.models:
            self.models[key] = mujoco.MjModel.from_xml_path(
                str(model_path(self.identification, *key))
            )
        model = self.models[key]
        model.dof_armature[0] = float(candidate.joint[0])
        model.dof_damping[0] = float(candidate.joint[1])
        model.dof_frictionloss[0] = float(candidate.joint[2])
        kp, kv = controller_gains(candidate, episode.controller_id, self.identification)
        model.actuator_gainprm[0, 0] = kp
        model.actuator_biasprm[0, 1] = -kp
        model.actuator_biasprm[0, 2] = -kv
        temporary_data = mujoco.MjData(model)
        mujoco.mj_setConst(model, temporary_data)
        return model

    def simulate_true(self, episode: Episode, candidate: Candidate) -> np.ndarray:
        model = self.model(episode, candidate)
        data = mujoco.MjData(model)
        command = signal(episode, "applied_position_rad")
        time = signal(episode, "time_s")
        target_position = signal(episode, "observed_position_rad")
        target_velocity = signal(episode, "observed_velocity_rad_s")
        if command.size != time.size or command.size == 0:
            raise ValueError(f"Invalid command/time record in {episode.episode_id}")
        sample_dt = float(np.median(np.diff(time)))
        if not np.allclose(np.diff(time), sample_dt, rtol=0.0, atol=1.0e-8):
            raise ValueError(
                f"Episode {episode.episode_id} requires a frozen uniform analysis grid"
            )
        substeps_float = sample_dt / model.opt.timestep
        substeps = round(substeps_float)
        if not np.isclose(substeps_float, substeps):
            raise ValueError("sample interval must be an integer number of MuJoCo steps")
        data.qpos[0] = float(target_position[0])
        data.qvel[0] = float(target_velocity[0])
        data.ctrl[0] = float(command[0])
        mujoco.mj_forward(model, data)

        def delayed_command(query_time: float) -> float:
            delayed_time = query_time - float(
                self.identification["controller_mapping"].get(
                    "fixed_command_delay_s", 0.0
                )
            )
            command_index = int(np.searchsorted(time, delayed_time, side="right") - 1)
            command_index = min(max(command_index, 0), command.size - 1)
            return float(command[command_index])

        position = np.empty(command.size, dtype=float)
        for index, sample_time in enumerate(time):
            data.ctrl[0] = delayed_command(float(sample_time))
            mujoco.mj_forward(model, data)
            position[index] = data.qpos[0]
            if index + 1 < command.size:
                for substep in range(substeps):
                    query_time = float(sample_time) + substep * model.opt.timestep
                    data.ctrl[0] = delayed_command(query_time)
                    mujoco.mj_step(model, data)
        return position

    def position_meas(self, position_true: np.ndarray) -> np.ndarray:
        return (
            np.round(position_true / self.position_resolution_rad)
            * self.position_resolution_rad
        )


def delayed_samples(command: np.ndarray, time: np.ndarray, delay_s: float) -> np.ndarray:
    indices = np.searchsorted(time, time - delay_s, side="right") - 1
    return command[np.clip(indices, 0, command.size - 1)]


def fixture_bias_and_inertia(
    episode: Episode,
    position: np.ndarray,
    velocity: np.ndarray,
    identification: dict,
) -> tuple[np.ndarray, float, tuple[float, float]]:
    """Reconstruct known fixture terms from measured state and a matched MJCF."""

    model = mujoco.MjModel.from_xml_path(
        str(model_path(identification, episode.controller_id, episode.fixture_id))
    )
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    full_mass = np.zeros((model.nv, model.nv), dtype=float)
    mujoco.mj_fullM(model, full_mass, data.qM)
    fixture_inertia = float(full_mass[0, 0] - model.dof_armature[0])
    bias = np.empty(position.size, dtype=float)
    for index, (q_value, v_value) in enumerate(zip(position, velocity)):
        data.qpos[0] = float(q_value)
        data.qvel[0] = float(v_value)
        mujoco.mj_forward(model, data)
        bias[index] = data.qfrc_bias[0]
    force_range = (
        float(model.actuator_forcerange[0, 0]),
        float(model.actuator_forcerange[0, 1]),
    )
    return bias, fixture_inertia, force_range


def method1_regression(
    calibration: list[Episode], delay_s: float, identification: dict
) -> tuple[np.ndarray, float, dict]:
    method = identification["method1"]
    window = int(method["filter"]["savgol_window_samples"])
    order = int(method["filter"]["savgol_polynomial_order"])
    integration_window = int(method["integration_window_samples"])
    integration_step = int(method["integration_step_samples"])
    speed_threshold = float(method["moving_speed_threshold_rad_s"])
    moving_fraction = float(method["minimum_moving_fraction"])
    mapping = identification["controller_mapping"]
    lower = JOINT_LOWER
    upper = JOINT_UPPER
    blocks_x: list[np.ndarray] = []
    blocks_y: list[np.ndarray] = []
    rows_by_episode = {}
    fixtures = {}
    for episode in calibration:
        time = signal(episode, "time_s")
        q_meas = signal(episode, "observed_position_rad")
        v_meas = signal(episode, "observed_velocity_rad_s")
        command = delayed_samples(
            signal(episode, "applied_position_rad"), time, delay_s
        )
        valid = signal(episode, "valid").astype(bool)
        saturated = signal(episode, "saturated").astype(bool)
        local_window = min(window, q_meas.size if q_meas.size % 2 else q_meas.size - 1)
        if local_window <= order:
            raise ValueError(f"Filter window is invalid in {episode.episode_id}")
        q = savgol_filter(q_meas, local_window, order, mode="interp")
        velocity = savgol_filter(v_meas, local_window, order, mode="interp")
        bias, fixture_inertia, force_range = fixture_bias_and_inertia(
            episode, q, velocity, identification
        )
        fixtures[f"{episode.controller_id}/{episode.fixture_id}"] = fixture_inertia
        coordinate = mapping["coordinates"][episode.controller_id]
        p_coordinate = float(
            coordinate.get("kp_Nm_per_rad", coordinate.get("normalized_P"))
        )
        d_coordinate = float(
            coordinate.get("kv_Nm_s_per_rad", coordinate.get("normalized_D"))
        )
        controller_effort = np.clip(
            p_coordinate * (command - q) - d_coordinate * velocity,
            force_range[0],
            force_range[1],
        )
        rows = []
        responses = []
        margin = local_window // 2 + 1
        stop = q.size - integration_window - margin
        for start in range(margin, stop, integration_step):
            end = start + integration_window
            sample_slice = slice(start, end + 1)
            if not np.all(valid[sample_slice]) or np.any(saturated[sample_slice]):
                continue
            moving = np.abs(velocity[sample_slice]) >= speed_threshold
            if float(np.mean(moving)) < moving_fraction:
                continue
            local_time = time[sample_slice]
            delta_velocity = float(velocity[end] - velocity[start])
            delta_position = float(q[end] - q[start])
            friction_direction = np.where(
                moving, np.sign(velocity[sample_slice]), 0.0
            )
            direction_integral = float(np.trapezoid(friction_direction, local_time))
            bias_integral = float(np.trapezoid(bias[sample_slice], local_time))
            effort_integral = float(
                np.trapezoid(controller_effort[sample_slice], local_time)
            )
            rows.append(
                [
                    delta_velocity,
                    delta_position,
                    direction_integral,
                ]
            )
            responses.append(
                effort_integral
                - fixture_inertia * delta_velocity
                - bias_integral
            )
        if not rows:
            raise ValueError(f"No qualified Method 1 windows in {episode.episode_id}")
        design = np.asarray(rows, dtype=float)
        response = np.asarray(responses, dtype=float)
        weight = 1.0 / math.sqrt(response.size)
        blocks_x.append(design * weight)
        blocks_y.append(response * weight)
        rows_by_episode[episode.episode_id] = int(response.size)
    design = np.vstack(blocks_x)
    response = np.concatenate(blocks_y)
    result = lsq_linear(design, response, bounds=(lower, upper), lsmr_tol="auto")
    residual = design @ result.x - response
    scaled_design = design * np.array([0.001, 0.015, 0.01])
    diagnostics = {
        "bounded_solver_success": bool(result.success),
        "integrated_balance_rmse_Nm_s": float(
            np.sqrt(np.sum(np.square(residual)) / len(blocks_y))
        ),
        "weighted_design_rank": int(np.linalg.matrix_rank(design)),
        "scaled_design_condition_number": float(np.linalg.cond(scaled_design)),
        "qualified_window_count": int(sum(rows_by_episode.values())),
        "windows_by_episode": rows_by_episode,
        "fixture_inertia_kg_m2": fixtures,
    }
    return result.x, diagnostics["integrated_balance_rmse_Nm_s"], diagnostics


def split_score(
    episodes: list[Episode], split_name: str, candidate: Candidate, engine: ReplayEngine
) -> float:
    scores = []
    for episode in subset(episodes, split_name):
        prediction = engine.simulate_true(episode, candidate)
        target = signal(episode, "observed_position_rad")
        valid = signal(episode, "valid").astype(bool)
        scores.append(rmse(prediction[valid] - target[valid]))
    return float(np.mean(scores))


def fit_method1(
    episodes: list[Episode], engine: ReplayEngine, identification: dict
) -> Fit:
    calibration = subset(episodes, "calibration")
    candidates = []
    fixed_delay_s = float(
        identification["controller_mapping"].get("fixed_command_delay_s", 0.0)
    )
    for delay_s in [fixed_delay_s]:
        fitted, objective, diagnostics = method1_regression(
            calibration, float(delay_s), identification
        )
        candidate = Candidate(joint=fitted[:3])
        selection = split_score(episodes, "model_selection", candidate, engine)
        candidates.append((selection, objective, candidate, diagnostics))
    selection, objective, candidate, diagnostics = min(candidates, key=lambda item: item[0])
    diagnostics.update(
        {
            "evidence_status": identification["method1"]["status"],
            "consumed_logical_fields": identification["fit_field_allowlist"],
            "filter": identification["method1"]["filter"],
            "integration_window_samples": identification["method1"][
                "integration_window_samples"
            ],
            "integration_step_samples": identification["method1"][
                "integration_step_samples"
            ],
            "delay_candidates": [
                {
                    "delay_s": fixed_delay_s,
                    "calibration_integrated_balance_rmse_Nm_s": item[1],
                    "model_selection_output_gap_rmse_rad": item[0],
                }
                for item in candidates
            ],
        }
    )
    return Fit("method1", candidate, objective, selection, diagnostics)


def fit_method2(
    episodes: list[Episode],
    engine: ReplayEngine,
    identification: dict,
    *,
    quick: bool,
) -> Fit:
    calibration = subset(episodes, "calibration")
    mapping = identification["controller_mapping"]
    lower = JOINT_LOWER
    upper = JOINT_UPPER
    starts = list(METHOD2_JOINT_STARTS)
    if quick:
        starts = starts[:1]
    stride = METHOD2_SAMPLE_STRIDE

    def residual(values: np.ndarray, delay_s: float) -> np.ndarray:
        candidate = Candidate(values[:3])
        blocks = []
        for episode in calibration:
            predicted = engine.simulate_true(episode, candidate)
            target = signal(episode, "observed_position_rad")
            valid = signal(episode, "valid").astype(bool)
            retained = np.flatnonzero(valid)[::stride]
            if retained.size == 0:
                raise ValueError(f"No valid Method 2 samples in {episode.episode_id}")
            blocks.append(
                (predicted[retained] - target[retained]) / math.sqrt(retained.size)
            )
        return np.concatenate(blocks)

    max_nfev = 18 if quick else METHOD2_MAX_NFEV
    results = []
    fixed_delay_s = float(mapping.get("fixed_command_delay_s", 0.0))
    for delay_s in [fixed_delay_s]:
        for start_index, start in enumerate(starts):
            result = least_squares(
                lambda values: residual(values, float(delay_s)),
                start,
                bounds=(lower, upper),
                max_nfev=max_nfev,
                xtol=1.0e-8,
                ftol=1.0e-8,
                gtol=1.0e-8,
                x_scale="jac",
            )
            calibration_objective = float(
                np.sqrt(
                    np.sum(np.square(residual(result.x, float(delay_s))))
                    / len(calibration)
                )
            )
            candidate = Candidate(result.x[:3])
            selection = split_score(episodes, "model_selection", candidate, engine)
            results.append(
                (selection, calibration_objective, start_index, result, candidate)
            )
    selection, objective, start_index, selected_result, candidate = min(
        results, key=lambda item: item[0]
    )
    diagnostics = {
        "evidence_status": identification["method2"]["status"],
        "consumed_logical_fields": identification["fit_field_allowlist"],
        "sample_stride": stride,
        "episode_weighting": "equal complete episode",
        "joint_parameter_bounds": {
            name: [float(low), float(high)]
            for name, low, high in zip(JOINT_NAMES, JOINT_LOWER, JOINT_UPPER)
        },
        "fixed_controller_conditions": mapping["coordinates"],
        "starts": [start.tolist() for start in starts],
        "candidate_results": [
            {
                "delay_s": fixed_delay_s,
                "start_index": int(item[2]),
                "calibration_output_gap_rmse_rad": float(item[1]),
                "model_selection_output_gap_rmse_rad": float(item[0]),
            }
            for item in results
        ],
        "selected_start_index": int(start_index),
        "function_evaluations": int(selected_result.nfev),
        "solver_success": bool(selected_result.success),
        "solver_message": str(selected_result.message),
        "quick_mode": bool(quick),
    }
    return Fit("method2", candidate, objective, selection, diagnostics)


def replay_candidates(
    episodes: list[Episode], candidates: dict[str, Candidate], engine: ReplayEngine
) -> dict[str, dict[str, dict[str, np.ndarray]]]:
    predictions = {}
    for candidate_id, candidate in candidates.items():
        predictions[candidate_id] = {}
        for episode in episodes:
            position_true = engine.simulate_true(episode, candidate)
            predictions[candidate_id][episode.episode_id] = {
                "position_true_rad": position_true,
                "position_meas_rad": engine.position_meas(position_true),
            }
    return predictions


def episode_metrics(
    episodes: list[Episode], predictions: dict[str, dict]
) -> list[dict]:
    rows = []
    for candidate_id, candidate_predictions in predictions.items():
        for episode in episodes:
            candidate = candidate_predictions[episode.episode_id]["position_meas_rad"]
            target = signal(episode, "observed_position_rad")
            command = signal(episode, "applied_position_rad")
            valid = signal(episode, "valid").astype(bool)
            gap = candidate[valid] - target[valid]
            tracking = candidate[valid] - command[valid]
            rows.append(
                {
                    "candidate": candidate_id,
                    "episode_id": episode.episode_id,
                    "split": episode.split,
                    "episode_controller": episode.controller_id,
                    "fixture_id": episode.fixture_id,
                    "profile_id": episode.profile_id,
                    "output_gap_rmse_rad": rmse(gap),
                    "output_gap_mae_rad": mae(gap),
                    "output_gap_max_abs_rad": float(np.max(np.abs(gap))),
                    "tracking_rmse_rad": rmse(tracking),
                    "tracking_mae_rad": mae(tracking),
                    "tracking_max_abs_rad": float(np.max(np.abs(tracking))),
                }
            )
    return rows


def aggregate_metrics(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        grouped.setdefault((row["candidate"], row["split"]), []).append(row)
    nominal = {
        split: float(
            np.mean(
                [
                    row["output_gap_rmse_rad"]
                    for row in rows
                    if row["candidate"] == "nominal_model" and row["split"] == split
                ]
            )
        )
        for split in ("calibration", "model_selection", "held_out")
    }
    output = []
    for (candidate_id, split), items in sorted(grouped.items()):
        gap = float(np.mean([item["output_gap_rmse_rad"] for item in items]))
        output.append(
            {
                "candidate": candidate_id,
                "split": split,
                "episode_count": len(items),
                "equal_episode_output_gap_rmse_rad": gap,
                "equal_episode_tracking_rmse_rad": float(
                    np.mean([item["tracking_rmse_rad"] for item in items])
                ),
                "gap_reduction_vs_nominal_percent": (
                    0.0
                    if candidate_id == "nominal_model"
                    else 100.0 * (1.0 - gap / nominal[split])
                ),
            }
        )
    return output


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def candidate_record(candidate: Candidate) -> dict:
    return {
        "joint_parameters": {
            name: float(value) for name, value in zip(JOINT_NAMES, candidate.joint)
        }
    }


def parameter_rows(
    source: Candidate, nominal: Candidate, fits: list[Fit]
) -> list[dict]:
    candidates = {"source_model": source, "nominal_model": nominal}
    candidates.update(
        {CANDIDATE_FOR_METHOD[fit.method_id]: fit.candidate for fit in fits}
    )
    rows = []
    for index, (name, unit) in enumerate(zip(JOINT_NAMES, JOINT_UNITS)):
        row = {"parameter": name, "unit": unit}
        target = source.joint[index]
        for candidate_id, candidate in candidates.items():
            value = candidate.joint[index]
            row[candidate_id] = float(value)
            row[f"{candidate_id}_difference_percent"] = float(
                100.0 * (value - target) / target
            )
        rows.append(row)
    return rows


def mapping_rows(
    source: Candidate, nominal: Candidate, fits: list[Fit], identification: dict
) -> list[dict]:
    rows = []
    for controller_id, coordinate in identification["controller_mapping"][
        "coordinates"
    ].items():
        row = {
            "controller_id": controller_id,
            "kp_Nm_per_rad": float(
                coordinate.get("kp_Nm_per_rad", coordinate.get("normalized_P"))
            ),
            "kv_Nm_s_per_rad": float(
                coordinate.get("kv_Nm_s_per_rad", coordinate.get("normalized_D"))
            ),
            "command_delay_s": float(
                identification["controller_mapping"].get("fixed_command_delay_s", 0.0)
            ),
            "identification_status": "known and fixed; not fitted",
        }
        rows.append(row)
    return rows


def metric_label(prefix: str, error: np.ndarray) -> str:
    return (
        f"{prefix}: RMSE={rmse(error):.5f} rad, "
        f"MAE={mae(error):.5f}, max={np.max(np.abs(error)):.5f}"
    )


def plot_result_sets(episode: Episode, predictions: dict[str, dict]) -> None:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    time = signal(episode, "time_s")
    command = signal(episode, "applied_position_rad")
    target = signal(episode, "observed_position_rad")
    values = {
        candidate_id: records[episode.episode_id]["position_meas_rad"]
        for candidate_id, records in predictions.items()
    }
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.7), constrained_layout=True)
    left, right = axes
    left.plot(time, command, "--", color=COLORS["input"], label="Applied input")
    left.plot(time, target, color=COLORS["source"], linewidth=2, label="Source Model output")
    for candidate_id, candidate in values.items():
        left.plot(
            time,
            candidate,
            color=COLORS[candidate_id],
            linewidth=1.1,
            label=f"{CANDIDATE_DISPLAY[candidate_id]} output",
        )
    left.set(title="All Declared Inputs and Outputs", xlabel="Time (s)", ylabel="Position (rad)")
    left.legend(fontsize=8)
    left.grid(alpha=0.25)
    target_tracking = target - command
    right.plot(time, command, "--", color=COLORS["input"], label="Applied input")
    right.plot(
        time,
        target,
        color=COLORS["source"],
        label=metric_label("Source Model tracking", target_tracking),
    )
    right.set(title="Source Model Tracking", xlabel="Time (s)", ylabel="Position (rad)")
    right.legend(fontsize=8)
    right.grid(alpha=0.25)
    fig.suptitle(f"Set 1 — {episode.controller_id} / {episode.fixture_id} / {episode.profile_id}")
    fig.savefig(PLOT_DIR / "set-01-all-and-source.png", dpi=180)
    plt.close(fig)

    titles = {
        "nominal_model": "Set 2 — Nominal Model",
        "sim_position_m1": "Set 3 — Sim-Position M1 Candidate",
        "sim_position_m2": "Set 4 — Sim-Position M2 Candidate",
    }
    numbers = {"nominal_model": "02", "sim_position_m1": "03", "sim_position_m2": "04"}
    for candidate_id, candidate in values.items():
        gap = candidate - target
        tracking = candidate - command
        fig, axes = plt.subplots(1, 2, figsize=(14, 4.7), constrained_layout=True)
        left, right = axes
        left.plot(time, target, color=COLORS["source"], linewidth=2, label="Source Model output")
        left.plot(
            time,
            candidate,
            color=COLORS[candidate_id],
            label=metric_label(f"{CANDIDATE_DISPLAY[candidate_id]} output gap", gap),
        )
        left.set(title="Output-to-Output Gap", xlabel="Time (s)", ylabel="Position (rad)")
        left.legend(fontsize=8)
        left.grid(alpha=0.25)
        right.plot(time, command, "--", color=COLORS["input"], label="Applied input")
        right.plot(
            time,
            candidate,
            color=COLORS[candidate_id],
            label=metric_label(f"{CANDIDATE_DISPLAY[candidate_id]} tracking", tracking),
        )
        right.set(title="Input-to-Output Tracking", xlabel="Time (s)", ylabel="Position (rad)")
        right.legend(fontsize=8)
        right.grid(alpha=0.25)
        fig.suptitle(titles[candidate_id])
        fig.savefig(
            PLOT_DIR / f"set-{numbers[candidate_id]}-{candidate_id}.png", dpi=180
        )
        plt.close(fig)


def plot_parameter_comparison(
    source: Candidate, nominal: Candidate, fits: list[Fit]
) -> None:
    candidates = [source, nominal] + [fit.candidate for fit in fits]
    labels = ["Source Model\n(evaluation only)", "Nominal Model", "Sim-Position\nM1 Candidate", "Sim-Position\nM2 Candidate"]
    colors = [COLORS["source"], COLORS["nominal_model"], COLORS["sim_position_m1"], COLORS["sim_position_m2"]]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.4), constrained_layout=True)
    for index, (axis, name, unit) in enumerate(zip(axes, JOINT_NAMES, JOINT_UNITS)):
        values = [candidate.joint[index] for candidate in candidates]
        bars = axis.bar(np.arange(4), values, color=colors)
        axis.set_xticks(np.arange(4), labels, fontsize=8)
        axis.set_title(f"MuJoCo {name}")
        axis.set_ylabel(unit)
        axis.grid(axis="y", alpha=0.25)
        axis.bar_label(
            bars, labels=[f"{value:.5g}" for value in values], padding=2, fontsize=8
        )
    fig.suptitle("Joint-Parameter Candidates")
    fig.savefig(PLOT_DIR / "parameter-comparison.png", dpi=180)
    plt.close(fig)


def plot_split_metrics(aggregate: list[dict]) -> None:
    lookup = {
        (row["candidate"], row["split"]): row["equal_episode_output_gap_rmse_rad"]
        for row in aggregate
    }
    splits = ("calibration", "model_selection", "held_out")
    labels = ("Calibration", "Model Selection", "Held Out")
    x = np.arange(len(splits))
    width = 0.25
    fig, axis = plt.subplots(figsize=(9.5, 4.8), constrained_layout=True)
    for offset, candidate_id, label in (
        (-width, "nominal_model", "Nominal Model"),
        (0.0, "sim_position_m1", "Sim-Position M1 Candidate"),
        (width, "sim_position_m2", "Sim-Position M2 Candidate"),
    ):
        axis.bar(
            x + offset,
            [lookup[(candidate_id, split)] for split in splits],
            width=width,
            color=COLORS[candidate_id],
            label=label,
        )
    axis.set_xticks(x, labels)
    axis.set_ylabel("Equal-Episode Output-Gap RMSE (rad)")
    axis.set_title("Behavioral Gap on Frozen Dataset Splits")
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    fig.savefig(PLOT_DIR / "split-output-gap.png", dpi=180)
    plt.close(fig)


def fit_record(fit: Fit, source: Candidate, identification: dict) -> dict:
    record = {
        "method": fit.method_id,
        "candidate_name": (
            "Sim-Position M1 Candidate"
            if fit.method_id == "method1"
            else "Sim-Position M2 Candidate"
        ),
        **candidate_record(fit.candidate),
        "equivalent_gains": {
            controller_id: {
                "kp_Nm_per_rad": controller_gains(
                    fit.candidate, controller_id, identification
                )[0],
                "kv_Nm_s_per_rad": controller_gains(
                    fit.candidate, controller_id, identification
                )[1],
            }
            for controller_id in identification["controller_mapping"]["coordinates"]
        },
        "calibration_objective": fit.calibration_objective,
        "model_selection_score": fit.selection_score,
        "diagnostics": fit.diagnostics,
    }
    record["evaluation_only_relative_joint_parameter_distance"] = float(
        np.linalg.norm((fit.candidate.joint - source.joint) / source.joint)
    )
    return record


def write_results_readme(
    source: Candidate,
    nominal: Candidate,
    fits: list[Fit],
    aggregate: list[dict],
    identification: dict,
) -> None:
    fit_lookup = {fit.method_id: fit for fit in fits}
    agg = {(row["candidate"], row["split"]): row for row in aggregate}
    lines = [
        "# Section 2.3 Sim-Position Candidate Results",
        "",
        "Both methods were fitted from the same hardware-realistic logical fields: applied position, measured position, measured velocity, validity/saturation flags, controller metadata, and matched fixture properties. No MuJoCo true-state or generalized-force array was admitted to either fitter.",
        "",
        "## Joint Parameters",
        "",
        "| MuJoCo Parameter | Source Model (Evaluation Only) | Nominal Model | Sim-Position M1 Candidate | Sim-Position M2 Candidate |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for index, (name, unit) in enumerate(zip(JOINT_NAMES, JOINT_UNITS)):
        target = source.joint[index]
        cells = [f"{target:.7g} {unit}"]
        for candidate in (
            nominal,
            fit_lookup["method1"].candidate,
            fit_lookup["method2"].candidate,
        ):
            value = candidate.joint[index]
            difference = 100.0 * (value - target) / target
            cells.append(f"{value:.7g} ({difference:+.2f}%)")
        lines.append(f"| `{name}` | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Fixed Simulation Controller Conditions",
        "",
        "| Condition | MuJoCo kp | MuJoCo kv | Applied-Command Delay | Identification Status |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for controller_id, coordinate in identification["controller_mapping"][
        "coordinates"
    ].items():
        lines.append(
            f"| {controller_id} | {float(coordinate.get('kp_Nm_per_rad', coordinate.get('normalized_P'))):.4f} N·m/rad | "
            f"{float(coordinate.get('kv_Nm_s_per_rad', coordinate.get('normalized_D'))):.4f} N·m·s/rad | "
            f"{float(identification['controller_mapping'].get('fixed_command_delay_s', 0.0)):.3f} s | known and fixed; not fitted |"
        )
    lines += [
        "",
        "## Equal-Episode Output-Gap RMSE",
        "",
        "| Dataset Split | Nominal Model | Sim-Position M1 Candidate | Reduction | Sim-Position M2 Candidate | Reduction |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for split in ("calibration", "model_selection", "held_out"):
        n = agg[("nominal_model", split)]
        m1 = agg[("sim_position_m1", split)]
        m2 = agg[("sim_position_m2", split)]
        lines.append(
            f"| {split.replace('_', ' ').title()} | {n['equal_episode_output_gap_rmse_rad']:.6f} rad | {m1['equal_episode_output_gap_rmse_rad']:.6f} rad | {m1['gap_reduction_vs_nominal_percent']:.1f}% | {m2['equal_episode_output_gap_rmse_rad']:.6f} rad | {m2['gap_reduction_vs_nominal_percent']:.1f}% |"
        )
    lines += [
        "",
        "## Interpretation Boundary",
        "",
        "- Method 1 is an integrated closed-loop approximation. It avoids measured torque and numerical acceleration, but remains sensitive to velocity resolution, friction reversal, filtering, and the fixed effective PD controller context.",
        "- Method 2 uses nonlinear MuJoCo replay and the same three-parameter candidate vector. It is more computationally expensive but does not differentiate the measured response.",
        "- The C1/C2 MuJoCo controller gains and zero-delay boundary are fixed generation settings, not fitted parameters. Held-out episodes are evaluated only after the three-parameter candidate is frozen.",
        "- Source parameters are used only for post-fit simulation verification. They will be unavailable in the hardware release.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "python3 -m venv .venv",
        ".venv/bin/pip install -r requirements-simulation.txt",
        identification.get(
            "reproduction_command",
            ".venv/bin/python scripts/run_chapter02_sim_position_identification_base.py",
        ),
        "```",
        "",
    ]
    (RESULT_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use one Method 2 start and fewer evaluations for a smoke test.",
    )
    args = parser.parse_args()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    contract, manifest, identification, episodes = load_episodes()
    # Remove evaluation-only truth before any fitter receives the
    # identification contract. Joint truth remains only in `contract`, which
    # the replay engine immediately reduces to sensor resolution.
    simulation_evaluation = identification.pop("simulation_evaluation_only")
    engine = ReplayEngine(contract, identification)
    nominal = initial_candidate(contract, identification)
    print("Running Method 1 from hardware-shaped command/position/velocity data...", flush=True)
    method1 = fit_method1(episodes, engine, identification)
    print(f"  joint={method1.candidate.joint}", flush=True)
    print("Running Method 2 from the identical hardware-shaped data contract...", flush=True)
    method2 = fit_method2(episodes, engine, identification, quick=args.quick)
    print(f"  joint={method2.candidate.joint}", flush=True)
    fits = [method1, method2]
    # Ground truth is deliberately loaded only after both fitters return.
    source = Candidate(
        joint=np.array(
            [contract["source_model"][name] for name in JOINT_NAMES], dtype=float
        )
    )
    candidates = {
        "nominal_model": nominal,
        "sim_position_m1": method1.candidate,
        "sim_position_m2": method2.candidate,
    }
    print("Replaying the frozen candidates on all dataset splits...", flush=True)
    predictions = replay_candidates(episodes, candidates, engine)
    episode_rows = episode_metrics(episodes, predictions)
    aggregate = aggregate_metrics(episode_rows)
    write_csv(
        RESULT_DIR / "joint-parameter-estimates.csv",
        parameter_rows(source, nominal, fits),
    )
    write_csv(
        RESULT_DIR / "fixed-controller-conditions.csv",
        mapping_rows(source, nominal, fits, identification),
    )
    write_csv(RESULT_DIR / "episode-metrics.csv", episode_rows)
    write_csv(RESULT_DIR / "aggregate-metrics.csv", aggregate)
    aggregate_lookup = {
        (row["candidate"], row["split"]): row for row in aggregate
    }
    simulation_decision = {
        candidate_id: {
            "accepted": bool(
                aggregate_lookup[(candidate_id, "model_selection")][
                    "gap_reduction_vs_nominal_percent"
                ]
                > 0.0
                and aggregate_lookup[(candidate_id, "held_out")][
                    "gap_reduction_vs_nominal_percent"
                ]
                > 0.0
            ),
            "model_selection_gap_reduction_percent": aggregate_lookup[
                (candidate_id, "model_selection")
            ]["gap_reduction_vs_nominal_percent"],
            "held_out_gap_reduction_percent": aggregate_lookup[
                (candidate_id, "held_out")
            ]["gap_reduction_vs_nominal_percent"],
        }
        for candidate_id in ("sim_position_m1", "sim_position_m2")
    }
    result = {
        "result_schema": identification.get(
            "result_schema", "phyintel-section-2.3-sim-position-results-v2"
        ),
        "dataset_release_id": manifest["release_id"],
        "dataset_sha256": manifest["data_sha256"],
        "experiment_contract_sha256": manifest["contract_sha256"],
        "identification_contract_schema": identification["schema_version"],
        "evidence_role": "projected simulation evidence",
        "hardware_transfer_rule": "same logical position-interface fields, three-parameter candidate, fixed declared controller context, bounds, preprocessing, split discipline, and replay code",
        "fit_field_allowlist": identification["fit_field_allowlist"],
        "sim_torque_fields_admitted_to_fitters": [],
        "source_parameters_loaded_after_fitting": True,
        "methods_executed": [
            "Method 1 — integrated closed-loop analytical regression",
            "Method 2 — bounded MuJoCo output-error optimization",
        ],
        "simulation_predictive_acceptance": {
            "rule": "positive model-selection and held-out gap reduction relative to the Nominal Model",
            **simulation_decision,
        },
        "source_model_evaluation_only": candidate_record(source),
        "nominal_model": candidate_record(nominal),
        "fits": [fit_record(fit, source, identification) for fit in fits],
        "sim_position_output_gap_equation": "candidate_position_meas_rad - observed_position_rad",
        "gap_reduction_equation": "100 * (1 - candidate_equal_episode_RMSE / nominal_model_equal_episode_RMSE)",
        "model_selection_used_for_delay_choice": False,
        "held_out_used_during_fit_or_selection": False,
        "quick_mode": bool(args.quick),
    }
    write_json(RESULT_DIR / "result.json", result)
    representative = next(
        episode
        for episode in episodes
        if episode.episode_id == "held_out__C2__G1__P06_heldout_composite"
    )
    plot_result_sets(representative, predictions)
    plot_parameter_comparison(source, nominal, fits)
    plot_split_metrics(aggregate)
    write_results_readme(source, nominal, fits, aggregate, identification)
    print(f"Wrote results to {RESULT_DIR.relative_to(ROOT)}", flush=True)
    print(f"Wrote figures to {PLOT_DIR.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
