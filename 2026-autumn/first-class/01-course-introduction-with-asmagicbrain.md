---
description: 20 October 2026 · 09:00–10:20 · CR6 | SONG Chaoyang
layout:
  width: wide
---

# 01 Course Introduction with asMagicBrain

## Central question

> Given something we want a robot to understand or learn, what physical interactions should we arrange, what should we record, and how will we know whether those records helped?

A robot's behavior depends on its body, environment, sensors, controller and available experience. This course examines those connections through controlled actuator experiments, manipulation and human-guided robot interaction. You will develop one team project whose implementation, data and conclusions can be examined together.

## Learning objectives

By the end of this class, you should be able to:

- Explain how embodiment, sensing, action and collection choices shape robot learning.
- Distinguish a physical interaction, its recorded traces and an interpretation of those traces.
- Explain the different roles of feedback control, a learned policy and a predictive model.
- Compare the collection and learning arrangements of ALOHA, LEAP Hand and UMI.
- Identify your team and its repository, and explain the course's project and submission pathway.

## Lecture

### Begin with a motor, a lever and a question

Imagine a motor turning a short lever. We command it to reach an angle and record its position over time. We then attach a load and repeat the command. Suppose the loaded motion appears slower. **What can we conclude?**

The load might change inertia and gravitational loading. Friction, a current limit or the controller's response might also contribute. Different starting conditions, sensor processing or timestamp conventions could change the apparent comparison. This is a constructed example: no measured outcome is being asserted.

The traces give us something to investigate. They do not, by themselves, identify the cause. Before collecting more data, decide what you want to learn.

| Intended purpose | What the experiment needs |
| --- | --- |
| Describe the response | Defined commands, observations and timing. |
| Identify a physical property | Conditions that distinguish its effect from competing effects. |
| Learn a reaching behavior | Experience covering relevant targets, loads and disturbances. |
| Compare simulation and hardware | Corresponding configurations, inputs, observations and evaluation conditions. |

The same apparatus can serve several purposes, but each purpose places different demands on the experiment. Repeating one successful motion may help describe that motion while revealing little about recovery from a disturbance.

### Separate the interaction, the record and the explanation

**Physical interaction → recorded traces → interpreted outcome**

The physical interaction includes the motor, lever, load and environment responding to applied inputs. The recorded traces retain selected observations, commands and context. The interpreted outcome is an explanation supported or challenged by those records.

An encoder provides a position-related measurement. It does not reveal every internal force, deformation or source of heat. A stored command describes what was requested; limits and internal control can change what was applied. Likewise, a column named `torque` might contain requested effort, a current-derived estimate or a direct measurement. Its name alone does not establish its meaning.

For a record to remain useful, another person must be able to understand its units, timing, configuration and derivation. When two traces differ, first ask what changed in the encounter and what changed in the recording process.

### Experience-generating physical systems

Here, **experience** means interaction data together with the context needed to interpret and use it. It does not imply conscious experience. We use **Experience-Generating Physical Systems**, abbreviated **ExpGen PhySyst**, as an integrative perspective: design and operate physical interactions so that their records can improve understanding or capability.

The relevant system includes more than the robot:

**Body and environment ↔ action and sensing → records → analysis or learning → next interaction**

A person, controller or policy selects actions. The body and environment determine which encounters are possible. Sensors determine what can be observed. Recording and interpretation determine what information reaches a learning process. Changing the apparatus can therefore change the learning problem.

**Designing data begins before a file is saved.** It includes choosing the task and starting conditions, the actions and interventions, the observations to retain, and the conditions to cover. It also includes deciding which comparison will establish whether the records were useful. More recordings of an easy case may leave the important uncertainty untouched.

### A short historical perspective

Physical AI connects several established lines of inquiry. The following examples offer useful questions rather than a single historical progression.

| Perspective | Question carried into this course |
| --- | --- |
| Alan Turing: evaluation and learning | What evidence would establish a capability, and what initial capacities and subsequent experiences should a learner receive? |
| Norbert Wiener: feedback and communication | How do observed consequences influence subsequent action? |
| Rodney Brooks: situated perception and action | How does behavior depend on continuing interaction with the physical environment? |
| Learning from demonstration | How can human behavior shape the experience available to a learner? |
| Predictive and world models | What consequences can a model predict, and which tests expose errors that matter for control? |

Turing's 1950 *Computing Machinery and Intelligence* examines evaluation through an imitation game and also discusses learning. Success in a conversational test would not establish physical manipulation skill. The broader lesson is to define the evidence appropriate to the capability being claimed.

Wiener's *Cybernetics*, first published in 1948, connects control and communication. Brooks's 1991 *Intelligence without Representation* emphasizes behavior grounded in perception and action. Together, these perspectives encourage us to examine an algorithm within the physical and informational arrangement through which it operates.

Feedback and learning are distinct. A fixed controller can repeatedly correct an error without changing its control law. Learning changes a model, policy or parameter using experience.

| Component | Main question |
| --- | --- |
| Feedback controller | How should the input change in response to observed conditions or error? |
| Learned policy | What action should be taken from the available observations and task information? |
| Predictive model | What might happen following an action? |

These components can operate together. Learning may occur before deployment or during operation; real-time robot movement alone does not establish that learning is taking place. When watching a demonstration, identify which component produces the action and which, if any, is being updated.

### Three research examples

ALOHA, LEAP Hand and UMI illustrate different ways to connect apparatus, experience and learning.

| System | Main arrangement | What to notice |
| --- | --- | --- |
| [ALOHA / ACT](https://tonyzhaozh.github.io/aloha/) | Leader–follower teleoperation supports bimanual demonstrations and imitation learning. | How operator movement becomes robot targets, and which observations accompany those targets. |
| [LEAP Hand](https://v1.leaphand.com/) | A dexterous hand supports several control and learning workflows. | How morphology, actuation and interfaces shape feasible behavior and the use of experience. |
| [UMI](https://umi-gripper.github.io/) | Handheld grippers and cameras collect demonstrations for later robot learning. | How recorded human demonstrations become compatible with a deployment robot. |

For ALOHA, distinguish leader joint positions used as targets from follower positions and camera observations. For LEAP Hand, distinguish the physical platform from a particular learning method: its reported learning examples do not all share the same data source. For UMI, separating collection from the deployment robot changes the apparatus, but alignment, timing and feasible robot motion still matter.

These research systems motivate questions for our course platforms. Their published results do not establish the performance of the classroom hardware or configuration.

### Know where information comes from

| Information | Example | What to retain |
| --- | --- | --- |
| Measured | Encoder position | Instrument, calibration, units and timestamp meaning. |
| Estimated | Velocity calculated from positions | Input samples, processing method and assumptions. |
| Simulated | Joint motion from a computational model | Model, parameters, controller and simulation settings. |
| Human supplied | Demonstration, instruction or outcome label | Meaning, collection procedure and relevant judgments. |

These categories can overlap. One demonstration can contain measurements, estimates and human judgments. Preserve their relationships: a simulated trajectory is not a measurement of the physical robot, and an operator's target is not the robot's measured response.

A live interaction is not automatically a dataset. Check whether the relevant channels are actually recorded, whether their timing can be interpreted, and whether resets, interventions and outcomes remain identifiable.

### Use Sim2Real differences to choose the next experiment

A simulation makes specified assumptions executable. A physical experiment tests correspondence within the conditions actually observed. When results differ, ask whether configurations and starting conditions were comparable, inputs had the same meaning, observations were aligned, and consequential effects were simplified or omitted.

Agreement on one trajectory supports a limited conclusion. A successful simulated policy still needs appropriate physical evaluation. The useful outcome of a Sim2Real comparison is often a better-defined next experiment: one that can distinguish plausible explanations or expose an important failure condition.

### How the course develops these ideas

| Course stage | Main investigation |
| --- | --- |
| Classes 02–04 | Controlled action, digital representation and actuator-level Sim2Real comparison. |
| Classes 05–07 | Multi-actuator embodiment, learned manipulation and visual feedback. |
| Classes 08–11 | Arm operation, teleoperation, demonstration collection and deployment differences. |
| Classes 12–17 | Develop one project through Claim, Experience, System, Grounding, Learning and Decision. |
| Classes 18–21 | Communicate, reproduce, present and demonstrate the resulting project. |

Your project should connect a precise question to an implemented system, interpretable records and a supported conclusion. An explained limitation or negative finding can be more informative than an impressive clip without a defined test.

## Teaching team demonstrations

The teaching assistants introduce the asMagicBrain Platform through a LEAP Hand and a reBot leader–follower arm arrangement. Before each demonstration, identify the action source, observations, control mode and operating boundary. The designated operator controls the system; keep the stop available and remain outside its motion area.

### LEAP Hand: real-time hand retargeting

The teaching team uses an **iPhone 17 Pro running asMagic** to capture human hand movement and retarget it to the LEAP Hand in real time.

**Human hand movement → iPhone/asMagic capture → retargeting → LEAP Hand commands → physical movement**

Human and robot hands have different structures and motion limits. Retargeting translates captured movement into robot commands that respect the chosen mapping and limits. Observe how tracking quality, delay and actuation affect the resulting movement. A correspondence between gestures does not mean every human joint has an identical robot counterpart.

### LEAP Hand: cube rotation

The teaching team demonstrates the prepared LEAP Hand cube-rotation task and identifies the controller or policy used, the observations it receives, and any human intervention. Compare its action source with the human-driven retargeting demonstration.

Watch how the hand maintains and changes contact with the cube. A successful attempt illustrates a capability under the shown conditions. Reliability needs defined starting conditions, a success/failure rule and repeated outcomes, including failed attempts.

### reBot: leader–follower teleoperation

The teaching team introduces the leader and follower arms, then demonstrates the follower being teleoperated by the leader in real time.

**Operator moves leader → leader joint readings → command mapping → follower arm movement**

Distinguish the leader's readings, the transmitted targets and the follower's actual response. Notice how the chosen mapping and motion limits affect what the follower can reproduce. The operator supplies the guidance; identify any separate control process that tracks the commanded movement.

### reBot: iPhone-guided pusher

The teaching team uses an **iPhone running the asMagic App** to teleoperate the follower arm. The arm carries the **3D-printed custom stick adaptor used as a pusher in Class 09**.

**Operator moves iPhone → captured pose → frame and command mapping → follower arm → pusher movement**

Distinguish the tracked phone pose, the commanded robot motion and the pusher's physical interaction with its surroundings. Phone and robot coordinates require an explicit mapping; the pusher's contact point also differs from the phone's tracked reference. This demonstration previews guided interaction in Class 09.

### Compare the four demonstrations

| Demonstration | Question to discuss |
| --- | --- |
| Hand retargeting | How is movement translated across different embodiments? |
| Cube rotation | What observations and control method produce the behavior? |
| Leader–follower arms | How does the leader's movement become a follower command? |
| iPhone-guided pusher | How are captured motion, robot coordinates and contact connected? |

For each demonstration, ask what is displayed live, whether data are being recorded, and what evidence would be needed to evaluate the behavior beyond the selected attempt. The teaching team can show a labelled recording if a live demonstration is unavailable.

### Course and repository walkthrough

Open the course and one assigned team repository. Locate the notes, resources, submission folders and an example result with its configuration. Distinguish saving locally, committing and pushing. Explain which remote version the teaching team retains at a deadline.

asMagicBrain is demonstrated as part of the platform workflow. Students can also access the course materials and manage project files with GitHub, GitBook and standard development tools; installing asMagicBrain is not a condition for joining a team.

## Student activity: form eight teams

**Eight teams must be formed and their membership confirmed by the end of Class 01.**

1. Join one of the eight teams and confirm its member list with the teaching assistants.
2. Receive or confirm your assigned **Team01–Team08** identifier.
3. Identify the matching private repository in the table below and check access where available.
4. Locate its README, checkpoint folders and final submission folders.
5. Report unresolved membership or access issues to the teaching team before leaving.

The teaching assistants retain the confirmed roster. Repository-access problems are recorded for follow-up rather than delaying confirmation of the team list. This activity adds no graded worksheet or upload.

## Your assigned team repository

Each team develops and submits one project in its assigned private GitHub repository. The instructor will show these actual repositories in Class 01. Access is assigned by the teaching team; use your own team's repository throughout the course.

| Team | Assigned repository |
| --- | --- |
| Team 01 | [2026Autumn-Team01](https://github.com/asEmbodiedAISyst/2026Autumn-Team01) |
| Team 02 | [2026Autumn-Team02](https://github.com/asEmbodiedAISyst/2026Autumn-Team02) |
| Team 03 | [2026Autumn-Team03](https://github.com/asEmbodiedAISyst/2026Autumn-Team03) |
| Team 04 | [2026Autumn-Team04](https://github.com/asEmbodiedAISyst/2026Autumn-Team04) |
| Team 05 | [2026Autumn-Team05](https://github.com/asEmbodiedAISyst/2026Autumn-Team05) |
| Team 06 | [2026Autumn-Team06](https://github.com/asEmbodiedAISyst/2026Autumn-Team06) |
| Team 07 | [2026Autumn-Team07](https://github.com/asEmbodiedAISyst/2026Autumn-Team07) |
| Team 08 | [2026Autumn-Team08](https://github.com/asEmbodiedAISyst/2026Autumn-Team08) |

Open the repository README and locate `submissions/class12/` through `submissions/class17/` for the initial worksheet checkpoints, `worksheets/` for the six final updated worksheets, and `poster/`, `code/` and `video/` for the final artifacts. Shared `environment/` and `results/` folders support the same project. The [Class 12 worksheet guide](../module-04-worksheets-guided-final-project-preparation/12-final-project-i-claim.md) begins the checkpoint sequence.

| Milestone | Main artifact | Deadline, Abu Dhabi time (UTC+4) |
| --- | --- | --- |
| [Class 18: poster](../module-05-final-project-submissions/18-final-poster-submission.md) | `poster/TeamNN-poster.pdf` | 27 November 2026, 10:50 |
| [Class 19: code](../module-05-final-project-submissions/19-final-code-submission.md) | `code/README.md` and implementation | 1 December 2026, 10:20 |
| [Class 20: video](../module-05-final-project-submissions/20-final-video-submission.md) | `video/TeamNN-video.mp4` | 2 December 2026, 11:50 |
| [Class 20: final updated worksheets](../module-05-final-project-submissions/20-final-video-submission.md#final-updated-worksheets) | Six final signed PDFs in `worksheets/`, using the six filenames listed in Class 20 | 2 December 2026, 11:50 |

Use your two-digit team number in place of `NN`, for example `Team01-poster.pdf` and `Team01-video.mp4`. The teaching team appends `-YYMMDD-HHMMSS` to collected filenames, using the GitHub-recorded submission push time in Abu Dhabi time (UTC+4), for example `Team01-poster-261127-104530.pdf`. Students keep code in the existing repository; instructors create `Team01-code-YYMMDD-HHMMSS.zip`.

Commit and push the deliverable to `main` before its deadline, then inspect the files on GitHub. A saved local file or unpushed commit is not available for collection. At each deadline the teaching team captures the remote revision, records its commit, GitHub push time and collection time separately, and retains that revision. The deadline concerns when the version reached GitHub, not its local commit date. Later changes remain later work; they do not replace the collected snapshot.

No release, tag, manifest or separate student collection record is required. The folders are the submission route. Classes 18–20 explain preparation of each artifact; these are progressive opportunities to finalize the same project.

## Further reading

- Alan Turing, [*Computing Machinery and Intelligence*](https://doi.org/10.1093/mind/LIX.236.433), 1950.
- Norbert Wiener, [*Cybernetics*](https://doi.org/10.7551/mitpress/11810.001.0001), first published 1948; linked edition is the 2019 reissue of the second edition.
- Rodney Brooks, [*Intelligence without Representation*](https://doi.org/10.1016/0004-3702(91)90053-M), 1991.
- Stefan Schaal, [*Learning from Demonstration*](https://proceedings.neurips.cc/paper/1996/hash/68d13cf26c4b4f4f932e3eff990093ba-Abstract.html), NIPS 1996 proceedings, published 1997.

**Carry into Class 02:** When we command an actuator, which physical quantities are controlled, which are measured, and which remain inferred?
