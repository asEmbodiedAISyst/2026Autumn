"""Compare saved first-goal results and check matched initial states."""
import argparse,json
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('runs',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if a.output.exists():p.error('Use a new output file.')
reports=[json.loads((r/'summary.json').read_text()) for r in a.runs]
rows=[[json.loads(l) for l in (r/'episodes.jsonl').read_text().splitlines()] for r in a.runs]
checks=[]
for i in range(1,len(rows)):
 pairs={x['seed']:x for x in rows[i]};matched=0;max_delta=0.
 for x in rows[0]:
  if x['seed'] not in pairs:continue
  y=pairs[x['seed']];matched+=1
  for field in ('qpos','qvel','ctrl','goal_quat_wxyz'):
   max_delta=max(max_delta,float(np.max(np.abs(np.asarray(x['initial_state'][field])-y['initial_state'][field]))))
 checks.append({'run':str(a.runs[i]),'common_seeds':matched,'max_initial_state_difference':max_delta,
                'initial_states_matched_at_1e_minus6':matched>0 and max_delta<1e-6})
result={'runs':[{'path':str(path),'summary':r} for path,r in zip(a.runs,reports)],'initial_state_checks':checks,
        'interpretation':'Same seeds do not guarantee matched backend resets. Compare noise, timestep and history contracts; this table alone does not isolate a cause.'}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
