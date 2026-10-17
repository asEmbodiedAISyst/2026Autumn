# Class 19 figure code

## Figure 1 — Trace the result through the experiment

**Teaching purpose:** explain why reconstructing a result requires its protocol and denominator, and why a selected replay, training and physical deployment are separate checks. This is an authored schematic review of retained simulation evidence, not a new evaluation.

**Generating entry point:** [`claim_to_evidence()` in generate_figure.py](generate_figure.py). The function produces both variants from the same input and layout. `main()` verifies the outcome sum, registers genuine MiSans faces and writes the outputs and provenance receipt.

**Outputs:**

| Variant | Canvas | Files |
| --- | --- | --- |
| Paper master | 182 × 96 mm; 7 pt body; 8 pt panel letters | `claim-to-evidence-paper.svg`, `.pdf`, `.png` |
| Classroom | 364 × 192 mm; 14 pt body; 16 pt panel letters | `claim-to-evidence-classroom.svg`, `.pdf`, `.png` |

The PNG files use 450 dpi. SVG retains text; PDF embeds TrueType fonts. Captions remain in the lesson.

### Inputs and processing

[`source-data/class06-first-goal-summary.json`](source-data/class06-first-goal-summary.json) is an unmodified copy of the [retained Class 06 summary](../../resources/class06/code/results/native-task-10ms-noisy-heldout/summary.json). It identifies the supplied policy, versions, seed range, evaluator and 100 completed native-simulation episodes. Values plotted are the exact counts: 88 first-goal successes, 12 timeouts and zero falls. No filtering, selected episodes, interpolation or uncertainty calculation is performed. The denominator is 100 completed episodes; the plot does not estimate performance on hardware or under other protocols.

The retained configuration supplies the original observation-noise condition, 0.1 rad threshold and 1000-control-step limit. At 20 Hz this limit is 50 simulated seconds. The comparison with the continuous replay and with training/hardware is a schematic explanation of scope, not additional plotted experimental data.

### Reproduce the figure

Run from this `media/class19/` directory in an isolated environment. The tested versions were Python 3.12, Matplotlib 3.11.2, NumPy 2.5.4, Pillow 12.3.0 and fontTools 4.67.0. Supply locally licensed native MiSans Regular and MiSans Semibold TTF files using the two environment variables below; the font files are not redistributed with this illustration.

```sh
python generate_figure.py \
  --font-regular "$MISANS_REGULAR" \
  --font-semibold "$MISANS_SEMIBOLD" \
  --input source-data/class06-first-goal-summary.json \
  --out .
```

`figure_typography.py` applies `publication.mplstyle` and rejects a different font family. The renderer restricts MiSans resolution to the two supplied faces, preventing an installed Bold face from replacing the requested Semibold face. The source fonts use internal numeric weights that differ from conventional CSS weight numbers; the genuine face names and SHA-256 values are recorded in `figure-provenance.json`. SVG viewers require MiSans installed; the PNG is the fixed delivery preview.

### Checks

Rendering performs plotting only. It does not simulate, load a policy, train a model or repeat the 100-episode evaluation. Compare all three counts with the input summary, verify their sum is 100, and inspect labels, denominator, arrows and scope boundaries at final size. Paper and classroom variants must encode identical counts and conditions. Inspect the PDF’s embedded fonts and SVG text retention. The provenance receipt identifies input and output hashes and the actual native font files.

Verified on 17 October 2026: the generator completed all six outputs from the declared JSON input. The paper and classroom PNGs were visually inspected; labels, count values, arrows and margins were checked. The paper SVG retained 36 text objects. The paper PDF declares embedded MiSans Regular and MiSans Semibold TrueType font streams (`FontFile2`), with no other font family. Matplotlib reported the source fonts’ numeric weight mapping (330 and 520); the receipt confirms the genuine Regular and Semibold files were used. These are figure-generation checks, not a fresh scientific evaluation.
