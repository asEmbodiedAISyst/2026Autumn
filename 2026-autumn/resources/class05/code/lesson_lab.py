"""Reaggregate supplied metrics, preserving physical-record pairing. No fitting or hardware IO."""
from pathlib import Path
import csv,json,math
from collections import defaultdict
R=Path(__file__).resolve().parents[1]
def analyse():
 rows=list(csv.DictReader((R/'data/episode_metrics.csv').open()))
 h=[x for x in rows if x['split']=='held_out'];pairs=defaultdict(dict)
 events=defaultdict(set);roles=defaultdict(set)
 for row in rows:
  event=row['simultaneous_episode_id'];events[event].add(int(row['motor_id']));roles[event].add(row['split'])
 assert len(events)==125 and all(v==set(range(16)) for v in events.values())
 assert all(len(v)==1 for v in roles.values()), 'A collection event crosses split boundaries'
 assert {k:sum(v=={k} for v in roles.values()) for k in ['calibration','model_selection','held_out']}=={'calibration':72,'model_selection':23,'held_out':30}
 parameters=list(csv.DictReader((R/'data/fitted_parameters.csv').open()))
 selected=[v for v in parameters if v['model']=='hardware_fitted']
 assert len(selected)==32 and len({(v['controller_id'],v['motor_id']) for v in selected})==32
 for x in h:
  k=x['episode_id'];m=x['model']
  if m in pairs[k]:raise ValueError('Duplicate prediction')
  pairs[k][m]=float(x['position_rmse_rad'])
 assert len(pairs)==480 and all(set(v)=={'synthetic_baseline','hardware_fitted'} for v in pairs.values())
 assert len({x['simultaneous_episode_id'] for x in h})==30
 b=sum(v['synthetic_baseline'] for v in pairs.values())/len(pairs)
 f=sum(v['hardware_fitted'] for v in pairs.values())/len(pairs)
 cells=[]
 for c in ['H1','H2']:
  for m in range(16):
   rr=[x for x in h if x['controller_id']==c and int(x['motor_id'])==m]
   assert len(rr)==30 and len({v['episode_id'] for v in rr})==15
   vals={k:sum(float(x['position_rmse_rad']) for x in rr if x['model']==k)/sum(x['model']==k for x in rr) for k in ['synthetic_baseline','hardware_fitted']}
   cells.append(dict(motor=m,controller=c,baseline=vals['synthetic_baseline'],fitted=vals['hardware_fitted'],reduction=100*(1-vals['hardware_fitted']/vals['synthetic_baseline'])))
 result=dict(scope='Supplied metrics reaggregation; no new fitting',events=30,records=480,baseline=b,fitted=f,reduction=100*(1-f/b),cells=cells)
 assert math.isclose(result['reduction'],31.985323,abs_tol=1e-5)
 (R/'results').mkdir(exist_ok=True);(R/'results/lesson-summary.json').write_text(json.dumps(result,indent=2)+'\n')
 return result
if __name__=='__main__':
 s=analyse();print(json.dumps({k:v for k,v in s.items() if k!='cells'},indent=2))
 for x in s['cells']:
  if x['motor'] in [0,9]:print(x)
