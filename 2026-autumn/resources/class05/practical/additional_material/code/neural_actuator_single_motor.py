#!/usr/bin/env python3
"""Train and evaluate NeuralActuator on one XC330 lever.

This is a single-joint adaptation of NeuralActuator's torque-surrogate path.
It uses a Transformer over a causal history of Dynamixel command and telemetry,
then optimizes the predicted torque through an MJX rollout.  It intentionally
does not include the paper's force and motor-condition heads: the single-motor
system-identification data has no external-force or condition labels.
"""

import argparse
import json
import math
import os
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

import jax
import jax.numpy as jnp
import mujoco
from mujoco import mjx
import optax
import flax.linen as nn


RAD_PER_DEG = math.pi / 180.0
DEFAULT_CSV = REPO / "Dynamixel_Motors/data/sysid/batch_20260720_142525_b1_id0to7_real/servo_id_id0_trajectories.csv"
DEFAULT_XML = REPO / "sim2real_sysid/models/XC330withLever.xml"
FEATURE_NAMES = ("goal_rad", "q_rad", "qdot_rad_s", "current_mA",
                 "pwm", "voltage_V", "temperature_C", "position_error_rad")


class SingleMotorTransformer(nn.Module):
    hidden_dim: int = 64
    num_heads: int = 4
    num_layers: int = 2
    d_ff: int = 128

    @nn.compact
    def __call__(self, history, current):
        # history: batch x history_length x feature_dim; current: batch x feature_dim
        x = jnp.concatenate((history, current[:, None, :]), axis=1)
        x = nn.Dense(self.hidden_dim)(x)
        positions = self.param("positions", nn.initializers.normal(0.02),
                               (1, x.shape[1], self.hidden_dim))
        x = x + positions
        for _ in range(self.num_layers):
            residual = x
            x = nn.LayerNorm()(x)
            x = nn.MultiHeadDotProductAttention(num_heads=self.num_heads)(x, x)
            x = residual + x
            residual = x
            x = nn.LayerNorm()(x)
            x = nn.Dense(self.d_ff)(x)
            x = nn.gelu(x)
            x = nn.Dense(self.hidden_dim)(x)
            x = residual + x
        x = nn.LayerNorm()(x)
        x = x[:, -1, :]
        x = nn.Dense(self.hidden_dim)(x)
        x = nn.silu(x)
        # tanh keeps torque inside the XC330's 0.93 N m rated range.
        return 0.93 * jnp.tanh(nn.Dense(1, kernel_init=nn.initializers.zeros)(x))[:, 0]


def load_trajectories(csv_paths, center_deg):
    """Read the physical sysid export and preserve trajectory boundaries."""
    if isinstance(csv_paths, (str, Path)):
        csv_paths = [csv_paths]
    df = pd.concat([pd.read_csv(path) for path in csv_paths], ignore_index=True)
    needed = {"trajectory_id", "host_time_s", "q_cmd_rad", "q_rad",
              "qdot_rad_s", "present_current_mA", "present_pwm_raw",
              "present_input_voltage_V", "present_temperature_C"}
    missing = sorted(needed - set(df.columns))
    if missing:
        raise ValueError(f"servo_id export is missing {missing}")

    center_rad = center_deg * RAD_PER_DEG
    trajectories = []
    for trajectory_id, group in df.groupby("trajectory_id", sort=True):
        group = group.sort_values("sample_idx" if "sample_idx" in group else "host_time_s")
        group = group.drop_duplicates("host_time_s")
        if len(group) < 20:
            continue
        time_s = group.host_time_s.to_numpy(dtype=np.float64)
        dt = float(np.median(np.diff(time_s)))
        if not np.isfinite(dt) or dt <= 0:
            continue
        goal = group.q_cmd_rad.to_numpy(dtype=np.float32) + center_rad
        q = group.q_rad.to_numpy(dtype=np.float32) + center_rad
        qdot = group.qdot_rad_s.to_numpy(dtype=np.float32)
        current = group.present_current_mA.to_numpy(dtype=np.float32)
        pwm = group.present_pwm_raw.to_numpy(dtype=np.float32)
        voltage = group.present_input_voltage_V.to_numpy(dtype=np.float32)
        temp = group.present_temperature_C.to_numpy(dtype=np.float32)
        features = np.column_stack((goal, q, qdot, current, pwm, voltage, temp, goal - q))
        finite = np.isfinite(features).all(axis=1)
        features = features[finite]
        if len(features) >= 20:
            trajectories.append({"id": str(trajectory_id), "dt": dt,
                                 "features": features.astype(np.float32)})
    if len(trajectories) < 3:
        raise ValueError("Need at least three valid trajectories for train/validation/test.")
    return trajectories


def split_trajectories(trajectories):
    """Hold out complete motions, avoiding leakage between train and test."""
    n = len(trajectories)
    n_test = max(1, round(n * 0.18))
    n_val = max(1, round(n * 0.18))
    train_end = max(1, n - n_val - n_test)
    return trajectories[:train_end], trajectories[train_end:train_end + n_val], trajectories[train_end + n_val:]


def load_mjx_model(xml_path, data_dt, substeps):
    model = mujoco.MjModel.from_xml_path(str(xml_path))
    position_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "position_baseline")
    torque_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "custom_servo_motor")
    if position_id < 0 or torque_id < 0 or model.nq != 1 or model.nv != 1:
        raise ValueError("XML must be the one-joint XC330 model with both position_baseline and custom_servo_motor.")
    # NeuralActuator supplies torque through custom_servo_motor. Disable the
    # conventional position servo so it cannot contribute an unmodelled torque.
    model.actuator_gainprm[position_id, :] = 0.0
    model.actuator_biasprm[position_id, :] = 0.0
    model.actuator_ctrlrange[torque_id] = np.array([-0.93, 0.93])
    model.opt.timestep = data_dt / substeps
    model.opt.solver = mujoco.mjtSolver.mjSOL_NEWTON
    model.opt.iterations = 1
    model.opt.ls_iterations = 0
    model.opt.tolerance = 0
    return model, mjx.put_model(model), torque_id


def normalize(features, mean, std):
    return (features - mean) / std


def make_rollout_functions(network, mjx_model, torque_id, substeps, history_length, mean, std):
    mean = jnp.asarray(mean)
    std = jnp.asarray(std)

    def loss_fn(params, window):
        # Window length is history + rollout + one initial-state frame. Keeping
        # this shape fixed is required by JAX's compiled rollout.
        initial = window[history_length]
        data = mjx.make_data(mjx_model).replace(
            qpos=jnp.array([initial[1]]), qvel=jnp.array([initial[2]])
        )
        history = normalize(window[:history_length], mean, std)

        def step(carry, raw):
            sim_data, hist = carry
            goal, _, _, current, pwm, voltage, temperature, _ = raw
            simulated_q = sim_data.qpos[0]
            simulated_v = sim_data.qvel[0]
            current_raw = jnp.array([goal, simulated_q, simulated_v, current, pwm,
                                     voltage, temperature, goal - simulated_q])
            current_norm = normalize(current_raw, mean, std)
            tau = network.apply(params, hist[None, ...], current_norm[None, ...])[0]
            ctrl = jnp.zeros(mjx_model.nu).at[torque_id].set(tau)
            sim_data = sim_data.replace(ctrl=ctrl)
            sim_data = jax.lax.fori_loop(0, substeps, lambda _, d: mjx.step(mjx_model, d), sim_data)
            # Keep exploratory early training rollouts inside the physical joint
            # envelope. These values are state safeguards, not learned dynamics.
            sim_data = sim_data.replace(
                qpos=jnp.clip(jnp.nan_to_num(sim_data.qpos), 0.0, 2.0 * jnp.pi),
                qvel=jnp.clip(jnp.nan_to_num(sim_data.qvel), -30.0, 30.0),
            )
            history = jnp.concatenate((hist[1:], current_norm[None, :]), axis=0)
            return (sim_data, history), (sim_data.qpos[0], tau)

        targets = window[history_length + 1:]
        (_, _), (predicted_q, torques) = jax.lax.scan(step, (data, history), targets)
        target_q = targets[:, 1]
        # Huber loss is robust to occasional serial telemetry spikes.
        error = predicted_q - target_q
        abs_error = jnp.abs(error)
        position_loss = jnp.mean(jnp.where(abs_error < 0.15, 0.5 * error**2 / 0.15,
                                           abs_error - 0.075))
        torque_regularizer = 1e-4 * jnp.mean(torques**2)
        return position_loss + torque_regularizer, (predicted_q, torques, target_q)

    def mean_batch_loss(params, windows):
        losses, _ = jax.vmap(lambda window: loss_fn(params, window))(windows)
        return jnp.mean(losses)

    def rollout_batch(params, windows):
        return jax.vmap(lambda window: loss_fn(params, window)[1])(windows)

    return jax.jit(jax.value_and_grad(mean_batch_loss)), jax.jit(rollout_batch)


def valid_starts(trajectory, history_length, rollout_steps):
    return np.arange(history_length, len(trajectory["features"]) - rollout_steps - 1)


def evaluate(network, params, mjx_model, torque_id, trajectories, history_length,
             rollout_steps, substeps, mean, std, batch_size):
    _, rollout_batch = make_rollout_functions(network, mjx_model, torque_id, substeps,
                                              history_length, mean, std)
    errors = []
    windows = []
    for trajectory in trajectories:
        features = trajectory["features"]
        starts = valid_starts(trajectory, history_length, rollout_steps)
        for start in starts[::rollout_steps]:
            windows.append(features[start - history_length:start + rollout_steps + 1])
    for offset in range(0, len(windows), batch_size):
        chunk = windows[offset:offset + batch_size]
        actual_size = len(chunk)
        if actual_size < batch_size:
            chunk += [chunk[-1]] * (batch_size - actual_size)
        predicted, _, target = rollout_batch(params, jnp.asarray(np.stack(chunk)))
        errors.append(np.abs(np.asarray(predicted[:actual_size] - target[:actual_size])).reshape(-1))
    error_rad = np.concatenate(errors) if errors else np.array([np.nan])
    return {"mae_deg": float(np.nanmean(error_rad) / RAD_PER_DEG),
            "rmse_deg": float(np.sqrt(np.nanmean(error_rad**2)) / RAD_PER_DEG),
            "n_rollout_samples": int(len(error_rad))}


def save_checkpoint(path, params, mean, std, args, data_dt, train_set, val_set, test_set):
    """Persist weights before a later validation or GPU failure can lose them."""
    with path.open("wb") as file:
        pickle.dump({"params": jax.device_get(params), "feature_mean": mean,
                     "feature_std": std, "history": args.history,
                     "substeps": args.substeps, "data_dt": data_dt,
                     "model": {"hidden_dim": args.hidden_dim, "num_heads": args.num_heads,
                               "num_layers": args.num_layers, "d_ff": args.d_ff},
                     "center_deg": args.center_deg,
                     "train_trajectories": [x["id"] for x in train_set],
                     "val_trajectories": [x["id"] for x in val_set],
                     "test_trajectories": [x["id"] for x in test_set]}, file)


def train(args):
    trajectories = load_trajectories(args.csv, args.center_deg)
    train_set, val_set, test_set = split_trajectories(trajectories)
    all_train = np.concatenate([x["features"] for x in train_set], axis=0)
    mean = all_train.mean(axis=0).astype(np.float32)
    std = np.maximum(all_train.std(axis=0), np.array([0.05, 0.05, 0.1, 10., 10., .1, 1., .05], dtype=np.float32))
    data_dt = float(np.median([x["dt"] for x in trajectories]))
    _, mjx_model, torque_id = load_mjx_model(args.xml, data_dt, args.substeps)
    network = SingleMotorTransformer(args.hidden_dim, args.num_heads, args.num_layers, args.d_ff)
    params = network.init(jax.random.PRNGKey(args.seed),
                          jnp.zeros((1, args.history, len(FEATURE_NAMES))),
                          jnp.zeros((1, len(FEATURE_NAMES))))
    optimizer = optax.chain(
        optax.clip_by_global_norm(args.grad_clip),
        optax.adamw(args.learning_rate, weight_decay=1e-5),
    )
    opt_state = optimizer.init(params)
    loss_and_grad, _ = make_rollout_functions(network, mjx_model, torque_id,
                                               args.substeps, args.history, mean, std)
    rng = np.random.default_rng(args.seed)
    candidates = [(trajectory, start) for trajectory in train_set
                  for start in valid_starts(trajectory, args.history, args.rollout)]
    if not candidates:
        raise ValueError("Trajectories are too short for selected history and rollout length.")
    best = (float("inf"), None)
    evaluations_without_improvement = 0
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    last_output = output.with_name(output.stem + "_last.pkl")
    print(f"Loaded {len(trajectories)} trajectories: train={len(train_set)}, val={len(val_set)}, test={len(test_set)}")
    print(f"Data dt={data_dt:.5f}s, feature_dim={len(FEATURE_NAMES)}, candidates={len(candidates)}")
    for step in range(1, args.steps + 1):
        choices = rng.integers(len(candidates), size=args.batch_size)
        windows = []
        for choice in choices:
            trajectory, start = candidates[choice]
            windows.append(trajectory["features"][start - args.history:start + args.rollout + 1])
        loss, grads = loss_and_grad(params, jnp.asarray(np.stack(windows)))
        updates, opt_state = optimizer.update(grads, opt_state, params)
        params = optax.apply_updates(params, updates)
        if step == 1 or step % args.log_every == 0 or step == args.steps:
            save_checkpoint(last_output, params, mean, std, args, data_dt,
                            train_set, val_set, test_set)
            try:
                metrics = evaluate(network, params, mjx_model, torque_id, val_set,
                                   args.history, args.rollout, args.substeps, mean, std,
                                   args.batch_size)
            except Exception as error:
                print(f"step={step:5d} train_loss={float(loss):.6f} validation failed: {error}")
                print(f"  Continuing; latest parameters saved to {last_output}")
                continue
            print(f"step={step:5d} train_loss={float(loss):.6f} val_mae={metrics['mae_deg']:.3f} deg")
            if metrics["mae_deg"] < best[0]:
                best = (metrics["mae_deg"], jax.device_get(params))
                save_checkpoint(output, params, mean, std, args, data_dt,
                                train_set, val_set, test_set)
                evaluations_without_improvement = 0
            else:
                evaluations_without_improvement += 1
                if evaluations_without_improvement >= args.early_stop_patience:
                    print(f"  Early stopping after {evaluations_without_improvement} validations without improvement.")
                    break
    if best[1] is None:
        raise RuntimeError("Validation failed every time; latest weights are in " + str(last_output))
    params = best[1]
    test_metrics = evaluate(network, params, mjx_model, torque_id, test_set,
                            args.history, args.rollout, args.substeps, mean, std,
                            args.batch_size)
    report = {"best_validation_mae_deg": best[0], "test": test_metrics,
              "checkpoint": str(output), "data_dt": data_dt,
              "splits": {"train": [x["id"] for x in train_set],
                         "validation": [x["id"] for x in val_set],
                         "test": [x["id"] for x in test_set]}}
    report_path = output.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(description="Single-XC330 NeuralActuator training")
    parser.add_argument("--csv", type=Path, nargs="+", default=[DEFAULT_CSV],
                        help="One or more physical servo_id trajectory CSVs")
    parser.add_argument("--xml", type=Path, default=DEFAULT_XML, help="Single-motor MuJoCo XML")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/xc330_single_motor_best.pkl")
    parser.add_argument("--center-deg", type=float, default=180.0)
    parser.add_argument("--steps", type=int, default=3000)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--history", type=int, default=8)
    parser.add_argument("--rollout", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--grad-clip", type=float, default=1.0,
                        help="Maximum global gradient norm")
    parser.add_argument("--early-stop-patience", type=int, default=5,
                        help="Stop after this many validation checks without improvement")
    parser.add_argument("--substeps", type=int, default=2)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--num-heads", type=int, default=4)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--d-ff", type=int, default=128)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--log-every", type=int, default=100)
    return parser


if __name__ == "__main__":
    train(build_parser().parse_args())
