---
description: Basic digitization of physical embodiment · ROB7103/8103
---

# 03 Basic Digitization of Physical Embodiment

**ROB7103/8103 · 23 October 2026 · L12**

**Central question:** What does a digital representation preserve, and which parts can we validate?

A digital model makes selected properties of a physical mechanism explicit: its geometry, moving bodies, joints, mass distribution and the assumptions used to simulate it. Our purpose is to prepare a single-actuator link/payload experiment whose digital and physical versions can be compared. The quality of that comparison depends on what each stage of digitization preserves.

By the end of this class, you should be able to distinguish a digital representation, digital cousin and task-bounded digital twin; inspect geometry, frames, joints, mass, inertia and collision assumptions; and define validation for a specified actuator experiment.

[Lecture](#1-geometry-alone-does-not-establish-behavioral-correspondence) · [Instructor/TA demonstration](#instructor-and-ta-demonstration) · [Student activity](#student-activity)

## 1. Geometry alone does not establish behavioral correspondence

Our example is an XC330 actuator with a link and two attached pin–payload assemblies. The motor housing is fixed; the link and attached assemblies rotate about one output axis. The task today is to represent this structure, its mass distribution and its ideal gravity behavior. Predicting the complete servo response requires further controller and actuator information.

![Physical B2 fixture, CAD assembly and loaded MuJoCo scene](../media/class03/physical_cad_mjcf_comparison.png)

*Figure 1. Three views of the declared B2 configuration. The photograph shows the built fixture, CAD shows its designed assembly, and MuJoCo shows the loaded representation. Similar appearance alone does not establish equal physical behavior.* [Figure source](#figure-sources)

Use the supplied **110 g fixture family**: a 22 g link and two complete 44 g pin–payload assemblies. These masses come from the submission's physical record. The payload split and inertia tensors in the model are derived from CAD. Keeping that distinction lets us improve uncertain properties later.

A **digital representation** records selected properties. A **digital cousin** supports exploration with a similar system. For this course, a **task-bounded digital twin** additionally requires an identified physical counterpart and tested correspondence for stated conditions. A model can be useful before it supports that stronger claim.

**Pause and predict:** What could you verify from the photograph? What would require a ruler, a scale or a motion experiment?

## 2. Understand where Sim2Real differences enter

A simulation begins with a designed representation, while an experiment uses a manufactured and assembled mechanism. Differences enter at several stages:

| Stage | Possible difference | What to inspect or record |
|---|---|---|
| Design | Simplified geometry, rigid connections, omitted cables | Which features matter for the intended motion? |
| Manufacturing | Printed density, shrinkage, hole size and surface finish | Dimensions, component mass and process settings |
| Assembly | Clearance, shaft alignment, fasteners and play | Fit, reference pose and the actual moving assembly |
| Communication | Command delivery, timestamps and sample intervals | The command and observation clocks |
| Controller | Internal trajectory generation, gains and effort limits | The actuator mode and settings used in the experiment |
| Simulation | Collision policy, friction model and numerical integration | Explicit settings and the behavior they exclude |

For example, a printed link can match the CAD outline while weighing less because it is not solid. A joint can look correctly placed while its axis sign is reversed. A commanded step can arrive after the timestamp used by the replay. Each discrepancy changes the interpretation of a physical–digital comparison.

Use this table as a diagnostic map. First establish geometry and model structure; then investigate response differences with matched experimental records. Changing several assumptions at once makes it difficult to explain an improvement.

## 3. Treat CAD physical properties as estimates

Three descriptions serve different purposes:

| Description | Question it answers | Example check |
|---|---|---|
| Visual geometry | What does the mechanism look like? | Mesh scale and placement match a known dimension |
| Collision geometry | Where can contact constrain motion? | Intended surfaces participate in collision |
| Inertial properties | How does mass distribution affect motion? | Mass, centre of mass and inertia match the declared assembly |

A detailed visual mesh may be unnecessarily expensive for contact computation. A simpler collision shape can be appropriate when it preserves the contact features required by the task. Our supplied models set `contype` and `conaffinity` to zero, excluding their geometries from contact. The visible floor therefore does not establish floor contact.

Mass tells us how much matter moves. The centre of mass describes its mean location. Rotational inertia describes resistance to angular acceleration about a specified axis. Moving the same payload farther from the axis changes inertia even though its mass stays constant.

For a point-mass approximation,

$$
J_{\mathrm{payloads}} = \sum_i m_i r_i^2.
$$

Here each radius is the perpendicular distance to the rotation axis. A distributed component also has inertia about its own centre of mass. The point-mass expression isolates the placement effect; a complete model includes the component's central inertia and the link.

CAD supplies a tensor rather than a single universal inertia. The relevant joint inertia depends on the rotation axis, orientations and offsets. We will inspect the supplied tensors rather than derive a full multibody algorithm today.

The 22 g link and complete 44 g assemblies belong to the submission's recorded mass description. The model rescales CAD inertias to those masses while retaining geometry and centre-of-mass locations. This approximates a density change; weighing a part does not independently measure its inertia tensor. Check the assembled part and record how each model property was obtained.

### A load-placement example

![The 110 g fixture configurations and their declared positions](../media/class03/configuration_mass_positions.png)

*Figure 2. Each green assembly is 44 g including its pin. B0, B1 and B2 use symmetric positions; G1 places both assemblies on one side. M0 omits the external fixture.* [Figure source](#figure-sources)

Compare B0 with payload centres at ±60 mm and B2 at ±100 mm. Their external moving mass is the same:

$$
m_{\mathrm{moving}}=0.022+2(0.044)=0.110\ \mathrm{kg}.
$$

Moving both assemblies outward changes their point-mass contribution by

$$
\Delta J=2(0.044)(0.100^2-0.060^2)
=0.0005632\ \mathrm{kg\,m^2}.
$$

The link and unchanged component central inertias do not contribute to this difference under the stated rigid-placement approximation. Greater inertia requires greater torque for the same angular acceleration when the other terms are held fixed.

Balance concerns the **signed first moment**, rather than squared distance. For equal masses at equal opposite positions, the contributions cancel. Their inertia contributions still add. In the ideal horizontal-axis model, the symmetric fixture therefore has essentially zero gravity moment about the joint while retaining nonzero inertia.

The same-side G1 fixture introduces a gravity moment. Use the current figure's 44 g assemblies when comparing the supplied 110 g models.

## 4. Define the single-actuator validation experiment

Choose a physical actuator, a declared link/payload configuration and an operating range. Record which bodies move, the payload-centre positions, the joint axis, zero pose and the command mode. The digital model and physical test must refer to the same declared configuration before comparing outputs.

For a position-response comparison, preserve the applied command sequence and controller settings, establish compatible time bases, and compare measured and simulated positions at matched observation times. Choose the comparison metric and operating conditions explicitly. Reserve independent trajectories for checking whether the result transfers beyond the data used to adjust it. Class 04 develops this procedure.

Today we check selected properties: topology, dimensions, axis, limits, moving mass and gravity behavior. A model that passes those checks is ready for the next experiment; it has not yet demonstrated accurate actuator response across arbitrary motions or contacts.

A useful model record connects each important property with its evidence:

| Property | Evidence in this example | Interpretation |
|---|---|---|
| 22 g link and 44 g assemblies | Submission's physical mass record | Recorded measurements used by this model family |
| Component shapes and inertias | CAD geometry and mass-scaled tensors | Derived estimates |
| ±90° range and disabled contact | XML declarations | Chosen simulation scope |
| One moving coordinate | Joint tree and compiled inspection | Executable structural property |
| Physical position response | Requires matched physical and simulated experiments | Next stage of validation |

The model is ready for structural inspection and controlled exploration of declared load placement. Predicting measured actuator motion requires more evidence. Keep a property ledger: what was measured, what came from CAD, what was assumed, and what remains to be tested.

Changing payload position can preserve mass and balance while changing inertia. A successful render is one check in this larger evidence chain.

## 5. Follow CAD through robot description into MuJoCo

![Physical fixture to CAD, robot description, MJCF and load checks](../media/class03/digitization_workflow.png)

*Figure 3. Each conversion preserves selected information and introduces assumptions. Check the result at every stage.* [Figure source](#figure-sources)

CAD describes parts, placement and assembly relationships. A robot description adds an explicit body tree, joints, coordinate frames and physical properties in a form simulation software can interpret. MJCF is MuJoCo's native XML description; URDF is another common robot-description format. Exporting either requires inspecting what the exporter actually produced.

The preparation sequence is:

1. Identify fixed components and groups that move rigidly together.
2. Define the revolute joint, its origin, axis, zero pose and permitted range.
3. Check dimensions and material-based mass estimates against the physical assembly.
4. Export geometry and the robot description, keeping their relative asset paths.
5. Load the result and inspect topology, units, inertial properties and geometry roles.

![Recorded Fusion joint, material and ACDC4Robot export views](../media/class03/fusion_acdc_workflow.png)

*Figure 4. Recorded Fusion/ACDC4Robot workflow views. They illustrate joint assignment, material settings and export selection; they are not a step-by-step reconstruction of the 110 g B2 model. Enlarge the image to inspect the interface.* [Figure source](#figure-sources)

CAD material density is an estimate of the manufactured component. A printed part may contain infill and voids; screws and fasteners may add mass. Check clearance and fit on the built assembly and weigh the moving components. Changing a density setting until the rendered shape looks right cannot establish inertia.

### Inspect the frames and units

A rigid body can contain several connected physical parts. In our example, pins and payloads have separate entries for bookkeeping but no additional moving joints. They remain fixed to the rotating link. One hinge gives one degree of freedom; the number of meshes does not determine the number of degrees of freedom.

A frame specifies an origin and axes. State where the joint is, which axis it turns about, and what positive rotation means. Apply the right-hand rule. The camera view can change without changing these mechanical definitions.

![A declared coordinate transformation worked geometrically](../media/class03/frame-transform-classroom.png)

*Figure 5. Teaching coordinates, independent of the fixture: rotate a point, then add the parent-frame translation. Directions such as a joint axis use rotation only.* [Figure source](#figure-sources)

For a point expressed in a child frame B, its parent-frame A coordinates are

$$
{}^{A}p = {}^{A}R_{B}\,{}^{B}p + {}^{A}p_{B}.
$$

For example, rotating [0.08, 0, 0] m by +90° about z gives [0, 0.08, 0] m. Adding a parent-frame translation [0.10, 0.02, 0] m gives [0.10, 0.10, 0] m. A payload position written in a local frame must be transformed before comparing it with a world-frame measurement.

Use metres, kilograms and seconds in this package. The mesh scale `0.001 0.001 0.001` converts exported millimetres to metres. A 100 mm distance should become 0.100 m. Compare a known dimension numerically: camera zoom can make an incorrectly scaled model look plausible. Positions in XML and mesh vertices need their own unit checks.

The supplied model declares radians and a joint range of approximately −1.571 to +1.571 rad, or ±90°. This is a model boundary; it is not evidence that the physical actuator has hard stops there.

**Checkpoint:** If a payload is attached rigidly to the link, should adding its mesh add another degree of freedom? Explain using the joint tree.

### Read the executable model

The supplied [B2 model](../resources/class03/consolidation/additional_material/models/1DOF-B2.xml) contains these declarations, shown here as selected lines rather than a complete runnable file:

```xml
<compiler angle="radian" inertiafromgeom="false" />
<option timestep="0.002" gravity="0 0 -9.81" />
<mesh name="Link" file="assets/Link.stl" scale="0.001 0.001 0.001" />
<joint name="actuator_joint" type="hinge"
       axis="0 1 1.0963452368173417e-15"
       range="-1.5707963267948966 1.5707963267948966" />
```

The local joint axis is effectively [0, 1, 0]; the tiny third component is export roundoff. Follow the parent-body transforms before interpreting that axis in world coordinates. Explicit inertial records supply the body properties. One torque actuator supplies effort; it does not recreate the embedded XC330 position controller.

Check the compiled model in a useful order: one coordinate and one velocity coordinate; expected meshes and scale; joint range and direction; 0.110 kg external moving mass; the chosen collision policy; and balanced versus eccentric gravity behavior. Loading successfully establishes that the simulator can interpret the file. Agreement with declared values establishes implementation consistency. Neither alone validates physical motion.

For an isolated hinge, the mechanics can be summarized as

$$
J\ddot q + \tau_{\mathrm{resistance}} + \tau_g(q)=\tau_{\mathrm{actuator}}.
$$

The geometry and mass distribution contribute inertia and gravity. Real actuator response also depends on friction, transmission, embedded control, effort limits and timing. A 2 ms physics step specifies numerical integration; it is not a measured hardware sampling period. Class 04 will address response data and effective model parameters.

## 6. Relate the digital model to printing and assembly

Printing converts a nominal design into an as-built part. Material, layer orientation, wall count and infill influence mass and stiffness. Hole size, shaft fit, support removal and fastener seating affect clearance and alignment. A good-looking print can still require a different mass record or a revised joint assumption.

Use a prepared printed link to compare a known CAD dimension with the actual component. Check whether a shaft or fastener fits as intended and weigh the component together with the attachments that move with it. Record the material and print settings alongside the measured mass. Treat a nominal material density or slicer estimate as an estimate until checked.

In the H2D preparation demonstration, inspect the supplied link file, its units, orientation and sliced preview. Relate the chosen orientation to the joint interface and fit. The class uses an already printed part; fabrication can continue after class. Account registration and software installation belong in preflight.

**Checkpoint:** If a printed link has the correct outer dimensions but a different measured mass, which model properties should you revisit? Which properties still need separate evidence?

## Practical preparation and resources

The instructor/TA prepares Fusion, the exporter, MuJoCo and the slicer before class. Account registration, installation and a fresh CAD reconstruction are not student activity tasks. Have the RS06 mechanical reference, prepared exports, XC330 model, a printed link and its mass/dimension record ready.

The inspection command uses the supplied [offline script](../resources/class03/code/class03_inspect.py) from `2026-autumn/resources/class03` in the downloaded repository. If needed, prepare its environment beforehand:

```sh
python3.12 -m venv .venv-class03-core
.venv-class03-core/bin/python -m pip install mujoco==3.3.7
.venv-class03-core/bin/python code/class03_inspect.py --case B2
```

The activity's `python` command assumes this environment is selected. The saved tables on this page provide a complete numerical fallback. CAD, MJCF, engineering drawing and printing files are linked in the demonstration as supporting assets.

## Instructor and TA demonstration

Follow the CAD-to-simulation sequence using the prepared RS06 reference and fixture exports, then relate the model to a printed component.

### Inspect the RS06 reference and assembly

Open the [RS06 motor STEP](../resources/class03/preparation/demonstration/rs06/RS06_vendor_motor.step) in Fusion and compare its output axis and mounting interfaces with the [engineering drawing](../media/class03/RS06_outline_and_mounting_dimensions.png). Inspect component origins, dimensions and physical properties. The STEP is the motor reference, not a complete editable fixture assembly.

Identify the fixed base and moving link/payload in the prepared RS06 model. Distinguish CAD-derived mass/inertia from manufacturer values and actual measurements. Keep the RS06 properties separate from the XC330 student example.

![RS06 outline and mounting dimensions](../media/class03/RS06_outline_and_mounting_dimensions.png)

*Figure 6. Manufacturer engineering drawing supplied with the RS06 reference. Dimensions are nominal reference values, not measurements of the available unit.*

### Inspect the joint and export decisions

Using the prepared jointed assembly when available, inspect the revolute joint, reference pose and rigid attachments. Remove visual detail only where the simulation task permits it. Keep collision simplification separate from visual geometry and inertial declarations.

Show the recorded [Fusion/ACDC4Robot sequence](../media/class03/fusion_acdc_workflow.png) to explain joint/material assignment and MJCF export. Those interface captures show the XC330 workflow. Apply the checks to the RS06 reference; do not describe the captures as a newly performed RS06 export.

Open the existing [RS06 Fusion/ACDC4Robot export](../resources/class03/preparation/rs06_fixtures/source-assets/mjcf/test_station_balanced_payload/test_station_balanced_payload.xml) and its [export report](../resources/class03/preparation/rs06_fixtures/source-assets/mjcf/test_station_balanced_payload/export_report.txt). Trace mesh paths, transforms and the joint declaration. Use the prepared export as the fallback when a complete editable RS06 CAD assembly is unavailable.

### Load the prepared MJCF and inspect it

Load the prepared [RS06 B1 model](../resources/class03/preparation/rs06_fixtures/model-sources/B1.xml) in MuJoCo. Locate `rs06_joint`; inspect its local axis, parent transforms, reference pose and declared range. Compare the source export with the prepared model to see which actuator and passive-property assumptions were added.

Inspect the geometry at a small positive joint displacement. Compare gravity on and off with the same pose and control settings. The position actuator can resist gravity, so distinguish gravity bias from net motion. Use the saved inspection table below if a viewer is unavailable; [raw inspection records](../resources/class03/results/class03-core/rs06-inspection.json) remain downloadable. These checks concern declared model behavior, not new hardware measurements.

### Compare a printed part and prepare the H2D

Show a prepared printed link and compare dimensions, clearance and measured mass with CAD assumptions. Open [Link_for_H2D.3mf](../resources/class03/preparation/demonstration/h2d/Link_for_H2D.3mf) in the prepared slicer. Confirm millimetres, select the actual H2D printer/nozzle/plate/material configuration, inspect orientation, slice and review the preview. Relate hole fit and material/process choices to model uncertainty.

Use an already printed part and the prepared preview; printing does not need to finish during class. CAD reconstruction, repeated exports and custom printing can continue as project work. Continue with the [student activity](#student-activity).

### Saved RS06 model checks

These values use MuJoCo 3.3.7 at joint position 0.4 rad, zero velocity and zero control. They report the generalized gravity bias, not net acceleration or hardware measurements. The position actuator is a separate effort contribution.

| Fixture | Coordinates | Velocities | Actuators | Gravity-on bias (N m) | Gravity-off bias (N m) |
|---|---:|---:|---:|---:|---:|
| B1 | 1 | 1 | 1 | 0.00036840032 | 0 |
| G1 | 1 | 1 | 1 | 1.1659619 | 0 |

The prepared RS06 joint axis is locally [−1, 0, 0] and its declared range is [−1.1, 1.1] rad. Follow parent transforms to interpret the axis in world coordinates.


## Student activity

**Work individually or in pairs**

Use the 110 g fixture from the lecture above: a 22 g link and two 44 g assemblies. B2 places them at ±100 mm. Move both centres inward to ±80 mm, retaining their masses and internal properties.

### Predict

Write whether each quantity changes: total external moving mass, joint count, rotational inertia and ideal balance. Give one sentence explaining your prediction.

### Calculate and inspect

Calculate the change in the two assemblies' point-mass inertia contribution, using metres and kilograms. Compare your answer with `inertia_change_kg_m2` in the saved XC330 inspection below ([raw output](../resources/class03/results/class03-core/inspection.json)). Read the base and modified moving masses, coordinate counts and gravity probes.

If the environment is already prepared, run:

```sh
python code/class03_inspect.py --case B2 --radius-mm 80
```

Otherwise use the saved output. Installing software is not part of this activity.

### Compare with the physical component

Compare the declared link dimension or payload mass with the actual or prepared printed component. Record the value, unit and how it was obtained. If the component is unavailable, use the supplied photograph and mass record, identifying them as source records. State one additional measurement you would make to check the model. Inspect the printer when feasible.

### Explain the evidence

Identify one XML property that is a modeling choice rather than a measurement. Explain why a successful load and a plausible picture do not establish an accurate physical position response.

### Submit

Submit one short record: your four predictions, the inertia calculation with units, the observed mass and coordinate count, the physical comparison and two evidence sentences. A screenshot or software installation is not required. Keep the supplied models unchanged.

### Saved XC330 inspection

Use these saved model values after making your prediction. They are sufficient when a Python environment is unavailable.

| Quantity | Original B2 | Modified B2 |
|---|---:|---:|
| Payload-centre positions (mm) | ±100 | ±80 |
| External moving mass (kg) | 0.110 | 0.110 |
| Coordinates / velocities / actuators | 1 / 1 / 1 | 1 / 1 / 1 |
| Joint inertia (kg m²) | 0.0009813575 | 0.0006645575 |
| Gravity bias at 0.4 rad (N m) | 2.756e-14 | 2.754e-14 |

The record's `inertia_change_kg_m2` is -0.0003168 kg m². The source XML files remain unchanged; the demonstration command modifies an in-memory model.


## Figure sources

| Figures | Source |
|---|---|
| 1 Physical/CAD/MJCF comparison | Retained B2 photograph, CAD screenshot and native model render, composed by `actual_cad_mjcf` in [the submission figure generator](../resources/class03/consolidation/additional_material/code/generate_figures.py) |
| 2 Fixture placements | Declared 110 g family, `configuration_schematic` in the same generator |
| 3 Digitization chain | Conceptual diagram, `workflow` in the same generator |
| 4 Fusion/export workflow | Recorded XC330 interface captures, `fusion_acdc_demo` in the same generator |
| 5 Coordinate transform | Declared mathematical example in [visual_lessons.py](../resources/class03/code/visual_lessons.py) |
| 6 RS06 engineering drawing | Manufacturer reference supplied with the [RS06 manual](../resources/class03/preparation/demonstration/rs06/RS06_User_Manual_260713.pdf) |

The figures are reused unchanged. The coordinate diagram is illustrative; photographs, CAD views and simulator renders support different claims.

## References

The official [MuJoCo modeling guide](https://mujoco.readthedocs.io/en/stable/modeling.html) and [XML reference](https://mujoco.readthedocs.io/en/stable/XMLreference.html) describe body trees, coordinate frames and model attributes.
