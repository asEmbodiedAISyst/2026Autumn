# Class 08 figure code and inputs

The six inline classroom figures are supplied as PNGs, editable SVGs and PDF masters. They use the retained Class 08 data and native simulation renders. No physical-arm result is represented.

| Figure | Type and input | Code entry |
| --- | --- | --- |
| model-pipeline | Conceptual description-to-experiment chain | `flow([...])` |
| arm-poses | Native zero/home renders, same camera | `arm_poses` |
| joint-limits | Compiled ranges and declared software limits from inspection.json | `joint_limits` |
| control-loop | Conceptual feedback path | `feedback_loop` |
| joint-response | All 180 pre-step joint2 trace rows | `joint_response` |
| control-clock | Declared stepping arithmetic | `control_clock` |

The portable [rendering entry point](figure-source/render_class08.py) selects the retained functions in [lecture_figures.py](figure-source/source/lecture_figures.py). Its exact function mapping and the supplied inputs determine each output. The [reproduction notes](figure-source/README.md) describe dependencies and the external licensed MiSans font requirement.

From figure-source, use the plotting environment and licensed local font files:

```sh
python -m pip install -r requirements-plotting.txt
python render_class08.py --font-dir /path/to/authorised/MiSans/fonts
```

This replot reads the retained images, inspection and CSV rather than rerunning physics. To regenerate simulation records, use the Class 08 simulation resource commands on the lesson page. The published images retain their original pixels/vector content; a new plot writes a new font receipt rather than asserting byte-identical typography.

The signed trace residual is pre-step position minus the paired target. Its maximum absolute value is 1.3264337276199711 degrees. The current controlled-motion runner uses seventeen steps of 1/510 s per update. Older post-step plots from the 34 ms implementation are excluded from the inline figure set.

The [asset manifest](asset-manifest.json) records the public bundle's relative paths and SHA-256 hashes. The [measurement audit](figure-source/measurement-audit.json) records the trace boundary and calculations.
