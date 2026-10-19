# Class 11 — Practice

The required activity on this page reads saved ACT results and the success and failure recordings of Push Cube, then writes a bounded claim. The class page [Class 11](11-sim2real-gap-in-hardware-deployment.md) explains the pipeline, the evidence ladder and the physical tests. Generating data, training and evaluating a new policy are optional extended practice.

---

## Required saved-record activity

Use the [ACT results and recordings in simulation](11-sim2real-gap-in-hardware-deployment.md#rung-5-in-simulation-act-on-push-cube), the [physical evidence summary](11-sim2real-gap-in-hardware-deployment.md#state-of-the-physical-evidence) and the [50-episode result file](../resources/class11/additional_material/data/videos/results_act_ip17_cube300_handheld_060000_pusher_n100.json). The [successful recording](../resources/class11/recordings/source/act-push-cube-sim.mp4) and the [failed recording](../resources/class11/recordings/source/act-push-cube-sim-failure.mp4) are also in the repository. This activity needs no installation, data collection or training.

1. Read the result file: its `policy`, `task`, `success_rate` and episode entries. Count the successes and all episodes, failures included.
2. Compare the successful and the failed recording. State one failure that you observe and, separately, a hypothesis for its cause. The failed video reaches the 450-step limit.
3. Write a bounded ACT claim: task, training data, checkpoint, scene, embodiment, action-chunk execution length, success rule, numerator/denominator and evidence rung. Mark the settings that you cannot find as unknown. Contrast the simulation result with the 0/10 physical series.
4. Propose one controlled change and the settings and outcomes to record to test it. Predicting its effect completes this activity; running it is the extended practice.

Prepare one short claim, an evidence table and the proposed test for class discussion.

---

## Set up

This setup belongs to the optional executable route. The saved-record activity above needs no installation.

The code is the pusher package of the course, the same as in Class 10:
[`2026-autumn/resources/class11/additional_material/`](https://github.com/asEmbodiedAISyst/2026Autumn/tree/main/2026-autumn/resources/class11/additional_material).

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

Training reads the dataset videos through FFmpeg. Install it first: `sudo apt install ffmpeg` on Ubuntu, `brew install ffmpeg` on macOS. On a shared computer, use the environment prepared by the teaching team. If a run starts with a long `Could not load libtorchcodec` warning that ends with `Falling back to 'pyav'`, the run continues normally.

Get the code and make the environment:

```bash
git clone https://github.com/asEmbodiedAISyst/2026Autumn.git rob7103
cd rob7103
cd 2026-autumn/resources/class11/additional_material
uv sync
```

{% hint style="info" %}
If you cloned the repository in an earlier class, run `git pull` in the `rob7103` folder instead of `git clone`.
{% endhint %}

**macOS:** the commands of this page open no window. Train on the GPU of the Mac with `--policy.device=mps`
instead of `--policy.device=cuda`; the training step gives both.

An Intel Mac has no MPS backend; training on the CPU (`--policy.device=cpu`) works but is very slow. Generation and evaluation run on the CPU.

| Script | What it does |
| --- | --- |
| [`scripts/generate_tool_demos.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/2026-autumn/resources/class11/additional_material/scripts/generate_tool_demos.py) | Simulated demonstrations of the scripted expert, written as a LeRobot dataset |
| `lerobot-train` | Trains a policy on a LeRobot dataset ([LeRobot](https://github.com/huggingface/lerobot)) |
| [`scripts/eval_policy.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/2026-autumn/resources/class11/additional_material/scripts/eval_policy.py) | Runs a policy in closed loop on the simulated arm or tool: success rate, results file and videos |

---

## Optional: train and evaluate in simulation

This route is extended practice. No trained checkpoint is included: you generate the data, train your own policy and evaluate it. Your policy has its own score.

{% stepper %}
{% step %}
### Get the data

Generate 300 simulated Push Cube demonstrations with the scripted expert. The course machine needed about six minutes. On a Mac the generation is much slower, about 15 s per episode or about one hour in total; use a Linux machine when you can:

```bash
uv run python scripts/generate_tool_demos.py --task push_cube --embodiment handheld --num-episodes 300 \
    --seed 20000 --repo-id local/sim_push_cube --root datasets/sim_push_cube
```

| Parameter | Meaning |
| --- | --- |
| `--task push_cube` | the task: push the cube into the target  |
| `--embodiment handheld` | who holds the tool in the demonstrations: the simulated hand (`pusher`: the simulated arm) |
| `--num-episodes 300` | number of successful episodes to keep |
| `--seed 20000` | seed of the first attempt; each next attempt uses the next seed |
| `--repo-id local/sim_push_cube` | the LeRobot name of the dataset; `local/` means it stays on your computer |
| `--root datasets/sim_push_cube` | the folder of the dataset |

The terminal ends with:

```
done: 300 episodes (355 attempts, 55 discarded as unreachable for the arm), dataset datasets/sim_push_cube
```

This is the simulated dataset of Class 10. You can also train on the episodes that you recorded yourself in Class 10:
copy the dataset folder into this package, or give its full path in `--dataset.root`, and set `--dataset.repo_id` to
its name. Keep its action mode and height reference in mind when you evaluate.
{% endstep %}

{% step %}
### Train ACT

{% tabs %}
{% tab title="Linux" %}
```bash
uv run lerobot-train --dataset.repo_id=local/sim_push_cube --dataset.root=datasets/sim_push_cube \
    --policy.type=act --output_dir=outputs/train/act_sim_push_cube --job_name=act_sim_push_cube \
    --policy.device=cuda --wandb.enable=false --policy.push_to_hub=false \
    --steps=60000 --batch_size=16 --save_freq=20000
```
{% endtab %}

{% tab title="macOS" %}
```bash
uv run lerobot-train --dataset.repo_id=local/sim_push_cube --dataset.root=datasets/sim_push_cube \
    --policy.type=act --output_dir=outputs/train/act_sim_push_cube --job_name=act_sim_push_cube \
    --policy.device=mps --wandb.enable=false --policy.push_to_hub=false \
    --steps=60000 --batch_size=16 --save_freq=20000
```
{% endtab %}
{% endtabs %}

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

60k steps take about one hour on an RTX 5090 GPU and more than ten hours on an Apple-silicon Mac. For a short exercise, use `--steps=5000`, about one hour on a Mac. Keep full training outside the class. If the output folder already exists, the run stops: choose a new `--output_dir` or delete the old folder.

**Look at:** the log prints `loss`, `l1_loss` and `kld_loss` at regular steps. A decreasing loss is necessary, but it
does not show that the policy does the task.
{% endstep %}

{% step %}
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

Use a new output folder for each changed setting, so that a later run cannot overwrite an earlier one. Save the configuration file of the next step with the results.

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

This excerpt shows five episodes of a 60k-step policy; your numbers will differ.

`distance` is the final distance between the cube and the target centres in metres. Success means less than
1.5 cm.
{% endstep %}

{% step %}
### Save the evaluation configuration alongside its outcomes

`eval_policy.py` writes `results.json` when `--video-dir` is given. It saves the policy path, the task, the success rate and, for every episode, the seed, the outcome, the steps and the metrics. It does **not** save the embodiment, `n_action_steps`, the step limit, the delta reference, the device, the image size, the scene or the checkpoint digests.

Before an evaluation, write a `run-config.json` or `run-config.md` in its output folder, next to `results.json`, the terminal output and the videos. Record:

| Record | Required content |
| --- | --- |
| Code and environment | repository commit, package path, dependency lockfile digest, installed MuJoCo/LeRobot/PyTorch versions, actual device and renderer/backend |
| Dataset and policy | training dataset name and split, height reference and action mode; exact checkpoint directory; SHA256 of each weight, config, preprocessor/postprocessor and statistics file; camera-feature mapping |
| Evaluation command | exact command and resolved values: task, embodiment, effective `n_action_steps`, `max_steps`, `delta_reference`, device, image size, first seed and complete seed list |
| Simulator and executor | selected scene XML and digest of it plus its included XML/assets; action mode inferred from checkpoint output (9 = episode, 6 = delta); reset/start/noise rules; fps, limits and success/termination rule |
| Outputs | run ID/date, complete attempted-episode denominator, output paths and any interruption or intervention |

For the command above the settings are `push_cube`, `pusher`, 50 episodes, 450 steps, 10 actions per inference, seeds 100000 to 100049, `delta_reference=command`, 480×640 images and CPU inference. Compute the digests with `sha256sum` on Linux or `shasum -a 256` on macOS, with the file paths. Copy the configuration and preprocessor files rather than retyping them. The scene of each embodiment is chosen in `rebot_sim/tasks.py`.

Without this file, a result cannot be compared with another run.

### Read the results

The folder `outputs/eval/act_sim_push_cube/` has `results.json`, with the seed, the success, the number of steps,
`ik_ok` and the final distance of every episode, and the videos of the first episodes: the phone image on the left,
the scene on the right.

The class page reports 62 % for $$n$$ = 10 and 56 % for $$n$$ = 100 on the arm. With 50 episodes the standard error is about 7 percentage points; an exact comparison also needs the same checkpoint, scene and seeds.

**Try:**

* `--n-action-steps 100`: the arm executes the whole chunk before the policy looks again;
* `--embodiment handheld`: the same policy on the handheld pusher, as in the data;
* the checkpoint after 20k steps, `checkpoints/020000/pretrained_model`.
{% endstep %}

{% endstepper %}

---

## Optional executable activity

The [saved-record activity](#required-saved-record-activity) is the class deliverable. This executable extension follows the optional route above.

* [ ] **Run:** evaluate your policy on 50 episodes, saving the configuration file and every outcome. Write the success rate and the setting ($$n$$, embodiment,
  checkpoint digest, scene, seeds and output record).
* [ ] **Failure:** pick one failed episode in `results.json` and watch its video. Where does the motion stop, and
  what does the phone image show at that moment?
* [ ] **One change:** propose one change (more data, more steps, another $$n$$) and predict its effect. Then run it.
* [ ] **Claim:** write the result as a bounded claim, as in the bounded-claim section of the class page: task, data, conditions,
  number of episodes, and the rung it reached.

The deployment on the physical arm and its results are in the physical-evidence section of the class page. Only the teaching team runs
the arm.
