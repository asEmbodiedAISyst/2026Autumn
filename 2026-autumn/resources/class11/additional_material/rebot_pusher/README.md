# Class 11 — Practice

This folder holds the code of the practice. The steps below are the same as on the [practice page](../../../../module-03-arm-data-for-guided-interaction/11-practice.md), written for reading on GitHub or in an editor.

The required activity on this page reads saved ACT results and success/failure recordings for Push Cube, then writes a bounded claim. The class page [Class 11](../../../../module-03-arm-data-for-guided-interaction/11-sim2real-gap-in-hardware-deployment.md) explains the pipeline, evidence ladder and separate physical failure reports. Generation, training and a new simulation evaluation are optional extended practice, available only after the matching checkpoint/environment and run record are verified.

---

## Required saved-record activity

Use the retained [ACT simulation comparison and success/failure recordings](../../../../module-03-arm-data-for-guided-interaction/11-sim2real-gap-in-hardware-deployment.md#rung-5-in-simulation-act-on-push-cube), the [physical evidence summary](../../../../module-03-arm-data-for-guided-interaction/11-sim2real-gap-in-hardware-deployment.md#state-of-the-physical-evidence), and the supplied [50-episode result JSON](../data/videos/results_act_ip17_cube300_handheld_060000_pusher_n100.json). The [successful source recording](../../recordings/source/act-push-cube-sim.mp4) and [failed source recording](../../recordings/source/act-push-cube-sim-failure.mp4) are also distributed as files. You can complete this route without installing dependencies, collecting data, training or possessing a ready checkpoint.

1. Read the saved result's `policy`, `task`, `success_rate` and episode entries. Count successes and all attempted episodes, including failures. Record 32/50 = 64% as the result in that file, and distinguish it from the manuscript's reported 62%/56% arm cells. Its path/filename does not establish the missing checkpoint bytes, embodiment, execution horizon or scene identity.
2. Compare one retained successful and one failed source recording. State an observable failure and a separately labelled hypothesis. The lesson's failed video reaches the 450-step limit; do not assign it a particular JSON episode ID unless a matching record establishes that identity.
3. Write a bounded ACT claim: task, training data as reported, checkpoint identity or explicit missing identity, scene, embodiment, action-chunk execution length, success rule, numerator/denominator and evidence rung. Mark unestablished settings as unknown. Contrast the saved simulation evidence with the separate physical 0/10 report; neither is a fresh run by you.
4. Propose one controlled change and identify the settings/outcome record needed to test it. Predicting its effect completes this required activity; executing it is extended practice.

Prepare one short claim and evidence table plus the proposed test for class discussion. A missing checkpoint is a limitation to state in that claim, not a reason to invent a fresh result.

---

## Set up

This setup belongs to the optional executable route. The required saved-record activity above needs no installation.

The code is the pusher package of the course, the same as in Class 10:
[`2026-autumn/resources/class11/additional_material/rebot_pusher/`](https://github.com/asEmbodiedAISyst/2026Autumn/tree/main/2026-autumn/resources/class11/additional_material/rebot_pusher).

You need Ubuntu 22.04 or 24.04 with a desktop session, or macOS 12 or later (Apple silicon or Intel).

<details>

<summary>Install uv (once)</summary>

`uv` installs Python and the packages of each class folder. Install it once, following the
[uv installation page](https://docs.astral.sh/uv/getting-started/installation/) or with this command, the same on
Linux and macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

If `curl` is not found, as on a fresh Ubuntu, install it with `sudo apt install curl`, or use `wget` instead:

```bash
wget -qO- https://astral.sh/uv/install.sh | sh
```

Open a new terminal afterwards, so that the `uv` command is found. Check it with `uv --version`.

</details>

Training reads dataset videos through FFmpeg. Check that FFmpeg is available to the selected training environment before starting. On a shared computer, use a prepared isolated environment/container supplied by the teaching team rather than changing system packages. FFmpeg availability and the selected PyTorch backend are prerequisites to verify; the source recipe is not a guarantee of an already configured training machine.

Get the code and make the environment:

```bash
git clone https://github.com/asEmbodiedAISyst/2026Autumn.git rob7103
cd rob7103
cd 2026-autumn/resources/class11/additional_material/rebot_pusher
uv sync
```

> [!NOTE]
> If you cloned the repository in an earlier class, run `git pull` in the `rob7103` folder instead of `git clone`.

**macOS:** the commands of this page open no window. Train on the GPU of the Mac with `--policy.device=mps`
instead of `--policy.device=cuda`; the training step gives both.

The source gives CUDA and Apple-silicon MPS training commands. Backend support and performance must be checked with the installed environment; an Intel Mac has no MPS backend. CPU training is an available but slow optional route (`--policy.device=cpu`), not the planned classroom workload. Generation and evaluation can run on a CPU, while their offscreen renderer still needs a supported graphics backend.

| Script | What it does |
| --- | --- |
| [`scripts/generate_tool_demos.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/2026-autumn/resources/class11/additional_material/rebot_pusher/scripts/generate_tool_demos.py) | Simulated demonstrations of the scripted expert, written as a LeRobot dataset |
| `lerobot-train` | Trains a policy on a LeRobot dataset ([LeRobot](https://github.com/huggingface/lerobot)) |
| [`scripts/eval_policy.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/2026-autumn/resources/class11/additional_material/rebot_pusher/scripts/eval_policy.py) | Runs a policy in closed loop on the simulated arm or tool: success rate, results file and videos |

---

## Optional: train and evaluate in simulation

The following source recipe is extended practice. No ready matching checkpoint is included in this distribution. New evaluation requires either a verified checkpoint supplied by the teaching team or your separately trained checkpoint, its preprocessing/statistics/data identity, and a rehearsed isolated environment. A newly trained policy has its own identity and score; it does not inherit a historical source result. Until these prerequisites are met, use the required saved-record activity above.

### Get the data

A reported checkpoint result requires the matching checkpoint, preprocessing and configuration. If no ready checkpoint is distributed, this is a generation-and-training route; it is not a zero-training playback package. Do not replace missing weights with another policy while keeping the reported score.

Generate the declared 300 simulated Push Cube demonstrations with the source scripted expert. The source machine needed about six minutes. On a Mac the generation is much slower, about 15 s per episode or about one hour in total; use a Linux machine when you can:

```bash
uv run python scripts/generate_tool_demos.py --task push_cube --embodiment handheld --num-episodes 300 \
    --seed 20000 --repo-id local/sim_push_cube --root datasets/sim_push_cube
```

| Parameter | Meaning |
| --- | --- |
| `--task push_cube` | the task: push the cube into the target  |
| `--embodiment handheld` | who holds the tool in the demonstrations: the simulated hand (`pusher`: the simulated arm) |
| `--num-episodes 300` | number of successful episodes to keep |
| `--seed 20000` | seed of the first episode; each next attempt uses the next seed, so seeds identify the attempted reset sequence under a fixed implementation |
| `--repo-id local/sim_push_cube` | the LeRobot name of the dataset; `local/` means it stays on your computer |
| `--root datasets/sim_push_cube` | the folder of the dataset |

The source records the following terminal output for its declared run:

```
done: 300 episodes (355 attempts, 55 discarded as unreachable for the arm), dataset datasets/sim_push_cube
```

This is the source recipe used in Class 10. Matching seeds alone does not guarantee identical episodes across changed simulator, code or dependency versions; retain those versions with the generated dataset. You can also train on the
episodes that you recorded yourself in Class 10, provided you replace `--dataset.root` and `--dataset.repo_id` with their actual values. Class 10 and Class 11 have separate package directories; a relative `datasets/...` path in one does not automatically refer to the other. Keep the action semantics and height reference with the chosen dataset.

### Train ACT

**Linux:**

```bash
uv run lerobot-train --dataset.repo_id=local/sim_push_cube --dataset.root=datasets/sim_push_cube \
    --policy.type=act --output_dir=outputs/train/act_sim_push_cube --job_name=act_sim_push_cube \
    --policy.device=cuda --wandb.enable=false --policy.push_to_hub=false \
    --steps=60000 --batch_size=16 --save_freq=20000
```

**macOS:**

```bash
uv run lerobot-train --dataset.repo_id=local/sim_push_cube --dataset.root=datasets/sim_push_cube \
    --policy.type=act --output_dir=outputs/train/act_sim_push_cube --job_name=act_sim_push_cube \
    --policy.device=mps --wandb.enable=false --policy.push_to_hub=false \
    --steps=60000 --batch_size=16 --save_freq=20000
```

| Parameter | Meaning |
| --- | --- |
| `--dataset.repo_id`, `--dataset.root` | the dataset of step 1: its name and its folder |
| `--policy.type=act` | the policy: ACT, Action Chunking with Transformers (`diffusion`: Diffusion Policy) |
| `--output_dir`, `--job_name` | where the checkpoints and the log go, and the name of the run |
| `--policy.device=cuda` | the GPU that trains (`mps` on a Mac, `cpu` without GPU, very slow) |
| `--wandb.enable=false` | no logging to Weights & Biases |
| `--policy.push_to_hub=false` | the checkpoint stays on your computer, not on the Hugging Face Hub |
| `--steps=60000` | number of gradient steps |
| `--batch_size=16` | number of samples per step |
| `--save_freq=20000` | a checkpoint every 20k steps, in `checkpoints/020000/`, `040000/`, … and `last/` |

The source reported approximately one hour for 60k steps on its RTX 5090 setup; this is a recorded planning estimate, not a verified runtime for every machine. For a short optional training exercise, the source suggests `--steps=5000`. Its decreasing loss would be a new observed optimisation result, not evidence that the 60k-step score has been reproduced. Keep full training outside the main classroom demonstration. The MPS command requests the Apple-silicon GPU; verify its kernel support before a long run. It is a supplied recipe, not evidence that this checkpoint has already been trained on the current Mac.

**Look at:** the log prints `loss`, `l1_loss` and `kld_loss` at regular steps. A decreasing loss is necessary, but it
does not show that the policy does the task.

### Run it on the simulated arm

```bash
uv run python scripts/eval_policy.py \
    --policy-path outputs/train/act_sim_push_cube/checkpoints/last/pretrained_model \
    --task push_cube --embodiment pusher --episodes 50 --max-steps 450 --n-action-steps 10 \
    --seed 100000 --delta-reference command --image-size 480x640 --device cpu \
    --video-dir outputs/eval/act_sim_push_cube
```

| Parameter | Meaning |
| --- | --- |
| `--policy-path` | the checkpoint to evaluate: `pretrained_model` of the last checkpoint |
| `--task push_cube` | the task of the training data |
| `--embodiment pusher` | the tool on the simulated arm (`handheld`: the simulated hand, as in the data) |
| `--episodes 50` | number of evaluation episodes |
| `--max-steps 450` | time limit of an episode, in control steps at 30 Hz (450 = 15 s) |
| `--n-action-steps 10` | actions executed from each predicted chunk before the policy looks again |
| `--video-dir` | the folder of the results file and of the videos |

Use a distinct output directory for each changed setting so later runs cannot overwrite earlier outcomes. This command explicitly selects CPU inference; another verified backend is an optional change and belongs in the run configuration. Save the configuration sidecar described below before running.

The policy was trained on handheld demonstrations and now drives the tool on the arm. Each episode has a new
layout of the cube and the target, with seeds from 100000, disjoint from the training seeds. The time limit is
450 steps (15 s). The terminal prints one line per episode and the success rate:

```
episode 0: failure, 450 steps, {'ik_ok': 1.0, 'distance': 0.016508746392610765}
episode 1: failure, 450 steps, {'ik_ok': 1.0, 'distance': 0.01769435448608064}
episode 2: failure, 450 steps, {'ik_ok': 1.0, 'distance': 0.02621384182830727}
episode 3: success, 58 steps, {'ik_ok': 1.0, 'distance': 0.014771520458464856}
episode 4: success, 57 steps, {'ik_ok': 1.0, 'distance': 0.013960237341998064}

success rate: 40.0% (2/5)
```

This is a five-episode terminal excerpt retained in the source practice page. The matching ready checkpoint is not included, and its exact identity against the larger source benchmarks remains to be supplied. It is not a new run or the 50-episode result.

`distance` is the final distance between the cube and the target centres in metres. Success means less than
1.5 cm.

### Save the evaluation configuration alongside its outcomes

The unchanged `eval_policy.py` writes `results.json` only when `--video-dir` is supplied. It saves the policy path, task, aggregate score and per-episode seed/outcome/steps/scalar metrics. It does **not** save embodiment, effective `n_action_steps`, maximum steps, delta reference, device, image size, scene/model identity or checkpoint digests. A path or filename alone cannot recover these settings later.

Before a new evaluation, create a separate `run-config.json` or `run-config.md` in that run's output folder and retain it with `results.json`, terminal output and videos. Record:

| Record | Required content |
| --- | --- |
| Source and environment | repository commit, package path, dependency lockfile digest, installed MuJoCo/LeRobot/PyTorch versions, actual device and renderer/backend |
| Dataset and policy | training dataset identity/split and height/action convention; exact checkpoint directory; SHA256 of each weight, config, preprocessor/postprocessor and statistics file; camera-feature mapping |
| Evaluation command | exact command and resolved values: task, embodiment, effective `n_action_steps`, `max_steps`, `delta_reference`, device, image size, first seed and complete seed list |
| Simulator and executor | selected scene XML and digest of it plus its included XML/assets; action mode inferred from checkpoint output (9 = episode, 6 = delta); reset/start/noise rules; fps, limits and success/termination rule |
| Outputs | run ID/date, complete attempted-episode denominator, output paths and any interruption or intervention |

For the explicit command above, the declared settings are `push_cube`, `pusher`, 50 episodes, 450 steps, 10 actions per inference, seed 100000 through 100049, `delta_reference=command`, 480×640 images and CPU inference. Confirm that the loaded ACT configuration and environment actually use them. Use `sha256sum` on Linux or `shasum -a 256` on macOS for each retained input file; include the file paths with the digests. Copy the actual configuration/preprocessor files rather than recreating their contents from memory. The task chooses the embodiment-specific scene in `rebot_sim/tasks.py`; resolve that path and its dependencies in the checked-out revision.

Do not backfill unknown historical settings as though they were logged. Without this sidecar, a new outcome file is an outcome record with incomplete run identity, not a complete reproduction protocol. The teaching team must verify one optional run with this record and a matching checkpoint before assigning fresh evaluation.

### Read the results

The folder `outputs/eval/act_sim_push_cube/` has `results.json`, with the seed, the success, the number of steps,
`ik_ok` and the final distance of every episode, and the videos of the first episodes: the phone image on the left,
the scene on the right.

Compare your result only after establishing the checkpoint/scene/executor identity. The source manuscript reports 62% for execution horizon $n$ = 10 and 56% for $n$ = 100 on the arm. The supplied file named `results_act_ip17_cube300_handheld_060000_pusher_n100.json` records 32/50 = 64%, but its JSON does not establish the executor or horizon. If the filename describes the same setting, the corresponding manuscript cell is 56% at $n$ = 100; a filename alone does not resolve the configuration identity. Do not treat the 62% and 64% values as a matched $n$ = 10 comparison. Fifty independent episodes give a standard error near 7 percentage points around this result; that is not a 95% interval. A rerun can differ, and an exact comparison also requires the same checkpoint, scene and seeds.

**Try:**

* `--n-action-steps 100`: the arm executes the whole chunk before the policy looks again;
* `--embodiment handheld`: the same policy on the handheld pusher, as in the data;
* the checkpoint after 20k steps, `checkpoints/020000/pretrained_model`.

---

## Optional executable activity

The [required saved-record activity](#required-saved-record-activity) is the common class deliverable. Complete this executable extension only after its checkpoint and environment prerequisites are met.

* [ ] **Run:** evaluate your verified policy on 50 episodes, saving the configuration sidecar and every outcome. Write the success rate and the setting ($n$, embodiment,
  checkpoint digest, scene, seeds and output record).
* [ ] **Failure:** pick one failed episode in `results.json` and watch its video. Where does the motion stop, and
  what does the phone image show at that moment?
* [ ] **One change:** propose one change (more data, more steps, another $n$) and predict its effect. Then run it.
* [ ] **Claim:** write the result as a bounded claim, as in the bounded-claim section of the class page: task, data, conditions,
  number of episodes, and the rung it reached.

The deployment on the physical arm and its results are in the physical-evidence section of the class page. Only the teaching team runs
the arm.
