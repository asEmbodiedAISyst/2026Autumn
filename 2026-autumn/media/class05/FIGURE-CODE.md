# Class 05 current figure code and source record

The ten illustrations in the current lesson are retained; this review preserves the original figure topics and nine image families. Figure 8 now pairs positions with signed residuals; its data are unchanged. All authored figure text uses MiSans. The two source visual composites/detections retain their original typography and evidence status.

| Figure | File | Source or generator |
|---|---|---|
|1 physical arrangement|physical_and_combined_simulation.jpg|Retained supplied campaign views and scene composite; visual context, not a new dynamics measurement|
|2 scale of evidence|evidence-scale-classroom.png|`code/draw_figures.py`, conceptual comparison|
|3 replay boundary|replay-boundary-classroom.png|Same generator; declared input/output boundary|
|4 actuator model and policy|neural-actuator-classroom.png|Same generator; conceptual distinction, no Class 05 learned weights|
|5 experiment units|experiment-units-classroom.png|Same generator;30 events×16 motors×2predictions|
|6 motor population|population-errors-classroom.png|Same generator; held-out means from supplied metrics|
|7 effective armature|effective-armature-classroom.png|Same generator;32 selected source vectors|
|8 selected trajectories|paired-traces-classroom.png|Same generator; selected G1/H1/P06/R01 CSV, motors0and9; positions and signed residuals, common residual scale|
|9 marker detections|aruco_assigned_view_detection.png|Retained source detection composite; no optical calibration claim|
|10 measurement chains|measurement-chain-classroom.png|Same generator; conceptual encoder/optical comparison|

Run the data lab before regenerating plots. From the class resource folder, in the isolated figure environment:

```sh
python code/lesson_lab.py
python code/draw_figures.py --font-dir /path/to/MiSans --output-dir figure-output
```

The font folder must contain genuine MiSans-Regular.ttf and MiSans-Semibold.ttf. The generator checks their family and hash through `source/figure_typography.py`, exports classroom/paper PNG, editable-text SVG and embedded-font PDF, and saves a font-check receipt. Dependencies are pinned in `source/requirements-figures.txt`. Use the bundled private fonts or licensed local fonts for the public package. No new figure, hardware record, simulation or fit is created by replotting saved evidence.

The original local explorer and older figures/generator are retained separately for historical and optional use; their generation instructions do not supersede this current list.
