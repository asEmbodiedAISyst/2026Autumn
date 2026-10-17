"""Check prepared simulation diagnostics using standard Python only."""
from pathlib import Path
import json,math
R=Path(__file__).resolve().parents[1]
for name in ['baseline','delay150','dropout30']:
 p=R/'results'/name;s=json.loads((p/'summary.json').read_text());rows=[json.loads(x) for x in (p/'trace.jsonl').read_text().splitlines()]
 assert len(rows)==s['steps'];assert sum(x['goal_event'] for x in rows)==s['goal_events'];assert sum(x['dropped'] for x in rows)==s['dropped_packets'];assert math.isclose(max(x['feature_age_s'] for x in rows),s['max_feature_age_s']);assert s['engine_warnings']==0
 print(name,dict(first_goal_time_s=s['first_goal_time_s'],goal_events=s['goal_events'],steps=s['steps'],fall=s['fall'],max_age_ms=round(s['max_feature_age_s']*1000)))
p=json.loads((R/'results/perception-summary.json').read_text());assert not p['occlusion_example']['valid'];assert p['trials'][0]['median_translation_mm']<1e-4
print('Synthetic PnP noise-free recovery and unavailable-pose gate passed')
