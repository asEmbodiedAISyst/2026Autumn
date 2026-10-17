"""Class09 mapped-pose arithmetic and recorded-stream inspection; no phone required."""
from pathlib import Path
import csv,json,argparse,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'consolidation/package/additional_material/code'))
from teleop_common import PhoneMapper

def audit(p):
 rows=list(csv.DictReader(p.open()));t=np.array([float(x['timestamp']) for x in rows]);dt=np.diff(t);a=np.array([[float(row[k]) for k in row if k.startswith('action.')] for row in rows]);s=np.array([[float(row[k]) for k in row if k.startswith('state.')] for row in rows])
 return {'source':str(p.name),'frames':len(rows),'state_dimension':s.shape[1],'action_dimension':a.shape[1],'finite':bool(np.isfinite(a).all() and np.isfinite(s).all()),'monotonic':bool((dt>0).all()),'duration_s':float(t[-1]-t[0]),'effective_hz':float((len(t)-1)/(t[-1]-t[0])),'median_dt_s':float(np.median(dt)),'max_dt_s':float(dt.max()),'nominal_hz':30,'scope':'stored simulation recording, wall-clock timing; seven state/action channels have different sign/scale semantics'}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('mode',choices=['mapping','audit']);ap.add_argument('--recording',type=Path,default=ROOT/'data/recorded/circle/frames.csv');a=ap.parse_args()
 if a.mode=='audit':report=audit(a.recording)
 else:
  m=PhoneMapper(1,True);m.engage(np.zeros(3),np.eye(3),np.array([.25,0,.10]),np.eye(3));p,R=m.map(np.array([.01,.02,0]),np.eye(3));report={'declared_example':'identity initial phone and robot orientations; first filter sample','phone_displacement_m':[.01,.02,0],'target_m':p.tolist(),'target_rotation':R.tolist()}
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
