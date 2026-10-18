# Class 04: Single-actuator identification

[Lecture](../../2026-autumn/module-01-actuator-data-for-1-dof-systems/04-basic-quantification-of-sim2real-gap.md) · [04-rs06-hardware-identification](../../2026-autumn/module-01-actuator-data-for-1-dof-systems/04-rs06-hardware-identification.md)

## Available material

Raw campaigns, paired samples, frozen parameters, full-fit/replay/analysis code, MJCF and the RS06 identification package.

## Evidence and execution boundary

The current source results/overall_heldout_result.csv reports 30 held-out XC330 episodes, mean baseline RMSE 0.02064688985201488 rad and fitted RMSE 0.0148139849688432 rad (28.2508% reduction). Earlier source README values describe a stale result. Effective fit parameters are not isolated motor constants.

## Source and file identity

Runtime code, numerical data and model files are copied unchanged from the teaching authors' course package at source commit `f7c118edaadc9f33498669736fa9d99160ff629a`. The lecture and practice pages explain the current task and available evidence. Source package documentation may describe historical configurations; use the explicit qualifications above.

Paper-production files, fonts and standalone figure-generation sources remain with the teaching authors. Classroom illustrations are published once as PNG in the class resources; camera/dataset images and recordings retain their original runtime formats. Missing checkpoints or external bundles have not been replaced.

Use an isolated virtual environment as directed by the practice/package requirements. Installing dependencies or running a recipe is a separate step from reproducing a result; this distribution update does not report new training or powered-hardware tests.
