# Dataset contract (one page)

| Field | Entry |
| --- | --- |
| Dataset name and version | |
| Purpose (which policy, which task) | |
| Task string (exact text in `task`) | |
| Embodiment (`robot_type`) | seeed_b601_rs_follower / seeed_b601_rs_sim / rebot_pusher_tool_handheld / rebot_pusher_tool_robot |
| Features: `observation.state` (dimension, names in order, unit) | |
| Features: `action` (dimension, names in order, unit, direction convention) | |
| Cameras (keys, resolution, placement) | |
| Extra features (environment state, depth) and whether real data can have them | |
| fps and timestamp rule | |
| Initial conditions (ranges, units) | |
| Reset procedure | |
| Success rule (number, unit, hold time) | |
| Time limit | |
| Reject rules (list each with its threshold) | |
| Number of episodes collected / kept / rejected | |
| Splits: training episodes, held-out episodes, evaluation seeds | |
| Leakage rule (what must not be shared between splits) | |
| Software versions (lerobot, mujoco, asmagic, model commit) | |
| Where the audit record is stored | |
| Collected by, date | |
