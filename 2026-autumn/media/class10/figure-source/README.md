# Class 10 portable plotting inputs

This folder retains only the functions, style and saved inputs required to replot the seven classroom figures. It does not contain instructor answers, review drafts, training code or trained policy weights. The numeric audit JSON and canonical-frame IK text are saved source records; replotting them does not recompute either check.

Install the plotting dependencies in a local Python environment, then run:

```sh
python -m pip install -r requirements-plotting.txt
python render_class10.py --font-dir /path/to/authorised/MiSans/fonts
```

The external font directory must provide licensed `MiSans-Regular.ttf` and `MiSans-Semibold.ttf`. Font files are not redistributed in this bundle. The preflight requires the MiSans family and records the faces actually resolved. The retained source receipt resolves its semibold request to `MiSans-Bold.ttf`; that receipt describes the copied source figures. A rerender writes its own font receipt and may differ in typography or file metadata. SVG text requires an installed MiSans family for matching appearance; PDF masters retain embedded font data.

The output directory defaults to `media/` inside this folder; `--output-dir` can select another destination. Eighteen published PNG/SVG/PDF assets one level above are copied unchanged from the source. The three `action-chunks` formats were regenerated after correcting the legend from “Execute 1 steps” to “Execute 1 step”; values, arithmetic and geometry are unchanged. The source's seven plotting functions retain their original values and image panels. The entry point replaces the class-folder selector with an explicit seven-figure list.

`data/pilot-nominal.png` and `data/pilot-turned.png` are complete selected simulation video frames, without retouching. `evidence/image-inputs.json` records video identity, frame indices and nominal time offsets; the source video is outside this minimal plotting bundle. The frames establish what those selected observations show and do not establish whole-episode visibility.

`results/pilot-audit.json` reports 10 episodes and 638 frames. Its final saved distance is a geometric check, not a complete episode outcome. `data/target-frame-reachability.txt` is the rounded recorded report for a particular canonical frame, robot model, solver and limits. Reachability fractions do not certify collision, contact, effort, dynamics or full demonstration acceptance.

The portable subset was successfully rendered with the tested package versions in `evidence/portable-replot-check.json`. The six unchanged PNGs reproduced pixel for pixel; the corrected action-chunks PNG was inspected directly. `measurement-audit.json` records numeric boundaries, direct PNG review, original asset hashes and the three corrected hashes. `../asset-manifest.json` supplies relative paths and SHA-256 hashes for this complete figure bundle. The manifest excludes itself.
