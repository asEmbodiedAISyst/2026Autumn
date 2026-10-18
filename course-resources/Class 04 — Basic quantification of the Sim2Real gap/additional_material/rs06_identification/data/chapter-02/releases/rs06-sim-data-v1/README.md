# RS06 Sim Data v1

This release follows the Chapter 2 v1.1 artifact layout while using the four
supplied RS06 Fusion MJCF fixtures and the modified 32-episode matrix.

`rs06-sim-position-v1.npz` is the hardware-shaped 100 Hz position-interface
dataset. `rs06-sim-torque-v1.npz` is a separate 500 Hz simulation-only effort
replay dataset. The latter is not a claim that qualified joint torque is
available from the physical RS06 position-mode feedback.

The Source Model uses disclosed synthetic priors. The Nominal Model is
deliberately mismatched. Fixture inertias are taken from the supplied CAD
exports; M0 uses only a `1e-6 kg` / `1e-12 kg*m^2` moving-body regularizer.

Regeneration commands are in the package root `README.md` and `reproduce.sh`.
