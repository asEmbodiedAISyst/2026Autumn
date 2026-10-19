# RS06 physical identification comparison

The current [RS06 companion lesson](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/2026-autumn/module-01-actuator-data-for-1-dof-systems/04-rs06-hardware-identification.md) presents `hardware-position-v1`: 108 physical episodes, 57,694 samples and one invalid sample excluded from scoring. It compares integral and output-error identification under fixed H1/H2 position-controller conditions. The applied position request is the replay input; reported firmware torque is not used as a fitted drive signal.

Read [hardware/README.md](hardware/README.md) for CAD-derived fixture properties, controller-interface settings and recorded versus unknown physical facts. The current lesson defines the selected scientific comparison and its limits. A CAD-derived quantity is not an independent measurement of the as-built apparatus, and fitted terms are effective parameters of the declared closed-loop model.

## Synthetic reference material

`data/chapter-02/releases/rs06-sim-data-v1/` contains a separate 32-episode generated Sim-Position/Sim-Torque study. It is reference data, not the 108-episode physical experiment and not an additional required Class 04 practical. Its parameter recovery and verification results cannot establish physical identification accuracy. The retained source scripts and release contracts keep their original bytes; follow the current companion for this class's exercise rather than treating the historical all-stage `reproduce.sh` as its entry point.
