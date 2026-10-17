# Recorded ACT baseline: separate evidence branch

These files concern the source's **7-channel arm/gripper scripted demonstration baseline** (`rebot_push_cube_scripted`). They are not evaluation of the 9D pose handheld pilot in `../data/pilot_push_cube_handheld`.

- `results_act_push_cube_40k.json`: retained 50-episode simulation result, seeds 100000–100049; 24 success flags / 50 = 48%.
- `class10_act_push_cube_ep000.mp4`: source episode 0, seed 100000, reported failure, 450 steps, final distance about 38.24 mm.
- `class10_act_push_cube_ep002.mp4`: source episode 2, seed 100002, reported success, 147 steps, final distance about 11.73 mm.
- `SOURCE-COMMANDS.md`: unmodified source recipe, included for evidence interpretation; it refers to repositories and scripts outside this portable subset. It is not the installation/run guide for this bundle.

The recorded recipe generated 60 scripted gripper demonstrations, trained ACT for 40,000 steps, batch size 16, checkpoint interval 10,000, CUDA device, W&B disabled and Hub publication disabled. It evaluated 50 simulation episodes. The same source command file separately mentions 300 handheld demonstrations; that is a different branch. Its RTX 5090 runtime estimate is a source claim, not a measurement made during this preparation.

Exact trained weights and processors are absent. The supplied JSON and clips can be inspected, but policy inference and training are not reproduced here. The retained 9D pusher task code checks a distance below 0.015 m immediately; its implementation does not apply the 0.5 s dwell mentioned in source prose. That observation concerns the pusher implementation, not the separate 7-channel gripper result branch. The baseline JSON alone does not establish its evaluator identity or dwell rule. A final-frame threshold in the pilot audit is a separate snapshot check.
