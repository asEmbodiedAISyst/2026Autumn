# Original Playground reference evaluation

This experiment evaluates the supplied ONNX policy in the unmodified pinned `LeapCubeReorient` task, using MJX/Warp on the Linux GPU. It performs inference only.

## Run in ~/Downloads/Class06

Use a new Class06 folder in the Linux Downloads directory. Copy `Class06-Linux-v5.zip` into that Class06 folder, then run:

```sh
mkdir -p "$HOME/Downloads/Class06"
cd "$HOME/Downloads/Class06"
unzip -n Class06-Linux-v5.zip
bash linux_reference_eval.sh --reuse-venv "$HOME/Downloads/Class06-Playground-Reproduction/Class06-Playground-Reproduction/.venv-gpu"
```

The archive has flat package paths: the launcher is directly inside Class06. `unzip -n` preserves existing files; package verification detects a mixed or incomplete extraction rather than silently using it. Python 3.12, Git, unzip, flock and the existing NVIDIA driver are prerequisites. Set `CLASS06_PYTHON` only if the Python 3.12 executable has another path. The script never uses sudo or installs a driver/system package.

The recommended command reuses the previously verified virtual environment without installing into or modifying it. Core runtime versions must match; any mismatch stops instead of upgrading that environment. Inference dependencies are installed with `--target` into `.inference-deps` inside Class06. The package list before and after successful evaluation is compared. Python bytecode, pip/CUDA/JAX/Warp caches, pinned `upstream` source and runs remain inside Class06; the old course source is not modified.

Alternatively, run `bash linux_reference_eval.sh` without arguments to create and use a new `.venv-reference` entirely inside Class06. Existing unmarked local environment/source/overlay folders and symlinks are refused. A file lock prevents two launches from updating the same environment concurrently. Repeated runs use either the explicitly selected existing environment or the launcher's own marked environment, with its clean pinned source.

Core runtime versions are pinned in `requirements-gpu-reference.txt` and `constraints-gpu-reference.txt`; resolved dependencies are recorded in each run. Fresh mode installs only into the new virtual environment; reuse mode installs only into the separate inference overlay. The source and compiled physical-model arrays are verified before evaluating. MuJoCo/JAX/Warp use the GPU without preallocating all available GPU memory; no existing process is stopped.

This runs seeds 20000–20099 twice: ideal observations (noise 0) and original noise (noise 1). Both use 10 ms physics, 20 Hz control and the original 0.1 rad success threshold. GPU buffers are `njmax=512` and `naconmax=16384` for one world. Overflow warnings reject the run.

At completion or ordinary failure, the terminal prints an absolute `runs/reference-eval-…-Results.tar.gz` path. The archive contains configurations, logs, dependency versions, initial states and per-episode traces, with an exit-code receipt. A zero exit code is required for valid completed evaluation. The v4 launcher and policy completed this evaluation on 4 October 2026; v5 keeps the executable code unchanged and includes the returned results in the lesson. Ideal observations reached 58/100 first targets; original noisy observations reached 89/100. The noisy 89/100 condition exceeds the agreed 80% teaching baseline; the 58/100 ideal condition remains a useful diagnostic. Repeating these commands reproduces the same experiment, not a new training run.

## Compare with native physics

Use an isolated native environment:
```sh
.venv-demo/bin/python qualification.py --backend native-task --noise-level 0 --sim-dt .01 --seed 20000 --episodes 100 --output runs/native-ideal
.venv-demo/bin/python qualification.py --backend native-task --noise-level 1 --sim-dt .01 --seed 20000 --episodes 100 --output runs/native-noisy
.venv-demo/bin/python qualification.py --backend native-player --noise-level 0 --sim-dt .002 --seed 20000 --episodes 100 --output runs/native-player
.venv-demo/bin/python compare_qualification.py runs/native-noisy /path/to/returned/playground-noise-1 --output runs/backend-comparison.json
```

The comparison checks initial configurations, velocities, motor targets and target quaternions. Equal seed numbers alone do not establish equality across CPU/GPU random-number implementations. A mismatch means the comparison is distributional rather than a matched-trajectory experiment.

The native-player route reuses the supplied controller but applies the task's random reset distribution rather than the player's fixed home-keyframe reset. It is an explicitly identified diagnostic. It differs from native-task in physics timestep, sensor/control callback timing and previous-action history; their success rates alone cannot identify the cause.

## Qualification criterion

First-goal success means orientation error below 0.1 rad within 1000 control steps (50 s), before a fall. All declared seeds remain in the denominator. A timeout is an unresolved goal, not evidence by itself of mechanical wedging. Report success count, 95% Wilson interval, falls, timeouts and first-goal time. Repeated-goal reliability requires the separate continuous runner.

An observed rate of 80% is sufficient for the teaching baseline. This is not a population lower confidence bound or a hardware guarantee. Seeds 20000–20099 are the present qualification set. Once results inform tuning, use a new declared set for final qualification.

## Training decision

If performance differs between original Playground and native playback, resolve backend/interface differences first. If both fail qualification, use the upstream training pipeline and a controlled hyperparameter/capacity study. Preserve the task, reward and physics for the initial study. Equal transition counts do not reproduce PPO when environment counts, minibatches and update rates differ.

This ONNX artifact has no resumable optimizer checkpoint or complete training configuration. Do not pass it as a Brax resume checkpoint. Fine-tuning requires a compatible training checkpoint, or an explicitly evaluated policy-conversion/distillation step. No further training is launched by this package.
