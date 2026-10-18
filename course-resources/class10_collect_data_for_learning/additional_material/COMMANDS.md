# Commands used in class (class10_collect_data_for_learning)

Run every command inside `additional_material/rebot_pusher` after `uv sync`. On macOS, `scripts/teleop_real.py`
runs with `mjpython` instead of `python`.

```bash
# phone simulator, for a test without an iPhone (second terminal)
uv run python -m rebot_sim.teleop.fake_phone --pattern circle --hold tool --image
# record handheld demonstrations
uv run python scripts/record_handheld.py --phone-ip <phone IP> --root datasets/my_handheld --num-episodes 5
# record hands-free, with gestures and voice
uv run python scripts/record_handheld.py --phone-ip <phone IP> --root datasets/my_handheld --gesture --voice
# teleoperate the simulated arm and record
uv run python scripts/teleop_real.py --robot sim --phone-ip <phone IP> --record --root datasets/my_sim_teleop \
  --num-episodes 5
# replay a handheld dataset on the simulated arm: reach, speed, tilt, yaw
uv run python scripts/check_handheld_dataset.py --root datasets/my_handheld
# audit the pilot with injected faults
uv run python ../code/audit_dataset.py ../data/pilot_push_cube_handheld
# audit a physical dataset of the package and write the report
uv run python ../code/audit_dataset.py datasets/real_teleop_push_cube --json outputs/real-teleop-audit.json
# convert a dataset with start-anchored height to table-anchored height
uv run python tools/anchor_z_to_table.py datasets/<name>
# generate the simulated demonstrations with the scripted expert
uv run python scripts/generate_tool_demos.py --task push_cube --embodiment handheld --num-episodes 300 \
  --seed 20000 --repo-id local/sim_push_cube --root datasets/sim_push_cube
uv run python scripts/generate_tool_demos.py --task push_t --embodiment handheld --num-episodes 100 \
  --seed 3000 --max-unreachable-frac 0.02 --repo-id local/sim_push_t --root datasets/sim_push_t
```
