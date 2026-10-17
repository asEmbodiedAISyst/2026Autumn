#!/usr/bin/env python3
"""Analyze the Appendix B RS06 Real-Position dataset.

The primary evidence path uses only the recorded position interface. Controller
settings are fixed, H1 and H2 are fitted independently, and only MuJoCo joint
``armature``, ``damping``, and ``frictionloss`` are estimated. The unqualified
RS06 firmware torque field and the static-gravity records are reported only as
supporting diagnostics.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import shutil
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mujoco
import numpy as np
from scipy.optimize import least_squares, lsq_linear
from scipy.signal import savgol_filter


CONTROLLERS = {
    "H1": {"kp": 50.0, "kd": 3.38},
    "H2": {"kp": 100.0, "kd": 1.95},
}
JOINT_NAMES = ("armature", "damping", "frictionloss")
JOINT_UNITS = ("kg m^2", "N m s/rad", "N m")
LOWER = np.array([1e-7, 0.0, 0.0], dtype=float)
UPPER = np.array([0.10, 10.0, 10.0], dtype=float)
METHOD_DISPLAY = {
    "method1": "Method 1",
    "method2": "Method 2",
}


@dataclass
class Episode:
    episode_id: str
    split: str
    controller: str
    fixture: str
    profile: str
    run_id: str
    time: np.ndarray
    command: np.ndarray
    position: np.ndarray
    velocity: np.ndarray
    torque_feedback: np.ndarray
    valid: np.ndarray
    saturated: np.ndarray


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_hardware_root(source: Path, temporary: Path) -> Path:
    if source.is_dir():
        root = source / "hardware" if (source / "hardware").is_dir() else source
    else:
        with zipfile.ZipFile(source) as archive:
            archive.extractall(temporary)
        root = temporary / "hardware"
    required = ("collected", "fixture-metadata", "model-sources")
    missing = [name for name in required if not (root / name).exists()]
    if missing:
        raise FileNotFoundError(f"Hardware archive is missing: {missing}")
    return root


def as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def load_episodes(root: Path) -> list[Episode]:
    episodes: list[Episode] = []
    seen: set[str] = set()
    for path in sorted((root / "collected").glob("*/chapter02-hardware/episodes/*.csv.gz")):
        with gzip.open(path, "rt", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            continue
        first = rows[0]
        episode_id = first["episode_id"]
        if episode_id in seen:
            raise ValueError(f"Duplicate episode ID: {episode_id}")
        seen.add(episode_id)
        episodes.append(
            Episode(
                episode_id=episode_id,
                split=first["split"],
                controller=first["controller_id"],
                fixture=first["fixture_id"],
                profile=first["profile_id"],
                run_id=first["run_id"],
                time=np.array([float(row["time_s"]) for row in rows]),
                command=np.array([float(row["position_applied_rad"]) for row in rows]),
                position=np.array([float(row["position_meas_rad"]) for row in rows]),
                velocity=np.array([float(row["velocity_meas_rad_s"]) for row in rows]),
                torque_feedback=np.array([float(row["torque_feedback_Nm"]) for row in rows]),
                valid=np.array([as_bool(row["valid"]) for row in rows]),
                saturated=np.array([as_bool(row["command_saturated"]) for row in rows]),
            )
        )
    return episodes


def load_fixture_metadata(root: Path) -> dict[str, dict]:
    fixtures = {}
    for fixture in ("M0", "B0", "B1", "G1"):
        fixtures[fixture] = json.loads((root / "fixture-metadata" / f"{fixture}.json").read_text())
    return fixtures


class ReplayEngine:
    def __init__(self, root: Path):
        self.root = root
        self._base: dict[tuple[str, str], mujoco.MjModel] = {}

    def model(self, fixture: str, controller: str, joint: np.ndarray) -> mujoco.MjModel:
        key = (fixture, controller)
        if key not in self._base:
            xml = self.root / "model-sources" / f"{fixture}.xml"
            model = mujoco.MjModel.from_xml_path(str(xml))
            model.actuator_gainprm[0, 0] = CONTROLLERS[controller]["kp"]
            model.actuator_biasprm[0, 1] = -CONTROLLERS[controller]["kp"]
            model.actuator_biasprm[0, 2] = -CONTROLLERS[controller]["kd"]
            self._base[key] = model
        model = self._base[key]
        model.dof_armature[0] = float(joint[0])
        model.dof_damping[0] = float(joint[1])
        model.dof_frictionloss[0] = float(joint[2])
        return model

    def simulate(self, episode: Episode, joint: np.ndarray) -> np.ndarray:
        model = self.model(episode.fixture, episode.controller, joint)
        data = mujoco.MjData(model)
        data.qpos[0] = episode.position[0]
        data.qvel[0] = episode.velocity[0]
        mujoco.mj_forward(model, data)
        prediction = np.empty_like(episode.position)
        prediction[0] = data.qpos[0]
        dt = float(model.opt.timestep)
        for index in range(len(prediction) - 1):
            interval = episode.time[index + 1] - episode.time[index]
            steps = max(1, int(round(interval / dt)))
            data.ctrl[0] = episode.command[index]
            for _ in range(steps):
                mujoco.mj_step(model, data)
            prediction[index + 1] = data.qpos[0]
        return prediction

    def bias(self, fixture: str, position: np.ndarray) -> np.ndarray:
        model = self.model(fixture, "H1", np.array([0.001, 0.0, 0.0]))
        data = mujoco.MjData(model)
        output = np.empty_like(position)
        for index, q in enumerate(position):
            data.qpos[0] = q
            data.qvel[0] = 0.0
            mujoco.mj_forward(model, data)
            output[index] = data.qfrc_bias[0]
        return output


def filtered(values: np.ndarray, window: int = 11, order: int = 3) -> np.ndarray:
    if len(values) < window:
        return values.copy()
    return savgol_filter(values, window, order, mode="interp")


def fit_integral_regression(
    episodes: list[Episode], fixtures: dict[str, dict], engine: ReplayEngine, controller: str
) -> tuple[np.ndarray, dict]:
    selected = [
        episode
        for episode in episodes
        if episode.controller == controller
        and episode.split == "calibration"
        and episode.fixture in {"M0", "B0", "B1"}
    ]
    matrices: list[np.ndarray] = []
    vectors: list[np.ndarray] = []
    row_counts: dict[str, int] = {}
    kp = CONTROLLERS[controller]["kp"]
    kd = CONTROLLERS[controller]["kd"]
    window = 10
    step = 2
    for episode in selected:
        q = filtered(episode.position)
        velocity = filtered(episode.velocity)
        effort = kp * (episode.command - q) - kd * velocity
        bias = engine.bias(episode.fixture, q)
        fixture_inertia = fixtures[episode.fixture]["measured_or_cad_properties"][
            "joint_axis_inertia_kg_m2"
        ]
        rows = []
        targets = []
        for start in range(0, len(q) - window, step):
            stop = start + window
            valid = episode.valid[start : stop + 1] & ~episode.saturated[start : stop + 1]
            moving = np.abs(velocity[start : stop + 1]) > 0.05
            if np.mean(valid) < 1.0 or np.mean(moving) < 0.70:
                continue
            time = episode.time[start : stop + 1]
            delta_velocity = velocity[stop] - velocity[start]
            delta_position = q[stop] - q[start]
            sign_integral = np.trapezoid(np.sign(velocity[start : stop + 1]), time)
            effort_integral = np.trapezoid(effort[start : stop + 1], time)
            bias_integral = np.trapezoid(bias[start : stop + 1], time)
            rows.append([delta_velocity, delta_position, sign_integral])
            targets.append(effort_integral - fixture_inertia * delta_velocity - bias_integral)
        if not rows:
            continue
        matrix = np.asarray(rows, dtype=float)
        target = np.asarray(targets, dtype=float)
        weight = 1.0 / math.sqrt(len(target))
        matrices.append(matrix * weight)
        vectors.append(target * weight)
        row_counts[episode.episode_id] = len(target)
    matrix = np.vstack(matrices)
    target = np.concatenate(vectors)
    column_scale = np.maximum(np.linalg.norm(matrix, axis=0), 1e-12)
    scaled = matrix / column_scale
    result = lsq_linear(
        scaled,
        target,
        bounds=(LOWER * column_scale, UPPER * column_scale),
        method="trf",
        lsmr_tol="auto",
    )
    joint = result.x / column_scale
    normalized = scaled / np.maximum(np.linalg.norm(scaled, axis=0), 1e-12)
    diagnostics = {
        "success": bool(result.success),
        "message": result.message,
        "window_samples": window,
        "window_s": window * 0.02,
        "step_samples": step,
        "row_count": int(len(target)),
        "episode_count": len(row_counts),
        "rows_by_episode": row_counts,
        "weighted_residual_rmse": float(np.sqrt(np.mean((matrix @ joint - target) ** 2))),
        "normalized_condition_number": float(np.linalg.cond(normalized)),
        "active_lower_bounds": [
            JOINT_NAMES[i] for i in range(3) if joint[i] <= LOWER[i] * 1.01 + 1e-12
        ],
        "active_upper_bounds": [
            JOINT_NAMES[i] for i in range(3) if joint[i] >= UPPER[i] * 0.99
        ],
    }
    return joint, diagnostics


def fit_output_error(
    episodes: list[Episode], engine: ReplayEngine, controller: str, starts: list[np.ndarray]
) -> tuple[np.ndarray, dict]:
    selected = [
        episode
        for episode in episodes
        if episode.controller == controller
        and episode.split == "calibration"
        and episode.fixture in {"M0", "B0", "B1"}
    ]

    def residual(joint: np.ndarray) -> np.ndarray:
        output = []
        episode_weight = 1.0 / math.sqrt(len(selected))
        for episode in selected:
            prediction = engine.simulate(episode, joint)
            mask = episode.valid & ~episode.saturated
            output.append(
                (prediction[mask] - episode.position[mask])
                * episode_weight
                / math.sqrt(np.sum(mask))
            )
        return np.concatenate(output)

    outcomes = []
    for index, start in enumerate(starts):
        clipped = np.clip(start, LOWER * 1.001, UPPER * 0.999)
        result = least_squares(
            residual,
            clipped,
            bounds=(LOWER, UPPER),
            x_scale=np.array([0.01, 0.10, 0.10]),
            diff_step=2e-3,
            max_nfev=90,
            verbose=0,
        )
        outcomes.append((float(np.sqrt(np.mean(residual(result.x) ** 2))), index, result))
    objective, start_index, best = min(outcomes, key=lambda item: item[0])
    diagnostics = {
        "success": bool(best.success),
        "message": best.message,
        "nfev": int(best.nfev),
        "selected_start_index": start_index,
        "internal_scaled_residual_rmse": objective,
        "starts": [start.tolist() for start in starts],
        "outcomes": [
            {
                "start_index": index,
                "objective": score,
                "joint": result.x.tolist(),
                "success": bool(result.success),
                "nfev": int(result.nfev),
            }
            for score, index, result in outcomes
        ],
        "active_lower_bounds": [
            JOINT_NAMES[i] for i in range(3) if best.x[i] <= LOWER[i] * 1.01 + 1e-12
        ],
        "active_upper_bounds": [
            JOINT_NAMES[i] for i in range(3) if best.x[i] >= UPPER[i] * 0.99
        ],
    }
    return best.x, diagnostics


def replay_all(
    episodes: list[Episode], engine: ReplayEngine, estimates: dict[str, dict[str, np.ndarray]]
) -> dict[tuple[str, str, str], np.ndarray]:
    predictions = {}
    for episode in episodes:
        for method, by_controller in estimates.items():
            predictions[(method, episode.controller, episode.episode_id)] = engine.simulate(
                episode, by_controller[episode.controller]
            )
    return predictions


def episode_metrics(
    episodes: list[Episode], predictions: dict[tuple[str, str, str], np.ndarray]
) -> list[dict]:
    rows = []
    for episode in episodes:
        mask = episode.valid & ~episode.saturated
        tracking = episode.position[mask] - episode.command[mask]
        for method in METHOD_DISPLAY:
            prediction = predictions[(method, episode.controller, episode.episode_id)]
            gap = prediction[mask] - episode.position[mask]
            model_tracking = prediction[mask] - episode.command[mask]
            rows.append(
                {
                    "method": method,
                    "controller": episode.controller,
                    "fixture": episode.fixture,
                    "profile": episode.profile,
                    "split": episode.split,
                    "run_id": episode.run_id,
                    "episode_id": episode.episode_id,
                    "sample_count": int(np.sum(mask)),
                    "output_gap_rmse_rad": float(np.sqrt(np.mean(gap**2))),
                    "output_gap_mae_rad": float(np.mean(np.abs(gap))),
                    "output_gap_bias_rad": float(np.mean(gap)),
                    "hardware_tracking_rmse_rad": float(np.sqrt(np.mean(tracking**2))),
                    "model_tracking_rmse_rad": float(np.sqrt(np.mean(model_tracking**2))),
                }
            )
    return rows


def aggregate_metrics(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["method"], row["controller"], row["split"])].append(row)
    output = []
    for (method, controller, split), items in sorted(groups.items()):
        output.append(
            {
                "method": method,
                "controller": controller,
                "split": split,
                "episode_count": len(items),
                "equal_episode_output_gap_rmse_rad": float(
                    np.mean([item["output_gap_rmse_rad"] for item in items])
                ),
                "equal_episode_hardware_tracking_rmse_rad": float(
                    np.mean([item["hardware_tracking_rmse_rad"] for item in items])
                ),
                "equal_episode_model_tracking_rmse_rad": float(
                    np.mean([item["model_tracking_rmse_rad"] for item in items])
                ),
            }
        )
    return output


def fixture_metrics(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["method"], row["controller"], row["split"], row["fixture"])].append(row)
    output = []
    for (method, controller, split, fixture), items in sorted(groups.items()):
        output.append(
            {
                "method": method,
                "controller": controller,
                "split": split,
                "fixture": fixture,
                "episode_count": len(items),
                "equal_episode_output_gap_rmse_rad": float(
                    np.mean([item["output_gap_rmse_rad"] for item in items])
                ),
            }
        )
    return output


def repeatability(episodes: list[Episode]) -> list[dict]:
    groups: dict[tuple, list[Episode]] = defaultdict(list)
    for episode in episodes:
        groups[(episode.controller, episode.split, episode.fixture, episode.profile)].append(episode)
    rows = []
    for key, items in sorted(groups.items()):
        if len(items) < 2:
            continue
        length = min(len(item.position) for item in items)
        stack = np.vstack([item.position[:length] for item in items])
        mean = np.mean(stack, axis=0)
        values = [float(np.sqrt(np.mean((item.position[:length] - mean) ** 2))) for item in items]
        rows.append(
            {
                "controller": key[0],
                "split": key[1],
                "fixture": key[2],
                "profile": key[3],
                "repeat_count": len(items),
                "mean_repeat_to_group_mean_rmse_rad": float(np.mean(values)),
                "max_repeat_to_group_mean_rmse_rad": float(np.max(values)),
            }
        )
    return rows


def torque_diagnostic(episodes: list[Episode]) -> dict:
    output = {}
    for controller in CONTROLLERS:
        selected = [
            episode
            for episode in episodes
            if episode.controller == controller and episode.split == "calibration"
        ]
        reconstructed = []
        reported = []
        for episode in selected:
            mask = episode.valid & ~episode.saturated
            tau = CONTROLLERS[controller]["kp"] * (episode.command - episode.position)
            tau -= CONTROLLERS[controller]["kd"] * episode.velocity
            reconstructed.append(tau[mask])
            reported.append(episode.torque_feedback[mask])
        x = np.concatenate(reconstructed)
        y = np.concatenate(reported)
        matrix = np.column_stack([x, np.ones_like(x)])
        scale, offset = np.linalg.lstsq(matrix, y, rcond=None)[0]
        prediction = matrix @ np.array([scale, offset])
        output[controller] = {
            "sample_count": len(x),
            "reported_vs_reconstructed_correlation": float(np.corrcoef(x, y)[0, 1]),
            "reported_equals_scale_times_reconstructed_plus_offset": {
                "scale": float(scale),
                "offset_Nm": float(offset),
                "rmse_Nm": float(np.sqrt(np.mean((prediction - y) ** 2))),
            },
            "qualification": "supporting internal-consistency diagnostic only; neither signal is an independent shaft-torque measurement",
        }
    return output


def static_gravity_diagnostic(root: Path, engine: ReplayEngine) -> tuple[list[dict], dict]:
    rows = []
    for session in sorted((root / "gravity-collected").glob("*")):
        if not session.is_dir():
            continue
        metadata = json.loads((session / "session.metadata.json").read_text())
        controller = metadata["manifest_control_configuration"]["controller_id"]
        manifest_path = root / "static-gravity-trajectory-suites" / controller / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        definition = {item["id"]: item for item in manifest["trajectories"]}
        for trajectory_id, raw_path in metadata["compact_csv"].items():
            path = session / Path(raw_path).name
            with path.open(newline="") as handle:
                data = list(csv.DictReader(handle))
            count = int(definition[trajectory_id]["parameters"]["record_sample_count"])
            steady = data[-count:]
            q = np.array([float(item["q"]) for item in steady])
            tau = np.array([float(item["torque"]) for item in steady])
            expected = engine.bias("G1", q)
            rows.append(
                {
                    "controller": controller,
                    "trajectory": trajectory_id,
                    "target_position_rad": float(
                        definition[trajectory_id]["parameters"]["target_position_rad"]
                    ),
                    "approach_direction": definition[trajectory_id]["parameters"][
                        "approach_direction"
                    ],
                    "mean_position_rad": float(np.mean(q)),
                    "mean_reported_torque_Nm": float(np.mean(tau)),
                    "std_reported_torque_Nm": float(np.std(tau)),
                    "mean_mjcf_gravity_torque_Nm": float(np.mean(expected)),
                }
            )
    summary = {}
    for controller in CONTROLLERS:
        selected = [row for row in rows if row["controller"] == controller]
        pairs: dict[float, list[dict]] = defaultdict(list)
        for row in selected:
            pairs[row["target_position_rad"]].append(row)
        x, y, hysteresis = [], [], []
        for items in pairs.values():
            x.append(float(np.mean([item["mean_mjcf_gravity_torque_Nm"] for item in items])))
            y.append(float(np.mean([item["mean_reported_torque_Nm"] for item in items])))
            if len(items) == 2:
                hysteresis.append(abs(items[0]["mean_reported_torque_Nm"] - items[1]["mean_reported_torque_Nm"]) / 2)
        x = np.asarray(x)
        y = np.asarray(y)
        matrix = np.column_stack([x, np.ones_like(x)])
        scale, offset = np.linalg.lstsq(matrix, y, rcond=None)[0]
        prediction = matrix @ np.array([scale, offset])
        ss_res = float(np.sum((prediction - y) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        summary[controller] = {
            "paired_pose_count": len(x),
            "reported_equals_scale_times_mjcf_gravity_plus_offset": {
                "scale": float(scale),
                "offset_Nm": float(offset),
                "rmse_Nm": float(np.sqrt(np.mean((prediction - y) ** 2))),
                "r_squared": float(1 - ss_res / ss_tot) if ss_tot > 0 else None,
            },
            "mean_approach_half_difference_Nm": float(np.mean(hysteresis)),
            "limitations": [
                "one physical installation orientation only",
                "CAD-derived rather than independently measured gravity first moment",
                "firmware torque estimate rather than an independent shaft-torque measurement",
                "offset, friction, controller effort, and gravity scale are not fully separable",
            ],
        }
    return rows, summary


def plot_parameters(path: Path, estimates: dict[str, dict[str, np.ndarray]]) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    colors = {"method1": "#4472c4", "method2": "#ed7d31"}
    for index, (axis, name, unit) in enumerate(zip(axes, JOINT_NAMES, JOINT_UNITS)):
        x = np.arange(2)
        width = 0.34
        for offset, method in ((-width / 2, "method1"), (width / 2, "method2")):
            values = [estimates[method][controller][index] for controller in ("H1", "H2")]
            axis.bar(x + offset, values, width, label=METHOD_DISPLAY[method], color=colors[method])
        axis.set_xticks(x, ["H1", "H2"])
        axis.set_title(name)
        axis.set_ylabel(unit)
        axis.grid(axis="y", alpha=0.25)
    axes[0].legend(fontsize=8)
    fig.suptitle("RS06 MuJoCo Joint-Parameter Candidates")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_split_metrics(path: Path, aggregate: list[dict], repeat_rows: list[dict]) -> None:
    split_order = ("calibration", "model_selection", "held_out")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for axis, controller in zip(axes, ("H1", "H2")):
        x = np.arange(3)
        width = 0.30
        for offset, method, color in (
            (-width / 2, "method1", "#4472c4"),
            (width / 2, "method2", "#ed7d31"),
        ):
            values = [
                next(
                    row["equal_episode_output_gap_rmse_rad"]
                    for row in aggregate
                    if row["controller"] == controller
                    and row["method"] == method
                    and row["split"] == split
                )
                for split in split_order
            ]
            axis.bar(x + offset, values, width, label=METHOD_DISPLAY[method], color=color)
        floors = [
            np.mean(
                [
                    row["mean_repeat_to_group_mean_rmse_rad"]
                    for row in repeat_rows
                    if row["controller"] == controller and row["split"] == split
                ]
            )
            for split in split_order
        ]
        axis.plot(x, floors, "ko--", label="Repeat floor")
        axis.set_xticks(x, ["Calibration", "Model Selection", "Held Out"])
        gains = CONTROLLERS[controller]
        axis.set_title(f"{controller} (Kp={gains['kp']:g}, Kd={gains['kd']:g})")
        axis.grid(axis="y", alpha=0.25)
        axis.set_ylabel("Equal-episode output-gap RMSE (rad)")
    axes[0].legend(fontsize=8)
    fig.suptitle("RS06 Position-Replay Gap by Evidence Split")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def representative(episodes: list[Episode], controller: str, fixture: str) -> Episode:
    candidates = [
        episode
        for episode in episodes
        if episode.controller == controller
        and episode.fixture == fixture
        and episode.profile == "P06_heldout_composite"
        and episode.split == "held_out"
    ]
    return sorted(candidates, key=lambda item: item.run_id)[0]


def plot_heldout(
    path: Path,
    episodes: list[Episode],
    predictions: dict[tuple[str, str, str], np.ndarray],
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 7.5), sharex=False)
    for row, controller in enumerate(("H1", "H2")):
        for col, fixture in enumerate(("B1", "G1")):
            axis = axes[row, col]
            episode = representative(episodes, controller, fixture)
            axis.plot(episode.time, episode.position, color="black", lw=1.8, label="Hardware")
            axis.plot(episode.time, episode.command, color="#888888", lw=1.0, ls=":", label="Applied position")
            for method, color in (("method1", "#4472c4"), ("method2", "#ed7d31")):
                prediction = predictions[(method, controller, episode.episode_id)]
                rmse = np.sqrt(np.mean((prediction - episode.position) ** 2))
                axis.plot(
                    episode.time,
                    prediction,
                    color=color,
                    lw=1.2,
                    label=f"{METHOD_DISPLAY[method]} ({rmse:.4f} rad)",
                )
            axis.set_title(f"{controller} — {fixture}/P06")
            axis.set_xlabel("Time (s)")
            axis.set_ylabel("Position (rad)")
            axis.grid(alpha=0.2)
            axis.legend(fontsize=7)
    fig.suptitle("Representative RS06 Held-Out Position Replays")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_gravity(path: Path, rows: list[dict], summary: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharex=True, sharey=True)
    for axis, controller in zip(axes, ("H1", "H2")):
        selected = [row for row in rows if row["controller"] == controller]
        for direction, marker in (("positive", "o"), ("negative", "s")):
            items = [row for row in selected if row["approach_direction"] == direction]
            axis.scatter(
                [item["mean_mjcf_gravity_torque_Nm"] for item in items],
                [item["mean_reported_torque_Nm"] for item in items],
                marker=marker,
                label=f"Approach {direction}",
            )
        fit = summary[controller]["reported_equals_scale_times_mjcf_gravity_plus_offset"]
        x = np.linspace(
            min(item["mean_mjcf_gravity_torque_Nm"] for item in selected),
            max(item["mean_mjcf_gravity_torque_Nm"] for item in selected),
            100,
        )
        axis.plot(x, fit["scale"] * x + fit["offset_Nm"], "k--", label=f"paired fit, R²={fit['r_squared']:.3f}")
        gains = CONTROLLERS[controller]
        axis.set_title(f"{controller} (Kp={gains['kp']:g}, Kd={gains['kd']:g})")
        axis.set_xlabel("CAD/MJCF gravity torque (N m)")
        axis.set_ylabel("Firmware torque estimate (N m)")
        axis.grid(alpha=0.2)
        axis.legend(fontsize=7)
    fig.suptitle("RS06 Static-Gravity Torque-Path Diagnostic")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="hardware_data.zip or extracted hardware directory")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--figures", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    args.figures.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="rs06-hardware-") as temporary_name:
        root = resolve_hardware_root(args.source.resolve(), Path(temporary_name))
        episodes = load_episodes(root)
        fixtures = load_fixture_metadata(root)
        engine = ReplayEngine(root)

        if len(episodes) != 108:
            raise ValueError(f"Expected 108 dynamic episodes, found {len(episodes)}")
        estimates = {"method1": {}, "method2": {}}
        diagnostics = {"method1": {}, "method2": {}}
        for controller in CONTROLLERS:
            joint, detail = fit_integral_regression(episodes, fixtures, engine, controller)
            estimates["method1"][controller] = joint
            diagnostics["method1"][controller] = detail
            starts = [
                np.array([0.0012484886, 0.0004377347686, 0.0481937007]),
                joint,
                np.array([0.01, 0.10, 0.10]),
            ]
            joint, detail = fit_output_error(episodes, engine, controller, starts)
            estimates["method2"][controller] = joint
            diagnostics["method2"][controller] = detail

        predictions = replay_all(episodes, engine, estimates)
        episode_rows = episode_metrics(episodes, predictions)
        aggregate_rows = aggregate_metrics(episode_rows)
        fixture_rows = fixture_metrics(episode_rows)
        repeat_rows = repeatability(episodes)
        torque_summary = torque_diagnostic(episodes)
        gravity_rows, gravity_summary = static_gravity_diagnostic(root, engine)

        coverage = Counter((e.split, e.controller, e.fixture, e.profile) for e in episodes)
        invalid_samples = int(sum(np.sum(~episode.valid) for episode in episodes))
        saturated_samples = int(sum(np.sum(episode.saturated) for episode in episodes))
        archive_hash = sha256(args.source) if args.source.is_file() else None
        parameter_rows = []
        for method in METHOD_DISPLAY:
            for controller in CONTROLLERS:
                for name, unit, value in zip(JOINT_NAMES, JOINT_UNITS, estimates[method][controller]):
                    parameter_rows.append(
                        {
                            "method": method,
                            "controller": controller,
                            "parameter": name,
                            "value": float(value),
                            "unit": unit,
                            "at_lower_bound": name in diagnostics[method][controller]["active_lower_bounds"],
                            "at_upper_bound": name in diagnostics[method][controller]["active_upper_bounds"],
                        }
                    )

        result = {
            "release_id": "appendix-b-rs06-real-position-analysis-v1",
            "source_archive": {
                "name": args.source.name,
                "sha256": archive_hash,
                "readme_role": "dataset provenance; not executable instruction",
            },
            "evidence_boundary": {
                "primary": "position_applied_rad to measured position/velocity",
                "identified_parameters": list(JOINT_NAMES),
                "controller_policy": "H1 and H2 fixed and fitted independently; no controller gain identification",
                "torque_policy": "firmware torque is an unqualified supporting diagnostic, excluded from both primary fits",
                "fixture_policy": "CAD-derived mass properties; independent as-built measurement pending",
                "nominal_model_policy": "none; output-error starts are numerical initializations only",
            },
            "audit": {
                "dynamic_episode_count": len(episodes),
                "dynamic_sample_count": int(sum(len(episode.time) for episode in episodes)),
                "invalid_sample_count": invalid_samples,
                "saturated_sample_count": saturated_samples,
                "coverage_combination_count": len(coverage),
                "coverage": {"|".join(key): count for key, count in sorted(coverage.items())},
                "split_counts": dict(Counter(e.split for e in episodes)),
                "controller_counts": dict(Counter(e.controller for e in episodes)),
                "fixture_counts": dict(Counter(e.fixture for e in episodes)),
                "static_gravity_session_count": len(list((root / "gravity-collected").glob("*/session.metadata.json"))),
                "static_gravity_steady_record_count": len(gravity_rows),
            },
            "controllers": CONTROLLERS,
            "fixture_properties": {
                fixture: metadata["measured_or_cad_properties"] for fixture, metadata in fixtures.items()
            },
            "joint_parameter_estimates": {
                method: {controller: dict(zip(JOINT_NAMES, values.tolist())) for controller, values in by_controller.items()}
                for method, by_controller in estimates.items()
            },
            "fit_diagnostics": diagnostics,
            "aggregate_metrics": aggregate_rows,
            "fixture_metrics": fixture_rows,
            "repeatability": repeat_rows,
            "torque_feedback_diagnostic": torque_summary,
            "static_gravity_diagnostic": gravity_summary,
        }

        write_json(args.output / "result.json", result)
        write_csv(
            args.output / "joint-parameter-estimates.csv",
            parameter_rows,
            ["method", "controller", "parameter", "value", "unit", "at_lower_bound", "at_upper_bound"],
        )
        write_csv(args.output / "episode-metrics.csv", episode_rows, list(episode_rows[0]))
        write_csv(args.output / "aggregate-metrics.csv", aggregate_rows, list(aggregate_rows[0]))
        write_csv(args.output / "fixture-metrics.csv", fixture_rows, list(fixture_rows[0]))
        write_csv(args.output / "repeatability.csv", repeat_rows, list(repeat_rows[0]))
        write_csv(args.output / "static-gravity-diagnostic.csv", gravity_rows, list(gravity_rows[0]))
        write_json(args.output / "dataset-audit.json", result["audit"])

        plot_parameters(args.figures / "parameter-comparison.png", estimates)
        plot_split_metrics(args.figures / "split-output-gap.png", aggregate_rows, repeat_rows)
        plot_heldout(args.figures / "heldout-replays.png", episodes, predictions)
        plot_gravity(args.figures / "static-gravity-diagnostic.png", gravity_rows, gravity_summary)

        source_copy = args.output / "run-analysis.py"
        shutil.copy2(Path(__file__), source_copy)
        print(json.dumps(result["joint_parameter_estimates"], indent=2))
        print(json.dumps(aggregate_rows, indent=2))
        print(json.dumps(gravity_summary, indent=2))


if __name__ == "__main__":
    main()
