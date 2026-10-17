---
description: 10 November 2026 · 09:00–10:20 · CR6
---

# 10 Collect Data for Reinforcement Learning

#### Scope clarification

This lesson compares reinforcement learning with demonstration-based imitation learning. The supplied Simple Arm ACT example is imitation learning; demonstration collection alone must not be called RL. Suggested future title: “Demonstration Data and Learning a Robot Skill.” The Instructor schedule title remains unchanged pending consolidation.

#### Lecture — 40 minutes

1. Demonstrations, online RL experience and evaluation records serve different roles.
2. Define task, initial conditions, reset procedure, outcomes and interventions.
3. Collect a small pilot before expanding a dataset.
4. Audit images, state/action dimensions, units, joint order, timing and terminal outcomes.
5. Dataset splits, leakage and a concise contract.
6. ACT as the tutorial's arm-learning example; contrast with the LEAP RL problem.

#### Break — 5 minutes

#### Demonstration — 25 minutes

Inspect accepted/rejected pilot episodes and a prepared simulation/checkpoint example once verified. Show training configuration and outputs without attempting full training in class.

#### Student activity — 10 minutes

Audit supplied episodes and write a short dataset contract with acceptance/rejection reasons.

#### Optional project continuation

Students may run full ACT/RL training if they arrange suitable resources or use available lab compute. The course provides repositories and examples, not guaranteed GPU training capacity.
