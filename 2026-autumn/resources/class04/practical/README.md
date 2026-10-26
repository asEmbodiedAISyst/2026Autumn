# Class 04: Single-actuator identification

[Lecture](../../../module-01-actuator-data-for-1-dof-systems/04-basic-quantification-of-sim2real-gap.md) · [Student practice](../../../module-01-actuator-data-for-1-dof-systems/04-practice.md) · [Standalone experiment](additional_material/standalone/README.md) · [Student guide](additional_material/standalone/STUDENT_GUIDE.md)

## Available material

Embedded B0/H2 measurement records, B0 MJCF and meshes, simulation-only identification code, tests, analysis outputs, the extended XC330 source campaign, and the RS06 identification package.

## Evidence and execution boundary

The standard classroom experiment reads 15 embedded V5 B0/H2 measurement episodes and does not collect new data. It fits on R01/R02 for profiles P01–P05 and validates on the five R03 episodes. The retained extended campaign separately reports 30 held-out B1/G1 episodes, mean baseline RMSE 0.02064688985201488 rad and fitted RMSE 0.0148139849688432 rad. Results and parameter values from these two experiments must remain separate. Effective fit parameters are not isolated motor constants.

## Source and file identity

Retained runtime code, numerical data and model files preserve their bytes from the teaching authors' course package at source commit `f7c118edaadc9f33498669736fa9d99160ff629a`. The lecture and practice pages explain the current task and available evidence. Use this entry and the linked current practice for instructions; superseded recipes and inactive alternatives are outside the current route.

Paper-production files, fonts and standalone figure-generation sources remain with the teaching authors. Classroom illustrations are published once as PNG in the class resources; camera/dataset images and recordings retain their original runtime formats. Missing checkpoints or external bundles have not been replaced.

Use an isolated virtual environment as directed by the practice/package requirements. Installing dependencies or running a recipe is a separate step from reproducing a result; this distribution update does not report new training or powered-system tests.
