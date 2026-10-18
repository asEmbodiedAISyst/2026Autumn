---
description: Replace Source Model observations with Real-Position Data from a matched XC330 prototype while preserving the Data2Model method contract.
---

# 2.4 Model2Prototype

{% hint style="warning" %}
**Development Status:** The 25 August 2026 XC330 campaign now contains the
complete dynamic M0/B0/B1/B2/G1 matrix: 260 recorded episodes, including 234
analysis episodes and 30 held-out H1/H2 repeats. Measured part masses and the
physical B0 ±60 mm revision are incorporated below. The first reproducible
Method 1/2 run is **retrospective preliminary evidence**, not the final
prospective result because the inner trajectory adapter was finalized
after collection. Controller gains are not identified. The known H1 and H2
registers are converted through one fixed, disclosed XC330 Mode-5 engineering
map to two SI-scale MuJoCo controller contexts, and each context produces its
own joint-parameter candidates.
{% endhint %}

## Progressive Claim

> **The matched 3D-printable XC330 1-DOF prototype can generate qualified
> position-command and position/velocity-response records from which the same
> analytical and optimization principles used with Sim-Position Data can
> build and prospectively test independent H1 and H2 Real-Position M1 and
> M2 Candidates within one context-bounded, three-parameter MuJoCo joint model
> class.**

Real-Position Data replace Source Model observations and change the
provenance of the configuration. They retain the transmitted Goal Position as
the application-facing input and the recorded DYNAMIXEL Position and Velocity
Trajectories as the inner controller references. They may retain optional, explicitly
qualified effort-related telemetry, but they do not authorize treating a
hardware estimate as MuJoCo `qfrc_actuator` or changing the three-parameter
target. The controller registers and their declared conversion are known and
fixed rather than improved by gain identification.

### Three ExpGen Questions

| Question From Chapter 1 | Model2Prototype Interpretation |
| --- | --- |
| Does interaction generate physically grounded experience? | The fabricated XC330-M288-T rig executes the declared profiles while command, measured response, controller, fixture, timing, operating condition, and repeat records are preserved. |
| Does the experience test or improve a bounded claim or capability? | Calibration records build separate H1 and H2 Real-Position M1 and M2 Candidates; model-selection and held-out-labeled records measure each candidate's absolute output-to-hardware gap. |
| Is the evidence preserved and managed? | CAD and print revisions, measured part properties, MJCFs, raw packets, conversions, device settings, clocks, exclusions, fits, predictions, failures, and results remain linked to one immutable campaign release. |

## What Must Stay Fixed and What May Change

The transition is an evidence-source substitution:

| Item | Section 2.3 Simulation Release | Section 2.4 Prototype Release | May the Method Change? |
| --- | --- | --- | --- |
| application-facing input | simulated requested/applied position | transmitted Goal Position converted to radians | retained for end-to-end tracking and later firmware-profile modeling |
| effective controller references | direct MuJoCo position command and its known controller context | recorded DYNAMIXEL Position and Velocity Trajectories converted to the same joint coordinate | used by the three-joint-parameter fit so firmware profile generation is not absorbed into `armature`, `damping`, or `frictionloss` |
| observed position | quantized Source Model position | synchronized XC330 Present Position | no |
| observed velocity | quantized Source Model velocity | Present Velocity or one qualified frozen estimate | no |
| optional mechanical-plant input context | privileged Source and Nominal Model `qfrc_actuator` fields, excluded from fitting | available current/PWM, torque command or feedforward, torque estimate, or independent torque measurement, each separately named and qualified | no; optional fields remain outside the primary fit for this study |
| controller conditions | fixed C1 and C2 MuJoCo `kp`/`kv` | fixed H1/H2 primary contexts converted through the declared Mode-5 engineering map, plus H3–H5 diagnostics | no gain is fitted; each H context identifies and evaluates its own joint vector |
| fixture record | preliminary matched MJCF | MJCF updated from measured printed-part properties | configuration values change; model boundary does not |
| Method 1 | three-parameter integrated closed-loop bounded regression | same equation and target applied independently to H1 and H2 after signals are qualified | preprocessing may be revised from calibration data, then frozen before prospective held out |
| Method 2 | three-parameter bounded MuJoCo output-error optimization | same three-parameter target, bounds discipline, replay, and split logic | no structural change after unblinding held out |
| ground-truth parameters | disclosed after fitting for simulation evaluation | unavailable | parameter-distance grading is removed |
| evidence label | projected Model2Model evidence | measured physical evidence | yes; provenance must change |

The present run is explicitly retrospective because the hardware adapter was
finalized after collection. The next release must freeze that adapter before
acquiring or unsealing a new held-out campaign. Controller values and
three-parameter bounds are fixed inputs to each fit, not additional variables.

## Matched Physical–Digital Boundary

| Boundary Item | Physical Prototype | MuJoCo Counterpart | Required Qualification |
| --- | --- | --- | --- |
| actuator | one XC330-M288-T with recorded model, ID, firmware, mode, and limits | one effective position actuator | identity and operating mode remain fixed for the campaign |
| moving fixture | printed link, pins, and payloads for M0/B0/B1/B2/G1 | matching bodies and inertials | measured mass, installed center distance, center of mass, and inertia estimate replace preliminary values |
| controller | H1 and H2 complete DYNAMIXEL register sets; H3–H5 diagnostic sets | H1: $$K_p^C=1.57984$$ N·m/rad and $$K_v^C=0.202115$$ N·m·s/rad; H2: $$K_p^C=2.10645$$ N·m/rad and $$K_v^C=0.202115$$ N·m·s/rad | fixed Mode-5 engineering conversion is disclosed; no gain is fitted |
| external input | requested and transmitted Goal Position | later end-to-end command/profile model input | sign, zero, unit conversion, clipping, sequence, and command time are documented |
| inner controller references | Position and Velocity Trajectory registers sampled with telemetry | zero-order-held references to a torque-limited position/velocity-error controller around a MuJoCo `<motor>` | firmware origin, sample time, quantization, and distinction from measured state are preserved |
| output | Present Position and velocity record | simulated sensor-equivalent position and initial velocity | resolution, rollover, sign, zero, timestamp, and filtering are qualified |
| operating context | supply, temperature, orientation, mounting, limits, packet health, and faults | declared effective context and gravity orientation | deviations are recorded rather than absorbed silently into parameters |

The prototype boundary therefore includes more than the bare servo. A change
in a printed part, payload location, supply, gain register, motion profile,
firmware, communication schedule, or analysis filter creates a different
configuration or campaign revision.

## Prototype Qualification Before Identification

Complete these checks before collecting accepted calibration episodes:

1. weigh every installed link, pin, and payload version;
2. measure the payload-center distance and mounting orientation for every
   fixture;
3. calculate each moving assembly's center of mass and inertia about the joint
   axis, then update and render its MJCF;
4. verify joint zero, positive direction, position conversion, safe range, and
   collision clearance;
5. record XC330 model, firmware, device ID, supply, interface, host software,
   DYNAMIXEL SDK revision, and collection revision;
6. freeze H1 and H2, including Operating Mode, Position PID, feedforward,
   profile, current, PWM, velocity, and position limits;
7. establish cold-start, warm-up, temperature-stop, fault-stop, packet-loss,
   and operator-stop rules;
8. qualify command and response timestamps, including any DYNAMIXEL Realtime
   Tick use and host-clock association; and
9. execute low-amplitude M0 pilot episodes before installing loaded fixtures.

The [XC330-M288-T e-Manual](https://emanual.robotis.com/docs/en/dxl/x/xc330-m288/)
is the authoritative reference for operating modes, control-table addresses,
units, profiles, limits, Present Position, Present Velocity, Present Current,
Present PWM, Realtime Tick, and Hardware Error Status. Raw values must be
preserved alongside every SI conversion.

### Measured Fixture Revision

The fabricated parts use one 6 g link, two 4 g pins, and two 42 g payloads in
every loaded configuration. Because the STL geometry is unchanged, each
part's preliminary center-of-mass inertia is scaled linearly from its original
uniform-density value to its measured mass. The parallel-axis theorem then
gives the following preliminary-as-built fixture properties:

| Fixture | Installed Payload Centers | Added Moving Mass | Fixture Inertia About Joint | First Moment | Maximum Gravity Torque |
| --- | --- | ---: | ---: | ---: | ---: |
| M0 | none | 0 kg | 0 kg·m² | 0 kg·m | 0 N·m |
| B0 | −60 mm, +60 mm | 0.098 kg | 0.000371055 kg·m² | approximately 0 kg·m | approximately 0 N·m |
| B1 | −80 mm, +80 mm | 0.098 kg | 0.000628655 kg·m² | approximately 0 kg·m | approximately 0 N·m |
| B2 | −100 mm, +100 mm | 0.098 kg | 0.000959855 kg·m² | approximately 0 kg·m | approximately 0 N·m |
| G1 | +60 mm, +100 mm | 0.098 kg | 0.000665455 kg·m² | 0.00736 kg·m unsigned | 0.0722016 N·m |

The G1 CAD locations are positive. In the recorded bench coordinate the
torque-off fixture rests toward negative position, so the matched MuJoCo model
uses a signed first moment of −0.00736 kg·m. These inertia values remain an
engineering approximation: they use measured masses and exact STL geometry
but assume uniform equivalent density within each printed part.

### Campaign Audit

The supplied archive contains 260 complete episode directories. Of these, 180
are calibration, 24 are model selection, 30 are held out, 14 are safety pilots,
and 12 are preparation/recentering records. All telemetry timing checks pass;
no Hardware Error Status sample is nonzero; no critical before/after register
check fails; and torque remains enabled inside every episode. The telemetry
interval averages 0.00499986 s, with a 0.0101282 s maximum gap. Recorded
voltage is 4.9–5.2 V, temperature is 22–26 °C, Present Current is
−0.211–0.259 A, and Present PWM is −0.44635–0.44861 of the device-native full
scale.

## Physical Data Record

The collection keeps the same four data categories used by Section 2.2.

| Common Data Category | Required Physical Record | Analysis Role |
| --- | --- | --- |
| command input | host request, transmitted Goal Position, sequence identity, raw register value, radian conversion, clipping, and command time; sampled Position Trajectory and Velocity Trajectory | preserves both the application-facing command and the inner firmware-generated controller references |
| controller definition | complete H1/H2 register snapshots, Operating Mode, update rate, profiles, and limits; fixed Mode-5 engineering conversion to MuJoCo coefficients | defines two independent physical/simulation contexts without adding gain variables to either joint fit |
| measured response | raw Present Position and Present Velocity with state time; Present Current, Present PWM, status, errors, and any qualified torque estimate as supporting telemetry | constructs observed position/velocity and validity records while retaining optional effort context |
| operating context | actuator, fixture, profile, repeat, orientation, supply, temperature, clock, software, fault, exclusion, and intervention metadata | bounds the claim and enables repeat analysis |

The minimum derived analysis arrays remain:

```text
time_s
external_goal_position_rad
controller_position_trajectory_rad
controller_velocity_trajectory_rad_s
observed_position_rad
observed_velocity_rad_s
valid
saturated
```

Controller, fixture, profile, split, and repeat identities are episode
metadata. The raw packet log is immutable; alignment and conversion create a
versioned derived archive. A field that cannot be qualified is marked
unavailable rather than silently inferred.

The distinction between the two position inputs is essential. Replaying Goal
Position directly through a bare MuJoCo `<position>` actuator omits the
DYNAMIXEL profile generator and causes profile delay to be absorbed into the
three joint parameters. The preliminary joint study therefore uses the
recorded Position and Velocity Trajectories as the matched inner-loop references. Goal Position is
still the authoritative application input and remains necessary for a later
end-to-end firmware-profile model.

Present Current and Present PWM are important diagnostic channels, especially
for finding clipping, load-dependent behavior, and temperature effects. They
are not required inputs to either primary method and must not be renamed
as generalized output-joint torque.

### Optional Mechanical-Plant Input Context

The v1.2 contract adds optional effort-related sample fields without changing
the minimum position analysis arrays:

| Field | Meaning | XC330 Position Mode | RS06 Position or MIT Mode |
| --- | --- | --- | --- |
| `current_cmd_A` | commanded current | normally unavailable as the active command | mode dependent; available in current mode rather than an ordinary position track |
| `current_meas_A` | reported or independently measured current | collect Present Current when available; it is device-input current, not phase-current or shaft-torque ground truth | collect available q-axis or filtered-current feedback with its exact source |
| `pwm_meas_native` | device-native PWM telemetry | collect Present PWM | generally not the common RS06 application field |
| `torque_cmd_Nm` | direct requested torque | unavailable in the primary position-mode experiment | mode dependent |
| `torque_ff_cmd_Nm` | torque-feedforward part of a composite command | unavailable | available in an MIT-style command when used |
| `torque_est_Nm` | firmware- or current-derived output-joint torque estimate | optional only after declaring the derivation; G1 static gravity calibration can provide a bounded check | collect the reported estimate when available, but retain its unqualified status until sign, scale, timing, bandwidth, and uncertainty are checked |
| `torque_meas_Nm` | independently qualified output-joint torque measurement | unavailable without added instrumentation; a known G1 gravity torque is a static reference, not a dynamic transducer | unavailable without added instrumentation |

Every unavailable field is stored as null or marked unavailable in episode
metadata; no zero-filled torque trajectory is fabricated. The record also
states the source, sign convention, units, update rate, and qualification
status of every populated effort channel.

For this XC330 study, these fields are supporting context only. The primary
Methods 1 and 2 continue to consume position, velocity, timing, validity,
controller context, and fixture properties. A later RS06 torque/current study
may define a separate effort-oriented analysis track, but that would be a new
declared evidence boundary rather than an unnoticed change to Real-Position
Data.

## Fixed Hardware and MuJoCo Controller Conditions

Each H record is the **complete hardware context**, not only three gain
registers: Operating Mode 5, Position P/I/D, feedforward values, profile
settings, current/PWM/velocity limits, command rate, supply, firmware, and any
other active register that changes motion. The campaign contains:

| Condition | Position P | Position I | Position D | Use in This Run |
| --- | ---: | ---: | ---: | --- |
| H1 | 600 | 0 | 150 | primary calibration, model selection, and held out |
| H2 | 800 | 0 | 150 | primary P-change self-check and held out |
| H3 | 600 | 0 | 220 | derivative-observability diagnostic |
| H4 | 300 | 0 | 60 | wider low-gain calibration diagnostic |
| H5 | 1200 | 0 | 320 | wider high-gain calibration diagnostic |

The candidate simulation context paired with hardware condition $$h$$ is

$$
C_h=\left\{K_{p,h}^{C},K_{v,h}^{C}\right\}.
$$

The XC330 control-table P and D values are dimensionless firmware settings;
copying 600 and 150 directly into SI-valued MuJoCo coefficients is not a valid
unit conversion. The [XC330-M288-T e-Manual](https://emanual.robotis.com/docs/en/dxl/x/xc330-m288/)
documents the internal P and D divisors, position and velocity units, current
unit, Current-Based Position Control Mode, and the 5 V performance data used
here. Define

$$
\rho_q=\frac{2\pi}{4096}\ \mathrm{rad/count},\qquad
\rho_v=0.229\frac{2\pi}{60}\ \mathrm{(rad/s)/count},\qquad
\rho_i=0.001\ \mathrm{A/count},
$$

and use the published 5 V static ratio
$$K_t^{pub}=0.517\ \mathrm{N\,m/A}$$. The fixed engineering map is

$$
K_{p,h}^{C}=K_t^{pub}\rho_i
\frac{P_h/128}{\rho_q},\qquad
K_{v,h}^{C}=K_t^{pub}\rho_i
\frac{D_h/16}{\rho_v}.
$$

The recorded 300-count Goal Current and Current Limit give the matching fixed
effort ceiling

$$
\tau_{lim}^{C}=300\rho_iK_t^{pub}=0.1551\ \mathrm{N\,m}.
$$

This is a declared **Mode-5-equivalent engineering approximation**, not a
claim that the proprietary embedded loop has been reproduced exactly. It
converts the known registers once; it does not fit controller gains from the
motion records. The model uses the recorded Position and Velocity Trajectories
as references and computes the internal simulated effort as

$$
\tau_C(t)=\operatorname{clip}\!\left(
K_{p,h}^{C}[q_{traj}(t)-q(t)]
+K_{v,h}^{C}[\dot q_{traj}(t)-\dot q(t)],
-\tau_{lim}^{C},\tau_{lim}^{C}
\right).
$$

MuJoCo's [`<motor>` actuator](https://mujoco.readthedocs.io/en/3.3.7/XMLreference.html#actuator-motor)
receives this computed effort. The controller remains a position-interface
model: torque is an internal simulated quantity, not a measured hardware input.

| Hardware Context | Fixed $$K_p^C$$ | Fixed $$K_v^C$$ | Fixed Effort Limit | Identification Status |
| --- | ---: | ---: | ---: | --- |
| H1: P/I/D = 600/0/150 | 1.579836 N·m/rad | 0.202115 N·m·s/rad | ±0.1551 N·m | known engineering map; never fitted |
| H2: P/I/D = 800/0/150 | 2.106448 N·m/rad | 0.202115 N·m·s/rad | ±0.1551 N·m | known engineering map; never fitted |

If this fixed representation produces an unacceptable hardware-output gap,
the representation or claim boundary fails. Method 1 or Method 2 must not
change $$K_p^C$$ or $$K_v^C$$ to make the result look better.

### Independent Joint Models for H1 and H2

The two hardware conditions define two independent effective joint models:

$$
\hat{\boldsymbol\theta}_{J,H1}^{MJ}
=\left[J_{a,H1}^{MJ},b_{H1}^{MJ},\tau_{c,H1}^{MJ}\right]^T,
\qquad
\hat{\boldsymbol\theta}_{J,H2}^{MJ}
=\left[J_{a,H2}^{MJ},b_{H2}^{MJ},\tau_{c,H2}^{MJ}\right]^T.
$$

They are not averaged, shared, or required to agree. Each vector is useful
only if its own H-specific model produces a sufficiently small calibration,
model-selection, and held-out output gap. H3–H5 remain controller-response
diagnostics and do not enter either primary fit.

## Collection Matrix and Episode Roles

The physical campaign preserves the semantic roles of the simulation design,
adds repeats, and adds H3–H5 controller diagnostics.

| Phase | Actual Accepted Dynamic Collection | Purpose |
| --- | --- | --- |
| primary calibration | M0/B0/B1/B2 × P01–P03 × H1/H2 × three repeats = 72 episodes | independently fit one H1 and one H2 three-parameter candidate for each method |
| controller diagnostics | M0/B0/B1/B2 × P01–P03 × H3/H4/H5 × three repeats = 108 episodes | test whether the wider gain changes are behaviorally observable; excluded from the primary fit |
| model selection | B0/B2 × P04–P05 × H1/H2 × three repeats = 24 episodes | test the frozen candidate on unseen profiles before held out |
| held out | G1 × P06–P07 × H1/H2 plus B1 × P06 × H1/H2, five repeats = 30 episodes | loaded and trajectory transfer evaluation |
| pilot and preparation | 14 pilot plus 12 recentering episodes | safety, setup, and audit only; excluded from all fits and scores |

The first valid repeat is not the final result. Repeat variation exposes
thermal, timing, assembly, and measurement effects absent from deterministic
simulation. A failed episode remains in the manifest with an exclusion reason;
it is not deleted to make the fit cleaner.

### Optional Real-Gravity Collection

Real-Gravity Data remain useful for checking Present Current, gravity
geometry, holding bias, and static friction, but they are not used to identify
controller gains or the three joint parameters. A future collection can use
the same position mode with standard and reversed G1 installations, seven safe
poses, both approach directions, and at least three repeats. At each pose,
record Present Position, Present Current, Present PWM, voltage, temperature,
faults, and timestamps.
This will check sign, gravity geometry, static friction, holding bias, and the
effective current-observation path without fitting `armature`, `damping`, or
`frictionloss`.

## Real-Position Analysis Adapter

The adapter performs these auditable transformations before either method is
called:

1. preserve the original command and state packet streams;
2. unwrap counters and positions where needed without erasing the raw values;
3. estimate the relationship between host and device clocks;
4. convert Goal/Present Position and Present Velocity to the bench coordinate
   and SI units;
5. retain the zero-order-held transmitted Goal Position as the external input
   and align the sampled Position and Velocity Trajectories as the inner
   controller references;
6. crop every scored episode to command rows with
   `active_profile_sample=true`, excluding setup, return, and post-hold phases;
7. construct `valid` from packet, timestamp, fault, limit, intervention, and
   configuration checks;
8. construct a conservative `saturated` or `limit_active` record from qualified
   controller limits and telemetry;
9. preserve optional effort-related fields with their availability and
   qualification metadata, without using them to create the primary analysis
   view; and
10. export complete episodes with immutable split, controller, fixture, profile,
   and repeat identifiers.

The adapter must pass a schema and range check before the analysis runner is
enabled. The supplied archive passes this schema and timing audit. The
reproducible runner and its machine-readable output are linked in the results
section below.

## Applying Method 1 to Real-Position Data

Method 1 now uses only quantities that the prototype provides: recorded
Position and Velocity Trajectories, measured position, measured velocity, two
fixed controller contexts, timestamps, active-profile records, and measured
fixture properties. It does **not** require measured generalized actuator
effort or acceleration.

The identical Section 2.3 procedure is applied:

1. select physical calibration episodes;
2. apply the frozen position/velocity filter;
3. reconstruct fixture inertia and bias from the measured matched MJCF;
4. reconstruct controller effort from both trajectory references using the
   fixed Mode-5 engineering conversion for H1 or H2;
5. form the same short-window integral regression;
6. fit one $$[J_a^{MJ},b^{MJ},\tau_c^{MJ}]$$ vector using H1 records only and
   another using H2 records only;
7. replay each H-specific Real-Position M1 Candidate only in its matching
   controller context; and
8. evaluate each H-specific model-selection and held-out output gap.

Present Velocity has finite resolution, and a velocity estimate derived from
Present Position has filtering and phase consequences. The selected velocity
source, filter, and uncertainty are therefore part of the method version. If
the design loses rank, becomes excessively ill-conditioned, presses against
bounds, or fails prospective replay, Method 1 is rejected even though the
solver returns numbers. The Section 2.3 simulation result demonstrates exactly
why this check is necessary.

## Applying Method 2 to Real-Position Data

Method 2 uses the same derived arrays and model class:

1. initialize the matched MJCF from the first qualified physical position and
   velocity;
2. replay the physical Position and Velocity Trajectories through the
   torque-limited effective MuJoCo controller while retaining Goal Position
   for external-interface diagnostics;
3. fix $$K_p^C/K_v^C$$ at 1.579836/0.202115 for H1 or
   2.106448/0.202115 for H2 and never vary them;
4. independently optimize only the matching H1 or H2 calibration episodes,
   varying `armature`, `damping`, and `frictionloss` with equal
   complete-episode weighting and declared starts;
5. freeze any permitted preprocessing revision using physical model-selection
   episodes;
6. freeze code, parameters, preprocessing, and configuration hashes; and
7. in a prospective release, score every untouched physical repeat; the
   present release scores the held-out-labeled repeats retrospectively.

Method 2 does not need measured torque or differentiated acceleration. It is
therefore the stronger initial method for this position-controlled smart-servo
prototype. It can still fail if the applied-command boundary is wrong, the
fixture model is inaccurate, the internal DYNAMIXEL profile is omitted,
backlash or saturation dominates, temperature changes substantially, or the
fixed Mode-5 engineering representation is inadequate.

Here, the internal profile is not omitted: its recorded Position and Velocity
Trajectories are the joint-model references. A future end-to-end model that
begins from Goal Position must add or learn the firmware profile operator
instead of silently changing the three joint parameters.

## Common Physical Evaluation

For observed hardware position $$q^{hardware}_e(t)$$ and candidate output
$$q^m_e(t)$$,

$$
E^{physical}_{m,e}=\sqrt{
\frac{1}{N_e}
\sum_{k=1}^{N_e}
\left[q^m_e(t_k)-q^{hardware}_e(t_k)\right]^2}.
$$

For each split, the primary summary is the equal-episode mean of this absolute
model-to-hardware gap. There is no nominal baseline in the Real-Position
study: an arbitrary starting vector would add no physical reference. Method
2's declared start vectors are solver initializations only and do not appear
as candidate models or evidence baselines.

There is also no physical “Source Model parameter” column because equivalent
MuJoCo parameters are the unknown. Acceptance depends on prospective absolute
behavioral gap, repeatability context, residual structure, and numerical
stability—not closeness to an unknowable ground-truth vector or reduction from
an arbitrary initial guess.

### Acceptance Gates

| Gate | Acceptable Evidence | Failure Interpretation |
| --- | --- | --- |
| data qualification | clocks, units, sign, zero, device state, fixtures, limits, and exclusions pass before fitting | repair collection or narrow the dataset; do not fit |
| numerical identification | rank/conditioning acceptable for Method 1; bounded multi-start behavior acceptable for Method 2 | parameters are not sufficiently constrained |
| H-specific prediction | each independent H1 or H2 candidate has a sufficiently small absolute gap under its matching fixed controller | otherwise reject or narrow that candidate or the controller representation |
| model-selection transfer | the frozen candidate maintains acceptable absolute gap on unseen profiles without using held-out records | otherwise reject or revise before unblinding held out |
| held-out transfer | the frozen candidate maintains acceptable absolute gap across the declared fixture/trajectory family and most repeats | otherwise the model is not accepted for the chapter claim |
| residual screening | errors are not dominated by time drift, reversal, saturation, temperature, or one fixture | otherwise revise the boundary or model rather than overclaiming three parameters |
| reproducibility | rerun from raw records reproduces the derived archive, candidate, and tables | otherwise the evidence release is incomplete |

Method 1 and Method 2 are judged independently. It is valid for Method 1 to be
rejected and Method 2 accepted, as occurred in the simulation-first run. It is
also valid for both to fail, in which case the simple effective PD-plus-joint
model is not supported by the physical evidence.

## Physical Results Register

{% hint style="warning" %}
**Preliminary Retrospective Result:** The runner reproduces every value and
figure below from source archive SHA-256
`732d8618f666d8764ced720c09d22065980a55af6c962670a05f414a31b42f6c`.
The result tests the fixed Mode-5 engineering map without fitting controller
gains. It is not yet prospective because the trajectory adapter and this
controller representation were finalized after collection.
{% endhint %}

### Position-Input Boundary

*Historical source asset: External Goal Position, internal Position and Velocity Trajectories, and measured XC330 response (`../assets/chapter-02/real-position-v2/hardware-input-boundaries.png`); not included in this extract.*

**Figure 2.16 — External and inner controller boundaries.** The DYNAMIXEL
Position and Velocity Trajectories expose firmware profile generation between
Goal Position and the embedded controller. The joint-parameter candidates use
the two inner references; Goal Position remains the application-facing input.

### Identified Joint Candidates

| MuJoCo Joint Parameter | Method 1 H1 | Method 2 H1 | Method 1 H2 | Method 2 H2 |
| --- | ---: | ---: | ---: | ---: |
| `armature` | 0.0107069 kg·m² | 0.00632963 kg·m² | 0.00935003 kg·m² | 0.00492244 kg·m² |
| `damping` | 0.0364783 N·m·s/rad | 0.0425664 N·m·s/rad | 0.0415251 N·m·s/rad | 0.0443182 N·m·s/rad |
| `frictionloss` | 0.0102269 N·m | 0.00736304 N·m | 0.00834278 N·m | 0.00599718 N·m |

*Historical source asset: Method 1 and Method 2 joint-parameter candidates for H1 and H2 (`../assets/chapter-02/real-position-v2/parameter-comparison.png`); not included in this extract.*

**Figure 2.17 — Independent context-bounded parameter candidates.** No
reported parameter is on a bound. Method 1 has full design rank with scaled
condition numbers of 22.31 for H1 and 22.21 for H2. All three Method 2 starts
converge to the same H-specific solution to the shown precision, so the Method
2 result is not start-sensitive in the declared bounds.

### Output-Gap Results

| Context | Split | Episodes | Method 1 Absolute RMSE | Method 2 Absolute RMSE |
| --- | --- | ---: | ---: | ---: |
| H1 | Calibration | 36 | 0.011945 rad | 0.004330 rad |
| H1 | Model Selection | 12 | 0.012093 rad | 0.004350 rad |
| H1 | Held Out | 15 | 0.023343 rad | 0.016523 rad |
| H2 | Calibration | 36 | 0.011222 rad | 0.003183 rad |
| H2 | Model Selection | 12 | 0.009041 rad | 0.002829 rad |
| H2 | Held Out | 15 | 0.021058 rad | 0.013441 rad |

*Historical source asset: Absolute identified-model output gaps across all physical splits (`../assets/chapter-02/real-position-v2/split-output-gap.png`); not included in this extract.*

**Figure 2.18 — Independent hardware output gaps.** Method 2 is stronger than
Method 1 on every split, but both are evaluated by absolute gap—not against an
arbitrary nominal hardware model. Method 2 reaches 0.00435 rad or less on
calibration and unseen balanced-fixture model-selection data. Its combined
held-out gap is higher because the held-out set includes G1.

*Historical source asset: Representative G1 held-out replay and output-to-hardware residuals (`../assets/chapter-02/real-position-v2/heldout-g1-replay.png`); not included in this extract.*

**Figure 2.19 — Representative G1 held-out replay.** The residual plot
compares model output with hardware output under the same recorded inner
controller references. It is not hardware input-to-output tracking error.

### Matched H1/H2 Output and Tracking Comparisons

The following figures use the same held-out G1/P06/R01 profile for H1 and H2.
This keeps fixture, trajectory, repeat identity, input boundary, and plotting
rules matched while changing only the controller context and identified joint
candidate.

*Historical source asset: H1 and H2 Method 1/2 simulated outputs compared with hardware output and their output gaps (`../assets/chapter-02/real-position-v2/heldout-output-comparison-h1-h2-m1-m2.png`); not included in this extract.*

**Figure 2.20 — Simulated-output to hardware-output comparison.** The left
column shows the recorded controller Position Trajectory, hardware output, and
the Method 1 and Method 2 simulated outputs. The right column reports
$$q_{simulation}-q_{hardware}$$ with per-episode RMSE, MAE, and maximum absolute
gap. These are model-discrepancy plots, not tracking-error plots.

*Historical source asset: H1 and H2 hardware and Method 1/2 tracking errors relative to the recorded controller Position Trajectory (`../assets/chapter-02/real-position-v2/heldout-tracking-comparison-h1-h2-m1-m2.png`); not included in this extract.*

**Figure 2.21 — Hardware and simulated tracking comparison.** Every trace is
computed against the same recorded inner Position Trajectory:
$$e_{track}=q_{output}-q_{trajectory}$$. The hardware trace measures physical
inner-reference tracking; the Method 1 and Method 2 traces show what their
matched simulations predict. Similar tracking RMSE does not by itself imply a
small model-to-hardware gap because two systems can have similarly sized but
differently structured errors.

The repeat-to-combination-mean floor is approximately 0.00100 rad on
calibration, 0.00133 rad on model selection, and 0.00137 rad on held out.
Method 2 is 3.20–4.35 times the repeatability floor on calibration and
2.12–3.26 times the floor on model selection. On held out it is 9.78 times the
floor for H2 and 12.02 times for H1.

Fixture-specific screening localizes much of that transfer error. The Method 2
held-out B1 gaps are 0.00340 rad for H1 and 0.00277 rad for H2, while G1 gaps
are 0.02309 and 0.01878 rad. This supports the fixed controller representation
far more strongly than the superseded raw-copy test, but it does **not** yet
support the G1 gravity/orientation model or a final chapter-wide Sim2Real
claim. The G1 signed first moment, installed zero/orientation, static holding
bias, and gravity calibration are the next items to verify.

### Reproduce and Inspect

The supplied scientific tables and result below link to this course repository. Historical downloads that are not included are identified explicitly. The result package does
not redistribute the raw hardware archive; it records that archive's filename,
size, and SHA-256 so an authorized local copy can be verified before rerunning.

**Historical source artifact:** `real-position-results-v2.zip`. This original download is not included in this extract.

Complete preliminary result package: summary, audit, fixed controller
conditions, parameter and metric tables, figures, requirements, and
reproducible runner.

[real-position-result-v2.json](../data/phyintel/xc330/published/result.json)

Machine-readable result, methodological decisions, diagnostics, source hash,
and acceptance status.

[real-position-joint-parameters-v2.csv](../data/phyintel/xc330/published/joint-parameter-estimates.csv)

Independent H1/H2 Method 1 and Method 2 parameter values.

[real-position-aggregate-metrics-v2.csv](../data/phyintel/xc330/published/aggregate-metrics.csv)

Equal-episode absolute output-gap metrics and gap-to-repeatability ratios for
all three evidence splits.

[real-position-fixture-split-metrics-v2.csv](../data/phyintel/xc330/published/fixture-split-metrics.csv)

Fixture-specific absolute output-gap metrics used to distinguish balanced B1
transfer from eccentric G1 transfer.

[real-position-fixture-mass-properties-v2.csv](../data/phyintel/xc330/published/fixture-mass-properties.csv)

Measured masses, installed positions, inertia estimates, and signed G1 first
moment used by the replay models.

[real-position-fixed-controller-conditions-v2.csv](../data/phyintel/xc330/published/fixed-controller-conditions.csv)

H1 and H2 hardware settings, unit factors, fixed Mode-5-equivalent MuJoCo
controller coefficients, and effort limit.

[run-chapter02-real-position-identification-v2.py](../code/upstream/run_chapter02_real_position_identification_v2.py)

Reproducible archive audit, Method 1/2 identification, evaluation, and plotting
runner.

**Historical source artifact:** `plot-chapter02-real-position-comparisons-v2.py`. This original download is not included in this extract.

Reproduce the matched H1/H2 output-gap and tracking-error figures from the
identified parameters and an authorized local copy of the hardware archive.

The following commands describe the historical authoring layout, including its original script names. For the portable numerical commands in this course package, use the [current optional examples](../RUN.md):

```bash
.venv/bin/python scripts/run_chapter02_real_position_identification_v2.py \
  "/path/to/episodes 1.zip"

.venv/bin/python scripts/plot_chapter02_real_position_comparisons_v2.py \
  "/path/to/episodes 1.zip"
```

The immediate decision is therefore: **retain the Method 2 H1 and H2
candidates as promising context-bounded models for balanced fixtures, reject
Method 1 as the preferred predictive method for this dataset, and withhold
acceptance for G1 and the chapter-wide Sim2Real claim.** No controller gain is
identified. A frozen prospective run and a corrected or qualified G1 gravity
boundary are still required.

## Safety and Stop Conditions

Before every loaded run, verify the fixture identity, payload locations,
fasteners, travel clearance, current/PWM/position limits, communication health,
and emergency stop. Stop and retain the partial record if any of the following
occurs:

- unexpected impact, loosening, or fixture motion;
- joint-limit approach outside the accepted margin;
- repeated packet failure or clock discontinuity;
- voltage or temperature outside the campaign boundary;
- hardware error, limit activity, or sustained effort behavior not covered by
  the pilot; or
- operator intervention.

An unsafe or interrupted run is not converted into a valid episode after the
fact.

## Five Development Layers Review

| Development Layer | Model2Prototype Requirement | Evidence to Preserve |
| --- | --- | --- |
| 1. Physical Embodiment | fabricated M0/B0/B1/B2/G1 fixtures with measured 6 g link, 4 g pins, 42 g payloads, and corrected B0/G1 geometry | measured mass-property table and signed G1 bench coordinate are now recorded |
| 2. Sensing and Actuation | H1–H5 Current-Based Position Control records include Goal, Position/Velocity Trajectories, Present Position/Velocity/Current/PWM, timing, status, and operating condition | 260 complete episode directories pass the archive audit |
| 3. Computation and Representation | immutable raw streams map to external Goal, inner trajectory references, measured response, fixed controller conditions, and active-profile episodes | adapter, schema audit, Mode-5 engineering map, results, and code are versioned |
| 4. Robo-Physical Learning and Task Validation | Methods 1 and 2 independently fit H1 and H2 calibration and score the matching model-selection and held-out records | Method 2 is stable and substantially more predictive than Method 1 on balanced fixtures; G1 gravity transfer remains unsupported |
| 5. Lifecycle Evidence | bind design, data, models, methods, decisions, and limitations to one preliminary release | source SHA, results, per-episode metrics, plots, and remaining prospective work are preserved |

Section 2.5 must report this as **promising preliminary retrospective evidence
for balanced-fixture Method 2 models, with G1 transfer and the final Sim2Real
claim still unsupported**.
