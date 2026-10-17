# Class 02 supporting resources

The main lesson remains at [02 Actuator Basics for Controlled Action](../../module-01-actuator-data-for-1-dof-systems/02-actuator-basics-for-controlled-action.md).

Use [RUN.md](RUN.md) for optional offline analysis, [activity.md](activity.md) for inspection and comparison, [telemetry-worked-example.md](telemetry-worked-example.md) for conversions and [reading-notes.md](reading-notes.md) for deeper motor/response analysis. No hardware is operated by the supplied analysis commands. Prepare an isolated virtual environment before running optional tools.

Figure code: `code/lesson_figures_v08.py`. Source photographs are under `media/hardware-source/`, CSV/JSON records under `data/xc330-hardware-demo/`, and MiSans setup under `source/fonts/`. `python code/lesson_figures_v08.py classroom` regenerates the six figures; paper variants use `paper`. All new figure text is explicitly MiSans. Existing copies of the plotted figures support offline reading; the GitBook page uses the publication copies under `.gitbook/assets/class02/`.

Source functions: `hardware_identity`, `telemetry_motion`, `communication_parts`, `connection_inspection`, `telemetry_electrical` and `telemetry_environment`. The complete 2,601-row record is retained; the reversal window is 1.1–2.1 seconds and the marked sample is original row 400. No new measurements or synthetic trials are introduced.

Earlier response/identification code is supporting material for later classes. The required Class 02 activity remains unpowered inspection and exact-model comparison.

The consolidated lesson also restores the platform overview, functional command architecture, manufacturer performance-curve reading, detailed ID/baud/daisy-chain explanations, six-channel telemetry and the XC330 control-table quick reference. [Figure sources and regeneration](media/FIGURE-CODE.md) distinguish reused source images from authored plots.
