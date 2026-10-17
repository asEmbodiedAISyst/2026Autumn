# Class08 retained figure source

The six published classroom PNG/SVG/PDF files are unchanged copies from the current Class08 media directory. The SVGs preserve editable text, paths and shapes. The arm-pose SVG contains two atomic native-rendered images plus editable panel labels; the robot pixels are simulation output rather than vector geometry.

The [figure-code map](../FIGURE-CODE.md) identifies each plotting function. The [asset manifest](../asset-manifest.json) records public relative paths and SHA-256 hashes. `measurement-audit.json` records the current trace boundary and exact values. `evidence/figure-fonts.json` retains the original font receipt; `evidence/image-inputs.json` records the image camera and joint configurations.

## Replot from the retained inputs

Install `requirements-plotting.txt` in a Python environment and supply licensed local MiSans Regular and Semibold font files:

```sh
python render_class08.py --font-dir /path/to/authorised/MiSans/fonts
```

This portable entry point calls the six selected functions in `source/lecture_figures.py`. The public source subset preserves their plotting operations and data selection. It plots the retained CSV, inspection JSON and raw arm frames; it does not rerun physics. Outputs are written below this folder in `media/` for comparison, leaving the published copies intact.

MiSans binaries are not bundled here because the available source font note does not include its redistribution licence. PNGs retain the original appearance. Editable SVG text needs MiSans to keep that appearance. The source font receipt records the resolved semibold face as `MiSans-Bold.ttf` (SHA-256 `d0c1d327952ed935e86fb78a97a6c182b44f2c2b08777326786b1f8b26d1fe1e`), whereas the retained course font dependency is `MiSans-Semibold.ttf` (SHA-256 `77c23f31ae124867778344970155a0c8d34a89897dedaab81aeee82ff00a4ce6`). The source receipt is preserved as evidence; no claim of byte-identical rerendering is made. A new render writes its own font receipt.

`requirements-plotting.txt` lists the Python plotting dependencies. The portable entry point has been syntax checked. No plotting environment was installed for this delivery; the published images were copied and visually checked.

## Scope of raw reproduction

This bundle supports replotting retained evidence. To generate new simulation records, use the simulation resource and commands on the lesson page. The exact retained image camera and joint vectors are in `evidence/image-inputs.json`; its model field identifies the source course model, which is not bundled here.

The trace contains 180 pre-step rows from 0 to 5.966666666666646 s, with 17 physics steps of 1/510 s per control update. The final update advances simulation time to 6 s. The signed residual is pre-step state minus the target selected for the same upcoming update. Its maximum absolute value is 1.3264337276199711 degrees. No filtering or alignment shift was used.

Older `joint2-tracking` and `joint-errors` figures are intentionally excluded: their evidence belongs to a 2 ms, 17-substep run (34 ms per update), not the current exact nominal 30 Hz trace. The control-clock figure explicitly compares that older arithmetic with the corrected period; it measures no operating-system scheduling.

All six current classroom PNGs were inspected for labels, clipping and content. They contain no lecture-duration labels. Quantitative axes state physical simulation time or angle. No artwork or quantitative evidence was changed.
