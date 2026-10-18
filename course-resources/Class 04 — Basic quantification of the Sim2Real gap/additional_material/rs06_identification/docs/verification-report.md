# Simulation data and identification: verification

Environment: MuJoCo 3.3.7, physics time step 0.002 s, Sim-Position output at 100 Hz, Sim-Torque output at
500 Hz. The aggregate checks are in `release-verification.json`; the identification numbers are in
`data/chapter-02/releases/rs06-sim-data-v1/sim-position-results-v1/README.md` and
`sim-torque-results-v1/joint-parameter-estimates.csv`.

## Data generation

- The four source MJCF and the 16 source, nominal and controller models load.
- All joints have the name `rs06_joint`.
- The M0 display mesh has no density and no collision; the numerical regulariser agrees with the contract.
- The 32 episodes split 18 / 8 / 6.
- Sim-Position has 34,156 samples; Sim-Torque has 170,652 samples.
- Each Sim-Torque episode reproduces the Sim-Position Source Model point by point at the 100 Hz boundaries.
- No Source episode has command saturation.
- The median position-gap RMSE between the Source and the Nominal model is about `5.10e-4 rad`, above the declared
  RS06 position quantisation, so the synthetic mismatch is observable.

## Identification

Sim-Position Method 2 (nonlinear MuJoCo replay, three parameters) reduces the output gap of the Nominal model by
about 96.7 % on the model-selection split and by about 94.9 % on the held-out split; it passes the declared
acceptance.

Sim-Position Method 1 (integrated closed-loop approximation) reaches the parameter bounds and does not pass the
predictive acceptance. This does not make the package unusable: the Method 1 of the original reference study also
fails its predictive acceptance. It shows that this simplified method must not be taken as the final RS06
parameter result under high gains, quantisation, a closed-loop analytic approximation and low damping.

Sim-Torque Method 2 gives a shared fit with a maximum relative error below `3e-6` against the disclosed Source
Model (armature `0.0012484886 kg m^2`, damping `0.0004377357 N m s/rad`, friction loss `0.0481937004 N m`). This
is a check of identifiability in simulation, not hardware torque evidence.

`release-verification.json` checks the archive hashes, the matrix correspondence, the H1 and H2 gains, the MJCF
joint, the episode counts of both datasets and the identification acceptance.
