# Class11 figure reproduction

Use a separate authoring environment with resources/class11/source/requirements-figures-macos.txt and locally licensed MiSans Regular/Semibold. No font software is bundled.

From a working copy of resources/class11 with MiSans fonts in source/fonts, run:

```sh
python source/lecture_figures.py --class-root .
python source/draw_lesson.py --root . --fonts /path/to/MiSans
```

The original generator infers class11 from the folder name and plots six retained families. The second script creates latency-budget and reset-comparison. Both write local media/ outputs; published assets are ../../media/class11. No plotting command runs training or powered hardware.

## Inputs and interpretation

- latency-budget: constructed20+40+20ms and constant0.10m/s travel; not measured latency.
- reference-choice: constructed10mm target increments, half-error tracking per tick; not robot data.
- evidence-checks: conceptual sequence; not a universal hardware requirement or readiness score.
- replay-components: model/integration state/same commands schematic, backed by results/replay-state.json.
- reset-comparison: actual new simulation experiment, code/compare_reset.py, results/reset-comparison.json/.csv. Compares the same scripted reference with full integration restoration and a deliberately incomplete qpos-only reset. Initial cube vx0.20m/s; observed maxima0 and4.932266mm. No physical-friction identification or learned-policy claim.
- stored-outcomes: complete50binary outcomes from consolidation/package/additional_material/data/videos/results_act_ip17_cube300_handheld_060000_pusher_n100.json, summarized in results/recorded-policy-summary.json. Wilson interval descriptive only under independent comparable-trial assumptions.
- failure-frames: left640×480policy-view crop of full1280×480 episode0 video at frames0,225,449. Native frame sources remain under data/. No retouching. Both complete success/failure clips are included. Video/frame exact-pixel checks are in evidence/video-check.json.
- next-experiment: conceptual hypothesis→controlled variation→prediction→claim sequence.

Genuine MiSans font receipt: resources/class11/evidence/figure-fonts.json. New and retained generators preserve editable vector text/shapes while native camera frames remain atomic raster panels. The exact deployed checkpoint/processors are not included; visualizations of stored policy outcomes are not fresh policy evaluations.
