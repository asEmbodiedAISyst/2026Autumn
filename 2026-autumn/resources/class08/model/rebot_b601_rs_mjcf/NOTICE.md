# Model source

- `ReBot_Arm_RS.urdf` and `meshes/` are copied from
  [Seeed-Projects/reBot-DevArm](https://github.com/Seeed-Projects/reBot-DevArm), folder `Rebot_Arm_description/RS`
  (commit `c247ea9cb0da29cd52c31953659cc8c47e6d1a6e`, 2026-10-04; identical to commit `171ed82` of 2026-10-07),
  license CERN-OHL-W-2.0, see `LICENSE.CERN-OHL-W`. Only the meshes that the arm model uses are kept
  (`meshes/shared`, `meshes/visual`).
- `rebot_b601_rs.xml` is generated from the URDF
- `table_env.xml`  contains table, lights, fixed cameras and `scene_table.xml` contains arm and table

## Public teaching export (2026-10-17)

This export retains the source URDF, the exact mesh set referenced by the URDF and MJCF, and this license and notice. The exported URDF mesh references were changed from `../meshes/` to `meshes/` so that they resolve from this folder. Geometry, joint definitions and mesh bytes are unchanged. This path correction is supplied under CERN-OHL-W-2.0.
