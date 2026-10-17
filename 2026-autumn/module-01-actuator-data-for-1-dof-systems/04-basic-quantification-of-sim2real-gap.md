---
description: 27 October 2026 · 09:00–10:20 · CR6
---

# 04 Basic Quantification of Sim2Real Gap

#### Central question

How do we estimate a MuJoCo model and test its usefulness against a physical actuator?

#### Lecture — 40 minutes

1. Hardware controller, simulated actuator and experiment runner are distinct components.
2. Matched commands, load, initial conditions and time bases.
3. Armature, damping and friction loss versus controller gains; parameters need not represent isolated physical motor constants.
4. Experiment design, calibration/model-selection/held-out data, metrics and failure diagnosis.
5. Identification estimates the model; validation checks physical actuator responses for the specified single-actuator/payload task. Later LEAP experiments examine broader usefulness.
6. Introduce Introduction → Claim2Design → Design2Data → Data2Model → Model2Prototype → Sim2Real. Analytical and optimization methods are introduced briefly.

#### Break — 5 minutes

#### Instructor/TA demonstration — 25 minutes

Show the XC330 hardware collection setup, a bounded recorded/live run, the asBrain and original asMagic capture roles, and a corresponding MuJoCo replay. Inspect commands, internal references, responses, timestamps and context. Use RS06 material to compare experiment choices without conflating its controller with XC330.

#### Student activity — 10 minutes

Run a prepared XC330 analysis. Compare recorded and simulated traces, report one error measure and propose one cause. No physical actuator operation is required.
