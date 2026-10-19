# Interpreting acceptance for the retained pilot

This note interprets the existing ten-episode **simulated handheld** Push Cube pilot. It does not replace `audit_reference.json`, regenerate data, change fault labels/metrics or report a new physical measurement. The JSON's `fault` records an injected change; `none` means no injection. Its `success` and rounded final distance come from the source simulator's final state. The numeric audit separately checks the last recorded state; those are different sampling points.

## Declare the acceptance question

For this exercise, a successful demonstration must pass numeric integrity/timing checks, reach the task goal, and be feasible for the declared arm/executor. Use reachability ≥0.98, peak linear speed ≤0.2625 m/s (the diagnostic's 105% tolerance on 0.25 m/s), tilt ≤30° and yaw within ±60°. Images must show the information needed for the push; inspect loss of visibility during the relevant phase, not only an episode average. The source does not publish a universal visibility-fraction threshold. State your image criterion and evidence before making a final acceptance decision. Workspace, angular speed and action-label/frame compatibility also require review; the pose checker does not assert all of them.

The numeric script `../../code/audit_dataset.py` checks metadata dimensions/counts, finite values, regular timestamp steps, command speed and the last recorded cube-goal distance. It does not assess orientation, images or reachability. Its two reported episode flags are not a complete list of rejections. The source reference additionally supplies reachability and a projected-centre visibility fraction; a projected centre in the image does not establish unobscured visibility of the full object.

## What the retained evidence already establishes

Episode numbers below are zero based, matching the JSON. Values are copied from the existing source reference; the 0.600 m/s command-speed flag for episode 6 is the supplied numeric-audit example. A speed/yaw **limit setting** in the JSON is configuration, not an observed peak/range. The table uses the recorded reach fraction/outcome or reported speed failure for a definite rejection, rather than inferring a violation solely from a raised limit.

| Episode | Injected label | Source reach fraction | Source success | Acceptance interpretation from the retained evidence |
| --- | --- | --- | --- | --- |
| 0 | `none` | 1.000 | true | No rejection established by these fields; eligible for image and remaining contract review |
| 1 | `none` | 1.000 | true | No rejection established by these fields; eligible for image and remaining contract review |
| 2 | `camera_away` | 0.456 | true | Reject: reachability below 0.98; inspect the images separately for task visibility |
| 3 | `none` | 0.903 | true | Reject: reachability below 0.98 despite no injected change |
| 4 | `truncated` | 1.000 | false | Reject: incomplete task, final source distance 0.0239 m >0.015 m; numeric audit also flags the last recorded state |
| 5 | `none` | 1.000 | true | No rejection established by these fields; eligible for image and remaining contract review |
| 6 | `too_fast` | 0.985 | true | Reject: reported peak command speed 0.600 m/s exceeds 0.2625 m/s, despite reachability passing |
| 7 | `unreachable` | 0.246 | true | Reject: reachability below 0.98; removing a yaw limit is its injected change, not a separate measured yaw result |
| 8 | `none` | 1.000 | true | No rejection established by these fields; eligible for image and remaining contract review; its projected both-visible fraction is 0.582 |
| 9 | `camera_away` | 0.617 | true | Reject: reachability below 0.98; inspect the images separately for task visibility |

Six episodes therefore already fail a declared acceptance gate. Episodes 0, 1, 5 and 8 are **candidates for acceptance**, not certified accepted episodes: image review and the remaining declared checks can reject them too. Do not invent a fixed five-rejection answer or accept an episode because its injection label is `none`. Record each check, its evidence and any unknown field. The supplied images, numerical records and source code can support that review without collecting a new dataset.

This interpretation does not claim a new full visual audit or a frame-aware replay of physical handheld data. The pilot generator computes its own simulated target-pose reachability. The separate fixed-frame checker reads observed poses, so its output can differ even before changing the robot, solver or frame convention.
