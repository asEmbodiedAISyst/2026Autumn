#!/usr/bin/env python3
"""Fit and assess the synthetic MuJoCo dataset."""

from __future__ import annotations

import csv
import gzip
import json
import math
import platform
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
import numpy as np
import scipy
from scipy.optimize import least_squares, lsq_linear


PACKAGE = Path(__file__).resolve().parents[1]
FIT_CONTRACT_PATH = PACKAGE / "config" / "fitting_contract.json"
EXPERIMENT_CONTRACT_PATH = PACKAGE / "data" / "experiment_contract.json"
RESULTS = PACKAGE / "results"
PLOTS = PACKAGE / "plots"
IDENTIFIED_MODELS = PACKAGE / "models" / "identified"


@dataclass(frozen=True)
class Episode:
    episode_id: str
    split: str
    fixture_id: str
    profile_id: str
    controller_id: str
    repetition: str
    arrays: dict[str, np.ndarray]


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_fit_context(path: Path) -> dict:
    """Return fixed simulation information without retaining plant references."""
    document = read_json(path)
    return {
        "simulation": dict(document["simulation"]),
        "controllers": {
            name: dict(values) for name, values in document["controllers"].items()
        },
        "fixture_ids": sorted(document["fixtures"]),
    }


def integrator_code(name: str) -> int:
    codes = {
        "euler": mujoco.mjtIntegrator.mjINT_EULER,
        "rk4": mujoco.mjtIntegrator.mjINT_RK4,
        "implicit": mujoco.mjtIntegrator.mjINT_IMPLICIT,
        "implicitfast": mujoco.mjtIntegrator.mjINT_IMPLICITFAST,
    }
    try:
        return int(codes[name.lower()])
    except KeyError as exc:
        raise ValueError(f"unsupported declared integrator: {name}") from exc


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def episode_split_counts(archive: Path) -> dict[str, int]:
    """Read the split index without opening any numeric episode fields."""
    with np.load(archive, allow_pickle=False) as data:
        splits = np.asarray(data["split"])
    return {
        split: int(np.count_nonzero(splits == split))
        for split in ("calibration", "model_selection", "held_out")
    }


def load_episodes(
    archive: Path, fields: list[str], allowed_splits: set[str] | None = None
) -> list[Episode]:
    """Load selected numeric fields only for the permitted episode splits."""
    metadata = [
        "episode_id",
        "split",
        "fixture_id",
        "profile_id",
        "controller_id",
        "repetition",
        "episode_offsets",
    ]
    with np.load(archive, allow_pickle=False) as data:
        missing = sorted(set(metadata + fields).difference(data.files))
        if missing:
            raise KeyError(f"dataset is missing fields: {missing}")
        offsets = np.asarray(data["episode_offsets"], dtype=np.int64)
        splits = np.asarray(data["split"])
        episodes: list[Episode] = []
        for index, episode_id in enumerate(data["episode_id"]):
            episode_split = str(splits[index])
            if allowed_splits is not None and episode_split not in allowed_splits:
                continue
            start, stop = map(int, offsets[index : index + 2])
            arrays = {name: np.asarray(data[name][start:stop]).copy() for name in fields}
            episodes.append(
                Episode(
                    episode_id=str(episode_id),
                    split=episode_split,
                    fixture_id=str(data["fixture_id"][index]),
                    profile_id=str(data["profile_id"][index]),
                    controller_id=str(data["controller_id"][index]),
                    repetition=str(data["repetition"][index]),
                    arrays=arrays,
                )
            )
    return episodes


def fixed_model_checks(
    model: mujoco.MjModel, controller: dict, simulation: dict
) -> tuple[int, int, dict[str, bool]]:
    joint_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, "actuator_joint"
    )
    actuator_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_ACTUATOR, "xc330_position"
    )
    if joint_id < 0 or actuator_id < 0:
        raise ValueError("required actuator_joint or xc330_position identifier is missing")
    expected_gravity = [0.0, 0.0, -float(simulation["gravity_m_s2"])]
    expected_gear = np.zeros(model.actuator_gear.shape[1], dtype=float)
    expected_gear[0] = 1.0
    kp = float(controller["kp_Nm_per_rad"])
    kv = float(controller["kv_Nm_s_per_rad"])
    checks = {
        "one_joint": int(model.njnt) == 1,
        "nq_nv_nu_are_one": (model.nq, model.nv, model.nu) == (1, 1, 1),
        "joint_is_hinge": int(model.jnt_type[joint_id])
        == int(mujoco.mjtJoint.mjJNT_HINGE),
        "joint_axis_exact": np.allclose(
            model.jnt_axis[joint_id], [0.0, -1.0, 0.0], rtol=0, atol=1e-12
        ),
        "joint_limit_enabled": bool(model.jnt_limited[joint_id]),
        "joint_range_exact": np.allclose(
            model.jnt_range[joint_id], simulation["joint_range_rad"], rtol=0, atol=1e-12
        ),
        "actuator_targets_joint": int(model.actuator_trnid[actuator_id, 0])
        == joint_id,
        "actuator_is_joint_transmission": int(model.actuator_trntype[actuator_id])
        == int(mujoco.mjtTrn.mjTRN_JOINT),
        "gear_is_one": np.allclose(
            model.actuator_gear[actuator_id], expected_gear, rtol=0, atol=1e-12
        ),
        "control_limit_enabled": bool(model.actuator_ctrllimited[actuator_id]),
        "control_range_exact": np.allclose(
            model.actuator_ctrlrange[actuator_id],
            simulation["ctrlrange_rad"],
            rtol=0,
            atol=1e-12,
        ),
        "force_limit_enabled": bool(model.actuator_forcelimited[actuator_id]),
        "force_range_exact": np.allclose(
            model.actuator_forcerange[actuator_id],
            simulation["forcerange_Nm"],
            rtol=0,
            atol=1e-12,
        ),
        "kp_gain_exact": np.isclose(
            model.actuator_gainprm[actuator_id, 0], kp, rtol=0, atol=1e-12
        ),
        "position_feedback_exact": np.isclose(
            model.actuator_biasprm[actuator_id, 1], -kp, rtol=0, atol=1e-12
        ),
        "velocity_feedback_exact": np.isclose(
            model.actuator_biasprm[actuator_id, 2], -kv, rtol=0, atol=1e-12
        ),
        "timestep_exact": np.isclose(
            model.opt.timestep,
            simulation["physics_timestep_s"],
            rtol=0,
            atol=1e-15,
        ),
        "integrator_exact": int(model.opt.integrator)
        == integrator_code(simulation["integrator"]),
        "gravity_exact": np.allclose(
            model.opt.gravity, expected_gravity, rtol=0, atol=1e-12
        ),
    }
    return joint_id, actuator_id, {name: bool(value) for name, value in checks.items()}


class ReplayBank:
    """Reusable exact nominal models with three joint parameters changed in memory."""

    def __init__(self, contract: dict, fit_context: dict):
        self.contract = contract
        self.fit_context = fit_context
        if "plants" in fit_context:
            raise ValueError("fit context must not contain plant reference values")
        self.models: dict[tuple[str, str], mujoco.MjModel] = {}
        self.model_paths: dict[tuple[str, str], Path] = {}
        self.fixture_inertias: dict[tuple[str, str], float] = {}
        for controller in sorted(fit_context["controllers"]):
            controller_spec = fit_context["controllers"][controller]
            for fixture in fit_context["fixture_ids"]:
                path = PACKAGE / "models" / "simulation" / "nominal" / controller / f"{fixture}.xml"
                model = mujoco.MjModel.from_xml_path(str(path.resolve()))
                _, _, checks = fixed_model_checks(
                    model, controller_spec, fit_context["simulation"]
                )
                if not all(checks.values()):
                    failed = sorted(name for name, passed in checks.items() if not passed)
                    raise ValueError(f"{path}: fixed-model checks failed: {failed}")
                self.models[(controller, fixture)] = model
                self.model_paths[(controller, fixture)] = path
                self.fixture_inertias[(controller, fixture)] = (
                    float(model.dof_M0[0]) - float(model.dof_armature[0])
                )
        self.position_resolution = float(
            fit_context["simulation"]["position_resolution_rad"]
        )
        self.sample_dt = 1.0 / float(fit_context["simulation"]["sample_rate_hz"])

    def _set_parameters(
        self,
        key: tuple[str, str],
        model: mujoco.MjModel,
        data: mujoco.MjData,
        theta: np.ndarray,
    ) -> None:
        model.dof_armature[0] = float(theta[0])
        model.dof_damping[0] = float(theta[1])
        model.dof_frictionloss[0] = float(theta[2])
        # Armature contributes to reference inertia, so constants must be refreshed.
        mujoco.mj_setConst(model, data)
        expected_M0 = self.fixture_inertias[key] + float(theta[0])
        if not np.isclose(model.dof_M0[0], expected_M0, rtol=0, atol=1e-13):
            raise RuntimeError(
                f"{key}: dof_M0 did not update after the armature change"
            )

    def rollout(self, episode: Episode, theta: np.ndarray, quantize: bool = False) -> np.ndarray:
        key = (episode.controller_id, episode.fixture_id)
        model = self.models[key]
        data = mujoco.MjData(model)
        self._set_parameters(key, model, data, theta)
        mujoco.mj_resetData(model, data)
        command = np.asarray(episode.arrays["position_applied_rad"], dtype=float)
        if command.size == 0:
            return np.empty(0, dtype=float)
        measured_position = np.asarray(episode.arrays["source_position_meas_rad"], dtype=float)
        measured_velocity = np.asarray(episode.arrays["source_velocity_meas_rad_s"], dtype=float)
        substeps_float = self.sample_dt / float(model.opt.timestep)
        substeps = int(round(substeps_float))
        if not np.isclose(substeps_float, substeps):
            raise ValueError("sample interval is not an integer multiple of the physics timestep")
        # Insert the first measured state once. Recorded state is never injected again.
        data.qpos[0] = float(measured_position[0])
        data.qvel[0] = float(measured_velocity[0])
        data.ctrl[0] = float(command[0])
        mujoco.mj_forward(model, data)
        prediction = np.empty(command.size, dtype=float)
        for index, value in enumerate(command):
            data.ctrl[0] = float(value)
            mujoco.mj_forward(model, data)
            prediction[index] = float(data.qpos[0])
            if index + 1 < command.size:
                for _ in range(substeps):
                    mujoco.mj_step(model, data)
        if quantize:
            prediction = np.round(prediction / self.position_resolution) * self.position_resolution
        return prediction

    def fixture_inertia_without_armature(self, controller: str, fixture: str) -> float:
        return self.fixture_inertias[(controller, fixture)]


def parameter_arrays(contract: dict) -> tuple[list[str], np.ndarray, np.ndarray]:
    names = list(contract["parameters"]["names"])
    bounds = contract["parameters"]["bounds"]
    lower = np.asarray([bounds[name][0] for name in names], dtype=float)
    upper = np.asarray([bounds[name][1] for name in names], dtype=float)
    return names, lower, upper


def to_physical(unit_vector: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    return lower + np.asarray(unit_vector, dtype=float) * (upper - lower)


def to_unit(theta: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    return (np.asarray(theta, dtype=float) - lower) / (upper - lower)


def error_metrics(prediction: np.ndarray, target: np.ndarray, valid: np.ndarray) -> dict[str, float]:
    mask = np.asarray(valid, dtype=bool) & np.isfinite(prediction) & np.isfinite(target)
    error = np.asarray(prediction[mask] - target[mask], dtype=float)
    if error.size == 0:
        raise ValueError("no valid samples for metrics")
    centered = target[mask] - float(np.mean(target[mask]))
    denominator = float(np.dot(centered, centered))
    sse = float(np.dot(error, error))
    return {
        "sample_count": int(error.size),
        "rmse_rad": math.sqrt(sse / error.size),
        "mae_rad": float(np.mean(np.abs(error))),
        "peak_abs_error_rad": float(np.max(np.abs(error))),
        "bias_rad": float(np.mean(error)),
        "r2": float(1.0 - sse / denominator) if denominator > 0 else float("nan"),
    }


def run_primary_fit(
    episodes: list[Episode], bank: ReplayBank, contract: dict, lower: np.ndarray, upper: np.ndarray
) -> tuple[list[dict], dict, list[dict], list[dict]]:
    method = contract["primary_method"]
    calibration = [episode for episode in episodes if episode.split == "calibration"]
    selection = [episode for episode in episodes if episode.split == "model_selection"]
    if not calibration or not selection:
        raise ValueError("calibration and model_selection episodes are required")
    stride = int(method["fit_sample_stride"])
    sample_indexes: dict[str, np.ndarray] = {}
    residual_layout: list[dict] = []
    cursor = 0
    for episode in calibration:
        valid = np.asarray(episode.arrays["valid"], dtype=bool)
        indexes = np.arange(valid.size, dtype=int)[::stride]
        indexes = indexes[valid[indexes]]
        if indexes.size == 0:
            raise ValueError(f"{episode.episode_id}: no valid calibration samples")
        sample_indexes[episode.episode_id] = indexes
        residual_layout.append(
            {
                "episode_id": episode.episode_id,
                "profile_id": episode.profile_id,
                "start": cursor,
                "stop": cursor + int(indexes.size),
            }
        )
        cursor += int(indexes.size)

    def residual(unit_vector: np.ndarray) -> np.ndarray:
        theta = to_physical(unit_vector, lower, upper)
        pieces = []
        for episode in calibration:
            indexes = sample_indexes[episode.episode_id]
            # Continuous simulated q is retained in the objective. The measured
            # target is encoder-quantized, but rounding the candidate here would
            # make finite-difference sensitivities discontinuous.
            prediction = bank.rollout(episode, theta, quantize=False)
            target = np.asarray(episode.arrays["source_position_meas_rad"], dtype=float)
            pieces.append((prediction[indexes] - target[indexes]) / math.sqrt(indexes.size))
        return np.concatenate(pieces)

    runs: list[dict] = []
    internal: list[dict] = []
    failures: list[dict] = []
    for start in contract["parameters"]["initial_vectors"]:
        start_id = str(start["id"])
        theta0 = np.asarray(start["values"], dtype=float)
        unit0 = to_unit(theta0, lower, upper)
        started = time.monotonic()
        try:
            result = least_squares(
                residual,
                unit0,
                bounds=(np.zeros(3), np.ones(3)),
                method="trf",
                loss=str(method["loss"]),
                diff_step=float(method["normalized_finite_difference_step"]),
                max_nfev=int(method["maximum_function_evaluations"]),
                ftol=1e-10,
                xtol=1e-10,
                gtol=1e-10,
            )
            theta = to_physical(result.x, lower, upper)
            selection_values = []
            calibration_values = []
            for episode_group, accumulator in ((calibration, calibration_values), (selection, selection_values)):
                for episode in episode_group:
                    prediction = bank.rollout(episode, theta, quantize=True)
                    metric = error_metrics(
                        prediction,
                        np.asarray(episode.arrays["source_position_meas_rad"], dtype=float),
                        np.asarray(episode.arrays["valid"], dtype=bool),
                    )
                    accumulator.append(metric["rmse_rad"])
            active_tolerance = float(contract["reporting"]["active_bound_fraction_of_range"])
            bound_labels = []
            for name, value in zip(contract["parameters"]["names"], result.x, strict=True):
                if value <= active_tolerance:
                    bound_labels.append(f"{name}:lower")
                elif value >= 1.0 - active_tolerance:
                    bound_labels.append(f"{name}:upper")
            successful = bool(result.success and np.all(np.isfinite(theta)))
            row = {
                "method": "primary_forward_output",
                "scope": "shared",
                "run_id": start_id,
                "optimizer_success": successful,
                "optimizer_status": int(result.status),
                "optimizer_message": str(result.message).replace("\n", " "),
                "nfev": int(result.nfev),
                "njev": int(result.njev) if result.njev is not None else "",
                "elapsed_s": time.monotonic() - started,
                "objective_cost": float(result.cost),
                "optimality": float(result.optimality),
                "armature_kg_m2": float(theta[0]),
                "damping_Nm_s_per_rad": float(theta[1]),
                "frictionloss_Nm": float(theta[2]),
                "calibration_mean_episode_rmse_rad": float(np.mean(calibration_values)),
                "model_selection_mean_episode_rmse_rad": float(np.mean(selection_values)),
                "active_bounds": ";".join(bound_labels),
                "selected": False,
                "used_for_predictions": False,
                "stability": "pending",
            }
            runs.append(row)
            internal.append({"row": row, "result": result, "theta": theta})
            if not successful:
                failures.append(
                    {"method": "primary_forward_output", "run_id": start_id, "classification": "failed", "reason": row["optimizer_message"]}
                )
        except Exception as exc:
            row = {
                "method": "primary_forward_output",
                "scope": "shared",
                "run_id": start_id,
                "optimizer_success": False,
                "optimizer_status": "",
                "optimizer_message": f"{type(exc).__name__}: {exc}",
                "nfev": "",
                "njev": "",
                "elapsed_s": time.monotonic() - started,
                "objective_cost": "",
                "optimality": "",
                "armature_kg_m2": "",
                "damping_Nm_s_per_rad": "",
                "frictionloss_Nm": "",
                "calibration_mean_episode_rmse_rad": "",
                "model_selection_mean_episode_rmse_rad": "",
                "active_bounds": "",
                "selected": False,
                "used_for_predictions": False,
                "stability": "failed",
            }
            runs.append(row)
            failures.append(
                {"method": "primary_forward_output", "run_id": start_id, "classification": "failed", "reason": row["optimizer_message"]}
            )

    candidates = [item for item in internal if item["row"]["optimizer_success"]]
    if not candidates:
        raise RuntimeError("all primary fits failed")
    selected = min(candidates, key=lambda item: item["row"]["model_selection_mean_episode_rmse_rad"])
    selected["row"]["selected"] = True
    selected["row"]["used_for_predictions"] = True
    best_selection = float(selected["row"]["model_selection_mean_episode_rmse_rad"])
    ratio_limit = float(contract["reporting"]["unstable_model_selection_ratio_from_best"])
    for item in internal:
        row = item["row"]
        reasons = []
        if row["active_bounds"]:
            reasons.append(f"active parameter bound: {row['active_bounds']}")
        if float(row["model_selection_mean_episode_rmse_rad"]) > ratio_limit * best_selection:
            reasons.append(f"model-selection RMSE exceeds {ratio_limit:g} times the best successful run")
        if reasons:
            row["stability"] = "unstable"
            failures.append(
                {"method": "primary_forward_output", "run_id": row["run_id"], "classification": "unstable", "reason": "; ".join(reasons)}
            )
        else:
            row["stability"] = "stable"

    sensitivity = sensitivity_diagnostics(selected["result"].jac, residual_layout)
    return runs, selected, failures, sensitivity


def sensitivity_diagnostics(jacobian: np.ndarray, layout: list[dict]) -> list[dict]:
    groups = ["P01_slow_triangle", "P02_multisine", "P03_smooth_levels", "pooled_P01_P03"]
    rows = []
    for group in groups:
        blocks = []
        episode_count = 0
        for item in layout:
            if group == "pooled_P01_P03" or item["profile_id"] == group:
                blocks.append(np.asarray(jacobian[item["start"] : item["stop"], :], dtype=float))
                episode_count += 1
        matrix = np.vstack(blocks)
        singular = np.linalg.svd(matrix, compute_uv=False)
        rank = int(np.linalg.matrix_rank(matrix))
        condition = float(singular[0] / singular[-1]) if singular[-1] > np.finfo(float).eps else float("inf")
        norms = np.linalg.norm(matrix, axis=0)
        rows.append(
            {
                "calibration_profile_group": group,
                "episode_count": episode_count,
                "residual_row_count": int(matrix.shape[0]),
                "normalized_jacobian_rank": rank,
                "normalized_jacobian_condition_number": condition,
                "largest_singular_value": float(singular[0]),
                "smallest_singular_value": float(singular[-1]),
                "armature_column_norm": float(norms[0]),
                "damping_column_norm": float(norms[1]),
                "frictionloss_column_norm": float(norms[2]),
            }
        )
    return rows


def run_secondary_fit(
    episodes: list[Episode],
    bank: ReplayBank,
    contract: dict,
    lower: np.ndarray,
    upper: np.ndarray,
    controller_scope: str,
) -> tuple[np.ndarray, dict]:
    if controller_scope not in {"C1", "C2", "shared"}:
        raise ValueError(f"unsupported torque-balance scope: {controller_scope}")
    minimum_speed = float(contract["secondary_method"]["minimum_absolute_velocity_rad_s"])
    raw_matrices = []
    raw_targets = []
    weighted_matrices = []
    weighted_targets = []
    used_samples = 0
    episode_count = 0
    for episode in episodes:
        if episode.split != "calibration":
            continue
        if controller_scope != "shared" and episode.controller_id != controller_scope:
            continue
        arrays = episode.arrays
        velocity = np.asarray(arrays["source_velocity_true_rad_s"], dtype=float)
        acceleration = np.asarray(arrays["source_acceleration_true_rad_s2"], dtype=float)
        torque = np.asarray(arrays["source_actuator_torque_Nm"], dtype=float)
        bias = np.asarray(arrays["source_bias_torque_Nm"], dtype=float)
        valid = np.asarray(arrays["valid"], dtype=bool)
        saturated = np.asarray(arrays["source_saturated"], dtype=bool)
        mask = valid & ~saturated
        mask &= np.isfinite(velocity) & np.isfinite(acceleration)
        mask &= np.isfinite(torque) & np.isfinite(bias)
        mask &= np.abs(velocity) >= minimum_speed
        count = int(np.count_nonzero(mask))
        if count == 0:
            continue
        fixture_inertia = bank.fixture_inertia_without_armature(
            episode.controller_id, episode.fixture_id
        )
        matrix = np.column_stack(
            (acceleration[mask], velocity[mask], np.sign(velocity[mask]))
        )
        target = torque[mask] - fixture_inertia * acceleration[mask] - bias[mask]
        weight = 1.0 / math.sqrt(count)
        raw_matrices.append(matrix)
        raw_targets.append(target)
        weighted_matrices.append(matrix * weight)
        weighted_targets.append(target * weight)
        used_samples += count
        episode_count += 1
    if not weighted_matrices:
        raise RuntimeError(
            f"no calibration rows available for {controller_scope} torque-balance fit"
        )
    design = np.vstack(weighted_matrices)
    target = np.concatenate(weighted_targets)
    result = lsq_linear(
        design,
        target,
        bounds=(lower, upper),
        method="trf",
        lsmr_tol="auto",
        max_iter=1000,
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        raise RuntimeError(
            f"{controller_scope} secondary fit failed: {result.message}"
        )
    scaled = design * (upper - lower)[None, :]
    singular = np.linalg.svd(scaled, compute_uv=False)
    unscaled_errors = [
        matrix @ result.x - target_values
        for matrix, target_values in zip(raw_matrices, raw_targets, strict=True)
    ]
    episode_rmse = [
        float(np.sqrt(np.mean(error**2))) for error in unscaled_errors
    ]
    all_unscaled_errors = np.concatenate(unscaled_errors)
    diagnostics = {
        "method": "secondary_torque_balance",
        "scope": controller_scope,
        "run_id": f"{controller_scope}_bounded_linear_fit",
        "optimizer_success": bool(result.success),
        "optimizer_status": int(result.status),
        "optimizer_message": str(result.message).replace("\n", " "),
        "nfev": "",
        "njev": "",
        "elapsed_s": "",
        "objective_cost": float(result.cost),
        "optimality": float(result.optimality),
        "armature_kg_m2": float(result.x[0]),
        "damping_Nm_s_per_rad": float(result.x[1]),
        "frictionloss_Nm": float(result.x[2]),
        "calibration_mean_episode_rmse_rad": "",
        "model_selection_mean_episode_rmse_rad": "",
        "active_bounds": ";".join(
            f"{name}:{'lower' if bound_state < 0 else 'upper'}"
            for name, bound_state in zip(
                contract["parameters"]["names"], result.active_mask, strict=True
            )
            if bound_state
        ),
        "selected": False,
        "used_for_predictions": controller_scope == "shared",
        "stability": "stable" if not np.any(result.active_mask) else "unstable",
        "torque_balance_episode_count": episode_count,
        "torque_balance_sample_count": used_samples,
        "normalized_design_rank": int(np.linalg.matrix_rank(scaled)),
        "normalized_design_condition_number": float(singular[0] / singular[-1]),
        "objective_space_residual_rms": float(np.sqrt(np.mean(result.fun**2))),
        "mean_episode_torque_balance_rmse_Nm": float(np.mean(episode_rmse)),
        "pooled_sample_torque_balance_rmse_Nm": float(
            np.sqrt(np.mean(all_unscaled_errors**2))
        ),
    }
    return np.asarray(result.x, dtype=float), diagnostics


def evaluate_models(
    episodes: list[Episode], bank: ReplayBank, theta_primary: np.ndarray, theta_secondary: np.ndarray
) -> tuple[list[dict], dict[tuple[str, str], np.ndarray]]:
    rows = []
    predictions: dict[tuple[str, str], np.ndarray] = {}
    for episode in episodes:
        target = np.asarray(episode.arrays["source_position_meas_rad"], dtype=float)
        valid = np.asarray(episode.arrays["valid"], dtype=bool)
        model_predictions = {
            "nominal": np.asarray(episode.arrays["nominal_position_meas_rad"], dtype=float),
            "primary_forward_output": bank.rollout(episode, theta_primary, quantize=True),
            "secondary_torque_balance": bank.rollout(episode, theta_secondary, quantize=True),
        }
        for method, prediction in model_predictions.items():
            predictions[(method, episode.episode_id)] = prediction
            metric = error_metrics(prediction, target, valid)
            rows.append(
                {
                    "episode_id": episode.episode_id,
                    "split": episode.split,
                    "fixture_id": episode.fixture_id,
                    "profile_id": episode.profile_id,
                    "controller_id": episode.controller_id,
                    "repetition": episode.repetition,
                    "model": method,
                    **metric,
                }
            )
    return rows, predictions


def aggregate_metrics(rows: list[dict]) -> list[dict]:
    output = []
    models = sorted({row["model"] for row in rows})
    for split in ("calibration", "model_selection", "held_out", "all"):
        for model in models:
            subset = [row for row in rows if row["model"] == model and (split == "all" or row["split"] == split)]
            if not subset:
                continue
            samples = sum(int(row["sample_count"]) for row in subset)
            pooled_sse = sum(float(row["rmse_rad"]) ** 2 * int(row["sample_count"]) for row in subset)
            output.append(
                {
                    "split": split,
                    "model": model,
                    "episode_count": len(subset),
                    "sample_count": samples,
                    "mean_episode_rmse_rad": float(np.mean([row["rmse_rad"] for row in subset])),
                    "pooled_rmse_rad": math.sqrt(pooled_sse / samples),
                    "mean_episode_mae_rad": float(np.mean([row["mae_rad"] for row in subset])),
                    "maximum_peak_abs_error_rad": float(np.max([row["peak_abs_error_rad"] for row in subset])),
                    "mean_episode_r2": float(np.mean([row["r2"] for row in subset])),
                }
            )
    return output


def write_unseen_predictions(
    path: Path, episodes: list[Episode], predictions: dict[tuple[str, str], np.ndarray]
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "episode_id", "split", "fixture_id", "profile_id", "controller_id", "repetition",
        "sample_index", "time_s", "position_applied_rad", "source_position_meas_rad",
        "nominal_position_rad", "primary_prediction_rad", "secondary_prediction_rad",
    ]
    count = 0
    with gzip.open(path, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for episode in episodes:
            if episode.split not in {"model_selection", "held_out"}:
                continue
            arrays = episode.arrays
            for index in range(arrays["time_s"].size):
                writer.writerow(
                    {
                        "episode_id": episode.episode_id,
                        "split": episode.split,
                        "fixture_id": episode.fixture_id,
                        "profile_id": episode.profile_id,
                        "controller_id": episode.controller_id,
                        "repetition": episode.repetition,
                        "sample_index": index,
                        "time_s": f"{float(arrays['time_s'][index]):.8f}",
                        "position_applied_rad": f"{float(arrays['position_applied_rad'][index]):.16g}",
                        "source_position_meas_rad": f"{float(arrays['source_position_meas_rad'][index]):.16g}",
                        "nominal_position_rad": f"{float(predictions[('nominal', episode.episode_id)][index]):.16g}",
                        "primary_prediction_rad": f"{float(predictions[('primary_forward_output', episode.episode_id)][index]):.16g}",
                        "secondary_prediction_rad": f"{float(predictions[('secondary_torque_balance', episode.episode_id)][index]):.16g}",
                    }
                )
                count += 1
    return count


def make_identified_models(
    theta: np.ndarray, experiment: dict, bank: ReplayBank
) -> list[dict]:
    records = []
    for controller in sorted(experiment["controllers"]):
        for fixture in sorted(experiment["fixtures"]):
            source = PACKAGE / "models" / "simulation" / "nominal" / controller / f"{fixture}.xml"
            destination = IDENTIFIED_MODELS / controller / f"{fixture}.xml"
            tree = ET.parse(source)
            root = tree.getroot()
            root.set("model", f"identified-shared-{controller}-{fixture}")
            joint = root.find(".//joint[@name='actuator_joint']")
            if joint is None:
                raise ValueError(f"{source}: actuator_joint not found")
            joint.set("armature", f"{float(theta[0]):.16g}")
            joint.set("damping", f"{float(theta[1]):.16g}")
            joint.set("frictionloss", f"{float(theta[2]):.16g}")
            for mesh in root.findall("./asset/mesh"):
                mesh.set("file", f"../../assets/{Path(mesh.get('file', '')).name}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            ET.indent(tree, space="  ")
            tree.write(destination, encoding="unicode")
            model = mujoco.MjModel.from_xml_path(str(destination.resolve()))
            joint_id, actuator_id, checks = fixed_model_checks(
                model,
                experiment["controllers"][controller],
                experiment["simulation"],
            )
            constant_data = mujoco.MjData(model)
            mujoco.mj_setConst(model, constant_data)
            expected_M0 = (
                bank.fixture_inertia_without_armature(controller, fixture)
                + float(theta[0])
            )
            checks.update(
                {
                    "joint_identifier_valid": joint_id >= 0,
                    "actuator_identifier_valid": actuator_id >= 0,
                    "armature_matches": np.isclose(
                        model.dof_armature[0], theta[0], rtol=0, atol=1e-14
                    ),
                    "damping_matches": np.isclose(
                        model.dof_damping[0], theta[1], rtol=0, atol=1e-14
                    ),
                    "frictionloss_matches": np.isclose(
                        model.dof_frictionloss[0], theta[2], rtol=0, atol=1e-14
                    ),
                    "dof_M0_matches_fixture_plus_armature": np.isclose(
                        model.dof_M0[0], expected_M0, rtol=0, atol=1e-13
                    ),
                }
            )
            checks = {name: bool(value) for name, value in checks.items()}
            records.append(
                {
                    "controller_id": controller,
                    "fixture_id": fixture,
                    "path": str(destination.relative_to(PACKAGE)),
                    "joint_id": int(joint_id),
                    "actuator_id": int(actuator_id),
                    "checks": checks,
                    "passed": bool(all(checks.values())),
                }
            )
    if not all(record["passed"] for record in records):
        raise RuntimeError("one or more identified MJCF checks failed")
    return records


def make_plots(
    episodes: list[Episode], predictions: dict[tuple[str, str], np.ndarray], aggregates: list[dict]
) -> None:
    PLOTS.mkdir(parents=True, exist_ok=True)
    preferred = [
        "B0__C1__P04_chirp__R01", "B0__C2__P04_chirp__R01",
        "G1__C1__P06_heldout_composite__R01", "G1__C2__P06_heldout_composite__R01",
    ]
    by_id = {episode.episode_id: episode for episode in episodes}
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharey=True, constrained_layout=True)
    for axis, episode_id in zip(axes.flat, preferred, strict=True):
        episode = by_id[episode_id]
        time_values = episode.arrays["time_s"]
        axis.plot(time_values, episode.arrays["position_applied_rad"], color="0.65", linestyle=":", label="Input")
        axis.plot(time_values, episode.arrays["source_position_meas_rad"], color="black", linewidth=1.4, label="Source output")
        axis.plot(time_values, predictions[("nominal", episode_id)], color="#d95f02", linewidth=1.0, label="Nominal")
        axis.plot(time_values, predictions[("primary_forward_output", episode_id)], color="#1b9e77", linewidth=1.1, label="Primary fit")
        axis.plot(time_values, predictions[("secondary_torque_balance", episode_id)], color="#7570b3", linewidth=1.0, label="Secondary fit")
        axis.set_title(f"{episode.fixture_id} {episode.controller_id} {episode.profile_id} ({episode.split})")
        axis.set_xlabel("Time (s)")
        axis.set_ylabel("Position (rad)")
        axis.grid(alpha=0.25)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=5)
    fig.suptitle("Input-output predictions on data not used for fitting")
    fig.savefig(PLOTS / "prediction_on_unseen_data.png", dpi=160)
    plt.close(fig)

    splits = ["calibration", "model_selection", "held_out"]
    methods = ["nominal", "primary_forward_output", "secondary_torque_balance"]
    labels = ["Nominal", "Primary fit", "Secondary fit"]
    colors = ["#d95f02", "#1b9e77", "#7570b3"]
    lookup = {(row["split"], row["model"]): row for row in aggregates}
    x = np.arange(len(splits), dtype=float)
    width = 0.24
    fig, axis = plt.subplots(figsize=(8.5, 4.8), constrained_layout=True)
    for index, (method, label, color) in enumerate(zip(methods, labels, colors, strict=True)):
        values = [lookup[(split, method)]["mean_episode_rmse_rad"] for split in splits]
        axis.bar(x + (index - 1) * width, values, width, label=label, color=color)
    axis.set_xticks(x, ["Calibration", "Model selection", "Held out"])
    axis.set_ylabel("Mean episode position RMSE (rad)")
    axis.set_title("Position-output error by data split")
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    fig.savefig(PLOTS / "comparison_metrics.png", dpi=160)
    plt.close(fig)


def parameter_rows(
    primary: np.ndarray,
    secondary_by_scope: dict[str, np.ndarray],
    secondary_runs_by_scope: dict[str, dict],
    experiment: dict,
    contract: dict,
) -> list[dict]:
    names, lower, upper = parameter_arrays(contract)
    nominal = experiment["plants"]["nominal"]
    reference = experiment["plants"]["source"]
    sources = [
        (
            "primary_forward_output",
            "shared",
            primary,
            True,
            None,
        ),
    ]
    for scope in ("C1", "C2", "shared"):
        sources.append(
            (
                "secondary_torque_balance",
                scope,
                secondary_by_scope[scope],
                True,
                secondary_runs_by_scope[scope],
            )
        )
    sources.extend(
        [
            (
                "nominal_starting_model",
                "not_applicable",
                np.asarray(
                    [
                        nominal["armature"],
                        nominal["damping"],
                        nominal["frictionloss"],
                    ]
                ),
                False,
                None,
            ),
            (
                "disclosed_source_reference",
                "not_applicable",
                np.asarray(
                    [
                        reference["armature"],
                        reference["damping"],
                        reference["frictionloss"],
                    ]
                ),
                False,
                None,
            ),
        ]
    )
    rows = []
    for method, scope, values, fitted, diagnostics in sources:
        for index, name in enumerate(names):
            rows.append(
                {
                    "method_or_reference": method,
                    "scope": scope,
                    "is_fitted_value": fitted,
                    "parameter": name,
                    "value": float(values[index]),
                    "unit": contract["parameters"]["units"][name],
                    "lower_bound": float(lower[index]),
                    "upper_bound": float(upper[index]),
                    "torque_balance_episode_count": (
                        diagnostics["torque_balance_episode_count"]
                        if diagnostics is not None
                        else ""
                    ),
                    "torque_balance_sample_count": (
                        diagnostics["torque_balance_sample_count"]
                        if diagnostics is not None
                        else ""
                    ),
                    "normalized_design_rank": (
                        diagnostics["normalized_design_rank"]
                        if diagnostics is not None
                        else ""
                    ),
                    "normalized_design_condition_number": (
                        diagnostics["normalized_design_condition_number"]
                        if diagnostics is not None
                        else ""
                    ),
                    "mean_episode_torque_balance_rmse_Nm": (
                        diagnostics["mean_episode_torque_balance_rmse_Nm"]
                        if diagnostics is not None
                        else ""
                    ),
                    "pooled_sample_torque_balance_rmse_Nm": (
                        diagnostics["pooled_sample_torque_balance_rmse_Nm"]
                        if diagnostics is not None
                        else ""
                    ),
                }
            )
    return rows


def reliability_rows(
    primary: np.ndarray, secondary: np.ndarray, successful_runs: list[dict], contract: dict, selected_condition: float
) -> list[dict]:
    names, lower, upper = parameter_arrays(contract)
    values = np.asarray([[float(row[name]) for name in names] for row in successful_runs], dtype=float)
    rows = []
    for index, name in enumerate(names):
        start_span = float(np.ptp(values[:, index])) if values.shape[0] > 1 else 0.0
        range_fraction = start_span / float(upper[index] - lower[index])
        method_difference = abs(float(primary[index] - secondary[index]))
        method_fraction = method_difference / max(abs(float(primary[index])), np.finfo(float).eps)
        at_bound = bool(
            primary[index] <= lower[index] + 1e-5 * (upper[index] - lower[index])
            or primary[index] >= upper[index] - 1e-5 * (upper[index] - lower[index])
        )
        reliable = bool(not at_bound and range_fraction < 0.02 and method_fraction < 0.10 and selected_condition < 1e4)
        reasons = []
        reasons.append(f"multi-start span is {100 * range_fraction:.3g}% of the allowed range")
        reasons.append(f"primary-secondary difference is {100 * method_fraction:.3g}% of the primary value")
        reasons.append(f"pooled normalized Jacobian condition number is {selected_condition:.4g}")
        if at_bound:
            reasons.append("the primary estimate is at an active bound")
        rows.append(
            {
                "parameter": name,
                "unit": contract["parameters"]["units"][name],
                "primary_value": float(primary[index]),
                "secondary_value": float(secondary[index]),
                "absolute_method_difference": method_difference,
                "relative_method_difference_fraction": method_fraction,
                "successful_multistart_span": start_span,
                "multistart_span_fraction_of_bound_range": range_fraction,
                "primary_active_bound": at_bound,
                "assessment": "reliable_in_this_simulation_study" if reliable else "uncertain",
                "basis": "; ".join(reasons),
            }
        )
    return rows


def format_parameter_table(theta: np.ndarray) -> str:
    return (
        "| Parameter | Value | Unit |\n|---|---:|---|\n"
        f"| Effective armature | {theta[0]:.12g} | kg·m² |\n"
        f"| Joint damping | {theta[1]:.12g} | N·m·s/rad |\n"
        f"| Friction loss | {theta[2]:.12g} | N·m |"
    )


def write_documents(
    primary: np.ndarray,
    secondary_by_scope: dict[str, np.ndarray],
    aggregates: list[dict],
    optimizer_rows: list[dict],
    failed_rows: list[dict],
    sensitivity: list[dict],
    reliability: list[dict],
    contract: dict,
    experiment: dict,
) -> None:
    held = {(row["model"]): row for row in aggregates if row["split"] == "held_out"}
    selected_run = next(row for row in optimizer_rows if row["method"] == "primary_forward_output" and row["selected"])
    pooled = next(row for row in sensitivity if row["calibration_profile_group"] == "pooled_P01_P03")
    settings = experiment["simulation"]
    secondary_runs = {
        row["scope"]: row
        for row in optimizer_rows
        if row["method"] == "secondary_torque_balance"
    }
    scope_table_lines = [
        "| Scope | Armature (kg·m²) | Damping (N·m·s/rad) | Friction loss (N·m) | Episodes | Samples | Rank | Condition | Mean episode RMSE (N·m) | Pooled RMSE (N·m) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scope in ("C1", "C2", "shared"):
        values = secondary_by_scope[scope]
        run = secondary_runs[scope]
        scope_table_lines.append(
            f"| {scope} | {values[0]:.12g} | {values[1]:.12g} | {values[2]:.12g} | "
            f"{run['torque_balance_episode_count']} | {run['torque_balance_sample_count']} | "
            f"{run['normalized_design_rank']} | {run['normalized_design_condition_number']:.6g} | "
            f"{run['mean_episode_torque_balance_rmse_Nm']:.6g} | "
            f"{run['pooled_sample_torque_balance_rmse_Nm']:.6g} |"
        )
    secondary_scope_table = "\n".join(scope_table_lines)
    now = datetime.now(ZoneInfo("Asia/Dubai")).strftime("%Y-%m-%d %H:%M:%S %Z")
    method_note = f"""# Data-to-Model Method and Results

Run time: {now}

## Scope

This study identifies one shared effective joint model for all five mechanical fixtures and both fixed MuJoCo controller conditions. Only armature, damping, and friction loss are fitted. Fixture geometry, body mass, inertia, gravity, actuator limits, C1/C2 gains, and timing remain fixed in their MJCF files. This is a synthetic simulation study; it is not a claim about physical XC330 parameters.

## Data use

- Calibration: 24 episodes, used by both fits.
- Model selection: 8 episodes, used only to choose among successful primary multi-start solutions.
- Held out: 6 episodes, opened for prediction only after the primary solution was selected.
- The primary objective reads applied position, measured position, measured velocity, validity, and time. It does not use simulator torque or true state derivatives. Its fit-facing context does not contain disclosed Source parameter values.

## Primary method

The primary result uses bounded closed-loop forward MuJoCo position-output error. Each candidate is replayed through the exact fixture/controller MJCF at {settings['physics_timestep_s'] if 'physics_timestep_s' in settings else contract['primary_method']['physics_timestep_s']:.3f} s physics steps and 100 Hz zero-order-held commands. Each rollout is initialized once from its first measured position and velocity; recorded state is not injected again. The objective compares continuous simulated position with encoder-quantized measured position at every fifth archived sample. Each episode is divided by the square root of its retained sample count, so long episodes do not dominate. Four independent starts use the same bounds. Final reported predictions are quantized to {settings['position_resolution_rad']:.12g} rad.

{format_parameter_table(primary)}

The selected start was `{selected_run['run_id']}`. Its mean model-selection episode RMSE was {float(selected_run['model_selection_mean_episode_rmse_rad']):.9g} rad. The pooled normalized calibration Jacobian has rank {pooled['normalized_jacobian_rank']} and condition number {float(pooled['normalized_jacobian_condition_number']):.6g}. Profile-level sensitivity details are in `sensitivity_diagnostics.csv`.

## Secondary comparison

The comparison fit solves bounded linear torque balance separately for C1, separately for C2, and once with both conditions pooled. It uses the 100 Hz archived simulator-only actuator effort, bias torque, true velocity, and true acceleration, excluding saturated samples and samples below {contract['secondary_method']['minimum_absolute_velocity_rad_s']:.3g} rad/s. This is useful as an idealized recoverability check because those privileged signals isolate the three joint terms. It is not the physics-step torque archive described by the full method, so discretization and archived acceleration can leave a small bias. It is not the intended route for future hardware data unless equivalent torque and sufficiently accurate derivatives are available.

{secondary_scope_table}

The shared scope is the only secondary vector replayed for prediction comparisons. C1-only and C2-only are reported as diagnostics; they do not create separate identified models.

## Prediction results

| Model | Model-selection mean episode RMSE (rad) | Held-out mean episode RMSE (rad) | Held-out pooled RMSE (rad) |
|---|---:|---:|---:|
| Nominal | {next(row for row in aggregates if row['split']=='model_selection' and row['model']=='nominal')['mean_episode_rmse_rad']:.9g} | {held['nominal']['mean_episode_rmse_rad']:.9g} | {held['nominal']['pooled_rmse_rad']:.9g} |
| Primary forward-output fit | {next(row for row in aggregates if row['split']=='model_selection' and row['model']=='primary_forward_output')['mean_episode_rmse_rad']:.9g} | {held['primary_forward_output']['mean_episode_rmse_rad']:.9g} | {held['primary_forward_output']['pooled_rmse_rad']:.9g} |
| Secondary torque-balance fit | {next(row for row in aggregates if row['split']=='model_selection' and row['model']=='secondary_torque_balance')['mean_episode_rmse_rad']:.9g} | {held['secondary_torque_balance']['mean_episode_rmse_rad']:.9g} | {held['secondary_torque_balance']['pooled_rmse_rad']:.9g} |

The complete per-episode table is `episode_metrics.csv`; sample-level model-selection and held-out predictions are in `predictions_unseen.csv.gz`.

## Stability and limitations

There were {len(failed_rows)} failed or unstable fit records. Details are in `failed_or_unstable_fits.csv`; an empty table means all runs passed the stated checks. Multi-start agreement, active bounds, method agreement, and local sensitivity are summarized in `PARAMETER_RELIABILITY.md`. The favorable result is expected for a deterministic simulator with the correct model structure. Hardware data will add effects that are absent here, including timing jitter, unmodeled compliance, temperature change, and uncertain torque scale.
"""
    (RESULTS / "METHOD_AND_RESULTS.md").write_text(method_note, encoding="utf-8")

    reliability_lines = [
        "# Parameter Reliability",
        "",
        "The labels below apply only to this disclosed synthetic study. They combine multi-start agreement, active-bound checks, primary-versus-secondary agreement, and pooled local sensitivity.",
        "",
        "| Parameter | Primary | Secondary | Relative difference | Assessment |",
        "|---|---:|---:|---:|---|",
    ]
    for row in reliability:
        reliability_lines.append(
            f"| {row['parameter']} | {row['primary_value']:.12g} | {row['secondary_value']:.12g} | {100*row['relative_method_difference_fraction']:.4g}% | {row['assessment'].replace('_', ' ')} |"
        )
    reliability_lines.extend(
        [
            "",
            "The machine-readable basis for each label is in `parameter_reliability.csv`. A parameter should be treated as uncertain for physical transfer even when it is well recovered here, because this dataset was produced by the same model family used for fitting.",
        ]
    )
    (RESULTS / "PARAMETER_RELIABILITY.md").write_text("\n".join(reliability_lines) + "\n", encoding="utf-8")

    readme = """# Data2Model

This package fits one shared three-parameter MuJoCo joint model to the synthetic simulation dataset and checks its predictions on profiles and fixtures that were not used for fitting. The primary result is the closed-loop forward position-output fit. The torque-balance result is a simulator-only comparison.

## Where each requested item is located

| Requested item | Files and folders |
|---|---|
| Simulation dataset used | `data/simulation_dataset.npz` is the complete numeric archive. `data/episode_list.csv` defines configuration, profile, fixed controller, repetition, and split. `data/DATA_DICTIONARY.md` explains each field. `data/experiment_contract.json` records the simulation design. |
| Primary model-fitting method and script | `scripts/fit_data2model.py` contains the bounded forward MuJoCo position-output fit. `config/fitting_contract.json` records fields, bounds, starts, optimizer settings, and selection rule. `results/METHOD_AND_RESULTS.md` explains the method. |
| Secondary comparison method and usefulness | The same script contains bounded simulator-only torque-balance fits for C1-only, C2-only, and shared scopes. The shared result is used for prediction. Their purpose and limits are stated in `config/fitting_contract.json` and `results/METHOD_AND_RESULTS.md`. |
| Fitted parameter values with units | `results/fitted_parameters.csv` contains the primary vector and all three torque-balance scopes with units, bounds, rank, condition, sample counts, physical residual metrics, the nominal starting model, and the disclosed synthetic reference. `results/METHOD_AND_RESULTS.md` presents the main tables. |
| Predictions on data not used for fitting | `results/predictions_unseen.csv.gz` contains sample-level model-selection and held-out predictions. `plots/prediction_on_unseen_data.png` shows representative input-output traces. |
| Comparison metrics and plots | `results/episode_metrics.csv` and `results/aggregate_metrics.csv` contain per-episode and split-level metrics. `plots/comparison_metrics.png` compares RMSE by split. `results/sensitivity_diagnostics.csv` records profile-level and pooled Jacobian rank, condition number, singular values, and column norms. |
| Failed or unstable fits | `results/failed_or_unstable_fits.csv` is the complete exception and stability table, including its header when there are no records. `results/optimizer_runs.csv` preserves every primary start and the three scoped secondary solver summaries. |
| Reliability and remaining uncertainty | `results/PARAMETER_RELIABILITY.md` is the short interpretation. `results/parameter_reliability.csv` contains the supporting numbers. `results/result.json` is the compact run summary and validation record. |

## Model files

- `models/simulation/nominal/C1/` and `models/simulation/nominal/C2/` are the exact candidate MJCFs used by the script.
- `models/identified/C1/` and `models/identified/C2/` hold the same shared primary joint parameters with each fixture's mechanics and fixed controller gains preserved.
- `models/assets/` contains the five meshes needed to load both MJCF sets.

## Software and reproduction

`requirements.txt` records the Python package versions expected by this package. From the `Data2Model` folder, run:

```bash
python scripts/fit_data2model.py
```

The script replaces the result tables, plots, notes, and identified MJCFs. It does not connect to hardware. Calibration data are used for fitting, model-selection data choose the primary start, and held-out data are evaluated only afterward.
"""
    (PACKAGE / "README.md").write_text(readme, encoding="utf-8")


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(parents=True, exist_ok=True)
    contract = read_json(FIT_CONTRACT_PATH)
    fit_context = load_fit_context(EXPERIMENT_CONTRACT_PATH)
    required_mujoco = str(fit_context["simulation"]["required_mujoco_version"])
    if mujoco.__version__ != required_mujoco:
        raise RuntimeError(
            f"MuJoCo {required_mujoco} is required; found {mujoco.__version__}"
        )
    archive = PACKAGE / contract["dataset"]["archive"]
    names, lower, upper = parameter_arrays(contract)
    primary_fields = list(dict.fromkeys(contract["primary_method"]["fit_fields"]))
    forbidden_primary = {
        "source_position_true_rad", "source_velocity_true_rad_s", "source_acceleration_true_rad_s2",
        "source_actuator_torque_Nm", "source_bias_torque_Nm", "source_passive_torque_Nm",
        "source_constraint_torque_Nm", "nominal_position_meas_rad",
    }
    overlap = forbidden_primary.intersection(primary_fields)
    if overlap:
        raise ValueError(f"primary fit field list contains privileged fields: {sorted(overlap)}")
    counts = episode_split_counts(archive)
    if counts != contract["dataset"]["expected_episode_counts"]:
        raise ValueError(f"unexpected episode counts: {counts}")
    primary_episodes = load_episodes(
        archive, primary_fields, allowed_splits={"calibration", "model_selection"}
    )
    if any(episode.split == "held_out" for episode in primary_episodes):
        raise RuntimeError("held-out episodes entered the primary fit stage")
    bank = ReplayBank(contract, fit_context)

    optimizer_rows, selected, failed_rows, sensitivity = run_primary_fit(
        primary_episodes, bank, contract, lower, upper
    )
    theta_primary = np.asarray(selected["theta"], dtype=float)

    secondary_fields = list(dict.fromkeys(contract["secondary_method"]["fields"] + ["position_applied_rad", "valid"]))
    secondary_episodes = load_episodes(
        archive, secondary_fields, allowed_splits={"calibration"}
    )
    secondary_by_scope: dict[str, np.ndarray] = {}
    secondary_runs_by_scope: dict[str, dict] = {}
    for scope in ("C1", "C2", "shared"):
        values, run = run_secondary_fit(
            secondary_episodes, bank, contract, lower, upper, scope
        )
        secondary_by_scope[scope] = values
        secondary_runs_by_scope[scope] = run
        optimizer_rows.append(run)
        if run["stability"] != "stable":
            failed_rows.append(
                {
                    "method": "secondary_torque_balance",
                    "run_id": run["run_id"],
                    "classification": "unstable",
                    "reason": f"active parameter bound: {run['active_bounds']}",
                }
            )
    theta_secondary = secondary_by_scope["shared"]

    # The full contract, including the disclosed reference, is opened for reporting
    # only after the primary and all secondary parameter vectors are frozen.
    experiment = read_json(EXPERIMENT_CONTRACT_PATH)

    # Held-out arrays are loaded only after primary selection and both parameter fits.
    evaluation_fields = [
        "time_s", "position_applied_rad", "source_position_meas_rad", "source_velocity_meas_rad_s",
        "nominal_position_meas_rad", "valid"
    ]
    evaluation_episodes = load_episodes(
        archive, evaluation_fields, allowed_splits=None
    )
    metric_rows, predictions = evaluate_models(evaluation_episodes, bank, theta_primary, theta_secondary)
    aggregates = aggregate_metrics(metric_rows)
    unseen_rows = write_unseen_predictions(RESULTS / "predictions_unseen.csv.gz", evaluation_episodes, predictions)
    identified_validation = make_identified_models(theta_primary, experiment, bank)

    successful_primary = [
        row for row in optimizer_rows if row["method"] == "primary_forward_output" and row["optimizer_success"]
    ]
    pooled = next(row for row in sensitivity if row["calibration_profile_group"] == "pooled_P01_P03")
    reliability = reliability_rows(
        theta_primary, theta_secondary, successful_primary, contract,
        float(pooled["normalized_jacobian_condition_number"]),
    )
    fitted_rows = parameter_rows(
        theta_primary,
        secondary_by_scope,
        secondary_runs_by_scope,
        experiment,
        contract,
    )

    optimizer_fields = [
        "method", "scope", "run_id", "optimizer_success", "optimizer_status",
        "optimizer_message", "nfev", "njev", "elapsed_s", "objective_cost",
        "optimality", *names, "calibration_mean_episode_rmse_rad",
        "model_selection_mean_episode_rmse_rad", "active_bounds", "selected",
        "used_for_predictions", "stability", "torque_balance_episode_count",
        "torque_balance_sample_count", "normalized_design_rank",
        "normalized_design_condition_number", "objective_space_residual_rms",
        "mean_episode_torque_balance_rmse_Nm",
        "pooled_sample_torque_balance_rmse_Nm",
    ]
    write_csv(RESULTS / "optimizer_runs.csv", optimizer_rows, optimizer_fields)
    write_csv(
        RESULTS / "failed_or_unstable_fits.csv", failed_rows,
        ["method", "run_id", "classification", "reason"],
    )
    write_csv(
        RESULTS / "sensitivity_diagnostics.csv", sensitivity,
        [
            "calibration_profile_group", "episode_count", "residual_row_count",
            "normalized_jacobian_rank", "normalized_jacobian_condition_number",
            "largest_singular_value", "smallest_singular_value", "armature_column_norm",
            "damping_column_norm", "frictionloss_column_norm",
        ],
    )
    write_csv(
        RESULTS / "fitted_parameters.csv", fitted_rows,
        [
            "method_or_reference", "scope", "is_fitted_value", "parameter", "value",
            "unit", "lower_bound", "upper_bound", "torque_balance_episode_count",
            "torque_balance_sample_count", "normalized_design_rank",
            "normalized_design_condition_number",
            "mean_episode_torque_balance_rmse_Nm",
            "pooled_sample_torque_balance_rmse_Nm",
        ],
    )
    write_csv(
        RESULTS / "episode_metrics.csv", metric_rows,
        [
            "episode_id", "split", "fixture_id", "profile_id", "controller_id",
            "repetition", "model", "sample_count", "rmse_rad", "mae_rad",
            "peak_abs_error_rad", "bias_rad", "r2",
        ],
    )
    write_csv(
        RESULTS / "aggregate_metrics.csv", aggregates,
        [
            "split", "model", "episode_count", "sample_count", "mean_episode_rmse_rad",
            "pooled_rmse_rad", "mean_episode_mae_rad", "maximum_peak_abs_error_rad",
            "mean_episode_r2",
        ],
    )
    write_csv(
        RESULTS / "parameter_reliability.csv", reliability,
        [
            "parameter", "unit", "primary_value", "secondary_value",
            "absolute_method_difference", "relative_method_difference_fraction",
            "successful_multistart_span", "multistart_span_fraction_of_bound_range",
            "primary_active_bound", "assessment", "basis",
        ],
    )
    make_plots(evaluation_episodes, predictions, aggregates)
    write_documents(
        theta_primary, secondary_by_scope, aggregates, optimizer_rows, failed_rows,
        sensitivity, reliability, contract, experiment,
    )

    held_primary = next(
        row for row in aggregates
        if row["split"] == "held_out" and row["model"] == "primary_forward_output"
    )
    summary = {
        "schema_version": "data2model-result-1",
        "run_time_asia_dubai": datetime.now(ZoneInfo("Asia/Dubai")).isoformat(),
        "software": {
            "python": platform.python_version(),
            "mujoco": mujoco.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "simulation_settings": {
            "physics_timestep_s": float(experiment["simulation"]["physics_timestep_s"]),
            "sample_rate_hz": float(experiment["simulation"]["sample_rate_hz"]),
            "integrator": experiment["simulation"]["integrator"],
            "gravity_m_s2": float(experiment["simulation"]["gravity_m_s2"]),
            "command_delay_s": float(experiment["simulation"]["command_delay_s"]),
            "force_range_Nm": experiment["simulation"]["forcerange_Nm"],
            "control_range_rad": experiment["simulation"]["ctrlrange_rad"],
        },
        "episode_counts": counts,
        "primary_method": contract["primary_method"]["name"],
        "primary_selected_start": selected["row"]["run_id"],
        "primary_parameters": dict(zip(names, map(float, theta_primary), strict=True)),
        "secondary_method": contract["secondary_method"]["name"],
        "secondary_prediction_scope": "shared",
        "secondary_parameters": dict(zip(names, map(float, theta_secondary), strict=True)),
        "secondary_scope_results": {
            scope: {
                "parameters": dict(
                    zip(names, map(float, secondary_by_scope[scope]), strict=True)
                ),
                "episode_count": int(
                    secondary_runs_by_scope[scope]["torque_balance_episode_count"]
                ),
                "sample_count": int(
                    secondary_runs_by_scope[scope]["torque_balance_sample_count"]
                ),
                "normalized_design_rank": int(
                    secondary_runs_by_scope[scope]["normalized_design_rank"]
                ),
                "normalized_design_condition_number": float(
                    secondary_runs_by_scope[scope][
                        "normalized_design_condition_number"
                    ]
                ),
                "objective_space_residual_rms": float(
                    secondary_runs_by_scope[scope]["objective_space_residual_rms"]
                ),
                "mean_episode_torque_balance_rmse_Nm": float(
                    secondary_runs_by_scope[scope][
                        "mean_episode_torque_balance_rmse_Nm"
                    ]
                ),
                "pooled_sample_torque_balance_rmse_Nm": float(
                    secondary_runs_by_scope[scope][
                        "pooled_sample_torque_balance_rmse_Nm"
                    ]
                ),
                "used_for_predictions": scope == "shared",
            }
            for scope in ("C1", "C2", "shared")
        },
        "held_out_primary_mean_episode_rmse_rad": float(
            held_primary["mean_episode_rmse_rad"]
        ),
        "held_out_primary_pooled_rmse_rad": float(held_primary["pooled_rmse_rad"]),
        "unseen_prediction_rows": unseen_rows,
        "failed_or_unstable_fit_count": len(failed_rows),
        "identified_models": identified_validation,
        "checks": {
            "required_mujoco_version_matches": mujoco.__version__
            == fit_context["simulation"]["required_mujoco_version"],
            "fit_context_excludes_plant_reference_values": "plants"
            not in fit_context,
            "secondary_scopes_complete": set(secondary_by_scope)
            == {"C1", "C2", "shared"},
            "shared_secondary_is_only_prediction_scope": all(
                run["used_for_predictions"] == (scope == "shared")
                for scope, run in secondary_runs_by_scope.items()
            ),
            "split_counts_read_from_metadata_only": True,
            "primary_fit_used_calibration_only": True,
            "primary_episode_objects_exclude_held_out": all(
                episode.split in {"calibration", "model_selection"}
                for episode in primary_episodes
            ),
            "secondary_episode_objects_are_calibration_only": all(
                episode.split == "calibration" for episode in secondary_episodes
            ),
            "model_selection_used_for_start_selection_only": True,
            "held_out_numeric_fields_loaded_after_fit_and_selection": True,
            "held_out_evaluated_after_selection": True,
            "primary_excluded_simulator_torque_and_true_state": True,
            "continuous_candidate_used_in_primary_objective": True,
            "reported_predictions_quantized_to_sensor_resolution": True,
            "initial_state_set_once_from_first_measured_position_and_velocity": True,
            "recorded_state_not_reinjected": True,
            "controller_gains_not_fitted": True,
            "one_shared_joint_parameter_vector_in_all_identified_models": True,
            "all_identified_models_load_and_pass_mapping_checks": all(
                item["passed"] for item in identified_validation
            ),
            "hardware_not_accessed": True,
        },
    }
    write_json(RESULTS / "result.json", summary)
    print(
        json.dumps(
            {
                "primary_parameters": summary["primary_parameters"],
                "secondary_parameters": summary["secondary_parameters"],
                "held_out_primary_mean_episode_rmse_rad": summary[
                    "held_out_primary_mean_episode_rmse_rad"
                ],
                "failed_or_unstable_fit_count": summary[
                    "failed_or_unstable_fit_count"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
