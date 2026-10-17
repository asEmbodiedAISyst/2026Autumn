# Hardware campaigns and reproducible MuJoCo models

Source: `asMagicBrain/PhyIntel`, commit `9821dae9cb14ecfcd9fde3f97f14308a21f5bc00`, recovered 10 October 2026. This class package carries both complete primary episode sets, exact upstream identification/replay modules, frozen parameters and tables. No GitHub access is needed to run the packaged examples.

## Dataset identities

| Campaign | Original file | SHA-256 | Primary episodes |
|---|---|---|---:|
| XC330 Mode 5 | `episodes 1.zip` | `732d8618f666d8764ced720c09d22065980a55af6c962670a05f414a31b42f6c` | 126 |
| RS06 position interface | `hardware_data.zip` | `144d6137e77e8b9b9a41844008ff05d7f063aeda14450546b00dcca85b2386ed` | 108 |

The RS06 archive is not an XC330 archive. It declares RS06 CAN ID 2, the MagicLimb transport, H1/H2 gains and M0/B0/B1/G1 fixtures. XC330's original archive has 260 episode directories; the adapter selects 126 primary calibration/selection/held-out episodes. Diagnostics are audited but not fitted by the primary study.

The earlier `data/xc330` CSVs are a separate August 17 Mode-3 weighted/light study. The earlier `data/rs06` R02 and retained Isaac Lab reports are also a different experiment/implementation. They are not used to fit the campaign joint models.

## Packaged representation

`data/phyintel/xc330` and `data/phyintel/rs06` contain `episodes.npz`, `episodes.json`, `fixtures.json`, `archive-audit.json`, `provenance.json`, and `published/` tables/results. RS06 also contains original fixture metadata and MJCF/mesh model sources. Every numeric array is round-trip checked against the exact upstream adapter output; the NPZ needs no pickle. Metadata identifies each episode and its role. No downsampling or float-precision reduction is added by the export.

XC330 arrays have already passed the upstream active-profile adapter: cropping excludes preparation/return samples, external commands use zero-order hold, and telemetry is interpolated onto a 10 ms grid. RS06 arrays retain the 20 ms dynamic episode grid and validity/saturation masks. These are analysis-ready arrays, not a replacement for original timestamped event streams or complete provenance archives.

Original archives are identified by their hashes above; each standalone class package includes all inputs needed for the documented replay and identification commands, without duplicating unrelated raw event records. The provenance JSON records the export-file and source-module hashes. Reconstructing complete raw archives is outside this package.

## Implementation and fidelity

`code/upstream/run_chapter02_real_position_identification_v2.py` and `code/upstream/run_appendix_b_rs06_hardware_identification_v1.py` are byte-identical copies of the recovered source. Their SHA-256 values are checked before use. `code/phyintel_lab.py` reconstructs their episode dataclasses from the compact arrays and calls their model, replay and fitting functions. It does not port Isaac Lab or replace the native MuJoCo engines.

The documented replay uses published frozen parameters. Optional integral regression estimates from calibration again. Optional output-error fitting uses the source's calibration subset, bounds and multiple starts. Generated fit outputs are kept separate from published parameters; a fresh fit does not automatically overwrite the classroom replay model.

## Evidence limits

The source evaluations are retrospective. XC330's controller mapping uses an engineering torque/current assumption; RS06's numerical gain equivalence is unqualified. Firmware effort is not independent calibrated shaft torque. XC330 fixture masses are source-recorded measurements combined with CAD inertia scaling; RS06 properties remain CAD-derived. Both fitted vectors are context-bounded effective joint models, not uniquely established bare motor constants. XC330 G1 transfer is materially weaker than balanced B1 transfer; preserve that failure in any class summary.

The source Markdown excerpts in `references/` are historical technical records. Unpackaged illustrations and archives are identified as historical source assets; all commands in RUN.md use the packaged code/data directly.

## Controlled simulation reference

The package also preserves v1.2 simulated-position and ideal simulated-torque result tables under data/phyintel/simulation-reference. Those source studies test a known Source Model and a declared Nominal Model; they are simulation evidence, not hardware recordings. The new simulation comparison figure reads published tables and does not claim to rerun their optimizers.
