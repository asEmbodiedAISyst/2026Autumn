"""Read one native run without dependencies or new simulation."""
from pathlib import Path
import argparse,json
p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
s=json.loads((a.run/'summary.json').read_text());print('episodes with a goal:',s['episodes_with_goal'])
for line in (a.run/'trace.jsonl').read_text().splitlines():
 row=json.loads(line)
 if row['goal_event']:print('time (s):',row['step']*.05,'error (rad):',row['orientation_error_rad'])
