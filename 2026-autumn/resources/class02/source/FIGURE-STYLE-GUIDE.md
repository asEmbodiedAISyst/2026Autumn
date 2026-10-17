# Course figure standard: publication-quality scientific artwork

Standing course-wide standard, 4 October 2026: develop all new or revised course figures as if preparing a research paper, using MiSans for every authored text element. This applies to plots, diagrams, schematics, model illustrations and simulation panels. A figure must communicate a defensible technical claim and remain legible at its final output size. A clean theme alone does not establish publication quality.

## Tools and source of truth

Use Matplotlib for measured plots, spatial schematics and reproducible panel assembly; NumPy for numerical processing; Pillow for actual recorded-frame handling. Retain source data, scripts, source/policy identities and evidence of any filtering or selection. Maintain editable SVG and PDF masters, with PNG previews for Markdown. A recorded simulation is distinct from a schematic; identify which each panel represents.

The reusable `publication.mplstyle` establishes baseline typography and strokes. It does not resize existing figures, remove titles, rearrange annotations, increase the true resolution of recording frames, verify data, or certify journal compliance.

## House specification

| Element | Default | Verification |
| --- | --- | --- |
| Canvas | Single column 88.9 mm; double column 182 mm | Design directly at output size; apply the chosen journal's dimensions when preparing submission |
| Typography | MiSans Regular; 7 pt body labels; MiSans Semibold 8 pt lower-case panel letters | Inspect at actual final size, including mathematical glyphs |
| Strokes | Data lines about 0.8 pt; axis lines about 0.6 pt | Preserve readability in grayscale and export |
| Layout | White background, aligned panels, useful whitespace, short in-panel labels | No overlap, unnecessary borders, decorative shadows, large embedded headlines or clipped annotations |
| Colour | Consistent categorical mapping; redundant markers/line styles; perceptually appropriate sequential/diverging maps | Check contrast, colour-vision accessibility and grayscale meaning; never rely only on red/green distinctions |
| Axes | Quantity and units, truthful scales, visible ticks | State logarithmic scales, coordinate frames and normalization; avoid misleading truncation |
| Statistical evidence | Denominator, seed/trial unit, relevant uncertainty and all material failures | Distinguish confidence intervals from SD/SEM and descriptive variability; disclose selected examples |
| Outputs | Editable PDF/SVG plus raster preview | Embed TrueType fonts in PDF; retain SVG text as text |
| Raster resolution | Default 450 dpi at final size for image panels; prefer vector line art | IEEE needs >300 dpi colour/grayscale and >600 dpi monochrome line art; use 1200 dpi if monochrome must be raster |
| Image content | Native high-resolution render/capture, with separate annotations | Do not upsample an old frame and describe it as newly resolved detail |
| Caption | What, conditions, units, sample size, uncertainty and interpretation boundary | Place long explanations in surrounding Markdown/caption, not inside plot |

These are course defaults informed by Nature and IEEE, not a universal journal requirement. Nature specifies body text 5–7 pt and panel labels 8 pt; a different target journal can override size and layout. MiSans remains the course font; any conflicting submission font requirement must be identified explicitly before producing a separate journal-specific version. IEEE column widths are used above; confirm the publication-specific template before submission.

Create the paper master first. Generate a larger classroom presentation variant from the same data and layout, with readable presentation text. The paper and classroom versions must retain identical data, conditions and meanings; simply shrinking an oversized lecture image does not produce a paper figure.

## Required typography: MiSans

MiSans is mandatory across all future course figure, plot, illustration and animation generation. Use MiSans Regular for labels, axes, ticks, legends, annotations and mathematical labels; use MiSans Semibold for panel letters and emphasis. Newly authored simulation/video overlays follow the same rule. Classroom and paper variants use the same family.

- Configure the renderer explicitly. Do not silently fall back to Arial, Helvetica, DejaVu Sans, Computer Modern or STIX.
- Register genuine MiSans TTF/OTF files when the plotting environment cannot discover them. Web WOFF2 assets used by the application are not evidence that the native plotting renderer has MiSans available.
- Run `figure_typography.py` before rendering. It rejects unresolved or incorrectly substituted font families. Register both regular and semibold files for the corresponding weights.
- Configure mathematical text to use MiSans and disable math-font fallback. Verify the actual glyphs in each equation. A missing glyph or unavailable weight must be resolved explicitly before release; a silent substitute is not acceptable.
- Keep TrueType fonts embedded in PDF. Retain SVG text as editable text and ensure MiSans is available to the viewer; check the exported result on the delivery system. Editable SVG appearance is not guaranteed by a font-family declaration alone.
- Record the exact font files, version/hash and export font checks with figure provenance. Use appropriately licensed fonts, retain required attribution, and check redistribution terms before bundling font software. The course materials use MiSans by Xiaomi.
- Historical/source screenshots retain their original typography as evidence. Any new overlays or regenerated screenshots must use MiSans.

Apply this standard consistently in every later class and revision. The guide and shared style are authoritative; individual scripts must not redefine another family after applying the style. In addition to preflight, inspect all rendered text and mathematical symbols at final size.

## Mandatory per-figure generation documentation

Every generated figure, illustration, plot, schematic, animation and video must have documented generating code saved alongside its class assets. This is a standing requirement for each individual output, including figures assembled by a shared script. An image or source-code file without a clear reproduction entry is insufficient.

For every figure record:

1. Figure identifier, purpose and output filenames.
2. A link to the generating source and exact function, entry point or clearly named source section. Shared scripts are allowed only when each output is explicitly mapped to its generating code.
3. An exact runnable command and working directory, with parameters, seed and output location.
4. Input data/model/assets with relative paths, provenance and versions/hashes; explicitly identify synthetic or schematic inputs.
5. Environment and pinned dependencies, font/style configuration and MiSans registration/preflight requirements.
6. Processing choices: filtering, pairing, aggregation, uncertainty calculation, normalization, frame selection and any manual editing.
7. Expected outputs and meaningful validation checks. State whether rerunning performs plotting only or executes simulation/training.

Place the readable entries in the class's `media/FIGURE-CODE.md` (or an equivalent per-figure README). Link each lesson figure/caption to its entry and source. Include scripts, configurations and accessible input data in the distributable material whenever their access/licensing permits. Keep restricted inputs private and explain the dependency explicitly rather than claiming full reproducibility. Any manual vector edits must retain the editable source and documented steps; prefer encoding layout changes in source code.

A figure is complete only when its visual review, data/provenance verification and generation-code documentation are complete. Code must recreate the figure from its declared inputs without hidden session state or unrecorded edits. Record verified reproduction separately from merely providing a command.

## Scientific content rules

- Every plot identifies its measured quantity, units, experiment condition and statistical unit.
- Success percentages retain the full denominator, including timeout/fall outcomes; uncertainty is stated precisely.
- Paired comparisons retain the pairing; different engine versions are reported rather than attributed to backend alone.
- A selected successful episode remains labelled selected; it cannot represent overall reliability.
- Geometric schematics declare frames and distinguish intended vectors from measured forces.
- Simulation screenshots use consistent camera/view when comparing variants; annotate the manipulated object and target without obscuring evidence.
- Multiframe panels disclose frame selection and time mapping; never imply unverified events from a visual frame alone.

## Authoring and release workflow

1. State the figure's technical question and choose a truthful plot or diagram.
2. Declare final physical dimensions and allocate panels before drawing.
3. Generate from versioned data/script; apply the shared style, then refine labels/layout manually in code. Write the per-figure source/input/command entry alongside the asset.
4. Export editable PDF/SVG and adequate-resolution PNG. Retain the numerical source and provenance.
5. Review at final paper size, course-page size, grayscale and with colour-vision accessibility checks.
6. Verify numbers, uncertainty, labels, units, frame definitions, caption and visual selection against the source.
7. Inspect rendered exports for fonts, collisions, clipping and raster image quality. Only then label the figure publication-ready.

## References

- [Nature research figure specifications](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/): typography, labels, accessibility, image integrity, RGB, editable vectors and fonts.
- [IEEE graphics resolution and size](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/resolution-and-size/): vector graphics, raster requirements and physical column dimensions.
- [Matplotlib colormap guidance](https://matplotlib.org/stable/users/explain/colors/colormaps.html): perceptual suitability of continuous maps.

Checked 4 October 2026. Recheck target-journal requirements when preparing an actual submission.

## Worksheet canvases and document diagrams

The Classes 12–17 workbook uses ReportLab for page geometry and schematic vector masters. This document-layout exception retains genuine MiSans Regular/Semibold, embedded PDF fonts, editable SVG text, 182 mm scientific diagram masters at 7 pt and 450 dpi PNG previews. A4/A3 writable canvases use larger type for print. Worksheet page previews are document renders, not measured research plots. The per-output code index and provenance remain required.
