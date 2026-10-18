# Commands used in class (class11_sim2real_deployment)

Run the `rebot_pusher` commands inside `additional_material/rebot_pusher` (after `uv sync`; `uv sync --group real`
on the computer of the arm). On macOS, `scripts/agent_control.py` runs with `mjpython` instead of `python`.

```bash
# exact replay with the full MuJoCo integration state (run in additional_material)
uv run --project rebot_pusher python code/replay_state_check.py --out results/replay-state.json
# closed-loop evaluation on the simulated arm with the tool (policy trained on simulated handheld data)
uv run python scripts/eval_policy.py --embodiment pusher --episodes 50 \
  --policy-path <checkpoint>/pretrained_model --n-action-steps 100
# open-loop check on held-out physical episodes (rung 3)
uv run python scripts/eval_offline.py --policy-path <checkpoint>/pretrained_model \
  --root datasets/handheld_push_cube --episodes 130-149
# kinematic replay of handheld data on the simulated arm
uv run python scripts/check_handheld_dataset.py --root datasets/real_teleop_push_cube
# supervised rollout on the physical arm (rung 5; safety rules of the README; data in the table frame)
uv run python scripts/rollout_real.py --robot real --can-port can0 --camera-ip <robot phone IP> \
  --policy-path <checkpoint>/pretrained_model --z-frame table --temporal-ensemble 0.01 \
  --max-speed 0.10 --episodes 10 --video-dir outputs/real_rollouts
# Claude as the controller: simulation, then the physical arm (API key in the environment, never on screen)
uv run python scripts/agent_control.py --robot sim --episodes 5 --model claude-sonnet-5-5 --mode push \
  --log-dir outputs/agent/sim_push
uv run python scripts/agent_control.py --robot real --can-port can0 --camera-ip <robot phone IP> \
  --model claude-opus-5-5 --mode push --max-speed 0.10 --episodes 3 --log-dir outputs/agent/real
```
