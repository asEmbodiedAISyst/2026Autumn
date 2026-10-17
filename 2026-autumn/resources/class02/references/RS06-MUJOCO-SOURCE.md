---
description: A completed RS06 hardware case study identifying and evaluating controller-context-bounded MuJoCo joint models from repeated position-interface data.
---

# B. RS06 Hardware Experiments for Joint-Parameter Identification

{% hint style="info" %}
This appendix reports a **completed retrospective analysis** of the supplied
RS06 hardware campaign. The dynamic records were assigned to calibration,
model-selection, and held-out roles during collection; the identification implementation was
developed after the complete archive became available. The results support
strong context-bounded position-prediction candidates, but they do not yet
establish uniquely recovered physical motor constants. Fixture mass properties
remain CAD-derived, the firmware torque field is not an independently calibrated
shaft-torque measurement, and a newly collected prospective held-out evaluation is still
recommended.
{% endhint %}

## B.1 Progressive Claim and Result

The bounded claim tested here is:

> **For each fixed RS06 position-controller context, repeated position-interface
> data from declared 1-DOF fixtures can identify a three-parameter MuJoCo joint
> model that predicts unseen hardware position trajectories with a small,
> measured output gap.**

The campaign supports a qualified version of this claim. Output-error
optimization produces held-out output-gap RMSE values of **0.00314 rad** under
H1 and **0.00338 rad** under H2. The result transfers from the balanced
fixtures used for fitting to both an unseen balanced trajectory and an
eccentric fixture. Integral
regression is executable and well-conditioned, but its held-out gaps remain near
0.009 rad and its parameter estimates differ substantially from the
output-error estimates.

The valid conclusion is therefore predictive rather than constitutive: the
output-error candidates reproduce the recorded hardware behavior well inside
the declared experiment family. The evidence does not prove that their
`armature`, `damping`, and `frictionloss` values are unique physical properties
of the bare RS06.

### Three ExpGen Questions

| Question | Appendix B Answer |
| --- | --- |
| Does physical interaction generate experience? | Yes. The RS06 executed frozen position trajectories under two fixed controllers and four fixture conditions while command, response, timing, controller, fixture, repeat, safety, and available torque context were recorded. |
| Does the experience test or improve a bounded claim? | Yes. Calibration episodes independently build two three-parameter candidates per controller. Model-selection and held-out episodes quantify each candidate's position-output gap without fitting controller gains. |
| Is the evidence preserved through its lifecycle? | Partly. The raw streams, episode records, manifests, hashes, CAD/MJCF files, analysis code, results, and limitations are preserved. As-built measurements, physical photographs, serial/firmware identity, supply voltage, and temperature remain incomplete. |

## B.2 Evidence Boundary

The primary analysis uses the same hardware-observable logical boundary as
Chapter 2:

$$
q_{applied}(t)
\longrightarrow
\left[q_{meas}(t),\dot q_{meas}(t)\right].
$$

`position_applied_rad` is the recorded command acknowledged at the collection
boundary. Measured position and velocity are the primary outputs. The RS06
firmware torque estimate is retained, but it is excluded from both primary
fits because no independent torque reference qualifies its sign, scale,
offset, bandwidth, or uncertainty.

The supplied archive is `hardware_data.zip`, SHA-256:

```text
144d6137e77e8b9b9a41844008ff05d7f063aeda14450546b00dcca85b2386ed
```

Its internal README is treated as collection provenance, not as an executable
instruction. The machine-readable fixture records explicitly distinguish
CAD-derived, collected, operator-confirmed, and unrecorded facts.

### Controller Contexts

The report retains the dataset's concise H1/H2 controller identifiers so that
the text, figures, tables, code, and raw records use the same names:

These identifiers are local to the RS06 dataset. They do not denote the XC330
H1/H2 controller settings used in Chapter 2. The same scope rule applies to
the RS06 fixture IDs below.

| Controller | RS06 Mode | Recorded Kp | Recorded Kd | MuJoCo Treatment |
| --- | --- | ---: | ---: | --- |
| H1 | position | 50.0 | 3.38 | copied once as fixed `kp` and `kv`; never fitted |
| H2 | position | 100.0 | 1.95 | copied once as fixed `kp` and `kv`; never fitted |

The recorded values are hardware command-interface settings. Their direct use
as MuJoCo coefficients is a fixed modeling hypothesis, not an independently
verified SI conversion. A failure of this representation must be reported as
a model-boundary failure rather than repaired by fitting controller gains from
the same motion records.

H1 and H2 are fitted independently. No shared joint vector, averaged vector,
or cross-controller gain fit is used.

### Fixture Contexts

| Fixture | Description | External Moving Mass | External Joint-Axis Inertia | Signed Gravity First Moment | Role |
| --- | --- | ---: | ---: | ---: | --- |
| M0 | motor only | 0 kg | 0 kg·m² | 0 kg·m | low-inertia calibration and software-path check |
| B0 | balanced link | 0.687213 kg | 0.0129095 kg·m² | −0.0000366 kg·m | calibration and model selection |
| B1 | balanced payload | 2.407213 kg | 0.0576790 kg·m² | −0.0000366 kg·m | calibration, model selection, and held out |
| G1 | eccentric payload | 1.547213 kg | 0.0352943 kg·m² | −0.129037 kg·m | unseen eccentric held-out evaluation and static-gravity diagnostic |

The inertia values come from the supplied Fusion/MJCF export and parallel-axis
calculation. They exclude the unknown RS06 reflected inertia and the MuJoCo
joint `armature`, preventing those terms from being deliberately counted
twice. They are not independent measurements of the as-built station.

## B.3 Dataset Audit

The dynamic archive contains **108 complete episodes and 57,694 samples** at
50 Hz. No command saturation is recorded. One sample in one H2/B1 chirp
episode is marked invalid and is excluded from scoring. The local episode grid
is exactly 0.02 s; raw host timing, schedule lateness, feedback gaps, and echo
delay remain preserved separately.

| Evidence Role | Assignment | Episodes | Repeats per Combination | Identification Use |
| --- | --- | ---: | ---: | --- |
| Calibration | M0/B0/B1 × P01–P03 × H1/H2 | 54 | 3 | estimate three parameters independently for each controller |
| Model Selection | B0/B1 × P04–P05 × H1/H2 | 24 | 3 | evaluate unseen trajectories; no parameter fitting |
| Held Out | B1 × P06 × H1/H2 and G1 × P06–P07 × H1/H2 | 30 | 5 | final balanced and eccentric transfer comparison |

This differs from the XC330 campaign in Section 2.4 because the RS06 station
provides B0 and B1 rather than the XC330's balanced fixture family. The
evidence logic remains equivalent: calibrate across declared inertia contrast,
select models using unseen trajectories, and evaluate final transfer using
complete held-out repeated episodes.

### Hardware Tracking Behavior

Tracking error compares the hardware output with its own applied command:

$$
e_{track,e}(t)=q_{meas,e}(t)-q_{applied,e}(t).
$$

| Controller | Calibration Tracking RMSE | Model-Selection Tracking RMSE | Held-Out Tracking RMSE |
| --- | ---: | ---: | ---: |
| H1 | 0.05841 rad | 0.08937 rad | 0.06510 rad |
| H2 | 0.02499 rad | 0.03660 rad | 0.02915 rad |

The second controller tracks more closely, but tracking performance is not the
model gap. A simulator can reproduce a hardware trajectory even when both
hardware and simulation have a nonzero command-tracking error.

### Repeatability Floor

For repeated episodes sharing controller, fixture, and trajectory, the report
computes each repeat's RMSE to the combination mean. The equal-combination
floors are:

| Controller | Calibration | Model Selection | Held Out |
| --- | ---: | ---: | ---: |
| H1 | 0.000565 rad | 0.000509 rad | 0.000425 rad |
| H2 | 0.000415 rad | 0.000581 rad | 0.000482 rad |

These floors describe repeat dispersion, not an attainable zero-error target.
They nevertheless provide a useful scale for judging whether model error is
large relative to observed run-to-run variation.

## B.4 One Three-Parameter MuJoCo Model

Both methods identify only

$$
\boldsymbol\theta_J^{MJ}=
\begin{bmatrix}
\texttt{armature} &
\texttt{damping} &
\texttt{frictionloss}
\end{bmatrix}^{T}.
$$

| MuJoCo Name | Mathematical Symbol | Unit | Effective Role |
| --- | --- | --- | --- |
| `armature` | $$J_a^{MJ}$$ | kg·m² | additional joint-space inertia beyond the declared fixture bodies |
| `damping` | $$b^{MJ}$$ | N·m·s/rad | velocity-proportional passive resistance |
| `frictionloss` | $$\tau_c^{MJ}$$ | N·m | MuJoCo dry-friction constraint-force limit |

The values are effective MuJoCo parameters for the complete declared
actuator–fixture–controller boundary. They may absorb rotor and transmission
dynamics, controller mismatch, timing, sensing, mounting, and unmodeled
friction behavior. Controller gains are fixed context rather than two
additional identification variables.

There is no Nominal Model in this hardware study. Method 2's three starting
vectors are numerical optimizer initializations only and are never treated as
physical or behavioral baselines.

## B.5 Method 1 — Integral Regression

The fixed controller representation reconstructs the simulated effort

$$
\tau_C(t)=
k_p\left[q_{applied}(t)-q(t)\right]-k_v\dot q(t).
$$

For the free-moving 1-DOF station,

$$
\left(J_{fixture}+J_a^{MJ}\right)\ddot q
+b^{MJ}\dot q
+\tau_c^{MJ}\operatorname{sgn}(\dot q)
+\tau_{bias}(q)
\approx\tau_C.
$$

Integrating over one window avoids differentiating the measured velocity:

$$
J_a^{MJ}\Delta\dot q
+b^{MJ}\Delta q
+\tau_c^{MJ}\int\operatorname{sgn}(\dot q)dt
\approx
\int\left(\tau_C-\tau_{bias}\right)dt
-J_{fixture}\Delta\dot q.
$$

The implementation applies a frozen Savitzky–Golay filter, uses 0.20 s
windows stepped by 0.04 s, excludes invalid/saturated samples, and admits only
windows moving above 0.05 rad/s for at least 70% of their duration. Complete
episodes receive equal weight. Bounded linear least squares estimates the
three joint quantities.

The normalized regression condition numbers are 2.52 for H1 and 2.50 for H2;
neither fit reaches a parameter bound. This demonstrates numerical solvability,
but the approximation still relies on the fixed controller law, filtered
velocity, CAD fixture properties, and the chosen three-term joint model.

## B.6 Method 2 — Output-Error Optimization

Output-error optimization treats MuJoCo as the nonlinear forward model. For
each calibration episode, the simulator receives the recorded applied position and the
matching fixed controller. Only the three joint parameters change. The
objective is

$$
\hat{\boldsymbol\theta}_{J,h}^{MJ}
=\underset{\boldsymbol\theta\in\Theta}{\operatorname{argmin}}
\frac{1}{|\mathcal E_{cal,h}|}
\sum_{e\in\mathcal E_{cal,h}}
\operatorname{MSE}\!\left[
\hat q_e(t;\boldsymbol\theta),q_{meas,e}(t)
\right].
$$

Each replay starts from the episode's first measured position and velocity.
The 50 Hz command is held across the 0.002 s MuJoCo physics steps. Three widely
separated starts are run for each controller; all converge to nearly the same
H-specific solution without reaching a bound. Model-selection and held-out
episodes do not enter the objective.

| Parameter | Lower Bound | Upper Bound |
| --- | ---: | ---: |
| `armature` | 0.0000001 kg·m² | 0.10 kg·m² |
| `damping` | 0 N·m·s/rad | 10 N·m·s/rad |
| `frictionloss` | 0 N·m | 10 N·m |

The starts are the source-MJCF vector
$$[0.00124849, 0.000437735, 0.0481937]$$, the matching integral-regression
estimate, and the deliberately separated vector $$[0.01, 0.10, 0.10]$$.
These are optimization starts, not Nominal Models or comparison baselines.

## B.7 Identified Parameters

| MuJoCo Parameter | Method 1 H1 | Method 2 H1 | Method 1 H2 | Method 2 H2 |
| --- | ---: | ---: | ---: | ---: |
| `armature` | 0.0625670 kg·m² | 0.0108577 kg·m² | 0.0459995 kg·m² | 0.0122131 kg·m² |
| `damping` | 0.653082 N·m·s/rad | 0.0693953 N·m·s/rad | 1.272206 N·m·s/rad | 0.229737 N·m·s/rad |
| `frictionloss` | 0.226202 N·m | 0.299307 N·m | 0.259537 N·m | 0.272210 N·m |

*Historical source asset: RS06 joint-parameter candidates (`../assets/appendix-b/rs06-real-position-v1/parameter-comparison.png`); not included in this extract.*

**Figure B.1 — Controller-specific joint candidates.** The two methods do not
recover the same vector. Output-error estimates are more predictive, while the
integral approximation attributes substantially more response to `armature`
and `damping`.

For the output-error candidates, H1-to-H2 symmetric differences are 11.75% for
`armature`, 107.20% for `damping`, and 9.48% for `frictionloss`. The large
`damping` difference reinforces the decision to retain two controller-specific
effective models. It also indicates that the fixed controller representation
and passive joint terms are not physically separable from these data alone.

## B.8 Output-Gap Evidence

The model-to-hardware gap is

$$
g_{m,e}(t)=\hat q_{m,e}(t)-q_{meas,e}(t).
$$

| Controller | Method | Calibration Gap | Model-Selection Gap | Held-Out Gap | Held-Out Gap / Repeat Floor |
| --- | --- | ---: | ---: | ---: | ---: |
| H1 | Method 1 | 0.00898 rad | 0.01242 rad | 0.00874 rad | 20.55× |
| H1 | Method 2 | 0.00447 rad | 0.00260 rad | 0.00314 rad | 7.39× |
| H2 | Method 1 | 0.00865 rad | 0.01201 rad | 0.00904 rad | 18.74× |
| H2 | Method 2 | 0.00389 rad | 0.00268 rad | 0.00338 rad | 7.01× |

*Historical source asset: RS06 output gap by split (`../assets/appendix-b/rs06-real-position-v1/split-output-gap.png`); not included in this extract.*

**Figure B.2 — Position-output gap and repeatability.** Output-error
optimization is consistently more predictive. Its held-out gap is small in
absolute angle but remains above repeat dispersion, so the remaining structured
gap should not be hidden by the favorable trajectory overlay.

### Fixture-Level Held-Out Transfer

| Controller | Method | Balanced-Payload B1/P06 | Eccentric G1/P06–P07 |
| --- | --- | ---: | ---: |
| H1 | Method 1 | 0.00933 rad | 0.00844 rad |
| H1 | Method 2 | 0.00358 rad | 0.00293 rad |
| H2 | Method 1 | 0.00919 rad | 0.00896 rad |
| H2 | Method 2 | 0.00351 rad | 0.00332 rad |

The eccentric transfer does not degrade relative to the balanced B1 held-out evaluation.
This is stronger than the present XC330 G1 result in Section 2.4, but it remains
conditional on the supplied G1 orientation and CAD mass properties.

*Historical source asset: Representative RS06 held-out replays (`../assets/appendix-b/rs06-real-position-v1/heldout-replays.png`); not included in this extract.*

**Figure B.3 — Representative held-out replays.** Each panel uses the first
recorded P06 repeat for a fixed controller and fixture. The applied command,
hardware output, and both candidate outputs remain distinct. The legend reports
model-to-hardware RMSE, not controller tracking error.

## B.9 Supporting Torque and Static-Gravity Diagnostics

### Firmware Torque Consistency

The recorded firmware torque estimate is compared with

$$
\tau_{reconstructed}=k_p(q_{applied}-q)-k_v\dot q
$$

only as an internal-consistency diagnostic:

| Controller | Correlation | Fitted Scale | Fitted Offset | Diagnostic RMSE |
| --- | ---: | ---: | ---: | ---: |
| H1 | 0.665 | 0.369 | 0.034 N·m | 0.362 N·m |
| H2 | 0.413 | 0.169 | 0.081 N·m | 0.474 N·m |

The weak-to-moderate agreement shows that direct numerical controller gains do
not reproduce the device's reported effort channel. This does not invalidate
the position-output candidates, but it explains why their joint vectors must
remain context-bounded: the passive parameters can absorb differences in the
unmodeled controller and effort path.

### Static-Gravity Diagnostic

Two G1 sessions hold seven poses from −2.356 to +2.356 rad, approached from
both directions, under H1 and H2. The final 1 s of each hold is averaged.
Approach-paired firmware torque is regressed against the gravity torque
computed from the supplied MJCF:

| Controller | Paired Poses | Scale | Offset | RMSE | $$R^2$$ | Mean Approach Half-Difference |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H1 | 7 | 1.038 | −0.033 N·m | 0.247 N·m | 0.920 | 0.141 N·m |
| H2 | 7 | 1.083 | 0.082 N·m | 0.363 N·m | 0.854 | 0.068 N·m |

*Historical source asset: RS06 static-gravity diagnostic (`../assets/appendix-b/rs06-real-position-v1/static-gravity-diagnostic.png`); not included in this extract.*

**Figure B.4 — Static-gravity torque-path diagnostic.** The approximately
unit scale and strong trend are encouraging workflow evidence. They are not a
complete torque calibration because only one physical installation orientation
was collected, the gravity first moment is CAD-derived, the torque signal is a
firmware estimate, and approach-dependent friction remains visible. The static
poses also extend beyond the supplied MJCF joint range of ±1.1 rad; this must be
reconciled before these records are used for dynamic MuJoCo validation.

## B.10 Model Decision and Reality-Gap Interpretation

| Candidate | Decision | Reason |
| --- | --- | --- |
| Real-Position M1 Candidate — H1 | retain as analytical diagnostic | solvable and bounded, but model-selection/held-out gap is about 0.009–0.012 rad and parameters are strongly method-sensitive |
| Real-Position M1 Candidate — H2 | retain as analytical diagnostic | same limitation; not preferred for forward prediction |
| Real-Position M2 Candidate — H1 | promising context-bounded candidate | 0.00314 rad held-out gap, stable optimizer convergence, balanced and eccentric transfer |
| Real-Position M2 Candidate — H2 | promising context-bounded candidate | 0.00338 rad held-out gap, stable optimizer convergence, balanced and eccentric transfer |

The chapter-level distinction remains essential:

- **tracking error** measures how the physical or simulated controller follows
  its own applied position;
- **model-to-hardware gap** measures whether a candidate reproduces the
  recorded hardware output under the same input; and
- **parameter difference** measures how two effective model vectors differ,
  not whether their predicted trajectories are acceptable.

The RS06 study reduces the behavioral reality gap to a few milliradians within
the recorded family. It does not eliminate the Controller2Model,
Measurement2Model, or Fixture2Model boundaries. The large method dependence
and H-specific `damping` values show that several unmodeled effects can still
be represented by the same three MuJoCo fields.

## B.11 Validity Boundary and Next Evidence

The current result is valid only for:

- this RS06 unit and unrecorded physical revision;
- position mode at 50 Hz;
- the two recorded fixed controller settings;
- the M0/B0/B1/G1 station family and supplied CAD mass properties;
- approximately the recorded ±0.75 rad dynamic range and trajectory bandwidth;
- the recorded but incompletely documented supply and thermal context; and
- the supplied MuJoCo model class, solver, limits, and 0.002 s timestep.

Before calling either output-error vector an accepted reusable hardware model:

1. measure the as-built moving masses, payload distances, joint-axis inertia,
   orientation, zero, and uncertainty;
2. record the motor asset/serial, firmware, supply voltage, temperature, and
   fixture/mounting revisions;
3. verify the physical range and reconcile it with the MJCF joint limits;
4. collect one newly frozen prospective model-selection and held-out campaign without
   revising preprocessing, gains, bounds, or model structure;
5. repeat static gravity in a reversed installation if the torque path is to
   support a calibrated effort claim; and
6. inspect time-series residuals for direction, speed, acceleration,
   temperature, and timing structure before expanding the validity range.

An independent torque transducer is not required for the present
position-to-position predictive claim. It becomes necessary if the claim is
expanded to physically calibrated output torque or uniquely separated motor
and controller dynamics.

## B.12 Reproduction and Files

The complete derived result package is downloadable here:

- *Historical source asset: RS06 hardware-identification results v1 (`../.gitbook/assets/appendix-b/rs06-real-position-results-v1.zip`); not included in this extract.*

Download SHA-256:

```text
f01efca40f2ef3aa756aab8deef390f3d55eccbdbe486ef89827ceecac84989c
```

Principal files are:

- `joint-parameter-estimates.csv`;
- `aggregate-metrics.csv`;
- `fixture-metrics.csv`;
- `episode-metrics.csv`;
- `repeatability.csv`;
- `static-gravity-diagnostic.csv`;
- `dataset-audit.json`;
- `result.json`; and
- `run-analysis.py`.

Reproduce the analysis from the supplied archive with:

```bash
.venv/bin/python scripts/run_appendix_b_rs06_hardware_identification_v1.py \
  /path/to/hardware_data.zip \
  --output data/appendix-b/rs06-real-position-v1 \
  --figures assets/appendix-b/rs06-real-position-v1
```

The runner verifies the expected 108-episode matrix, fits H1 and H2
independently, excludes the torque field from both primary methods, replays all
dynamic episodes, computes repeatability and split/fixture metrics, and
generates the static-gravity diagnostic.

## B.13 Five Development Layers Review

| Development Layer | Evidence Obtained | Remaining Boundary |
| --- | --- | --- |
| 1. Physical Embodiment | four hash-bound CAD/MJCF fixture definitions spanning 0 to 0.057679 kg·m² external inertia and an eccentric G1 load | as-built mass properties, assembly/mounting revisions, photographs, range, and uncertainty remain pending |
| 2. Sensing and Actuation | acknowledged position input, measured position/velocity, raw timing, fixed controller contexts, safety fields, and firmware torque estimate | controller SI equivalence and torque calibration remain unqualified; voltage and temperature were not recorded |
| 3. Computation and Representation | immutable source-archive hash, manifests, raw/episode records, explicit logical field boundary, executable analysis, and machine-readable results | future releases must preserve the field definitions and concise identifiers used here |
| 4. Robo-Physical Learning and Task Validation | two methods, two independent controller contexts, three calibration fixtures, unseen trajectories, repeated balanced/eccentric held-out episodes, and quantified gaps | method-sensitive parameters and residual gap above repeatability prevent a unique physical-parameter claim |
| 5. Lifecycle Evidence | claims, data boundary, parameters, methods, plots, decisions, limitations, and reproduction files are linked in one report | newly frozen prospective evidence and completed physical provenance are required for final acceptance |

The appendix therefore demonstrates that the Chapter 2 workflow transfers to
a QDD actuator in a technically useful way. Its strongest outcome is a pair of
predictive, controller-context-bounded MuJoCo models and a transparent account
of what those models do—and do not—establish.
