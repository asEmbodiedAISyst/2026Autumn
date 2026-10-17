---
description: 02 December 2026 · 10:30–11:50 · CR6
---

# 20 Final Video Submission

**Deadline: 2 December 2026, 11:50 — Abu Dhabi time (UTC+4).**

## Submission requirements

Use the [RSS 2026 video specifications](https://roboticsconference.org/2026/information/presentationInstructions/):

- **Duration:** “No longer than 4 minutes (240 seconds)”
- **Resolution:** “1920x1080 pixels (1080p)”
- **Format:** “MPEG-4”

**Course adaptation:** include narration or explanatory captions so the video can be understood without a live presenter. Submit an `.mp4` file named `TeamNN-video.mp4`, replacing `NN` with your two-digit team number: `01`–`08`. Team 01 submits `video/Team01-video.mp4`.

## How to submit and how we collect

Commit and push the video to the `main` branch of your assigned team repository before the deadline. Open the uploaded copy on GitHub and check playback. For upload help, use [GitHub’s large-file guidance](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).

At the deadline, the teaching team records and collects the remote `main` revision. We rename the collected file `TeamNN-video-YYMMDD-HHMMSS.mp4`. The suffix is the GitHub-recorded push time of the submitted file version, in Abu Dhabi time (UTC+4), used to check the deadline. We record collection time separately. Later pushes do not replace the collected submission. No separate submission form or record is required.

## Example and preparation guidance

Use the original **asRoBallet RSS 2026 narration transcript** as a reference for explaining the problem, method, evidence and conclusion. Rehearse your explanation before fixing the slideshow or edit timing. The example below is a presentation script.

![Original asRoBallet RSS 2026 narration transcript with twenty numbered spoken points.](../media/class20/asroballet-narration-original.png)

*Figure 1. Original asRoBallet narration transcript, retained from the earlier course notes. [Open the full-size script](../media/class20/asroballet-narration-original.png) · [Paper and research source](https://bionicdl.ancorasir.com/?p=2238). Prepare one video with narration or explanatory captions for this submission.*

### Optional examples from the worksheet papers

Use the [Classes 12–17 filled examples](../module-04-worksheets-guided-final-project-preparation/12-final-project-i-claim.md#filled-worksheet-examples) to connect Claim → Experience → System → Grounding → Learning → Decision. In a video, this becomes the system and task, how evidence was collected, results, and failures or limits. Label your team's own results separately from cited author footage.

| Author video resource | What to notice for your video |
| --- | --- |
| ALOHA / ACT: [task clip](https://tonyzhaozh.github.io/aloha/resources/slot_battery.mp4) · [failure clip](https://tonyzhaozh.github.io/aloha/resources/reactive_cup_fail.mov) | Identify the task and learned behavior; retain labelled failures. |
| UMI: [tossing clip](https://umi-gripper.github.io/videos/task_dynamic_tossing.mp4) · [latency ablation](https://umi-gripper.github.io/videos/comparison_tossing_no_latency_matching.mp4) | Distinguish demonstration from autonomous execution; make the comparison condition explicit. |
| DROID: [qualitative clip](https://droid-dataset.github.io/videos/droid_eval_videos/clean_droid_ood.mp4) · [comparison](https://droid-dataset.github.io/videos/droid_eval_videos/clean_oxe_ood.mp4) | Label method and out-of-distribution conditions; selected clips are not aggregate results. |
| BridgeData V2: [GCBC success clip](https://bridgedata-v2.github.io/videos_2x/unseen_pnp/gcbc_success.mp4) · [D-GCBC failure clip](https://bridgedata-v2.github.io/videos_2x/unseen_pnp/ddpm_fail.mp4) | Label method and goal; disclose the authors' **2× playback**. |
| LEAP Hand v1: [original author video](https://youtu.be/VKAlJPypQFI) | Separate teleoperation/autonomy and simulation/physical demonstrations. |
| NeuralFeels: [author presentation](https://youtu.be/KOHh0awhSEg) | Explain sensor inputs, estimated shape/pose and known-shape conditions. |
| Walk These Ways: [project video](https://www.youtube.com/watch?v=FViNnwLk5wI) | Identify terrain/task, gait tuning and the behavior's limits. |
| DayDreamer: [project video](https://www.youtube.com/watch?v=xAXvfVTgqr0) | Explain physical learning time, perturbations and recovery. |

Optional export help: [HandBrake’s official preview guide](https://handbrake.fr/docs/en/latest/workflow/preview-settings.html), following the encoder linked by RSS.
