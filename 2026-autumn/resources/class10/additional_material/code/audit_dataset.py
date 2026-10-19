"""Audit a supplied LeRobot v3 sample without training or robot drivers.

Run from additional_material (after uv sync): uv run python code/audit_dataset.py data/pilot_push_cube_handheld --json outputs/pilot-audit.json
A final recorded distance below 0.015m is a geometric snapshot check, not a complete rollout verdict.
Visibility, orientation quality and IK reachability require separate evidence. A successful task is not automatically an acceptable demonstration.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

SUCCESS_DIST=0.015
MAX_TOOL_SPEED=0.25
MAX_JOINT_SPEED=180.0

def audit(root:Path)->dict:
 info=json.loads((root/'meta/info.json').read_text());fps=info['fps'];features=info['features']
 files=sorted((root/'data').glob('chunk-*/file-*.parquet'))
 if not files:raise ValueError('No data parquet files in the declared dataset')
 df=pd.concat([pq.read_table(f).to_pandas() for f in files],ignore_index=True)
 tool=features['action']['names'][:3]==['x','y','z'];rows=[]
 for ep,g in df.sort_values(['episode_index','frame_index']).groupby('episode_index'):
  ts=g.timestamp.to_numpy();a=np.stack(g.action.to_numpy());s=np.stack(g['observation.state'].to_numpy());notes=[]
  shape_ok=(a.shape[1:]==tuple(features['action']['shape']) and s.shape[1:]==tuple(features['observation.state']['shape']))
  finite=bool(np.isfinite(a).all() and np.isfinite(s).all() and np.isfinite(ts).all())
  dt_ok=bool(len(ts)>1 and np.allclose(np.diff(ts),1/fps,atol=1e-4))
  if not shape_ok:notes.append('feature dimension mismatch')
  if not finite:notes.append('nonfinite state/action/timestamp')
  if not dt_ok:notes.append('timestamp step irregular or insufficient frames')
  diff=np.diff(a[:,:3] if tool else a[:,:6],axis=0)*fps
  speed=float(np.linalg.norm(diff,axis=1).max()) if tool and len(a)>1 else float(np.abs(diff).max()) if len(a)>1 else 0.0
  if speed>(MAX_TOOL_SPEED if tool else MAX_JOINT_SPEED)*1.05:notes.append('command speed exceeds declared limit')
  dist=None;geometric=None
  if 'observation.environment_state' in g:
   e=np.asarray(g['observation.environment_state'].iloc[-1]);dist=float(np.linalg.norm(e[:2]-e[3:5]));geometric=dist<SUCCESS_DIST
   if not geometric:notes.append('last recorded frame outside 15mm goal radius')
  if len(g)<30:notes.append('very short episode')
  rows.append({'episode_index':int(ep),'frames':len(g),'duration_s':float(ts[-1]-ts[0]),'dt_ok':dt_ok,'shape_ok':shape_ok,'finite':finite,'peak_command_speed':speed,'speed_unit':'m/s' if tool else 'deg/s','final_recorded_distance_m':dist,'inside_15mm_at_last_recorded_frame':geometric,'notes':notes,'visibility':'not assessed','reachability':'not assessed','acceptance':'requires image and reachability review'})
 return {'dataset':root.name,'fps':fps,'actual_frames':len(df),'declared_frames':info['total_frames'],'frame_count_matches':len(df)==info['total_frames'],'episode_count_matches':len(rows)==info['total_episodes'],'geometric_threshold_m':SUCCESS_DIST,'episodes':rows,'scope':'metadata, sampled timing, feature dimensions, finiteness, command speed and final recorded distance; not physical validity or full demonstration acceptance'}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('root',type=Path);ap.add_argument('--json',type=Path);args=ap.parse_args();report=audit(args.root)
 print(f"dataset {report['dataset']}: {len(report['episodes'])} episodes, {report['actual_frames']} frames, nominal {report['fps']}Hz")
 for row in report['episodes']:print(f"ep{row['episode_index']:02}: {row['frames']}frames; dt_ok={row['dt_ok']}; {row['peak_command_speed']:.3f}{row['speed_unit']}; inside15mm={row['inside_15mm_at_last_recorded_frame']}; {'; '.join(row['notes'])}")
 print('Visibility and reachability are NOT assessed; geometric success alone does not accept a demonstration.')
 if args.json:args.json.parent.mkdir(parents=True,exist_ok=True);args.json.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
