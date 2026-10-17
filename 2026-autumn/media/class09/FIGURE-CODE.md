# Class 09 figures

Seven figure families; classroom PNGs are displayed on the single lesson page. PDF/SVG masters and paper PNGs are retained here. No font software is redistributed.

## Reproduction

Use a separate authoring environment with resources/class09/source/requirements-figures-macos.txt and locally licensed MiSans Regular/Semibold. Run in a working copy of resources/class09 with the fonts in source/fonts. The retained source/lecture_figures.py produces the original six families from the two bundled recording CSVs. Its teleop-path, phone-axes and recording-order branches are superseded by source/draw_lesson.py, which also creates episode-views:

```sh
python source/lecture_figures.py --class-root .
python source/draw_lesson.py --root . --fonts /path/to/MiSans
```

Both write local media/ outputs. Published media are ../../media/class09. Rendering uses no hardware, policy training or external data download. The source generator infers class09 from the folder name.

## Interpretation

- teleop-path: conceptual command and response branches; no measured latency claim.
- phone-axes: independent frame-axis drawings plus declared C mapping; not measured calibration or a shared spatial orientation.
- motion-limit: constructed 0.25m/s at nominal30Hz gives8.33mm target-step bound.
- recording-order: observe/render/save before physics transition, checked against bridge code.
- command-state: all170 rows from retained circle, elbow action negated before motor-state comparison.
- stream-record: circle row intervals above, receiver age from a separate dropout run below; no synchronization between panels.
- episode-views: unretouched front/side frame000000 from retained circle, each640×480 RGB. Atomic raster camera panels are preserved inside editable PDF/SVG compositions.

Genuine MiSans typography is recorded in resources/class09/evidence/figure-fonts.json. New generator and all data inputs are bundled in the current student repository. Live GitBook verification is recorded separately in the class evidence folder.
