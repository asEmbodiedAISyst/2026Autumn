# Resource provenance

The course's retained Class 08 simulation package is the immediate source of the model, motion example, viewer, classroom inspection/trace code, saved results and tested dependency pins in this export. Original archive provenance: `class08_build_simple_arm 1.zip`, SHA-256 `14df0a298a7d015fdba51878bd8578a3c10c19c0734f52ec91ef90a0c6ef04f7`, consolidated 2026-10-14. The original archive is not required to run this bundle.

The model source attribution and CERN-OHL-W-2.0 license remain beside the model. The vendor source is [Seeed-Projects/reBot-DevArm](https://github.com/Seeed-Projects/reBot-DevArm), `Rebot_Arm_description/RS`, commit `c247ea9cb0da29cd52c31953659cc8c47e6d1a6e`, as recorded by the retained notice. The generated MJCF and the teaching environment are retained from the course package. No blanket license is asserted for the teaching code or notes; the model license applies to the identified model source.

## Changes in this teaching export, 2026-10-17

- Moved the executable code and model into the portable `code/` and `model/` layout. Removed the old consolidation-specific import path from `lesson_lab.py`; imports now resolve beside the script.
- Retained the corrected `ArmSim` control timing and all motion algorithms. Corrected its introductory timestep description to match runtime behavior.
- Clarified that the ROB path's speed parameter sets segment duration rather than a peak speed bound; adjusted its terminal label accordingly.
- Adjusted CLI examples for the bundle's virtual-environment workflow and printed portable model paths.
- Clarified the optional viewer's mixed model/software limits and the distinction between a zero model configuration and physical calibration.
- Changed the source URDF's mesh references from `../meshes/` to `meshes/` so that they resolve beside the URDF in this bundle. Mesh bytes, geometry, joint definitions and MJCF files are unchanged. The model notice records the path change.
- Added standard-library saved-data analysis and this operational documentation. The saved simulation results retain their original bytes.

The bundle contains no hardware driver, source papers, slide deck, original archive, instructor answer sheet, private evidence logs, environment or cache.
