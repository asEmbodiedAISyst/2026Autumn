---
description: 23 October 2026 · 09:00–10:50 · L12
---

# 03 Basic Digitization of Physical Embodiment

#### Central question

What does a digital representation preserve, and which parts can we validate?

#### Learning objectives

* Distinguish a digital representation, digital cousin and task-bounded digital twin.
* Inspect geometry, frames, joints, mass, inertia and collision assumptions.
* Define validation against a physical actuator with a specified link/payload experiment.

#### Lecture — 50 minutes

1. Geometry alone does not establish behavioral correspondence.
2. Sim2Real differences from design, manufacturing, assembly, communication, controllers and simulation assumptions.
3. CAD physical properties as estimates: validation is difficult and usually limited to selected properties and operating conditions.
4. The intended task here is the designed single-actuator identification experiment with a declared payload.
5. CAD → robot description → MuJoCo, including visual versus collision geometry.
6. Printing, clearance, material/process variation and mass/inertia uncertainty.

#### Break — 10 minutes

#### Instructor/TA demonstration — 35 minutes

Use a prepared RS06 assembly and engineering drawings. Inspect its joints and physical properties in Fusion, simplify for simulation, export with ACDC4Robot, and load the prepared MJCF in MuJoCo. Check dimensions, axes, limits and gravity behavior. Show a prepared printed part and a brief H2D printer setup; do not wait for printing to finish.

#### Student activity — 15 minutes

Load a supplied XC330/XL330 model, inspect one joint and change a declared link/payload parameter. Compare the simulation assumption with the actual or printed component. Inspect the printer when feasible.

#### Before/after class

Account registration and software installation belong in preflight. CAD remodeling, export repetition and custom printing may continue during project time. Optional printing work must record clearance and measured mass.
