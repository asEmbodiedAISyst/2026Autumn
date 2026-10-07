---
description: 2026 Autumn
---

# \[ROB7103/8103] Embodied AI Systems @ MBZUAI

### Course Description

This seven-week course examines how AI methods become parts of measurable, reproducible, and responsibly operated physical systems. It assumes prior competence in machine learning, computer vision, reinforcement learning, and related AI methods. It does not repeat general AI, kinematics, control, or planning courses. Instead, it concentrates on embodiment, sensing, actuation, communication, calibration, fabrication, simulation, Sim2Real evidence, robot-learning deployment, and experimental diagnosis.

The course normally contains three scheduled events per week, with durations determined by the official timetable. It includes six linked Embodied AI Meets Design worksheets, one revised worksheet portfolio, and one team final project. An optional two-day Seeed hackathon may be offered as a separate supervised event. Details will be announced separately.

The course begins on October 20, 2026. Access to the supporting source repositories is managed separately and does not determine the copyright or licensing status of the rendered materials.

### Course Aims

The course aims to enable students to design, build, instrument, and critically evaluate embodied AI systems. It bridges advanced AI knowledge and physical implementation without repeating foundational AI, kinematics, planning, or control theory. Students learn to translate a bounded system idea into a feasible physical-digital prototype, establish measurement validity, integrate a learning-enabled component, and evaluate the resulting capability with appropriate evidence. The course emphasizes data semantics and provenance, calibration, frames, timing, Sim2Real discrepancies, safety, reproducibility, and failure analysis. By the end of the course, students should be able to develop a bounded team prototype, compare learned and non-learned baselines, communicate limitations, and identify a defensible next step. The course also develops practical competence in CAD, limited rapid prototyping, simulation, robot interfaces, experiment design, and technical communication.

### Learning Outcomes

By the end of the course, a successful student should be able to:

1. Define and critique an embodied-AI system.
2. Engineer and bring a physical–digital platform into operation.
3. Produce research-quality embodied experience.
4. Evaluate correspondence between computational and physical representations.
5. Assess learning inside a real robotic feedback cycle.
6. Deliver and defend a repeatable team prototype.

### Content Summary

The course introduces embodied AI as a closed-loop physical system and uses an iterative project process to connect theory, system design, physical experimentation, learning, and responsible operation. Topics may include physical and actuator modeling; parameter identification; CAD, fabrication, and introductory 3D printing; robot descriptions and simulation; hardware commissioning and calibration; multi-actuator communication; robot morphology; multimodal sensing; frames, clocks, and data interfaces; motion retargeting and demonstration data; vision-guided manipulation; imitation learning; Sim2Real validation; digital models and digital twins; experimental baselines; uncertainty and failure analysis; safety and human authority; reproducible code and data lineage; and evidence-supported project decisions. Examples may use single- or multi-actuator systems, manipulation platforms, mobile perception, simple robot arms, or combinations of compatible systems. Six concise project worksheets guide the progressive development, evaluation, revision, and final assessment of a reproducible physical prototype. Specific frameworks, tools, systems, and open-source resources are selected according to course needs and may change between offerings.

### Assumed Knowledge

Students are expected to have graduate-level programming ability in Python and experience using Linux, command-line tools, and version control. They should understand the fundamentals of machine learning and computer vision and have prior exposure to reinforcement learning or robot learning. Working knowledge of linear algebra, calculus, probability, and experimental data analysis is expected. Familiarity with basic robotics concepts, coordinate frames, kinematics, dynamics, control, and planning is helpful because these topics are applied but not retaught systematically. Students must be willing to work collaboratively and follow laboratory, electrical, mechanical, data, and robot-safety instructions.

### Course Instructor and Teaching Team

* **Lead instructor:** Prof. SONG Chaoyang · Associate Professor of Robotics, MBZUAI
  * **Email:** Chaoyang.Song \[at] mbzuai.ac.ae
  * **Office:** C-1.01, Building 1B · **Office hours:** Mondays, 10:00–12:00
* **Teaching Assistants**
  * ZHANG Dunxing (Dunxing.Zhang \[at] mbzuai.ac.ae)
  * YANG Hang (Hang.Yang \[at] mbzuai.ac.ae)
* **Technical Support**
  * Dr. Mohamed HALWANI (Mohamed.Halwani \[at] mbzuai.ac.ae)
  * WEI Jinqi (Jinqi.Wei \[at] mbzuai.ac.ae)
  * LI Zhibin (Zhibin.Li \[at] mbzuai.ac.ae)
* **Research Support**: Prof. WAN Fang (wanf \[at] sustech.edu.cn)

### Grading Policy

Assessment combines individual participation with a progressive team project.

* Individual (10%)
  * 10%: Recorded attendance across scheduled meetings
* Team (90%)
  * 30%: Six staged project records
  * 25%: Working system and reproducibility package
  * 10%: Consolidated and updated project record
  * 10%: Narrated project video
  * 10%: Oral briefing and response to questions
  * 5%: Technical poster

### Academic Integrity

All work must comply with the University's academic-integrity requirements and with the specific collaboration and tool-use conditions stated for each assessment. Because this course depends on shared code, research papers, datasets, pretrained models, CAD files, and external software, clear attribution and traceability are essential parts of scholarly practice.

Students are expected to:

* cite publications, documentation, datasets, software, models, hardware designs, media, and other reused material;
* preserve license notices and observe any restrictions attached to third-party resources;
* distinguish their own contribution from instructor-provided, teammate-produced, open-source, and machine-generated material;
* maintain authentic experiment records, including unsuccessful trials and relevant changes to hardware, code, parameters, or data;
* verify technical claims and inspect generated code or text before including it in assessed work;
* disclose the use of generative AI or automated coding tools when an assessment brief requires it; and
* retain sufficient development history to explain how the submitted result was produced.

Examples of unacceptable practice include inventing or altering measurements, hiding failed runs that materially affect a conclusion, presenting another person's work as one's own, submitting unverified machine-generated content, disguising the source of reused assets, sharing restricted assessment material, or bypassing safety and authorization controls to obtain a result.

### Recommended Textbook(s)

1. Featherstone, R. **Rigid Body Dynamics Algorithms**. Springer, 2008. ISBN 978-0-387-74314-1.
2. Siciliano, B., and Khatib, O., editors. **Springer Handbook of Robotics**. 2nd edition. Springer, 2016. ISBN 978-3-319-32550-7.
3. Lynch, K. M., and Park, F. C. **Modern Robotics: Mechanics, Planning, and Control**. Cambridge University Press, 2017. ISBN 978-1-107-15630-2.
4. Sutton, R. S., and Barto, A. G. **Reinforcement Learning: An Introduction**. 2nd edition. MIT Press, 2018. ISBN 978-0-262-03924-6.

### Teaching Schedule

<table><thead><tr><th width="62.51953125">Wk</th><th>Tue 0900-1020 CR6</th><th>Wed 1030-1150 CR6</th><th>Fri 0900-1050 L12</th></tr></thead><tbody><tr><td>01</td><td><p>Oct 20: Class 01 </p><p>Course Introduction with asMagicBrain</p></td><td><p>Oct 21: Class 02</p><p>Actuator Basics for Controlled Action</p></td><td><p>Oct 23: Class 03</p><p>Basic Digitization of Physical Embodiment</p></td></tr><tr><td>02</td><td><p>Oct 27: Class 04</p><p>Basic Quantification of Sim2Real Gap</p></td><td><p>Oct 28: Class 05</p><p>From Single-Actuator to Multi-Actuator</p></td><td><p>Oct 30: Class 06</p><p>Learned In-Hand Cube Reorientation</p></td></tr><tr><td>03</td><td><p>Nov 03: Class 07</p><p>Rotating a Cube with Visual Feedback</p></td><td><p>Nov 04: Class 08</p><p>Let's Build a Simple Arm &#x26; Turn it On</p></td><td><p>Nov 06: Class 09</p><p>Teleoperation by Streaming from asMagic</p></td></tr><tr><td>04</td><td><p>Nov 10: Class 10</p><p>Collect Data for Reinforcement Learning</p></td><td><p>Nov 11: Class 11</p><p>Sim2Real Gap in Hardware Deployment</p></td><td><p>Nov 13: Class 12</p><p>Final Project I: Claim</p></td></tr><tr><td>05</td><td><p>Nov 17: Class 13</p><p>Final Project II: Experience</p></td><td><p>Nov 18: Class 14</p><p>Final Project III: System</p></td><td><p>Nov 20: Class 15</p><p>Final Project IV: Grounding</p></td></tr><tr><td>06</td><td><p>Nov 24: Class 16</p><p>Final Project V: Learning</p></td><td><p>Nov 25: Class 17</p><p>Final Project VI: Decision</p></td><td><p>Nov 27: Class 18</p><p>Final Poster Submission</p></td></tr><tr><td>07</td><td><p><del>Dec 01: Class 19</del></p><p>Final Code Submission</p><p><strong>(No Class. Public Holiday)</strong></p></td><td><p><del>Dec 02: Class 20</del></p><p>Final Video Submission </p><p><strong>(No Class. Public Holiday)</strong></p></td><td><p>Dec 04: Class 21</p><p>Final Project Showcase</p></td></tr></tbody></table>

### Important Deadlines

* Nov 13 @ 1050: Worksheet 1 — Claim
* Nov 17 @ 1020: Worksheet 2 — Experience
* Nov 18 @ 1150: Worksheet 3 — System
* Nov 20 @ 1050: Worksheet 4 — Grounding
* Nov 24 @ 1020: Worksheet 5 — Learning
* Nov 25 @ 1150: Worksheet 6 — Decision
* Nov 27 @ 1050: Final Poster
* Dec 01 @ 1020: Final Code
* Dec 02 @ 1150: Final Video
* Dec 04 @ 0900: Final Presentation & Final Demonstration

### How to Prepare

Bring a laptop and prepare to use Python, command-line tools, and Git. Use isolated virtual environments for class software. Follow the instructions supplied with each exercise and record the software versions used.

The course combines technical explanations, worked demonstrations and practical activities. Review the supplied material before each session. Retain code, measurements, and experiment notes so another team can reproduce your results.

Using asMagicBrain is optional. You can access course materials and project work through GitHub and standard development tools. Course code and downloadable materials are available in the [Students repository](https://github.com/asEmbodiedAISyst/2026Autumn).

### Final Project and Worksheets

Develop one team project through six worksheets: **Claim → Experience → System → Grounding → Learning → Decision**. The team guide and worksheet files will be provided before the project phase.

Complete one worksheet for each of Classes 12–17. Submit it handwritten and signed by every team member before the end of the corresponding session. You may revise earlier worksheets as your project develops; keep earlier submissions and explain any material changes.

The final project package includes the worksheet portfolio, reproducible code and environment instructions, relevant data and results, a technical poster and a narrated video. Present and demonstrate the project at the final showcase. Detailed artifact requirements will be supplied separately.

Each team will have a private project repository for its instructions, development and final submission. We will provide repository links when teams are assigned.

### Course Materials

This page provides the Autumn 2026 course information and schedule. Individual class pages are not available yet. Dates and assessment details follow the current course plan; we will announce any approved changes here. No-class dates in the schedule do not automatically cancel listed submission deadlines. All times are Abu Dhabi time (UTC+4).
