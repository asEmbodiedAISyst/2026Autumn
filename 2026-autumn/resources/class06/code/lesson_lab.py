"""Inspect supplied evaluation records without dependencies, fitting, or hardware IO."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1]
def inspect():
 checks=[]
 for name in ['native-task-10ms-noisy-heldout','playground-noise-1','playground-noise-0']:
  folder=R/'code/results'/name;s=json.loads((folder/'summary.json').read_text());rows=[json.loads(x) for x in (folder/'episodes.jsonl').read_text().splitlines()]
  assert len(rows)==100 and sorted(x['seed'] for x in rows)==list(range(20000,20100))
  counts={k:sum(bool(x[k]) for x in rows) for k in ['first_goal_success','fall','timeout']}
  assert sum(counts.values())==100
  assert counts['first_goal_success']==s['first_goal_successes'] and counts['fall']==s['falls'] and counts['timeout']==s['timeouts']
  checks.append(dict(condition=name,episodes=100,successes=counts['first_goal_success'],falls=counts['fall'],timeouts=counts['timeout'],observed_teaching_baseline_met=counts['first_goal_success']>=80,versions=s['configuration']['versions']))
 policy=R/'code/upstream-training-guide/leap_reorient_policy.onnx';digest=hashlib.sha256(policy.read_bytes()).hexdigest();assert digest=='1893e4a0f3b95f1657ce5e11745db0ac8749c8780d83013859082c414cb5f97f'
 tr=json.loads((R/'records/continuous-example.json').read_text())['trace'];events=[x['step'] for x in tr if x['goal_event']];assert events==[356,761]
 result=dict(scope='Inspection of existing records, not new policy evaluation',conditions=checks,policy_sha256=digest,selected_episode_events=events,selected_episode_times_s=[x*.05 for x in events],historical_95_percent_fields='Preserved in original receipts; no longer a teaching gate')
 (R/'evidence').mkdir(exist_ok=True);(R/'evidence/retained-results-check.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':print(json.dumps(inspect(),indent=2))
