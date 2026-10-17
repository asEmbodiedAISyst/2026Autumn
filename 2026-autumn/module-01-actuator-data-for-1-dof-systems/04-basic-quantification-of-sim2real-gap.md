---
description: Basic quantification of Sim2Real gap · ROB7103/8103
---

# 04 Basic Quantification of Sim2Real Gap

## Central question

How do we estimate a MuJoCo model, quantify its discrepancy from physical actuator responses, and judge its usefulness for a specified task?

[Lecture](#1-introduction) · [Instructor and TA demonstration](#instructor-and-ta-demonstration) · [Student activity](#student-activity) · [Practical preparation and resources](#practical-preparation-and-resources)

## 1 Introduction

A simulated trajectory can look close to a physical trajectory while missing a repeatable offset, a reversal or a response under a different load. Conversely, an actuator can follow its requested motion poorly while a model predicts that imperfect response closely. To interpret agreement, we need to name the two quantities being compared, make their conditions compatible and report a numerical discrepancy together with its context.

The **Sim2Real gap** in this class is the difference between simulated and measured **joint position** under declared input, controller, fixture and processing conditions. It is not one permanent number belonging to an actuator or simulator. Changing the command boundary, payload, operating range or scoring rule changes the question.

![Frozen XC330 prediction and physical response for the eccentric held-out case](../media/class04/xc330-H1-G1-P06.png)

*Figure 1. One recorded XC330 H1/G1/P06/R01 episode and two frozen MuJoCo candidates. The lower panel retains the signed model-to-measurement residual. These are predictions from the 98 g campaign; no parameter is adjusted to this episode. Method 2's position RMSE is approximately 0.02191 rad. Read the signal labels before deciding what the overlay establishes.*

Our example is one **XC330-M288-T in current-based position operation**, driving a rigid link and payload assembly about one joint. The numerical replay receives recorded internal position and velocity references. It predicts position using its own evolving simulated state. This is a conditional response model: it does not predict how firmware generates those references from an external goal.

Only a small mechanical vocabulary is needed. Joint position is an angle; its time derivatives are velocity and acceleration. Fixture inertia describes the moving assembly's resistance to angular acceleration. Gravity torque depends on the assembly's mass distribution and pose. The supplied model already declares its joint and fixture properties. Our work is to estimate three uncertain effective parameters and test its response; we do not rebuild CAD or survey actuator products.

The lecture follows **Introduction → Claim2Design → Design2Data → Data2Model → Model2Prototype → Sim2Real**. First define the comparison, then design informative observations, estimate a model, introduce physical evidence and evaluate the claim. Model2Prototype means moving from constructed observations to records from a matched physical prototype. It does not mean that students must fabricate another mechanism during this class.

The recurring questions **Claim, Experience, System, Grounding, Learning and Decision** can be asked throughout that process: what is claimed, what tests it, which system is represented, what evidence grounds it, what was learned and what decision follows. They are views across the work rather than alternative names for its stages.

By the end, you should be able to specify a fair comparison, explain the two identification methods, calculate or interpret position RMSE, read a residual and make a model-use decision limited to the evidence.

**Predict:** If hardware and simulation both lag their reference by the same amount, is their model-to-hardware gap necessarily large?

## 2 Claim2Design

### Specify the comparison before inspecting the score

“The simulator matches the actuator” leaves the input, output and operating conditions unspecified. Here the claim concerns measured joint-position prediction for a particular controller context, fixture and motion profile. A reference-driven replay, an external-goal-driven predictor and a torque-driven model are different experiments even when each produces an angle plot.

| Quantity | Symbol | Meaning here |
|---|---|---|
| External goal | $$q_d$$ | Application-facing requested position retained in the episode |
| Internal position reference | $$q_r$$ | Device-generated trajectory used as replay input |
| Internal velocity reference | $$v_r$$ | Recorded velocity trajectory used as replay input |
| Physical position | $$y_q$$ | Returned position converted to the declared joint coordinate |
| Physical velocity | $$y_v$$ | Qualified reported/processed physical velocity estimate |
| Simulated position | $$\hat q$$ | Output of the evolving MuJoCo model |
| Simulated velocity | $$\dot{\hat q}$$ | Velocity of that simulated state |

Positions use radians and velocities use rad/s. A hat denotes an estimate or model quantity; it does not turn a reported sensor value into an independent calibration. The script columns use explicit names such as `physical_position_rad` and `simulated_M2_position_rad`; the accompanying data guide maps them to these symbols.

The **experiment runner** schedules requests and associates them with a record. The **hardware controller** shapes references and produces a limited drive response on the device. The **capture path** preserves commands, observations, timestamps and configuration. In replay, a declared controller approximation computes effort from recorded references and simulated feedback; **MuJoCo** then integrates the mechanics. A torque channel in an XML file supplies a route for effort. It does not, by itself, recreate the embedded position controller.

![Physical record and conditional simulation boundary](../media/class04/comparison-boundary.png)

*Figure 2. The simulation receives recorded internal references and an initial state, then evolves independently. The physical position is the comparison target, not a state repeatedly injected into replay. The external goal remains visible but firmware reference generation lies outside this prediction boundary.*

### Keep the model versions distinct

The numerical results here belong to a **98 g added moving fixture**: a 6 g link, two 4 g pins and two 42 g payloads. Each complete pin/payload assembly is 46 g. Its fixture labels identify placements within this campaign.

| Source or example | What it represents | What carries into this class |
|---|---|---|
| Illustrative position-actuator example | Gains 3 and 0.03; a ±0.93 N m stall-based teaching bound | The distinction between a reference and simulated effort; those numerical settings are not used here |
| 110 g structural inspection family | A 22 g link and two 44 g assemblies in an exported body tree | Mechanical concepts; its mass and model values are not the source of these scores |
| 98 g identification campaign used here | Measured/source-recorded fixture masses, a reduced joint model and a fixed Mode-5 controller map | The configuration, frozen candidates, physical records and results evaluated below |

Shared B0/B1/B2/G1 labels do not establish identical hardware revisions. The available records do not settle whether the 110 g/98 g difference arose from different built parts or revised descriptions. We therefore preserve their identities. Changing a mass in an XML file would create another model; it would not transfer the following validation results to that model.

The primary numerical engine uses one reduced moving body, aggregate fixture inertia and a signed first moment. It does not use the detailed CAD body tree as its executable replay. A picture of that CAD can explain the mechanism, but cannot be labelled as the model producing these scores.

| 98 g fixture | Nominal payload-centre positions | Added fixture inertia about the joint, kg m² |
|---|---|---:|
| M0 | Motor only; no added link/payload fixture | 0 |
| B0 | −60, +60 mm | 0.000371055 |
| B1 | −80, +80 mm | 0.000628655 |
| B2 | −100, +100 mm | 0.000959855 |
| G1 | +60, +100 mm in the source placement description | 0.000665455 |

M0's zero is **added fixture inertia**, not zero actuator inertia. The fitted armature field remains separate. Loaded cases have 0.098 kg of added moving mass. The component central inertias are geometry-derived estimates scaled to the source-recorded masses; they have not been independently measured. For G1, the replay's bench-qualified signed first moment is −0.00736 kg m. Its sign depends on joint zero, positive direction and installation; positive CAD distances alone do not determine it. The maximum declared gravity-torque magnitude is about 0.07220 N m.

The recorded conversion places joint zero at 2048 position counts and converts one count to $$2\pi/4096$$ rad. In the reduced model, increasing angle is a positive rotation about the +Y joint axis and world gravity is [0, 0, −9.81] m/s². The signed G1 first moment is chosen to reproduce the recorded negative-angle resting direction. These conventions belong to this bench/model; they do not inherit another model's world placement. Replay initializes from the first cropped active-profile measurement, not a torque-off or zero-acquisition value from earlier preparation.

### Declare two different errors

Use reference-minus-measurement for the internal tracking error, consistent with the controller's error term:

$$
e_{\mathrm{track}}(t)=q_r(t)-y_q(t).
$$

Use simulation-minus-measurement for the model discrepancy:

$$
\delta q(t)=\hat q(t)-y_q(t).
$$

Positive discrepancy means the simulated angle is above the recorded physical angle in the declared coordinate. External-goal tracking would compare $$q_d$$ with $$y_q$$ and must be labelled separately.

For example, if both hardware and simulation are 0.05 rad below the same internal reference, internal tracking error is 0.05 rad while their instantaneous discrepancy is zero. The model predicts the lag even though the actuator has not followed its reference closely. Validation of a response model and evaluation of actuator tracking answer different questions.

The primary position metric for episode $$e$$ is

$$
R_e=\sqrt{\frac{1}{N_e}\sum_{i=1}^{N_e}\delta q_{e,i}^{\,2}}.
$$

Here $$N_e$$ counts the retained, time-paired samples under the declared processing rules. RMSE measures a typical magnitude in radians, not a signed direction or a causal explanation. We retain the signed residual trace alongside it.

Our **comparison record** binds the fixture, controller, input/output meaning, units, zero, initialization, time alignment, scoring interval, retained samples, frozen parameter candidate, metric and intended use. A numerical acceptance tolerance must come from that intended use. The archive does not provide a universal threshold for “good enough”.

**Checkpoint:** Which claim would become stronger if the model predicted directly from $$q_d$$, and which missing part of the system would it then need to represent?

## 3 Design2Data

### Give the unknown parameters something distinguishable to explain

Acceleration changes the inertial contribution to effort. Speed changes viscous resistance. Direction changes alter the sign of moving dry friction. A collection containing only one steady speed can fit a combination of resistance terms without distinguishing them well; it contributes little information about inertia during that steady segment.

Several motion types therefore serve different purposes. The campaign uses a slow triangle, multisine and smooth levels for calibration. Chirp and wide-sine profiles provide model-selection records. A composite motion and a sine-with-hold profile form the reserved evaluation motions. These labels identify records; informative excitation still has to be checked against the actual reference and measured response.

Changing payload distribution also changes inertia and, for an eccentric installation, gravity torque. It tests whether a candidate transfers across declared fixture conditions. It does not isolate a cause if controller settings, motion profiles or processing change simultaneously. Near rest, dry friction is particularly difficult to approximate; at saturation, larger reference error may not produce larger effort. Those regions require their stated treatment rather than silent removal.

An **episode** is one complete declared experiment. A **repeat** is another execution of the same fixture/controller/profile combination. Many samples within one episode are correlated observations of that experiment; they are not independent repeated trials.

### Separate estimation, selection and evaluation

| Role | XC330 primary records | Purpose |
|---|---|---|
| Calibration | M0/B0/B1/B2 × P01–P03 × H1/H2 × 3 repeats = 72 episodes | Estimate each controller context's parameters |
| Model selection | B0/B2 × P04–P05 × H1/H2 × 3 repeats = 24 | Choose among declared candidates or permitted modelling choices |
| Held-out-labelled evaluation | B1/P06 and G1/P06–P07 × H1/H2 × 5 repeats = 30 | Inspect reserved motion/fixture transfer |

The primary set has 126 episodes. The original archive contains additional controller diagnostics, pilots and preparation records; they are not additional primary fitting data. Split complete episodes and relevant conditions, not neighbouring samples selected at random. A model tested on samples adjacent to its fitting samples has faced a weaker prediction challenge than a model tested on a different complete experiment.

### Establish the clocks and processing rules

| Clock or representation | Meaning in this example |
|---|---|
| Original telemetry | Approximately 5 ms average spacing, about 200 samples/s |
| Analysis arrays | 10 ms grid, about 100 samples/s, after active-profile cropping and alignment |
| MuJoCo integration | 2 ms steps, five steps per 10 ms reference interval |
| Embedded firmware loop | Not established by any of those rates |

The adapter converts position and velocity into the bench coordinate, retains the external command with zero-order holding and interpolates sampled telemetry/internal references onto the analysis grid. Scoring excludes preparation, return and post-hold phases. During simulation, sampled references are held between their analysis-grid updates. Interpolating observations and holding commands are different operations, each part of the declared method.

The resulting arrays are reproducible analysis inputs, not raw event streams. A Goal Position register readback must also be distinguished from an independently timestamped host transmission. Time labels should state which event they timestamp.

A timing shift can create a structured residual. Increasing inertia to imitate that delay can make one plot look closer while hiding the incorrect time boundary. Align units, zero and timestamps through a declared rule before estimating parameters. Keep failed or interrupted records with status and exclusion reasons. Fit/scoring eligibility is part of the evidence, not an invitation to keep only attractive trajectories.

**Predict:** Which motion change would help separate inertia from viscous resistance? What must remain fixed for that comparison to be interpretable?

## 4 Data2Model

### State the model and its fixed controller approximation

For this fixed-axis, rigid-fixture, free-motion example, organize the mechanical balance as

$$
(J_f+J_a)\ddot q+b\dot q+\tau_{\mathrm{dry}}+\tau_g(q)=\tau_C.
$$

The fixture supplies $$J_f$$ and the gravity term $$\tau_g$$. The three estimated fields are additional effective joint inertia $$J_a$$, viscous damping $$b$$ and dry-friction magnitude $$\tau_c$$. They map to MuJoCo `armature`, `damping` and `frictionloss`, with units kg m², N m s/rad and N m respectively. Armature adds to the fixture contribution; it does not replace it.

This restricted equation has no additional contact torque. Constant fixture inertia is appropriate to the declared single-axis rigid assembly. Resistance and gravity are written separately; losses should not also be counted through an extra efficiency correction representing the same effect. MuJoCo handles friction loss through its constraint formulation. The sign-of-velocity expression used in the integral approximation below is not a complete description of sticking. See the [MuJoCo friction-loss discussion](https://mujoco.readthedocs.io/en/3.3.7/computation/index.html#friction-loss).

The replay computes limited effort using

$$
\tau_C=\operatorname{clip}\!\left(
K_p^C(q_r-\hat q)+K_v^C(v_r-\dot{\hat q}),
-\tau_{\mathrm{lim}},\tau_{\mathrm{lim}}\right).
$$

Clipping limits the result to the stated interval. $$K_v^C$$ is the velocity-error coefficient called $$K_d$$ in a common proportional/derivative notation. The superscript identifies a coefficient in the declared simulation controller, not a raw firmware register.

| Context | Recorded firmware P/I/D | Fixed $$K_p^C$$, N m/rad | Fixed $$K_v^C$$, N m s/rad | Effort limit |
|---|---|---:|---:|---:|
| H1 | 600/0/150 | 1.579836 | 0.202115 | ±0.1551 N m |
| H2 | 800/0/150 | 2.106448 | 0.202115 | ±0.1551 N m |

Firmware registers are dimensionless settings. The source converts their documented scales using a disclosed engineering map and a fixed 0.517 N m/A static torque/current ratio. A 300-count current-related limit maps to 0.300 A and therefore 0.1551 N m in this approximation. This is not a calibrated measurement of shaft torque or proof that the proprietary embedded loop is reproduced exactly.

In particular, the supplied `Present Current` interpretation is device-input current; it cannot simply be substituted for torque-producing winding current. It is not used as measured shaft torque in the primary fit. The [ROBOTIS model documentation](https://emanual.robotis.com/docs/en/dxl/x/xc330-m288/) supplies register and mode definitions; the conversion into this effective SI controller remains a modelling assumption.

H1 and H2 have separate fitted joint vectors. Controller gains are fixed within each context and never optimized here. If the mapping is inadequate, the resulting effective parameters can absorb some of its error. Their predictive performance is still testable, but their interpretation as isolated motor constants is not established.

### Method 1 integrates the equation

Computing acceleration by differentiating encoder position twice can amplify measurement noise. Instead, integrate the mechanical equation over a qualified moving window. Approximate moving dry friction by $$\tau_c\operatorname{sgn}(\dot q)$$ and collect the known terms:

$$
J_a\Delta\dot q+b\Delta q+
\tau_c\int_{t_0}^{t_1}\operatorname{sgn}(\dot q)\,dt
\approx
\int_{t_0}^{t_1}(\tau_C-\tau_g(q))\,dt-J_f\Delta\dot q.
$$

Each window supplies one row of $$A\theta\approx z$$, where $$\theta=[J_a,b,\tau_c]^{\mathsf T}$$. The columns are velocity change, position change and signed moving time. The right-hand side is integrated reconstructed controller effort minus the declared gravity and fixture-inertia contributions.

For this method, reconstructed effort uses qualified measured position and velocity in the fixed controller expression. Those measurements are being used to build the regression. In output-error replay, feedback instead uses the simulated state. Confusing those two operations would turn a free-running prediction into a measurement-driven calculation.

**Constructed worked row.** Suppose a 0.2 s window stays in positive motion, with velocity change 0.5 rad/s and position change 0.1 rad. The row is $$[0.5,0.1,0.2]$$. Illustrative parameters $$[0.001,0.04,0.005]$$ give

$$
0.5(0.001)+0.1(0.04)+0.2(0.005)=0.0055\ \mathrm{N\,m\,s}.
$$

These numbers demonstrate the calculation; they are not physical measurements or the campaign's parameter vector. One row cannot determine three unknowns. Several independent motion windows are needed, and bounds constrain the estimates. The actual XC330 implementation uses qualified 0.5 s windows, filtering and moving-fraction rules. Numerical rank concerns distinguishable columns; conditioning concerns sensitivity to small errors. Neither proves that reconstructed effort or the friction approximation is physically exact.

### Method 2 fits the simulated output

Output-error optimization proposes a parameter vector, simulates calibration episodes and compares predicted position with recorded position. It updates the vector within declared bounds and repeats the calculation. It does not require measured shaft torque or numerically differentiated acceleration.

For retained calibration samples, an equal-episode squared-error objective can be written

$$
L(\theta)=\sum_{e\in\mathcal C}\frac{1}{n_e}
\sum_{i\in\mathcal I_e}
\left(\hat q_{e,i}(\theta)-y_{q,e,i}\right)^2.
$$

Here $$\mathcal C$$ is the calibration set, $$\mathcal I_e$$ is the retained optimization sample set and $$n_e=|\mathcal I_e|$$. The packaged solver uses every fourth point of the 100 Hz arrays and normalizes each episode's residual block by the square root of its sample count. Three numerical starts test convergence within the stated bounds; they are not physical baseline models.

Replay starts once from the first measured position and velocity. It then uses five 2 ms physics steps per reference interval, computing feedback from its own state. Later measurements supply the comparison target rather than replacing simulated position or velocity.

The full-episode validation score is calculated separately from the optimizer's subsampled residual. A sum of episode mean squared errors, its square root and a mean of episode RMSE values are related summaries, but they are not numerically interchangeable. Name the one being reported.

Method 2 includes the declared saturation and MuJoCo friction treatment during repeated simulation. It costs more than solving one regression and remains dependent on the model class and fixed controller assumptions. Both methods are parameter estimation, not reinforcement learning.

### Freeze a candidate before evaluating it

The released H1 vectors illustrate how methods can disagree:

| Field | Method 1 | Method 2 |
|---|---:|---:|
| Armature, kg m² | 0.0107069 | 0.00632963 |
| Damping, N m s/rad | 0.0364783 | 0.0425664 |
| Friction loss, N m | 0.0102269 | 0.00736304 |

The values belong to this controller/model/data context. A small output discrepancy does not prove unique rotor inertia, calibrated torque, or accurate behaviour under contact. Compare predictions and parameter plausibility while retaining those limits. Replaying these supplied vectors reproduces a frozen candidate; it is not a fresh fit.

**Checkpoint:** Why can two methods return different parameters even when both execute correctly? Which comparison would help judge their usefulness?

## 5 Model2Prototype

### Replace constructed observations with physical records

In a constructed experiment, the generating parameters can be known and later revealed. That lets us distinguish calculation errors from imperfect parameter recovery under a declared observation model. On physical hardware, equivalent MuJoCo parameters are unknown. We evaluate measured-response prediction rather than distance to an unavailable true vector.

The 98 g campaign's evidence chain is a scripted collector, command/telemetry packet records with configuration, an alignment/conversion adapter, complete analysis episodes and a frozen replay. The configuration includes mode, gains, limits, fixture, firmware, coordinate conventions and operating context. The model's geometry-derived inertias and effort mapping remain estimates or assumptions even when their inputs are carefully recorded.

Structured motor records and visual context have different roles. In other supplied historical material, **asBrain** names the command/telemetry capture path and the original **asMagic** supplies phone-based visual context. That material belongs to a separate source family. The 98 g archive's collector records do not establish that those applications acquired this campaign. A video can help explain an installation or event; it does not supply the time-paired joint samples used to calculate this gap. The demonstration therefore follows the verified motor-record path and labels any additional visual illustration by its actual source.

### Preserve the physical comparison contract

The supplied arrays retain the declared fixture, profile, controller, repeat and split identity. The audit checks source hashes, episode identities, monotonic times and finite observations. Such checks support reproducibility and data integrity; they do not independently calibrate a sensor or prove every physical assumption.

The archived evaluation is **retrospective**: the trajectory adapter and controller representation were finalized after the archive existed. Held-out labels preserve a useful reserved-role comparison, but they do not make this an independent prospective confirmation. A prospective campaign would freeze the model class, processing and candidate selection before collecting or revealing new evaluation records.

If a residual motivates a new timing rule, gravity sign or model term, preserve the original result and record the revision. The revised candidate needs fresh evaluation. Moving a validation trace until it overlays neatly would change the comparison after seeing the answer.

## 6 Sim2Real

### Calculate the discrepancy and keep its meaning

For three constructed residual samples of −0.01, 0 and +0.01 rad, the mean signed error is zero. The positive and negative errors cancel. Their RMSE is

$$
\sqrt{\frac{(-0.01)^2+0^2+(0.01)^2}{3}}
\approx0.008165\ \mathrm{rad}.
$$

Zero mean signed error therefore does not establish an exact prediction. RMSE summarizes magnitude; the signed trace reveals where and in which direction discrepancies occur. A large peak can also matter to an intended task even when the average magnitude is modest.

Now inspect one selected real episode under H1. With the frozen candidates and the same analysis rules:

| P06 first held-out repeat | Method 1 episode RMSE | Method 2 episode RMSE |
|---|---:|---:|
| Balanced B1 | 0.00797565 rad | 0.00420779 rad |
| Eccentric G1 | 0.0223445 rad | 0.0219097 rad |

For the selected G1 episode, Method 2 is about 1.26 degrees in position RMSE. Its mean signed residual is −0.01593 rad and its largest absolute residual is about 0.04129 rad, near 3.83 s. Between 2 and 3 s all its retained residual samples are negative, so simulation underpredicts the measured joint angle throughout that interval. This is a specific observation, not proof of a gravity, timing or friction cause.

The same physical episode has internal-reference tracking RMSE about 0.04985 rad and external-goal tracking RMSE about 0.07643 rad. Those are different comparisons from the 0.02191 rad model gap. Both model candidates face the same episode, initialization and scoring rules. There is no arbitrary nominal physical baseline in this study.

![Matched P06 physical/simulated comparisons](../media/class04/xc330-matched-P06.png)

*Figure 3. B1 and G1 first repeats use the same named P06 profile and H1 context. The differing physical initial states and fixture properties are preserved. The comparison helps investigate condition dependence; it does not uniquely establish a failure mechanism.*

### Read a residual before assigning a cause

An approximately constant offset suggests checking zero or measurement bias. A discrepancy that changes around transitions suggests checking reference meaning, timing, saturation or model dynamics. Direction dependence motivates friction, backlash or controller checks. An eccentric fixture motivates inspecting gravity direction, installed zero and signed centre of mass. Several mechanisms can produce similar patterns.

| Observation | Possible explanation | Discriminating check |
|---|---|---|
| Offset across a motion | Coordinate zero or measurement bias | Check a physical reference pose and conversion independently of the scored trace |
| Error concentrated at transitions | Timing or reference/controller mismatch | Inspect timestamp events and recorded internal references under the frozen alignment rule |
| Different errors in opposite directions | Friction, lost motion or controller asymmetry | Compare repeated direction reversals at controlled speed and load |
| Weak eccentric transfer | Gravity/installation or missing load-dependent effects | Check signed geometry and holding behaviour at declared poses; preserve controller settings |

A proposed cause becomes stronger when a check separates it from a credible alternative. Residual shape alone is not proof. At this stage a defensible response is an observation, a hypothesis and a next test—not a confident diagnosis unsupported by measurements.

### Report the aggregation and the condition

The campaign summary is the **arithmetic mean of complete-episode RMSE values**:

$$
\overline R=\frac{1}{E}\sum_{e=1}^{E}R_e.
$$

Each episode has equal weight. Pooling all retained samples instead gives

$$
R_{\mathrm{pooled}}=
\sqrt{\frac{\sum_e N_e R_e^2}{\sum_e N_e}}.
$$

These statistics answer different questions. For two episodes with RMSE 0.002 and 0.010 rad and sample counts 100 and 900, the mean episode RMSE is 0.006 rad while pooled RMSE is about 0.009508 rad. The actuator has not changed; only the weighting question has changed.

The released H1 results also depend strongly on the evaluation condition:

| Evaluation group | Method 1 mean episode RMSE | Method 2 mean episode RMSE |
|---|---:|---:|
| Model selection, 12 episodes | 0.0120930 rad | 0.00434992 rad |
| Held out, all 15 H1 episodes | 0.0233431 rad | 0.0165230 rad |
| Held-out B1/P06, 5 repeats | 0.00869335 rad | 0.003398 rad |
| Held-out G1/P06–P07, 10 repeats | 0.0306679 rad | 0.023086 rad |

![Method and condition summaries with declared grouping](../media/class04/xc330-condition-means.png)

*Figure 4. Released mean episode RMSE values, not single-episode scores. B1 and G1 groups have different profile composition as labelled. These bars are deterministic summaries of this archive, not confidence intervals or estimates of a wider actuator population.*

The combined Method 2 held-out value is approximately

$$
\frac{5(0.003398)+10(0.023086)}{15}
\approx0.016523\ \mathrm{rad}.
$$

That aggregate hides the weaker G1 group. Because G1 includes P07 as well as P06, the aggregate contrast does not isolate eccentricity as the cause. Use the matched P06 comparison and additional discriminating checks when investigating the fixture effect.

### Compare prediction with repeatability and intended use

Repeated physical trajectories show how much the recorded response varies under the same declared condition. The archived held-out repeat-to-combination-mean RMSE averages about 0.001375 rad across the 30 primary held-out episodes. This is a run-to-run context measure, not an independent sensor calibration, universal noise floor or ready-made acceptance threshold. The predicted-to-measured gap includes effects that repeatability cannot separately identify.

A useful model decision therefore combines its position metric, residual structure, repeat context, tested operating scope and the consequence of prediction error for the intended task. A tolerable discrepancy for previewing broad free motion might be inadequate for a precise interaction task. This campaign supplies no evidence for contact accuracy or calibrated torque.

The evidence supports investigating the frozen Method 2 candidates for balanced-fixture position prediction within this controller/reference boundary. It leaves eccentric transfer materially weaker and the final prospective claim unresolved. A suitable decision is: **retain the candidate for the stated limited comparison, investigate the G1 discrepancy, and require new reserved evidence before extending the claim.**

**Checkpoint:** Which numerical result would you report for the selected activity episode? Which other result would you report to describe its condition across repeats? Why are those not the same number?

## Instructor and TA demonstration

The demonstration completes one comparison record using the supplied files. Physical hardware can be shown unpowered or through a correctly identified recording. A qualified brief live motion is optional; the numerical argument uses the preserved 98 g evidence and does not depend on completing a fresh collection.

### Identify the configuration and record

Open the configuration card and Figure 1. Identify XC330, Mode 5, H1, the 98 g G1 fixture and P06 first held-out repeat. Trace the external goal, internal references, measured position and simulated output. Locate the scoring interval, initialization and 10 ms analysis grid. Distinguish the original motor-record capture from a visual illustration. State that these figures use the reduced numerical model rather than the 110 g CAD inspection family.

### Show estimation and freezing

Open the H1 parameter table. Identify which quantities are fixed and which three fields were estimated. From the repository root in the prepared native environment, the following commands audit the campaign, inspect the models, replay frozen candidates and optionally reproduce the short integral fit:

```bash
cd 2026-autumn/resources/class04/native
python code/phyintel_lab.py audit --actuator xc330
python code/phyintel_lab.py inspect --actuator xc330
python code/phyintel_lab.py replay --actuator xc330
python code/phyintel_lab.py fit-integral --actuator xc330 --controller H1
```

Use the saved outputs if runtime execution is unavailable. The replay command does not fit parameters. The fresh integral result is written separately from the released candidates. Full output-error optimization is longer preparation work; its supplied frozen vector supports the classroom comparison.

### Quantify and interpret the reserved response

From the repository root, run the prepared selected-case analysis:

```bash
cd 2026-autumn/resources/class04
python3 code/analyze_episode.py --no-plot
```

This standard-library command reports the metric without requiring plotting packages. Omit `--no-plot` in the prepared Matplotlib environment to regenerate the overlay and residual. Read the supplied overlay, signed residual and RMSE. Confirm that the selected Method 2 G1 score is about 0.02191 rad. Compare Figure 3's B1 response before looking at the group means. Name one observed discrepancy and one discriminating check. Do not refit, change zero or shift the held-out trace to improve its score.

### Compare the RS06 boundary briefly

| Item | XC330 example | RS06 source example |
|---|---|---|
| Replay input | Logged internal position and velocity references | Applied position command |
| Controller representation | Fixed mapped limited feedback effort through a motor channel | Fixed position-actuator representation |
| Analysis grid | 10 ms | 20 ms |
| Effort evidence | Device current is not independent shaft torque | Firmware effort is excluded from primary fitting |

H1/H2 names are local to each campaign. Numerically copying RS06 gains into MuJoCo is a modelling hypothesis, not established controller equivalence. The two campaigns do not form a matched actuator-quality contest. The comparison demonstrates how the experiment boundary changes the meaning of a validation result.

Finish the demonstration by stating the candidate, observable, condition, measured gap, limitation and next test.

## Student activity

Analyse the supplied **H1/G1/P06 first held-out XC330 episode** using the configuration card, Figure 1 and the saved analysis output. Running `python3 code/analyze_episode.py --no-plot` from `2026-autumn/resources/class04` in the prepared environment is optional. The same saved figures, metric and paired samples are supplied for interpretation.

Submit a compact response with five items:

1. **Comparison:** identify the physical and simulated signals, controller context, fixture and input boundary.
2. **Metric:** report the Method 2 episode position RMSE with units and explain what it compares.
3. **Observation:** describe one specific feature of the signed residual and identify where it occurs in the figure.
4. **Hypothesis and check:** propose one possible explanation and a check that could distinguish it from another explanation.
5. **Decision:** state one sentence limiting the model's use to the evidence.

A useful response distinguishes the external goal, internal reference and measured output; reports approximately 0.02191 rad rather than a group mean; and treats its explanation as testable. It does not assert that residual shape proves a root cause. There is no requirement to operate hardware, install software during class, implement an optimizer, change the payload or refit the model.

**Correct analysis of the saved outputs receives equal credit to analysis of outputs generated by the command.** Assessment concerns the comparison, metric, observation, test and bounded decision. Code execution itself is not assessed.

## Practical preparation and resources

All required explanations, equations, figures, demonstration steps and activity instructions are on this page. The accompanying [configuration and data guide](../resources/class04/data/README.md), [selected episode CSV](../resources/class04/data/xc330-98g-H1-G1-P06-R01.csv), [saved metrics](../resources/class04/data/xc330-98g-selected-episode-metrics.json) and [analysis script](../resources/class04/code/analyze_episode.py) support the same reading path. They do not require physical actuator access.

For a prepared numerical environment, use a local virtual environment with NumPy and Matplotlib for the compact analysis. The [native replay package](../resources/class04/native/README.md) separately includes the exact engine, complete primary arrays and pinned dependencies for MuJoCo replay and identification. Installation belongs before class. Saved outputs remain sufficient if the environment is unavailable.

For terminology: a **fixture** is the declared link/payload arrangement; an **episode** is one execution; a **residual** is a signed predicted-minus-observed difference; **calibration** estimates the parameters; **held-out** identifies a reserved evaluation role; and **RMSE** summarizes squared discrepancy in the output's units. This archive's retrospective status qualifies how strongly its held-out role can be interpreted.

The primary evidence is the packaged XC330 campaign and its released configuration, parameters and per-episode results. MuJoCo's [actuation documentation](https://mujoco.readthedocs.io/en/3.3.7/modeling.html#actuators) explains simulator conventions; the [ROBOTIS XC330 documentation](https://emanual.robotis.com/docs/en/dxl/x/xc330-m288/) defines device registers and modes. Neither replaces the campaign-specific data and assumptions needed for this comparison.
