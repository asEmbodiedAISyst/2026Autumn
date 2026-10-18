# Class 04 scientific resources

The [Class 04 lesson](../../module-01-actuator-data-for-1-dof-systems/04-basic-quantification-of-sim2real-gap.md) contains the complete explanation, equations, figures, demonstration and student activity. These records support the same reasoning without requiring a new experiment.

| Evidence case | Supplied records | Interpretation boundary |
|---|---|---|
| Retained 98 g XC330 | [G1 activity samples](data/xc330-98g-H1-G1-P06-R01.csv), [B1 comparison samples](data/xc330-98g-H1-B1-P06-R01.csv), [frozen model configuration](data/xc330-98g-model-config.json), [saved activity metrics](data/xc330-98g-activity-saved-metrics.json), [condition summaries](data/xc330-98g-heldout-condition-metrics.csv) | Two frozen identification methods and conditional prediction from internal references; retrospective reserved roles |
| Declared-110 g XC330 fit | [Thirty paired held-out scores](data/xc330-declared110g-heldout-metrics.csv), [effective parameter vectors](data/xc330-declared110g-parameters.csv) | Separate model/processing revision; 28.3% reduction relative to its own synthetic-data baseline; no independent new weighing |
| RS06 hardware-position-v1 | [Split summaries](data/rs06-recorded-aggregate-metrics.csv), [parameter vectors](data/rs06-recorded-parameters.csv), [repeat variability](data/rs06-recorded-repeatability.csv), [fixture summaries](data/rs06-recorded-fixture-metrics.csv), [selected physical trace](data/rs06-B1-H2-P06-first-physical.csv) | Applied-command response prediction, CAD-derived fixtures and fixed gain assumptions; firmware torque remains a diagnostic |

The [data and signal guide](data/README.md) states scoring, units, case identities and field meanings. The [added scientific provenance record](data/consolidated-evidence-provenance.json) gives hashes and source revision for the new selective tables. No fit, hardware experiment or full identification rerun was performed for the added plots and arithmetic checks.

Existing optional saved-prediction analysis and native MuJoCo scientific code/data remain available. Their presence does not certify a newly tested runtime, prospective split integrity, a calibrated controller or a hardware-qualified procedure. Interpreting the supplied figures and metrics receives the same activity credit as numerical execution.
