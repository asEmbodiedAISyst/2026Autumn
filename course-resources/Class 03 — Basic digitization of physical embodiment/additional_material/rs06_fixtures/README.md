# RS06 one-degree-of-freedom fixtures: digital models and metadata

The RS06 counterpart of the XC330 fixtures M0, B0, B1, B2, G1 of this class. Four configurations exist for the
RS06 (there is no B2). These are the models and the metadata of the RS06 identification campaign of 25 August
2026; the simulation and hardware data of that campaign belong to Class 04.

| Path | Content |
| --- | --- |
| `source-assets/mjcf/test_station_*` | The four Fusion 360 / ACDC4Robot exports as delivered: MJCF, meshes and `export_report.txt` (no payload = M0, balanced link = B0, balanced payload = B1, one payload = G1) |
| `model-sources/M0.xml`, `B0.xml`, `B1.xml`, `G1.xml` + `meshes/` | The frozen hardware-matched MJCF of the four fixtures (joint `rs06_joint`, H1 actuator defaults kp 50, kv 3.38); `SHA256SUMS` gives the file hashes |
| `fixture-metadata/*.json` | Per fixture: CAD-derived moving mass, centre of mass, inertia about the joint axis, signed gravity first moment, joint axis and position, configured limits, hashes of the model files; `manifest.json` binds every captured hardware run to its fixture |
| `fixture-metadata/evidence/photos/` | CAD renders of the four assemblies (not as-built photographs) |
| `fixture-contract.json` | The fixture quantities used by the simulation release |

| ID | Configuration | Moving mass (kg) | Inertia about the joint (kg m^2) | Gravity first moment (kg m) |
| --- | --- | ---: | ---: | ---: |
| M0 | motor only, no external load | 0 (numerical regulariser 1e-6) | 0 (1e-12) | 0 |
| B0 | balanced link without end payloads | 0.6872 | 0.01291 | -3.66e-5 |
| B1 | balanced link with both end payloads | 2.4072 | 0.05768 | -3.66e-5 |
| G1 | one-sided payload | 1.5472 | 0.03529 | -0.1290 |

The values are computed from the CAD exports and are not measurements of the built fixtures. The inertia excludes
the motor rotor and the MuJoCo `armature`. M0 keeps a moving body with a tiny mass because a MuJoCo hinge needs a
moving child body; its mesh is display only. Physical range, as-built masses and photographs are not recorded
(the fixture metadata lists each missing value as null).
