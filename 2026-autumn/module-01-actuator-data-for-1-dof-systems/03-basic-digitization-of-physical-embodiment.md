---
description: 23 October 2026 · 09:00–10:50 · L12 | Mohamed HALWANI & SONG Chaoyang
---

# 03 Basic Digitization of Physical Embodiment

## Central question

> What must a digital model preserve before it can represent a physical mechanism?

Class 02 introduced the XC330 actuator, its operating modes, commands, and measured response. This class extends that foundation from the actuator alone to the physical mechanism connected to it. The mechanism must be described through geometry, rigid bodies, joints, frames, mass properties, inputs, and measurable outputs before its simulated behavior can be compared with hardware.

By the end of this class, you should be able to:

- distinguish a visual model from a mechanically meaningful digital representation;
- identify the bodies, joints, frames, units, mass properties, inputs, and outputs required for a one-degree-of-freedom model;
- explain how one fixture design can be represented through several mass configurations;
- inspect a CAD-to-MJCF conversion and identify the assumptions introduced during export;
- explain the difference between XML syntax and the MJCF model format; and
- relate the digitized mass, inertia, gravity, and actuation declarations to a one-degree-of-freedom equation of motion.

[Practice](03-practice.md) · [Instructor and TA demonstration](#instructor-and-ta-demonstration) · [Student activity](#student-activity)
## Digital representations of physical mechanisms

A photograph records appearance from one viewpoint. CAD describes designed geometry, assembly structure, reference frames, and assigned materials. A simulation description adds mechanical connectivity, mass properties, actuator inputs, sensors, gravity, contact rules, and numerical settings. Similar-looking renderings can therefore represent different mechanisms.

A **digital representation** preserves selected properties of a physical system. A **digital cousin** represents a similar mechanism without demonstrated correspondence to a particular unit. A **task-bounded digital twin** is linked to an identified physical counterpart and has tested predictive performance for stated tasks and operating conditions.

Digitization proceeds through a chain of evidence. Physical measurements constrain the CAD assembly; CAD establishes geometry and assembly relationships; and MJCF expresses those relationships as an executable mechanical model. Agreement across these representations makes every declared dimension, mass, joint, and frame traceable to the physical fixture.

### XML and MJCF describe different things

**XML**, the Extensible Markup Language, is a general text syntax for arranging information in nested elements with attributes. XML defines how a document is written, but it does not assign mechanical meaning to tags such as `body`, `joint`, or `geom`.

**MJCF**, the MuJoCo XML Format, is MuJoCo's model-description language written using XML syntax. MJCF defines the permitted elements, their attributes, units, defaults, and mechanical interpretation. An MJCF file therefore uses the `.xml` extension, but not every XML file is an MJCF model. The root `<mujoco>` element identifies the document as an MJCF model, while sections such as `<asset>`, `<worldbody>`, `<actuator>`, and `<sensor>` describe resources, rigid-body structure, inputs, and observable quantities.

| Term | Meaning | Role in this class |
|---|---|---|
| MuJoCo | Multi-Joint dynamics with Contact | physics engine that loads and simulates the mechanism |
| XML | Extensible Markup Language | general syntax used to structure the text file |
| MJCF | MuJoCo XML Format | MuJoCo-specific model language that gives the XML elements mechanical meaning |
| `.xml` | filename extension | identifies an XML text file; its contents determine whether it is MJCF |

![Digitization from the physical fixture to an executable model](../resources/class03/figures/digitization_workflow.png)

*Figure 1. Physical measurements, CAD definitions, and MJCF declarations form a traceable description of the physical mechanism.*

## A reusable one-degree-of-freedom fixture

The teaching fixture combines a ROBOTIS XC330-M288-T, an asBrain Box platform, a printed link, mounting pins, and payload bodies. The XC330 housing is fixed to the platform. Its output drives one revolute joint. The link, pins, and payloads attached to the output rotate as one rigid assembly.

Several physical parts can therefore belong to one moving body. Rigidly attaching another payload changes mass and inertia but does not introduce another degree of freedom. The number of independent joints, rather than the number of manufactured parts, determines the number of degrees of freedom.

The same fixture is prepared in five configurations so that geometry, mass placement, gravity loading, and inertia can be varied while the actuator and platform remain common.

| Configuration | Link | Payload-centre positions | External moving mass | Mechanical purpose |
|---|---:|---:|---:|---|
| M0 | none | — | 0 g | motor and platform reference |
| B0 | 22 g | −60 mm, +60 mm | 110 g | compact symmetric load |
| B1 | 22 g | −80 mm, +80 mm | 110 g | intermediate symmetric load |
| B2 | 22 g | −100 mm, +100 mm | 110 g | wide symmetric load |
| G1 | 22 g | +60 mm, +100 mm | 110 g | asymmetric gravity-loaded case |

![Mass and payload positions for the five configurations](../resources/class03/figures/configuration_mass_positions.png)

*Figure 2. External moving mass and payload-centre positions measured from the XC330 output axis.*


The labels M0, B0, B1, B2, and G1 identify fixture configurations within this apparatus. They are not general robotics categories and do not identify equivalent configurations on another platform.

### Controlled mechanical changes across the configuration family

The five configurations form a sequence of controlled mechanical changes rather than five unrelated assemblies. M0 retains the XC330 and platform without an external moving fixture. It establishes the motor-side reference and makes the absence of a link or payload explicit. Its MJCF contains a 1 mg numerical output body so that MuJoCo can represent the hinge; this placeholder is not counted as physical external moving mass. B0 introduces the complete symmetric moving assembly in its most compact arrangement.

B1 and B2 keep the same 110 g external moving mass as B0 while moving the two 44 g payload assemblies farther from the output axis. The mass is therefore held constant while its distribution changes. This distinction is fundamental: total mass alone does not determine resistance to angular acceleration. The radial placement of that mass determines its contribution to joint inertia.

G1 retains the 22 g link and the same two complete payload assemblies but places both payloads on the positive side of the axis. This breaks the symmetry of the B-series configurations. Its nonzero mass first moment makes gravity loading possible when the gravity vector has a moment arm about the joint axis.

| Configuration group | Quantity retained | Quantity changed | Mechanical concept isolated |
|---|---|---|---|
| M0 to B0 | actuator and platform | external moving assembly | addition of a connected load |
| B0 to B1 to B2 | component masses and symmetry | payload radius | rotational inertia from mass placement |
| B-series to G1 | link and payload masses | symmetry and mass first moment | configuration-dependent gravity moment |

This structure permits one MJCF template to represent a family of mechanisms. Configuration identity must remain attached to every CAD assembly, MJCF file, image, and result because equal total mass does not imply equal dynamics.

## Mass placement across the fixture family

The link has an accepted mass of 22 g. Each complete pin–payload assembly has an accepted mass of 44 g.

![Fixture components in the CAD record](../resources/class03/figures/source/fixture-components.png)

*Figure 3. Link, pin, and payload geometry used to construct the moving assembly.*

B0, B1, and B2 are symmetric about the output axis. Their ideal gravitational first moments cancel at the reference pose, while their rotational inertia increases as the payloads move outward. G1 places both payloads on the same side and produces a gravity moment when gravity has a moment arm about the joint axis.

For a rigid component, the parallel-axis principle gives

$$
J_{\mathrm{axis}}=J_{\mathrm{COM,parallel}}+mr^2.
$$

Moving both 44 g assemblies from the B0 positions at ±60 mm to the B2 positions at ±100 mm, while holding their orientations and internal properties fixed, gives

$$
\Delta J=2(0.044)(0.100^2-0.060^2)=0.0005632\ \mathrm{kg\,m^2}.
$$

The external moving mass remains 110 g because the same link and payload assemblies are used. Only their distance from the rotation axis changes. The calculation is derived from the declared geometry; it is not a measurement of total joint inertia.

## The B2 configuration across simulation, CAD, and hardware

B2 is the wide symmetric configuration. Its 22 g link carries two complete 44 g pin–payload assemblies at −100 mm and +100 mm from the XC330 output axis. The simulation, CAD, and physical records describe the same arrangement through different forms of evidence.

![B2 loaded in MuJoCo on the asBrain platform](../resources/class03/figures/source/B2_model_loaded.png)

*Figure 4. The B2 MJCF shows the symmetric payload assemblies at −100 mm and +100 mm from the XC330 output axis on the asBrain Box platform.*

![B2 Fusion 360 CAD assembly](../resources/class03/figures/source/1DOF-B2.png)

*Figure 5. The B2 CAD assembly records component geometry and assembly relationships.*

![Physical B2 fixture](../resources/class03/figures/source/260901-172518_B2_fixture-overview.png)

*Figure 6. The physical B2 fixture provides evidence of the assembled link, payloads, and actuator interface.*

The three representations contain the same mechanical elements: the fixed platform and XC330 housing, the output axis, the link, and two payload assemblies. The photograph records the assembled hardware, the CAD model defines its designed geometry and relationships, and the MJCF expresses the corresponding bodies, joint, inertial properties, and simulation interfaces. Their shared structure establishes geometric and mechanical correspondence, but it does not yet establish predictive dynamic agreement.

| Property | Physical or design source | MJCF representation |
|---|---|---|
| Component identity and arrangement | physical fixture and CAD assembly | MJCF body hierarchy and visual geometry |
| Revolute motion | actuator output and CAD joint | one MJCF hinge joint |
| Payload-centre positions | accepted dimension record | pin body positions in metres |
| Complete moving mass | accepted mass record | body masses and inertial declarations |
| Joint range | declared operating envelope | range of −π/2 to +π/2 rad |
| Collision behavior | free-motion simulation scope | disabled contact between fixture geometries |
| Motion response | encoder and command records | simulated joint state under the same command |

## Encoding the fixture in MJCF

### Expressing positions and axes in consistent frames and units

The model uses metres, kilograms, seconds, radians, and newton-metres. Its STL source assets are millimetre-scale, so each mesh declaration uses `scale="0.001 0.001 0.001"`. That scale applies to mesh vertices; it does not convert `body pos`, `joint pos`, or inertial positions.

Every coordinate is defined by a point, a reference frame, and a unit. The position of point $$P$$ expressed in frame $$A$$ is

$$
{}^A p_P={}^A R_B\,{}^B p_P+{}^A p_{O_B}.
$$

Point coordinates require both rotation and translation between frames, whereas an axis direction requires rotation only. A payload position expressed in the link frame therefore differs from its position in the world frame.

### Geometry, collision, and inertia describe different properties

| MJCF element | Role in this fixture |
|---|---|
| `body` | Builds the XC330, link, pin, and payload hierarchy |
| `joint` | Declares the single hinge and its range |
| `geom` | Supplies visual or collision geometry |
| `inertial` | Declares mass, centre of mass, and inertia tensor |
| `actuator` | Defines the simulation control input |
| `sensor` | Reports joint position, velocity, and actuator effort |

Collision is disabled in the fixture models because this class considers unconstrained rotational motion rather than contact. Visual geometry determines appearance, collision geometry determines possible contact, and inertial declarations determine mass distribution. A visible surface therefore does not imply that contact is active.

### Distinguish the simulation input from the XC330 interface

The MJCF `<motor>` accepts a direct joint-torque request in N m, bounded by the model at ±0.1551 N m. The physical XC330 instead receives register-level commands and closes embedded loops. Consequently, writing `data.ctrl[0]` is not equivalent to writing an XC330 `Goal Position`, and `data.qpos` is predicted state rather than encoder telemetry.

A later explicit controller may calculate torque from reference error,

$$
\tau_{\mathrm{cmd}}=\operatorname{sat}_{[-\tau_{\max},\tau_{\max}]}
\left(K_p(q_r-q)+K_v(\dot q_r-\dot q)\right),
$$

but this teaching controller is not a replica of XC330 firmware. The model limit is a declared simulation bound, not a measured torque result or a catalogue rating.

## From digitized properties to one-degree-of-freedom dynamics

The digitized mechanism supplies the physical quantities required to formulate rotational motion about the XC330 output axis. A one-degree-of-freedom representation can be written as

$$
J(q)\ddot q+b\dot q+\tau_f(\dot q)+\tau_g(q)=\tau_{\mathrm{act}},
$$

where $$q$$ is joint angle, $$J(q)$$ is the inertia about the joint axis, $$b\dot q$$ represents viscous damping, $$\tau_f$$ represents other friction effects, $$\tau_g$$ is the gravity moment, and $$\tau_{\mathrm{act}}$$ is the actuator torque applied to the modeled joint. For this rigid single-axis fixture, the body geometry and inertial declarations determine the modeled joint inertia for a selected configuration.

The B0, B1, and B2 payload assemblies are positioned symmetrically. Under the ideal declared geometry, equal gravity contributions from opposite sides cancel at corresponding orientations, while the joint-inertia contribution increases with payload radius. G1 places both assemblies on the same side, so their gravity contributions do not cancel.

Class 03 establishes the model structure needed by this equation: the moving bodies, joint axis, mass distribution, gravity vector, actuator input, and reported state. The numerical values of damping, friction, effective actuator response, delay, and other uncertain dynamic effects are not inferred from appearance or CAD export. Their identification and the comparison of predicted motion with measured motion belong to Class 04.

## Converting the CAD assembly to MJCF

The B0 CAD assembly illustrates how the physical mechanism becomes a connected rigid-body model. The XC330 output and link form a revolute relationship, while each payload is rigidly attached to its mounting pin. These relationships determine the body hierarchy and joint structure exported to MJCF.

![Joint-origin selection at the XC330 output](../resources/class03/figures/fusion-01-joint-origin.png)

*Figure 7. The motor-side joint origin is located at the XC330 output axis.*

![Link and motor joint-origin alignment](../resources/class03/figures/fusion-02-component-alignment.png)

*Figure 8. Coincident link-side and motor-side origins define the connection between the actuator and link.*

![Fusion revolute-joint motion setting](../resources/class03/figures/fusion-03-revolute-motion.png)

*Figure 9. The revolute joint permits rotation about the axis expressed in the Fusion joint frame.*

![Payload and pin joint-origin selection](../resources/class03/figures/fusion-04-payload-pin-origins.png)

*Figure 10. Payload and pin origins define the attachment location of the first payload assembly.*

![Rigid payload-to-pin relationship](../resources/class03/figures/fusion-05-rigid-payload.png)

*Figure 11. The rigid payload-to-pin relationship makes both components part of one moving assembly.*

![Second payload and pin attachment origins](../resources/class03/figures/fusion-06-second-payload.png)

*Figure 12. The second payload uses the same rigid attachment relationship.*

![ACDC4Robot MJCF and MuJoCo export settings](../resources/class03/figures/fusion-07-mjcf-export.png)

*Figure 13. The MJCF export transfers the CAD assembly structure to a MuJoCo model description.*

The CAD-to-MJCF conversion preserves the joint origin, joint axis, motion type, rigid grouping, component identity, and inertial data. These declarations give the exported model its mechanical meaning; geometry alone is insufficient.

### ACDC4Robot as the CAD-to-model translator

ACDC4Robot—Automated Conversion of Description Conventions for Robots from Design to Learning—is a Fusion 360 add-in that translates a CAD assembly into a robot-description format. For an MJCF export, it uses the component structure, joint definitions, joint origins, joint axes, geometry, and assigned material properties in the Fusion design to generate an XML model and its referenced mesh assets.

The add-in therefore transfers a mechanical description rather than creating one from an image. A Fusion revolute joint becomes the basis for a MuJoCo hinge, and rigidly connected components remain within the same moving branch of the exported body hierarchy. The reference frame selected in CAD is consequential: an incorrect joint origin or axis changes the rotational geometry represented in MJCF.

Exported geometry and body structure provide the starting point for simulation. Actuators, sensors, contact settings, controller gains, damping, friction, and other simulation-specific declarations are completed in the MJCF according to the purpose of the model. A successful export preserves the assembly relationships; it does not by itself establish that the model reproduces physical dynamic response.


## Mechanical meaning of the MJCF representation

Each configuration contains one revolute joint aligned with the XC330 output axis, one actuator, and sensors for joint position, joint velocity, and actuator effort. The named configuration determines the link and payload arrangement, payload-centre positions, and external moving mass. The joint range is −π/2 to +π/2 rad, and collision remains disabled for the free-motion simulation considered in this class.


![MuJoCo front views of the five XC330 fixture configurations](../resources/class03/figures/source/all-models.png)

*Figure 14. M0, B0, B1, B2, and G1 at zero joint angle show the unloaded motor, symmetric payload offsets, and asymmetric same-side loading on the common asBrain platform.*

The rendered configurations show how a common one-degree-of-freedom mechanism represents different mass placements. B0, B1, and B2 preserve symmetric loading while increasing the distance of each payload from the joint axis. G1 places both payloads on the same side and introduces a gravity moment. These geometric and inertial declarations define the mechanism being simulated; agreement with physical motion additionally depends on damping, friction, actuator response, and timing. This distinction separates physical digitization from dynamic system identification.

## Conclusion

A usable one-degree-of-freedom simulation begins with an unambiguous physical description: fixed and moving bodies, a joint origin and axis, rigid connections, geometry, mass, and mass placement. The M0, B0, B1, B2, and G1 configurations show that a common actuator and total moving mass can produce different inertia and gravity loading when the assembly changes.

Fusion 360 records the assembly relationships, and ACDC4Robot transfers those relationships into an MJCF starting point. The resulting XML model represents the mechanism only when its reference frames, joint structure, inertial declarations, meshes, and simulation-specific elements are consistent. Dynamic agreement with physical motion requires the additional experiments and parameter identification developed in Class 04.

## Instructor and TA demonstration

Use the [Class 03 practice](03-practice.md) to introduce the B0 assembly, its revolute and rigid joints, the ACDC4Robot MJCF export route, and the prepared MuJoCo models.

## Student activity

Complete the [Class 03 practice](03-practice.md). Record the selected assembly, the fixed and moving bodies, the joint relationships, the B0 moving-mass declaration, and the structural properties reported by the prepared MJCF inspection.

## Connection to Class 04

The B2 records establish the fixture-digitization method through a wide symmetric configuration. The standalone activity uses B0 so that the same assembly procedure can be followed with the compact symmetric arrangement. Both configurations use the accepted 110 g external moving mass, but their different payload radii produce different joint inertias.

[Class 04](04-basic-quantification-of-sim2real-gap.md) uses the complete P01–P05, R01–R03 experiment to quantify the pre-identification Sim2Real gap. Effective parameters are fitted on R01 and R02 and evaluated independently on R03. The [RS06 fixture companion](03-rs06-fixture-digitization.md) applies the same digitization principles to a different actuator and fixture.

## Source records and further reading

| Need | Course record |
|---|---|
| Standalone TA and student package | [Standalone package](../resources/class03/additional_material/standalone/README.md) |
| B2 CAD and MJCF | [STEP assembly](../resources/class03/additional_material/cad/STEP/1DOF-B2.step) and [B2 model](../resources/class03/additional_material/models/1DOF-B2.xml) |
| Accepted masses and positions | [Measurement record](../resources/class03/additional_material/measurements/AS_BUILT_DIMENSIONS_MASSES_AND_POSITIONS.txt) |
| Structural model checks | [JSON](../resources/class03/additional_material/results/model_validation.json), [CSV](../resources/class03/additional_material/results/tables/model_validation.csv), and [validator](../resources/class03/additional_material/code/validate_models.py) |
| Simulation figures | [Renderer](../resources/class03/additional_material/code/render_models.py) |

The source package retains the CAD, accepted measurements, MJCFs, meshes, photographs, hardware records, and executable activities used by the course. Featherstone, R. 2008. *Rigid Body Dynamics Algorithms*. Springer, supplies the rigid-body dynamics and frame background used in the lesson.
