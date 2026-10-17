# Class05 figure reproduction

From `2026-autumn/resources/class05`, install source/requirements-figures.txt in a separate authoring environment, provide licensed MiSans Regular/Semibold locally, then run:

```sh
python code/draw_figures.py --font-dir /path/to/MiSans --output-dir ../../media/class05
```

All plot inputs are bundled CSV and saved lesson summary. Diagrams are conceptual. The two source images (physical_and_combined_simulation.jpg and aruco_assigned_view_detection.png) are retained unchanged. No font binaries are redistributed. Editable SVG text and embedded-font PDF masters accompany PNGs. The original figure generator is reproducible from the bundled inputs; it does not run fitting or make hardware measurements.
