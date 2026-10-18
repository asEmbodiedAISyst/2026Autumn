# Class 08 resources

The [Class 08 course page](../../module-03-arm-data-for-guided-interaction/08-lets-build-a-simple-arm-and-turn-it-on.md) contains the comprehensive explanation, figures, worked examples, demonstration observations and activity. It is complete without installing software or operating hardware.

`results/inspection.json` records the supplied compiled model, joint ranges, reference configurations and control timing. `results/joint2-trace.csv` contains 180 simulation rows: time, target degrees and joint position sampled before that iteration's step. The signed residual is pre-step position minus its paired target; maximum absolute error is about 1.326°. This is a different comparison from the later response samples printed by the full motion example.

`code/` contains model inspection, trace generation, saved-data analysis, bounded joint/gripper motion, the free-space ROB example and an optional viewer. `model/rebot_b601_rs_mjcf/` contains the source URDF, retained MJCF/environment, 32 referenced meshes, model licence and notice. The [source record](SOURCE.md) identifies the supplied archive and export changes. [MANIFEST.json](MANIFEST.json) records file sizes and hashes.

The tested macOS dependency set uses Python 3.12, MuJoCo 3.14.0 and NumPy 2.5.4. It does not qualify every platform or graphical viewer. `ArmSim` adjusts the scene timestep to 1/510 s and uses 17 steps per 30 Hz control interval; the independent viewer retains the scene's own stepping behavior. Environment setup, launch commands and output handling belong to the separately prepared example package. Preserve supplied results when generating fresh outputs.

Software/model limits and the ROB trajectory are simulation declarations and tests. They do not establish physical motor calibration, jaw-stroke conversion, driver compatibility or hardware readiness. Keep the model [notice](model/rebot_b601_rs_mjcf/NOTICE.md) and [CERN-OHL-W-2.0 licence](model/rebot_b601_rs_mjcf/LICENSE.CERN-OHL-W) with reused source assets.


The added physical case includes [the single-joint motion-test JSON](data/motion-test-single-joint-20261010.json), [source provenance](data/consolidation-source.json) and [apparatus topology](figures/physical-topology-classroom.png). The JSON records joint2 only: 1.8724° worst tracking error, 1.9249 N m peak firmware-reported torque and 27°C. Its gravity sweep and fitted correction are stored diagnostics, not independently calibrated torque or qualification of all seven devices.
