# Course resources

Return to the [course home and linked schedule](../student.md#teaching-schedule). Read the relevant class page before downloading or running its practical files. **Public course files are learning resources; submit assessed work in your assigned private team repository.**

- **Classes 01–11:** use the class packages below for illustrations, code, models and data. Follow the linked instructions and their availability notes.
- **Classes 12–17:** open the [worksheet templates and submission guide](project-workbook/README.md); filled examples and source papers are linked separately on each class page.
- **Classes 18–21:** use the [poster](../module-05-final-project-submissions/18-final-poster-submission.md), [code](../module-05-final-project-submissions/19-final-code-submission.md), [video and final worksheets](../module-05-final-project-submissions/20-final-video-submission.md) and [showcase](../21-final-project-showcase.md) instructions.

To download code or a folder, open the [public student repository](https://github.com/asEmbodiedAISyst/2026Autumn), then clone it or choose **Code → Download ZIP**. Packages are under `2026-autumn/resources/classXX/`; use the selected class's setup instructions.

## Class packages

All course resources are organized by class in this folder. Each `classXX/` contains its classroom assets and selected records. The selected teaching-author code, data and models are in `classXX/additional_material/`. 

| Class | Package | Availability and interpretation |
|---|---|---|
| 01 | [Introduction and platform demonstrations](../first-class/01-course-introduction-with-asmagicbrain.md) | Conceptual illustrations of experience generation and the four TA pathways; not recorded performance evidence. |
| 02 | [Actuator basics](class02/additional_material/README.md) | The active lesson uses the hardware record, not the older simulation files retained in the source package. Geometry is not an identified dynamics model. |
| 03 | [Fixture digitization](class03/additional_material/README.md) | Validation establishes model structure and loading. It does not identify physical dynamics or validate a hardware controller. |
| 04 | [Single-actuator identification](class04/additional_material/README.md) | The current source results/overall_heldout_result.csv reports 30 held-out XC330 episodes, mean baseline RMSE 0.02064688985201488 rad and fitted RMSE 0.0148139849688432 rad (28.2508% reduction). Earlier source README values describe a stale result. Effective fit parameters are not isolated motor constants. |
| 05 | [Population identification](class05/additional_material/README.md) | The source campaign contains 125 events split 72/23/30. Keep event, motor and sample denominators distinct. Fixture mass declarations remain uncertain; fitted terms must not conceal that uncertainty. |
| 06 | [Continuous positive-Z cube rotation](class06/additional_material/README.md) | The active CONTINUOUS_Z_ROTATION_DEPLOYMENT_BUNDLE_20261014, checkpoint/server/bridge and raw deployment NPZ logs are not in this source tree. The launcher references that external bundle. This is evidence and supporting source, not a ready policy-playback package. Older visual-yaw files are not the active task; no working policy is supplied here. |
| 07 | [Visual measurement and stream inspection](https://github.com/asEmbodiedAISyst/2026Autumn/blob/main/2026-autumn/module-02-hand-data-for-multi-fingered-manipulation/07-rotating-a-cube-with-visual-feedback.md#instructor-and-ta-demonstration) | Geometry and frame/age analysis are available. A configured original receiver is required for live stream inspection; a complete cube estimator and visual-control policy are not supplied. |
| 08 | [Arm model and commissioning](class08/additional_material/README.md) | The simulation practice is separate from optional assembly and power-on instructions. Students do not assemble or power the physical arm in the required practice. |
| 09 | [Phone-to-pusher teleoperation](class09/additional_material/README.md) | The core practice is iPhone teleoperation of the simulated pusher to push a cube. The fake phone checks an input/mapping path. Physical operation and gripper comparison are optional. Verify package-specific phone axes before interpreting directions. |
| 10 | [Pusher-cube data collection](class10/additional_material/README.md) | The complete handheld training dataset is not included. Source Class09 six-joint recordings and Class10 nine-feature tip-pose recordings are different schemas. Preserve that boundary rather than combining them silently. |
| 11 | [ACT policy evaluation and transfer](class11/additional_material/README.md) | Ready ACT/Diffusion/SmolVLA policy checkpoint directories are absent. Training recipes require their specified datasets and backend. The source manuscript ACT62%/56% scores and supplied32/50(64%) JSON require run-identity reconciliation. Source physical learned-policy evidence includes0/10; no successful policy transfer is claimed here. |

Class07 currently has a stream/interface lesson but no complete source cube-estimation/control package. The Class09 receiver is a phone-teleoperation implementation, not a cube-pose estimator.

Install each package in its own virtual environment. Do not mix environments or assume that the packages use identical recording schemas. Only the teaching team operates the powered apparatus.
