---
description: 01 December 2026 · 09:00–10:20 · CR6
---

# 19 Final Code Submission

**Deadline: 1 December 2026, 10:20 — Abu Dhabi time (UTC+4).**

## Submission requirements

The [NeurIPS code guidelines](https://neurips.cc/public/guides/CodeSubmissionPolicy) state:

> Your code submission ideally should be self-contained and executable. If this is not the case, you must explain why.

For this course, keep your project implementation in `code/`, with `code/README.md` as its entry point. Explain the project boundary, tested environment, dependencies, required data/models, commands to reproduce an important result, expected output and known limits. Cite reused work. Use the authors’ README example or the linked template below for guidance.

## How to submit and how we collect

Commit and push the code and README to the `main` branch of your assigned team repository before the deadline. Check the uploaded files on GitHub.

At the deadline, the teaching team records and collects the remote `main` revision. We retain the complete repository, including referenced shared folders, and name its archive `TeamNN-code-YYMMDD-HHMMSS.zip`. The suffix is the GitHub-recorded push time of that submitted revision, in Abu Dhabi time (UTC+4), used to check the deadline. We record collection time separately. **Students do not create this ZIP.** Later pushes do not replace the collected submission. No separate submission form or record is required.

## Example and preparation guidance

Use the authors’ [asRoBallet MuJoCo repository and README](https://github.com/asRoBallet/asRoBallet_mujoco#readme), accompanying [Fang Wan et al.’s RSS 2026 paper](https://arxiv.org/abs/2604.24916). It documents the tasks, installation, training, evaluation and playback. Follow its approach to explaining the code; write instructions for your own project and available assets.

### Optional examples from the worksheet papers

The [Classes 12–17 filled examples](../module-04-worksheets-guided-final-project-preparation/12-final-project-i-claim.md#filled-worksheet-examples) connect Claim to the result being reproduced; Experience, System and Grounding to data, hardware and configuration; Learning and Decision to training, evaluation and expected outputs. Use these author READMEs as documentation references; distinguish published results from your team's verified outputs.

| Official code and README | What to learn for your code handoff |
| --- | --- |
| [ALOHA / ACT](https://github.com/tonyzhaozh/act#readme) | Separate collection, visualization, training and evaluation; identify real-robot dependencies. |
| [UMI](https://github.com/real-stanford/universal_manipulation_interface#readme) | Trace raw sessions through SLAM, dataset conversion, training and deployment. |
| [DROID collection](https://github.com/droid-dataset/droid#readme) · [policy learning](https://github.com/droid-dataset/droid_policy_learning#readme) | State each repository's role; pin data/calibration versions and companion dependencies. |
| [BridgeData V2](https://github.com/rail-berkeley/bridge_data_v2#readme) | Match the data-conversion route, checkpoint, configuration and image resolution. |
| [LEAP Hand API](https://github.com/leap-hand/LEAP_Hand_API#readme) | Separate hardware/API setup from policy experiments; identify the original v1 resources. |
| [NeuralFeels](https://github.com/facebookresearch/neuralfeels#readme) | Name dataset/model assets, object/log, sensor modalities and estimation mode. |
| [Walk These Ways](https://github.com/Improbable-AI/walk-these-ways#readme) | Separate setup tests, training, pretrained-policy evaluation and hardware deployment. |
| [DayDreamer](https://github.com/danijar/daydreamer#readme) | Explain actor, learner, replay/log paths and robot-specific configuration. |

Linked datasets/checkpoints differ between projects; a README or selected release does not establish access to every original experiment record. Document what your team actually supplies and can reproduce.

Optional guidance: [Papers with Code research-code tips](https://github.com/paperswithcode/releasing-research-code) and its [README template](https://github.com/paperswithcode/releasing-research-code/blob/master/templates/README.md), linked from NeurIPS. Adapt the relevant sections to your project.
