---
description: 01 December 2026 · Deadline 10:20 · No class meeting
layout:
  width: wide
---

# 19 Final Code Submission

**Deadline: 1 December 2026, 10:20 — Abu Dhabi time (UTC+4).**

**Public holiday: no class meeting. The submission deadline remains in effect.**

## Team preparation and the submission deadline

This milestone continues your final-project preparation. Use your team's preparation time to finish the implementation, check that the supplied files support the reported results, and make `code/README.md` usable by another reader. Use the guidance below as a reference for that work.

**There is no class meeting on this public holiday.** Work independently with your team and push the required `code/` contents, including `code/README.md`, to your assigned private team repository's `main` branch by the deadline above. Leave time to check the uploaded files on GitHub. The deadline is the submission checkpoint; no separate class attendance or additional progress form is required.

## Submission requirements

The [NeurIPS code guidelines](https://neurips.cc/public/guides/CodeSubmissionPolicy) state:

> Your code submission ideally should be self-contained and executable. If this is not the case, you must explain why.

For this course, keep your project implementation in `code/`, with `code/README.md` as its entry point. Explain the project boundary, tested environment, dependencies, required data/models, commands to reproduce an important result, expected output and known limits. Start the README with your assigned team identifier (**Team01–Team08**) and project title. Cite reused work. Use the authors’ README example or the linked template below for guidance.

## How to submit and how we collect

Commit and push the code and README to the `main` branch of your assigned team repository before the deadline. Check the uploaded files on GitHub.

At the deadline, the teaching team records the remote `main` commit, collects the required files from that revision and retains the snapshot. We record the GitHub push time for the submitted version and the collection time separately, in Abu Dhabi time (UTC+4). The deadline concerns when the version reached GitHub, not its local commit date. Later pushes do not replace the collected version. Confirm teaching-team access before the deadline; report an access problem promptly.

For our collected copy, we retain the complete repository, including referenced shared folders, in `TeamNN-code-YYMMDD-HHMMSS.zip`. **Students do not create this ZIP.** The teaching team adds the suffix using the GitHub-recorded submission push time, not the collection time. No separate upload, email, release, tag, manifest or student collection record is required.

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

### Optional preparation references

- Greg Wilson, Jennifer Bryan and colleagues (2017), [Good enough practices in scientific computing](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005510) — This article explains dependencies, usage examples, small test inputs with expected outputs and an understandable project overview.
- Benjamin D. Lee (2018), [Ten simple rules for documenting scientific software](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1006561) — This article explains usable READMEs, examples, quickstarts and checking instructions with someone unfamiliar with the software.
- Geir Kjetil Sandve and colleagues (2013), [Ten Simple Rules for Reproducible Computational Research](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1003285) — This article connects a reported result to its code, software versions, parameters, randomness and underlying plot data.

Optional guidance: [Papers with Code research-code tips](https://github.com/paperswithcode/releasing-research-code) and its [README template](https://github.com/paperswithcode/releasing-research-code/blob/master/templates/README.md), linked from NeurIPS. Adapt the relevant sections to your project.
