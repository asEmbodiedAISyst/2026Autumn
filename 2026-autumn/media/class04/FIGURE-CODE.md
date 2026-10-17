# Class 04 figure generation

All authored text uses the bundled MiSans. Fonts and license are in `../../resources/class04/code/fonts/`. These figures explain a declared response comparison; none depicts a measured shaft torque or an independently calibrated motor model.

| Figure | Packaged file | Source and generator |
|---|---|---|
|1 selected G1 response |`xc330-H1-G1-P06.png`|H1/G1/P06/R01 paired CSV; `code/figure_plots.py`|
|2 signal boundary |`comparison-boundary.png`|Conceptual signal map, not an acquired measurement; `code/draw_boundary.py`|
|3 matched P06 contrast |`xc330-matched-P06.png`|B1 and G1 first repeats from the two CSVs, with their own initial states/references; `code/figure_plots.py`|
|4 condition summaries |`xc330-condition-means.png`|Published per-episode scores regrouped in `data/xc330-98g-heldout-condition-metrics.csv`; `code/figure_plots.py`|
|B1 standalone companion |`xc330-H1-B1-P06.png`|Same B1 CSV; `code/figure_plots.py`|

From the Class04 resource folder in the isolated analysis environment:

```bash
python code/figure_plots.py --output-dir figure-output
python code/draw_boundary.py --output-dir figure-output
```

The commands write PNG, SVG and PDF variants in `figure-output/`, leaving released media/data untouched. They use packaged CSVs and produce no new hardware evidence or parameter fit. SVG text is converted to paths for reliable distribution; the Python source retains editable labels. Plot generation requires NumPy2.2.6 and Matplotlib3.10.3, pinned in `code/requirements-analysis.txt`.
