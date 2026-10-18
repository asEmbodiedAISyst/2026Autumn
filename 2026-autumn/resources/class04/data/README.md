# Class 04 selected scientific records

These tables support the current [XC330 lesson](../../../module-01-actuator-data-for-1-dof-systems/04-basic-quantification-of-sim2real-gap.md) and [RS06 comparison](../../../module-01-actuator-data-for-1-dof-systems/04-rs06-hardware-identification.md). Their code, raw data and models are in the selected [author package](https://github.com/asEmbodiedAISyst/2026Autumn/tree/main/course-resources/Class%2004%20%E2%80%94%20Basic%20quantification%20of%20the%20Sim2Real%20gap).

## Declared 110 g XC330 case

`xc330-declared110g-heldout-metrics.csv` preserves 30 paired episode scores. The equal-episode mean is 0.02064688985201488 rad for the baseline and 0.0148139849688432 rad for the fitted model, a 28.2508% reduction. `xc330-declared110g-parameters.csv` identifies the baseline and frozen H1/H2 effective parameters. The selected B1/H2/P06/R01 trace has baseline 0.0101192508763 rad and fitted 0.00274332282115 rad; it is one episode, not the aggregate.

The 110 g value is the source model's declaration, not an independent weighing. Controller, fixture, reference, initialization and scoring choices belong to this experiment. The earlier 98 g campaign is a different historical case and is not this class's practical.

## RS06 comparison

The `rs06-*.csv` files preserve source aggregate, fitted-parameter, repeatability, fixture and selected physical-trace records. The source declares 108 episodes and 57,694 samples, with one invalid sample excluded. Position requests drive this replay; firmware torque is excluded from both fits. Keep its integral and output-error methods distinct from the XC330 fit.

See `consolidated-evidence-provenance.json` for original source identity and retained table hashes. Reading these supplied records does not constitute a new fit, hardware acquisition or physical calibration.
