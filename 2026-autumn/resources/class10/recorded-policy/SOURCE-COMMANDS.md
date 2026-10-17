# Commands used in class (class10_collect_data_for_learning)

Run the simulation-repository commands inside `rebot-mbzuai-course-resources`; run the course-repository commands at the course repository root.

```bash
# audit the pilot (course repository, no simulation package needed)
uv run python course_resources/class10_collect_data_for_learning/\
  additional_material/code/audit_dataset.py \
  course_resources/class10_collect_data_for_learning/additional_material/data/pilot_push_cube_handheld
# generate demonstrations (simulation repository)
uv run python scripts/generate_demos.py --num-episodes 60 \
  --repo-id local/rebot_push_cube_scripted --root data/rebot_push_cube_scripted
uv run python scripts/generate_tool_demos.py --embodiment handheld --num-episodes 300 \
  --repo-id local/ip17_cube300_handheld --root data/ip17_cube300_handheld
# train ACT (RTX 5090: about 1 h for 40k steps)
uv run lerobot-train --dataset.repo_id=local/rebot_push_cube_scripted \
  --dataset.root=data/rebot_push_cube_scripted --policy.type=act \
  --output_dir=outputs/train/act_push_cube_scripted --job_name=act_push_cube_scripted \
  --policy.device=cuda --wandb.enable=false --policy.push_to_hub=false \
  --steps=40000 --batch_size=16 --save_freq=10000
# evaluate in simulation (50 episodes, seeds from 100000)
uv run python scripts/eval_policy.py \
  --policy-path outputs/train/act_push_cube_scripted/checkpoints/last/pretrained_model \
  --task push_cube --episodes 50 --video-dir outputs/eval/act_push_cube
```
