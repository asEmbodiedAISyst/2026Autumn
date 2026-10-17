# Class 10 figure code and inputs

The seven inline classroom figures are supplied as PNGs, SVGs with editable labels and PDF masters. They use MiSans typography, source simulation frames and retained audit values. Eighteen assets are copied unchanged; the action-chunks PNG/SVG/PDF trio was regenerated only to correct “Execute 1 steps” to “Execute 1 step” in its legend. All plotted values and timing arithmetic are unchanged. These figures contain no new policy or physical-arm result.

| Figure | Exact plotting function | Type and retained input |
| --- | --- | --- |
| learning-records | `learning_records()` | Conceptual comparison of demonstration, RL transition and evaluation records |
| tool-schema | `tool_schema()` | Declared 3-position plus 6-rotation-column feature schema and RGB image |
| pilot-views | `pilot_views()` | Complete selected frames from episodes 0 and 2; `data/pilot-nominal.png`, `data/pilot-turned.png` |
| pilot-audit | `pilot_audit()` | Saved numeric report; `results/pilot-audit.json` |
| pilot-reach | `pilot_reach()` | Recorded canonical-frame IK report; `data/target-frame-reachability.txt` |
| episode-splits | `split_episodes()` | Illustrative episode split A–J; not an actual dataset partition |
| action-chunks | `action_chunks()` | Constructed replanning intervals at nominal 30 Hz |

The [portable entry point](figure-source/render_class10.py) maps these identifiers directly to the retained functions in [lecture_figures.py](figure-source/source/lecture_figures.py). It uses the [shared style](figure-source/source/publication.mplstyle) and explicit MiSans [font preflight](figure-source/source/figure_typography.py). The [reproduction notes](figure-source/README.md) describe dependencies and the external licensed font requirement.

From `figure-source/`, run in a plotting environment:

```sh
python -m pip install -r requirements-plotting.txt
python render_class10.py --font-dir /path/to/authorised/MiSans/fonts
```

Replotting reads saved inputs and writes new plots into `figure-source/media/`; it does not train a model, run policy inference, recompute IK or rerun the numeric audit. Published assets remain one level above. A new render records its own font receipt instead of claiming byte-identical output. The retained source and correction receipts resolved a semibold font request to MiSans Bold; external font files are not included. The portable subset passed a complete seven-figure render, with the six unchanged PNGs reproducing pixel for pixel.

The numeric pilot report covers ten episodes and 638 saved frames. Its dashed lines are the declared 0.25 m/s target speed and 15 mm final-frame geometric radius. Final saved distance does not establish a complete task outcome or hold duration. The IK figure uses rounded percentages from the recorded terminal report; its 98% reach and 60° yaw lines are check settings. The result depends on the canonical frame, model, numerical solver and limits, and is not a proof of physical executability. The selected simulation frames support visual discussion only.

No ACT evaluation figure is included in this set. Any separate retained ACT outcome must remain labelled as a historical source result because the exact trained policy checkpoint is absent.

## learning-records

Suggested caption: Conceptual record types for demonstration, reinforcement-learning transitions and evaluation. The categories describe intended use and available information; they are not mutually exclusive file formats. Place beside the comparison of learning objectives.

## tool-schema

Suggested caption: Declared pusher features comprise three position values and two rotation-matrix columns, plus the tool-camera image. This schema grouping does not guarantee compatibility across tools or robot embodiments. Place beside the nine-value pose definition and units.

## pilot-views

Suggested caption: First frames from episodes 0 and 2 of the supplied simulated handheld pilot video. The selected frames support visual inspection and do not provide an automatic visibility score. Place beside the discussion of learner observations and privileged simulator information.

## pilot-audit

Suggested caption: Saved numeric audit of the supplied ten-episode pilot. Dashed lines show the declared 0.25 m/s speed and 15 mm final-frame distance thresholds. This is a data audit and does not evaluate a trained policy. Place beside the separate speed, geometry and visibility acceptance decisions.

## pilot-reach

Suggested caption: Recorded canonical-frame IK/limit check. Reachability percentages come from the checker's rounded terminal output. The 98% and 60° lines are check settings, conditional on the frame, model, solver and limits. Place beside the interpretation of target-frame executability.

## episode-splits

Suggested caption: Illustrative episode-level split. Letters A–J are constructed identifiers, not the supplied pilot's training assignment. Place beside the explanation of split units and correlated adjacent frames.

## action-chunks

Suggested caption: Constructed replanning intervals at nominal 30 Hz for executing 1, 10 or 30 actions before taking another observation. The figure illustrates timing and does not rank observed policy success. Place beside the distinction between predicted and executed chunk length.

The [measurement audit](figure-source/measurement-audit.json) records numeric boundaries, input scope, PNG inspection and the copied classroom asset hashes. The [asset manifest](asset-manifest.json) records relative paths and SHA-256 hashes for the bundle, excluding the manifest itself.
