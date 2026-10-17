# Class 18 poster teaching figures

These outputs teach poster composition and interpretation. They reuse retained Class 06 simulation evidence. Plotting does not run a policy, simulate a new episode, train a model or operate hardware. The deliberately flawed composition is a labelled teaching example, not a scientific claim.

## Reproduce the outputs

Working directory: this `media/class18/` directory. Use CPython 3.12.14 with the versions in [source/requirements.txt](source/requirements.txt). Supply locally licensed native MiSans font files; font software is not redistributed here.

```sh
python source/generate_class18.py --font /path/to/MiSans-Regular.ttf --font /path/to/MiSans-Semibold.ttf
```

The script calls [source/figure_typography.py](source/figure_typography.py) before rendering, using [source/publication.mplstyle](source/publication.mplstyle). It limits MiSans lookup to the explicitly supplied faces so that a host's other MiSans weights cannot change the export. It checks the resolved family and every authored glyph, retains SVG text, and embeds TrueType fonts in the PDF. The supplied faces have nonstandard internal weight numbers; Matplotlib reports weight matching while continuing to resolve the actual MiSans Regular and Semibold files. Filename and SHA-256 receipts are in [provenance.json](provenance.json).

## Per-output map

| Teaching figure | Source entry point | Outputs | Dimensions and processing |
|---|---|---|---|
| Full flawed poster | `posters()` → `draw_poster(revised=False)` | `poster-before-a0.png`, `.svg`, `.pdf` | A0 portrait, 841 × 1189 mm. Deliberately excessive background, unsupported title and missing context are explicitly identified as errors. Same retained number and selected frame as the revision. PNG preview at 100 dpi; PDF/SVG masters retain vectors and source-resolution image. |
| Full revised poster | `posters()` → `draw_poster(revised=True)` | `poster-after-a0.png`, `.svg`, `.pdf` | A0 portrait, 841 × 1189 mm. A bounded contribution, declared first-goal protocol and outcome composition replace the flawed framing. All 100 outcomes remain visible. No filtering or changed success criterion. |
| Figure 1, poster composition comparison | `comparison(mode)` | `poster-comparison-paper` and `poster-comparison-classroom`, each `.png`, `.svg`, `.pdf` | Paper: 182 × 142 mm at 450 dpi; classroom: 364 × 284 mm at 200 dpi. Two complete poster compositions rebuilt from the same vector drawing function. Miniatures communicate reading path; use the A0 masters for text inspection. |
| Figure 2, result and caption close-up | `evidence_detail(mode)` | `evidence-detail-paper` and `evidence-detail-classroom`, each `.png`, `.svg`, `.pdf` | Paper: 182 × 88 mm at 450 dpi; classroom: 364 × 176 mm at 200 dpi. An intentionally incomplete percentage is compared with its interpretable trial result. No change to numerical evidence. |

## Inputs and scientific identity

- [inputs/summary.json](inputs/summary.json) and [inputs/episodes.jsonl](inputs/episodes.jsonl) are exact copies of the existing Class 06 `native-task-10ms-noisy-heldout` evidence under `resources/class06/code/results/`. The generator checks 100 rows, seeds 20000–20099, 88 successes, 12 timeouts and no falls against the summary. Outcome categories form a composition of all trials, rather than a truncated-axis comparison. The posters report the observed outcomes and their evaluation protocol.
- Policy SHA-256: `1893e4a0f3b95f1657ce5e11745db0ac8749c8780d83013859082c414cb5f97f`. Task source: [MuJoCo Playground at commit ef4fefc13033c0468af4ef651847f5348af0c7d7](https://github.com/google-deepmind/mujoco_playground/tree/ef4fefc13033c0468af4ef651847f5348af0c7d7). The retained evaluation used native MuJoCo 3.6.0, the `native-task` adapter, original observation noise, 0.01 s physics steps and a 0.05 s control interval. It evaluates a supplied pretrained actor, not training performed for these posters.
- [inputs/selected-step-0356.png](inputs/selected-step-0356.png) is the exact retained 1920 × 1080 native rendering from Class 06 seed 9204 at control step 356. This selected frame is separate from the 100-trial evaluation. It illustrates the simulated hand, held cube and separate goal; the pose alone is not the evaluator's measurement. Placement preserves its aspect ratio and does not invent additional detail. No crop, retouch or new simulation rendering is performed.
- The frame is an existing course rendering of the retained LEAP simulation and face artwork. Source-model and upstream software notices remain with the [Class 06 package](../../resources/class06/README.md). The composition and annotations are course-authored teaching artwork; attributed evidence remains distinguishable.

## Verified reproduction

All six canvases were generated and inspected as PNG exports; PDF dimensions were checked as A0 for the full posters. Outcome counts were checked against all episode records. Authored glyph preflight resolved only the supplied genuine MiSans faces. SVG exports retain native text; PDF exports use embedded TrueType subsets. The paper and classroom variants retain the same evidence and wording. The process regenerates artwork only.

The machine-readable provenance records input/output SHA-256 hashes and actual font filenames and hashes. It contains no local installation paths. A new run may change metadata timestamps in PDF/SVG exports while preserving the scientific content.
