#!/usr/bin/env python3
"""Build Sim-Torque M1 and M2 Candidates from Sim-Torque Data.

This simulation-only companion runs two methods with C1, C2, and their shared
dataset. Method 1 uses a transparent torque-balance least-squares regression.
Method 2 uses MuJoCo forward dynamics as the nonlinear model and minimizes
acceleration prediction error. Neither method consumes the position
command or controller gains after the effort trajectory has been recorded.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import mujoco
import numpy as np
from scipy.optimize import least_squares, lsq_linear

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "data/chapter-02/releases/rs06-sim-data-v1"
ARCHIVE_PATH = RELEASE_DIR / "rs06-sim-torque-v1.npz"
MANIFEST_PATH = RELEASE_DIR / "sim-torque-manifest.json"
CONTRACT_PATH = RELEASE_DIR / "sim-torque-contract.json"
EXPERIMENT_PATH = RELEASE_DIR / "experiment-contract.json"
RESULT_DIR = RELEASE_DIR / "sim-torque-results-v1"
PLOT_DIR = ROOT / "assets/chapter-02/rs06-sim-torque-results-v1"
JOINT_NAMES = ("armature", "damping", "frictionloss")
JOINT_UNITS = ("kg·m²", "N·m·s/rad", "N·m")
LOWER = np.array([0.0002, 0.00001, 0.001], dtype=float)
UPPER = np.array([0.0080, 0.05000, 0.200], dtype=float)
GROUPS = ("C1", "C2", "shared")


@dataclass(frozen=True)
class Episode:
    metadata: dict
    values: dict[str, np.ndarray]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_episodes() -> tuple[dict, dict, dict, list[Episode]]:
    manifest = read_json(MANIFEST_PATH)
    contract = read_json(CONTRACT_PATH)
    experiment = read_json(EXPERIMENT_PATH)
    archive = np.load(ARCHIVE_PATH, allow_pickle=False)
    episodes = []
    for metadata in manifest["episodes"]:
        sample_slice = slice(int(metadata["start"]), int(metadata["stop"]))
        episodes.append(
            Episode(
                metadata,
                {
                    field: archive[field][sample_slice].copy()
                    for field in manifest["fields"]
                },
            )
        )
    return manifest, contract, experiment, episodes


def selected(episodes: list[Episode], group: str, split: str = "calibration") -> list[Episode]:
    return [
        episode
        for episode in episodes
        if episode.metadata["split"] == split
        and (group == "shared" or episode.metadata["controller_id"] == group)
    ]


def candidate_model(episode: Episode) -> mujoco.MjModel:
    model = mujoco.MjModel.from_xml_path(str(ROOT / episode.metadata["candidate_model"]))
    model.actuator_gainprm[0, :] = 0.0
    model.actuator_biasprm[0, :] = 0.0
    return model


def fixture_inertia(episode: Episode) -> float:
    model = candidate_model(episode)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    full_mass = np.zeros((model.nv, model.nv), dtype=float)
    mujoco.mj_fullM(model, full_mass, data.qM)
    return float(full_mass[0, 0] - model.dof_armature[0])


def method1(episodes: list[Episode], group: str) -> tuple[np.ndarray, dict]:
    blocks_x = []
    blocks_y = []
    rows_by_episode = {}
    for episode in selected(episodes, group):
        values = episode.values
        velocity = values["velocity_true_rad_s"]
        acceleration = values["acceleration_true_rad_s2"]
        effort = values["actuator_effort_input_Nm"]
        bias = values["bias_torque_Nm"]
        valid = values["valid"].astype(bool)
        moving = np.abs(velocity) >= 0.05
        accepted = valid & moving
        design = np.column_stack(
            [
                acceleration[accepted],
                velocity[accepted],
                np.sign(velocity[accepted]),
            ]
        )
        response = (
            effort[accepted]
            - fixture_inertia(episode) * acceleration[accepted]
            - bias[accepted]
        )
        weight = 1.0 / math.sqrt(response.size)
        blocks_x.append(design * weight)
        blocks_y.append(response * weight)
        rows_by_episode[episode.metadata["episode_id"]] = int(response.size)
    design = np.vstack(blocks_x)
    response = np.concatenate(blocks_y)
    fit = lsq_linear(design, response, bounds=(LOWER, UPPER), lsmr_tol="auto")
    residual = design @ fit.x - response
    return fit.x, {
        "solver_success": bool(fit.success),
        "weighted_design_rank": int(np.linalg.matrix_rank(design)),
        "scaled_condition_number": float(
            np.linalg.cond(design * np.array([0.001, 0.015, 0.010]))
        ),
        "qualified_sample_count": int(sum(rows_by_episode.values())),
        "equal_episode_torque_balance_rmse_Nm": float(
            np.sqrt(np.sum(np.square(residual)) / len(blocks_y))
        ),
        "rows_by_episode": rows_by_episode,
    }


class ForwardDynamicsObjective:
    def __init__(self, episodes: list[Episode], group: str):
        self.records = []
        self.models = {}
        for episode in selected(episodes, group):
            # Retain every fifth physics sample (100 Hz) while preserving the
            # exact Sim-Torque state, acceleration, and effort at that boundary.
            retained = np.arange(0, episode.values["time_s"].size, 5)
            self.records.append(
                (
                    episode,
                    episode.values["position_true_rad"][retained],
                    episode.values["velocity_true_rad_s"][retained],
                    episode.values["acceleration_true_rad_s2"][retained],
                    episode.values["actuator_effort_input_Nm"][retained],
                )
            )

    def model(self, episode: Episode, parameters: np.ndarray) -> mujoco.MjModel:
        key = (episode.metadata["controller_id"], episode.metadata["fixture_id"])
        if key not in self.models:
            self.models[key] = candidate_model(episode)
        model = self.models[key]
        model.dof_armature[0] = float(parameters[0])
        model.dof_damping[0] = float(parameters[1])
        model.dof_frictionloss[0] = float(parameters[2])
        mujoco.mj_setConst(model, mujoco.MjData(model))
        return model

    def residual(self, parameters: np.ndarray) -> np.ndarray:
        blocks = []
        for episode, position, velocity, acceleration, effort in self.records:
            model = self.model(episode, parameters)
            data = mujoco.MjData(model)
            predicted = np.empty(acceleration.size, dtype=float)
            for index in range(acceleration.size):
                data.qpos[0] = float(position[index])
                data.qvel[0] = float(velocity[index])
                data.qfrc_applied[0] = float(effort[index])
                mujoco.mj_forward(model, data)
                predicted[index] = data.qacc[0]
            scale = max(float(np.std(acceleration)), 1.0)
            blocks.append(
                (predicted - acceleration) / scale / math.sqrt(acceleration.size)
            )
        return np.concatenate(blocks)


def method2(episodes: list[Episode], group: str) -> tuple[np.ndarray, dict]:
    objective = ForwardDynamicsObjective(episodes, group)
    starts = (
        np.array([0.0005, 0.0001, 0.012], dtype=float),
        np.array([0.0020, 0.0020, 0.080], dtype=float),
    )
    candidates = []
    for start_index, start in enumerate(starts):
        fit = least_squares(
            objective.residual,
            start,
            bounds=(LOWER, UPPER),
            max_nfev=20,
            xtol=1.0e-10,
            ftol=1.0e-10,
            gtol=1.0e-10,
            x_scale="jac",
        )
        score = float(np.sqrt(np.mean(np.square(objective.residual(fit.x)))))
        candidates.append((score, start_index, fit))
    score, start_index, fit = min(candidates, key=lambda item: item[0])
    return fit.x, {
        "solver_success": bool(fit.success),
        "selected_start_index": int(start_index),
        "starts": [start.tolist() for start in starts],
        "function_evaluations": int(fit.nfev),
        "normalized_forward_dynamics_rmse": score,
        "episode_count": len(objective.records),
        "sample_stride_from_500_Hz": 5,
    }


def percent_error(values: np.ndarray, source: np.ndarray) -> np.ndarray:
    return 100.0 * (values - source) / source


def plot_parameter_results(results: dict, source: np.ndarray) -> None:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), constrained_layout=True)
    labels = ["M1 C1", "M1 C2", "M1 Shared", "M2 C1", "M2 C2", "M2 Shared"]
    colors = ["#23966f"] * 3 + ["#7c55a5"] * 3
    values = [results[method][group]["parameters"] for method in ("method1", "method2") for group in GROUPS]
    for index, (axis, name, unit) in enumerate(zip(axes, JOINT_NAMES, JOINT_UNITS)):
        series = [entry[index] for entry in values]
        axis.axhline(source[index], color="#2768a8", linewidth=2, label="Source Model")
        bars = axis.bar(np.arange(len(series)), series, color=colors)
        axis.set_xticks(np.arange(len(series)), labels, rotation=35, ha="right", fontsize=8)
        axis.set_title(f"MuJoCo {name}")
        axis.set_ylabel(unit)
        axis.grid(axis="y", alpha=0.25)
        axis.bar_label(bars, labels=[f"{value:.5g}" for value in series], fontsize=7, padding=2)
    axes[0].legend()
    fig.suptitle("Sim-Torque Candidates Across C1 and C2 Excitation")
    fig.savefig(PLOT_DIR / "parameter-invariance.png", dpi=180)
    plt.close(fig)


def plot_example(episodes: list[Episode]) -> None:
    episode = next(
        item
        for item in episodes
        if item.metadata["episode_id"] == "calibration__C2__B1__P02_multisine"
    )
    values = episode.values
    time = values["time_s"]
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True, constrained_layout=True)
    axes[0].plot(time, values["position_command_rad"], "--", color="#202020", label="Position command (provenance only)")
    axes[0].plot(time, values["position_true_rad"], color="#2768a8", label="Source Model output")
    axes[0].set_ylabel("Position (rad)")
    axes[0].legend()
    axes[0].grid(alpha=0.25)
    axes[1].plot(time, values["actuator_effort_input_Nm"], color="#d04a35", label="Torque-replay input")
    axes[1].set(xlabel="Time (s)", ylabel="Generalized effort (N·m)")
    axes[1].legend()
    axes[1].grid(alpha=0.25)
    fig.suptitle("Sim-Torque Data Boundary: Controller Effort Becomes Replay Input")
    fig.savefig(PLOT_DIR / "sim-torque-example.png", dpi=180)
    plt.close(fig)


def main() -> None:
    manifest, contract, experiment, episodes = load_episodes()
    source = np.array(
        [experiment["source_model"][name] for name in JOINT_NAMES], dtype=float
    )
    nominal = np.array(
        [experiment["nominal_model"][name] for name in JOINT_NAMES], dtype=float
    )
    results = {"method1": {}, "method2": {}}
    for group in GROUPS:
        print(f"Building Sim-Torque M1 Candidate on {group}...", flush=True)
        values, diagnostics = method1(episodes, group)
        results["method1"][group] = {
            "parameters": values,
            "diagnostics": diagnostics,
        }
        print(f"  {values}", flush=True)
    for group in GROUPS:
        print(f"Building Sim-Torque M2 Candidate on {group}...", flush=True)
        values, diagnostics = method2(episodes, group)
        results["method2"][group] = {
            "parameters": values,
            "diagnostics": diagnostics,
        }
        print(f"  {values}", flush=True)

    rows = []
    for index, (name, unit) in enumerate(zip(JOINT_NAMES, JOINT_UNITS)):
        row = {
            "parameter": name,
            "unit": unit,
            "source_model": float(source[index]),
            "nominal_model": float(nominal[index]),
            "nominal_difference_percent": float(percent_error(nominal, source)[index]),
        }
        for method in ("method1", "method2"):
            for group in GROUPS:
                values = results[method][group]["parameters"]
                candidate_id = f"sim_torque_m{1 if method == 'method1' else 2}_{group}"
                row[candidate_id] = float(values[index])
                row[f"{candidate_id}_difference_percent"] = float(
                    percent_error(values, source)[index]
                )
        rows.append(row)
    write_csv(RESULT_DIR / "joint-parameter-estimates.csv", rows)
    serializable = {
        method: {
            group: {
                "joint_parameters": {
                    name: float(value)
                    for name, value in zip(JOINT_NAMES, record["parameters"])
                },
                "difference_from_source_percent": {
                    name: float(value)
                    for name, value in zip(
                        JOINT_NAMES, percent_error(record["parameters"], source)
                    )
                },
                "diagnostics": record["diagnostics"],
            }
            for group, record in groups.items()
        }
        for method, groups in results.items()
    }
    result = {
        "result_schema": "phyintel-section-2.3-sim-torque-results-v1",
        "dataset_release_id": manifest["release_id"],
        "dataset_archive_sha256": manifest["archive_sha256"],
        "evidence_role": "simulation-only Sim-Torque identifiability check",
        "hardware_equivalent_claimed": False,
        "identified_parameters": list(JOINT_NAMES),
        "source_controller_gains_consumed_by_fitters": False,
        "source_position_command_consumed_by_fitters": False,
        "input_field": contract["input_field"],
        "method1": "bounded linear torque-balance least squares",
        "method2": "bounded MuJoCo pointwise forward-dynamics optimization",
        "source_model": {name: float(value) for name, value in zip(JOINT_NAMES, source)},
        "nominal_model": {name: float(value) for name, value in zip(JOINT_NAMES, nominal)},
        "candidate_names": {
            "method1": "Sim-Torque M1 Candidate",
            "method2": "Sim-Torque M2 Candidate",
        },
        "fits": serializable,
    }
    write_json(RESULT_DIR / "result.json", result)
    plot_parameter_results(results, source)
    plot_example(episodes)
    print(f"Wrote {RESULT_DIR.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
