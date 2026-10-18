#!/usr/bin/env python3
"""Compare XC330 real hardware with NeuralActuator and an optional kp/kv baseline."""

import argparse
import json
import pickle
from pathlib import Path

import jax.numpy as jnp
import matplotlib.pyplot as plt
import mujoco
import numpy as np

from neural_actuator_single_motor import (
    DEFAULT_CSV, DEFAULT_XML, RAD_PER_DEG, SingleMotorTransformer,
    load_mjx_model, load_trajectories,
)


def configure_parametric(model, config, data_dt):
    model.opt.timestep = float(config.get("sim_timestep", model.opt.timestep))
    position_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "position_baseline")
    joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "Revolute-4")
    model.actuator_gainprm[position_id, 0] = config["position_p_gain"]
    model.actuator_biasprm[position_id, 1] = -config["position_p_gain"]
    model.actuator_biasprm[position_id, 2] = -config["velocity_p_gain"]
    model.dof_damping[model.jnt_dofadr[joint_id]] = config["sim_damping"]
    model.dof_frictionloss[model.jnt_dofadr[joint_id]] = config["sim_frictionloss"]
    model.dof_armature[model.jnt_dofadr[joint_id]] = config["sim_armature"]
    force_range = config.get("sim_forcerange")
    if force_range is not None:
        model.actuator_forcerange[position_id] = np.asarray(force_range)
    return max(1, round(data_dt / model.opt.timestep))


def mae_deg(prediction, real):
    return float(np.mean(np.abs(prediction - real)) / RAD_PER_DEG)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--csv", type=Path, nargs="+", default=[DEFAULT_CSV])
    parser.add_argument("--xml", type=Path, default=DEFAULT_XML)
    parser.add_argument("--parametric-config", type=Path,
                        default=Path("../../../sim2real_sysid/data/batch_20260720_142525_b1_id0to7_sim_id0/config_id0.json"))
    parser.add_argument("--show-parametric", action="store_true",
                        help="Plot the tuned kp/kv MuJoCo baseline (default)")
    parser.add_argument("--hide-parametric", action="store_false", dest="show_parametric",
                        help="Hide the tuned kp/kv MuJoCo baseline")
    parser.set_defaults(show_parametric=True)
    parser.add_argument("--trajectory-id", help="Trajectory ID to compare (default: first test trajectory)")
    parser.add_argument("--output", type=Path, default=Path("outputs/xc330_neural_vs_parametric.png"))
    args = parser.parse_args()

    with args.checkpoint.open("rb") as file:
        checkpoint = pickle.load(file)
    trajectories = load_trajectories(args.csv, checkpoint["center_deg"])
    test_ids = checkpoint.get("test_trajectories", [])
    trajectory_id = args.trajectory_id or (test_ids[0] if test_ids else trajectories[-1]["id"])
    trajectory = next((item for item in trajectories if item["id"] == trajectory_id), None)
    if trajectory is None:
        raise ValueError(f"Trajectory {trajectory_id!r} is not in {args.csv}")
    model_cfg = checkpoint["model"]
    network = SingleMotorTransformer(**model_cfg)
    params = checkpoint["params"]
    mean = jnp.asarray(checkpoint["feature_mean"])
    std = jnp.asarray(checkpoint["feature_std"])
    history_length = checkpoint["history"]
    substeps = checkpoint["substeps"]
    features = trajectory["features"]
    data_dt = trajectory["dt"]

    param_model = None
    param_data = None
    parametric_substeps = None
    if args.show_parametric:
        with args.parametric_config.open() as file:
            parametric_config = json.load(file)
        param_model = mujoco.MjModel.from_xml_path(str(args.xml))
        parametric_substeps = configure_parametric(param_model, parametric_config, data_dt)
        param_data = mujoco.MjData(param_model)
        param_data.qpos[0], param_data.qvel[0] = features[0, 1], features[0, 2]
        mujoco.mj_forward(param_model, param_data)

    neural_model, _, torque_id = load_mjx_model(args.xml, data_dt, substeps)
    neural_data = mujoco.MjData(neural_model)
    neural_data.qpos[0], neural_data.qvel[0] = features[0, 1], features[0, 2]
    mujoco.mj_forward(neural_model, neural_data)
    # Seed history with the first measured frame; this is the causal padding used
    # at the beginning of a trajectory when no earlier telemetry exists.
    history = np.tile(np.asarray((jnp.asarray(features[0]) - mean) / std),
                      (history_length, 1))

    parametric = [param_data.qpos[0]] if param_data is not None else None
    neural = [neural_data.qpos[0]]
    torques = [0.0]
    for raw in features[1:]:
        if param_data is not None:
            param_data.ctrl[0] = raw[0]
            for _ in range(parametric_substeps):
                mujoco.mj_step(param_model, param_data)

        current = raw.copy()
        current[1] = neural_data.qpos[0]
        current[2] = neural_data.qvel[0]
        current[7] = current[0] - current[1]
        current_norm = (jnp.asarray(current) - mean) / std
        tau = float(network.apply(params, jnp.asarray(history[None, ...]), current_norm[None, ...])[0])
        neural_data.ctrl[torque_id] = tau
        for _ in range(substeps):
            mujoco.mj_step(neural_model, neural_data)
        neural_data.qpos[0] = np.clip(np.nan_to_num(neural_data.qpos[0]), 0.0, 2.0 * np.pi)
        neural_data.qvel[0] = np.clip(np.nan_to_num(neural_data.qvel[0]), -30.0, 30.0)
        history = np.concatenate((history[1:], np.asarray(current_norm)[None, :]), axis=0)
        if parametric is not None:
            parametric.append(param_data.qpos[0])
        neural.append(neural_data.qpos[0])
        torques.append(tau)

    time_s = np.arange(len(features)) * data_dt
    real = features[:, 1]
    goal = features[:, 0]
    parametric = np.asarray(parametric) if parametric is not None else None
    neural = np.asarray(neural)
    neural_error = mae_deg(neural, real)
    parametric_error = mae_deg(parametric, real) if parametric is not None else None
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    figure, (axis, torque_axis) = plt.subplots(2, 1, figsize=(13, 8), sharex=True,
                                                 gridspec_kw={"height_ratios": [3, 1]})
    axis.plot(time_s, goal / RAD_PER_DEG, "k--", linewidth=1.2,
              label="command target (input only)")
    axis.plot(time_s, real / RAD_PER_DEG, color="#2f7f5f", linewidth=2,
              label="real hardware encoder (ground truth)")
    if parametric is not None:
        axis.plot(time_s, parametric / RAD_PER_DEG, color="#d87932",
                  label=("tuned kp/kv MuJoCo simulation, not hardware "
                         f"(MAE vs hardware {parametric_error:.2f} deg)"))
    axis.plot(time_s, neural / RAD_PER_DEG, color="#4b6fa9",
              label=f"NeuralActuator MuJoCo simulation (MAE vs hardware {neural_error:.2f} deg)")
    axis.set_ylabel("position (deg)")
    axis.grid(alpha=.25)
    axis.legend(loc="best")
    torque_axis.plot(time_s, torques, color="#4b6fa9")
    torque_axis.set_xlabel("time (s)")
    torque_axis.set_ylabel("neural torque (N m)")
    torque_axis.grid(alpha=.25)
    figure.suptitle(
        f"XC330 comparison: {trajectory_id}\n"
        "Ground truth is the real hardware encoder; all MAE values are measured against it"
    )
    figure.tight_layout()
    figure.savefig(output, dpi=160)
    report = {
        "trajectory_id": trajectory_id,
        "ground_truth": "recorded real hardware encoder position",
        "neural_mae_deg": neural_error,
        "plot": str(output),
    }
    if parametric is not None:
        report.update({
            "parametric_mae_deg": parametric_error,
            "parametric_config": str(args.parametric_config),
            "parametric_timestep_s": float(param_model.opt.timestep),
            "parametric_substeps": parametric_substeps,
        })
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
