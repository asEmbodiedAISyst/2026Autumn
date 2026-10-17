# Class 07 figure reproduction

From `resources/class07`, use an authoring environment with source/requirements-figures.txt and locally licensed MiSans Regular/Semibold. No font binaries are bundled.

Seven retained figure families use `source/lecture_figures.py`, which expects the licensed fonts in source/fonts and reads the bundled results. Run it on a working copy; its original frame-chain branch is superseded by the geometric example below. It writes local media/ outputs. Published student media are in ../../media/class07.

The frame illustration uses:

```sh
python code/draw_frames.py --font-dir /path/to/MiSans --output-dir ../../media/class07
```

This produces paper/classroom PNG,PDF and editable SVG for the declared 90-degree camera-to-hand point transform. It contains synthetic geometry,not tracked measurements.

Other generator branches: vision-loop,packet-age,pinhole-points,pnp-sensitivity,observation-interface,feedback-diagnostic,retargeting. Diagrams are conceptual. PnP plots use the supplied500synthetic trials. Feedback plots read all selected native trace rows and retain the dropout run's early termination. No plotting command executes training or hardware control. Numerical reruns and their evidence are documented on the student page and in resources/class07/evidence/.
