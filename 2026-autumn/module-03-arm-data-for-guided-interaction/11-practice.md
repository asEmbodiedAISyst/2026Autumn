# Class 11 — Practice

On this page you train a policy on the simulated Push Cube data of Class 10, run it on the simulated arm and read
its results: rung 5 in simulation. The class page [Class 11](11-sim2real-gap-in-hardware-deployment.md) explains the pipeline, the evidence
ladder and what the physical arm showed.

---

## Set up

The code is the pusher package of the course, the same as in Class 10:
[`course-resources/class11_sim2real_deployment/additional_material/rebot_pusher/`](https://github.com/asEmbodiedAISyst/2026Autumn/tree/main/course-resources/class11_sim2real_deployment/additional_material/rebot_pusher).

You need Ubuntu 22.04 or 24.04 with a desktop session, or macOS 12 or later (Apple silicon or Intel).

The setup below installs `uv` in a course-local `.course-tools` environment and class dependencies in a package-local `.venv`. It does not change a system Python installation. If `uv` is already available, the three `.course-tools` bootstrap lines may be skipped.


Training reads dataset videos through FFmpeg. Check that FFmpeg is available to the selected training environment before starting. On a shared computer, use a prepared isolated environment/container supplied by the teaching team rather than changing system packages. FFmpeg availability and the selected PyTorch backend are prerequisites to verify; the source recipe is not a guarantee of an already configured training machine.

Get the code and make the environment:

```bash
git clone https://github.com/asEmbodiedAISyst/2026Autumn.git rob7103
cd rob7103
python3 -m venv .course-tools
.course-tools/bin/python -m pip install uv
export PATH="$PWD/.course-tools/bin:$PATH"
cd course-resources/class11_sim2real_deployment/additional_material/rebot_pusher
uv sync
```

If you already have the checkout, start from its `rob7103/` root and update it with `git pull --ff-only`; do not clone another copy or recreate an existing `.course-tools` environment. Continue from the `export PATH` line, then enter this page's package directory. Each class has its own `.venv`; switching to another class package does not reuse its dependencies automatically.

In every additional terminal, open the **same package directory** and expose the course-local `uv` command before running the examples:

```bash
export PATH="$(git rev-parse --show-toplevel)/.course-tools/bin:$PATH"
```

This line assumes the terminal is already inside the cloned repository. Omit it if your existing `uv` is already on `PATH`. Check `pwd` before using a relative data or output path.

**macOS:** the commands of this page open no window. Train on the GPU of the Mac with `--policy.device=mps`
instead of `--policy.device=cuda`; the training step gives both.

The source gives CUDA and Apple-silicon MPS training commands. Backend support and performance must be checked with the installed environment; an Intel Mac has no MPS backend. CPU training is an available but slow optional route (`--policy.device=cpu`), not the planned classroom workload. Generation and evaluation can run on a CPU, while their offscreen renderer still needs a supported graphics backend.

| Script | What it does |
| --- | --- |
| [`scripts/generate_tool_demos.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/course-resources/class11_sim2real_deployment/additional_material/rebot_pusher/scripts/generate_tool_demos.py) | Simulated demonstrations of the scripted expert, written as a LeRobot dataset |
| `lerobot-train` | Trains a policy on a LeRobot dataset ([LeRobot](https://github.com/huggingface/lerobot)) |
| [`scripts/eval_policy.py`](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/course-resources/class11_sim2real_deployment/additional_material/rebot_pusher/scripts/eval_policy.py) | Runs a policy in closed loop on the simulated arm or tool: success rate, results file and videos |

---

## Train and evaluate in simulation

{% stepper %}
{% step %}
### Get the data

A reported checkpoint result requires the matching checkpoint, preprocessing and configuration. If no ready checkpoint is distributed, this is a generation-and-training route; it is not a zero-training playback package. Do not replace missing weights with another policy while keeping the reported score.

Generate the declared 300 simulated Push Cube demonstrations with the source scripted expert. The source reported approximately six minutes for its generation machine; allow preparation time rather than assuming this duration on a student laptop:

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

The source reported approximately one hour for 60k steps on its RTX 5090 setup; this is a recorded planning estimate, not a verified runtime for every machine. For a short optional training exercise, the source suggests `--steps=5000`. Its decreasing loss would be a new observed optimisation result, not evidence that the 60k-step score has been reproduced. Keep full training outside the main classroom demonstration. The MPS command requests the Apple-silicon GPU; verify its kernel support before a long run. It is a supplied recipe, not evidence that this checkpoint has already been trained on the current Mac.

**Look at:** the log prints `loss`, `l1_loss` and `kld_loss` at regular steps. A decreasing loss is necessary, but it
does not show that the policy does the task.
{% endstep %}

{% step %}
### Run it on the simulated arm

```bash
uv run python scripts/eval_policy.py \
    --policy-path outputs/train/act_sim_push_cube/checkpoints/last/pretrained_model \
    --task push_cube --embodiment pusher --episodes 50 --max-steps 450 --n-action-steps 10 \
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
{% endstep %}

{% step %}
### Read the results

The folder `outputs/eval/act_sim_push_cube/` has `results.json`, with the seed, the success, the number of steps,
`ik_ok` and the final distance of every episode, and the videos of the first episodes: the phone image on the left,
the scene on the right.

Compare your result only after establishing the checkpoint/scene/executor identity. The source manuscript reports 62% for execution horizon $$n$$ = 10 and 56% for $$n$$ = 100 on the arm. The supplied file named `results_act_ip17_cube300_handheld_060000_pusher_n100.json` records 32/50 = 64%, but its JSON does not establish the executor or horizon. If the filename describes the same setting, the corresponding manuscript cell is 56% at $$n$$ = 100; a filename alone does not resolve the configuration identity. Do not treat the 62% and 64% values as a matched $$n$$ = 10 comparison. Fifty independent episodes give a standard error near 7 percentage points around this result; that is not a 95% interval. A rerun can differ, and an exact comparison also requires the same checkpoint, scene and seeds.

**Try:**

* `--n-action-steps 100`: the arm executes the whole chunk before the policy looks again;
* `--embodiment handheld`: the same policy on the handheld tool, as in the data;
* the checkpoint after 20k steps, `checkpoints/020000/pretrained_model`.
{% endstep %}

{% endstepper %}

---

## Student activity

* [ ] **Run:** evaluate your policy on 50 episodes. Write the success rate and the setting ($$n$$, embodiment,
  checkpoint).
* [ ] **Failure:** pick one failed episode in `results.json` and watch its video. Where does the motion stop, and
  what does the phone image show at that moment?
* [ ] **One change:** propose one change (more data, more steps, another $$n$$) and predict its effect. Then run it.
* [ ] **Claim:** write the result as a bounded claim, as in the bounded-claim section of the class page: task, data, conditions,
  number of episodes, and the rung it reached.

The deployment on the physical arm and its results are in the physical-evidence section of the class page. Only the teaching team runs
the arm.
