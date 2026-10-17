# Class 20 figure code and provenance

## Figure 1 — Explain a selected episode without overstating its result

**Teaching question:** how can a scientific video identify the task, show relevant behavior and state what the evidence supports?

| Output | Role | Generating function |
| --- | --- | --- |
| `course-video-storyboard-paper.svg`, `.pdf`, `.png` | Editable 182 mm paper master and 450 dpi preview | `source/make_figures.py::storyboard` |
| `course-video-storyboard-classroom.svg`, `.pdf`, `.png` | Larger classroom version and 170 dpi preview | The same function, same data, same text |

The source frames are retained course Class 06 native-MuJoCo renders, rather than images from the LEAP RSS 2023 paper or video. The source episode is seed 9204, zero added observation noise, 1000 control steps at 0.05 s per step. The retained summary reports two goal events and timeout. It is one selected episode, not an across-trial reliability estimate. The task's displayed goal may change after an event, and the rendered pose is not the event measurement.

Source rendering uses a supplied upstream ONNX policy, with policy hash and Playground commit recorded in [figure-provenance.json](figure-provenance.json). The course does not claim to have trained this policy. The class figure assembly does not execute a simulator, train a policy or operate hardware.

### Inputs and processing

The unchanged 1920 × 1080 source renders are `source/frames/step-0001.png`, `step-0356.png` and `step-1000.png`. SHA-256 identities are in the provenance file. All three use the same crop `(400, 440, 1460, 1080)` to remove blank floor while retaining the hand and displayed goal. Source poses, colors and textures are unchanged. The course adds vector labels, arrows and explanatory text. PNG delivery images do not create new detail in the underlying frames.

The course rendering uses LEAP assets from MuJoCo Menagerie and task/policy material from Google DeepMind's MuJoCo Playground. See the [pinned Playground source](https://github.com/google-deepmind/mujoco_playground/tree/ef4fefc13033c0468af4ef651847f5348af0c7d7) and [Menagerie](https://github.com/google-deepmind/mujoco_menagerie). Playground uses Apache-2.0; the retained LEAP asset license is MIT, copyright 2023 Ananye Agarwal. Their notices are retained as `source/PLAYGROUND-LICENSE` and `source/LEAP-ASSET-LICENSE`. The course's lettered-cube artwork is an added visual aid; the policy does not receive the letters as image observations.

### Reproduce the assembly

Working directory: this `2026-autumn/media/class20/` folder. Supply locally licensed genuine MiSans Regular and Semibold TTFs in a directory identified by `MISANS_FONT_DIR`; font software is not redistributed here. The [official MiSans site](https://hyperos.mi.com/font/en/download/) provides the font and terms.

Verified dependency versions: Python 3.12, Matplotlib 3.11.2, Pillow 12.3.0. The supplied `source/figure_typography.py` registers the explicit native font files and refuses a family or style substitution. The plotting code assigns the exact Regular/Semibold font files rather than relying on weight matching against a system font cache. `source/publication.mplstyle` supplies the remaining course style.

```bash
python3 source/make_figures.py --font-dir "$MISANS_FONT_DIR"
```

Expected result: the six listed exports and `figure-provenance.json`. Reproduction assembles artwork only. It requires no simulator or network access. PDF embeds TrueType font subsets; SVG preserves editable text and requires the licensed font on the viewing system.

### Verification performed

Both variants were generated and regenerated on 17 October 2026. The classroom PNG was inspected for correct object arrows, readable captions, aligned panels and clipping. The PDF font resources identify MiSans Regular and Semibold, with two embedded FontFile2 resources. The provenance records the actual native font hashes. No RSS video or research image was downloaded or redistributed to create this illustration.
