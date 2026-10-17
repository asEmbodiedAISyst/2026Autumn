"""Offline recorded-data analysis and native MuJoCo replay for Classes 02–04.
No hardware interfaces. Run from any directory; paths resolve against this file.
"""
import argparse, json, hashlib, platform, sys
from pathlib import Path
import numpy as np
import mujoco
ROOT=Path(__file__).resolve().parents[1]
def load(test,mid):
 a=np.genfromtxt(ROOT/f'data/xc330/{test}_id{mid}.csv',delimiter=',',names=True,dtype=float)
 if not np.isfinite(np.column_stack([a[k] for k in ('time','goal_deg','pos_deg')])).all():raise ValueError('Nonfinite CSV values')
 # Timestamps restart at each amplitude/frequency block; replay resets each block.
 for i in np.where(np.diff(a['time'])<=0)[0]:
  key='freq_hz' if 'freq_hz' in a.dtype.names else 'amplitude'
  if key not in a.dtype.names or a[key][i]==a[key][i+1]:raise ValueError('Unexpected timestamp reset')
 return a

def replay(a,mid,tau=0.,delay=0.,mass_scale=1.,armature_scale=1.):
 cuts=np.where(np.diff(a['time'])<=0)[0]+1
 if len(cuts):return np.concatenate([replay(block,mid,tau,delay,mass_scale,armature_scale) for block in np.split(a,cuts)])
 model=mujoco.MjModel.from_xml_path(str(ROOT/'models'/('XC330withWeightedLever.xml' if mid==1 else 'XC330withLever.xml')))
 model.dof_armature[:]*=armature_scale
 if mass_scale!=1:
  for bid in range(1,model.nbody):
   if model.body_parentid[bid]>0:
    model.body_mass[bid]*=mass_scale; model.body_inertia[bid]*=mass_scale
  mujoco.mj_setConst(model,mujoco.MjData(model))
 d=mujoco.MjData(model); d.qpos[0]=np.deg2rad(a['pos_deg'][0]); ref=np.deg2rad(a['goal_deg'][0]); d.ctrl[0]=ref
 mujoco.mj_forward(model,d)
 t=a['time']-a['time'][0]; goals=np.deg2rad(a['goal_deg']); dt=model.opt.timestep
 count=int(np.ceil(t[-1]/dt))+1; qt=np.zeros(count); times=np.arange(count)*dt
 j=0
 for k in range(count):
  qt[k]=d.qpos[0]
  while j+1<len(t) and t[j+1]<=d.time-delay+1e-12:j+=1
  if tau>0:ref+=(1-np.exp(-dt/tau))*(goals[j]-ref)
  else:ref=goals[j]
  d.ctrl[0]=ref; d.ctrl[1:]=0.; mujoco.mj_step(model,d)
 q=np.rad2deg(np.interp(t,times,qt))
 if not np.isfinite(q).all():raise ValueError('Unstable replay')
 return q

def response(a,q):
 frequencies=np.unique(a['freq_hz']); H=[]
 for f in frequencies:
  ix=np.flatnonzero(np.isclose(a['freq_hz'],f)); t=a['time'][ix]-a['time'][ix[0]]
  keep=t>=1/f; ix=ix[keep]; t=t[keep]
  if len(ix)<10:raise ValueError('Insufficient cycles')
  X=np.column_stack([np.sin(2*np.pi*f*t),np.cos(2*np.pi*f*t),np.ones(len(t))])
  c=np.linalg.lstsq(X,a['goal_deg'][ix],rcond=None)[0]; y=np.linalg.lstsq(X,q[ix],rcond=None)[0]
  H.append((y[0]+1j*y[1])/(c[0]+1j*c[1]))
 return frequencies,np.array(H)

def fit_response(f,base,real):
 # Deterministic bounded grid with four local refinements. Sine data only.
 lo=np.array([0.,0.]); hi=np.array([.2,.1]); best=None
 for level in range(5):
  taus=np.linspace(lo[0],hi[0],61); delays=np.linspace(lo[1],hi[1],61)
  pred=base[None,None,:]/(1+1j*2*np.pi*f[None,None,:]*taus[:,None,None])*np.exp(-1j*2*np.pi*f[None,None,:]*delays[None,:,None])
  costs=np.mean(abs(pred-real)**2,axis=2); i,j=np.unravel_index(np.argmin(costs),costs.shape)
  best=np.array([taus[i],delays[j]]); step=(hi-lo)/60
  lo=np.maximum([0.,0.],best-2*step);hi=np.minimum([.2,.1],best+2*step)
 return {'tau_s':float(best[0]),'delay_s':float(best[1]),'frequency_complex_rmse':float(np.sqrt(costs[i,j])),'boundary_hit':bool(best[0]<1e-6 or best[0]>.199999 or best[1]<1e-6 or best[1]>.099999)}

def inspect_models():
 out={}
 for mid in (1,2):
  m=mujoco.MjModel.from_xml_path(str(ROOT/'models'/('XC330withWeightedLever.xml' if mid==1 else 'XC330withLever.xml')));d=mujoco.MjData(m);d.qpos[0]=np.pi;mujoco.mj_forward(m,d)
  M=np.zeros((m.nv,m.nv));mujoco.mj_fullM(m,M,d.qM)
  moving=[b for b in range(1,m.nbody) if m.body_parentid[b]>0]
  out[str(mid)]={'nq':m.nq,'nv':m.nv,'nu':m.nu,'timestep_s':m.opt.timestep,'joint_axis_local':m.jnt_axis[0].tolist(),'moving_mass_kg':float(m.body_mass[moving].sum()),'generalized_inertia_kg_m2':float(M[0,0]),'armature_kg_m2':float(m.dof_armature[0]),'bias_at_pi_Nm':float(d.qfrc_bias[0]),'kp_Nm_per_rad':float(m.actuator_gainprm[0,0]),'kv_Nm_s_per_rad':float(-m.actuator_biasprm[0,2]),'contacts_enabled':bool(np.any(m.geom_contype))}
 return out

def analyse():
 out={}
 for mid in (1,2):
  s=load('step',mid);a=load('sine',mid);dt=np.diff(s['time']);dt=dt[dt>0]
  f,h=response(a,a['pos_deg'])
  out[str(mid)]={'step_samples':len(s),'median_interval_s':float(np.median(dt)),'max_interval_s':float(dt.max()),'tracking_rmse_step_deg':float(np.sqrt(np.mean((s['pos_deg']-s['goal_deg'])**2))),'frequency_hz':f.tolist(),'gain_db':(20*np.log10(abs(h))).tolist(),'phase_lag_deg':(-np.rad2deg(np.angle(h))).tolist()}
 return out

def identify():
 out={}; arrays={}
 for mid in (1,2):
  a=load('sine',mid);b=replay(a,mid);f,real=response(a,a['pos_deg']);_,base=response(a,b);fit=fit_response(f,base,real)
  fit['baseline_frequency_complex_rmse']=float(np.sqrt(np.mean(abs(base-real)**2)))
  metrics={}
  for test in ('step','chirp'):
   a=load(test,mid);b=replay(a,mid);q=replay(a,mid,fit['tau_s'],fit['delay_s'])
   br=float(np.sqrt(np.mean((b-a['pos_deg'])**2)));qr=float(np.sqrt(np.mean((q-a['pos_deg'])**2)))
   metrics[test]={'baseline_rmse_deg':br,'corrected_rmse_deg':qr,'reduction_pct':100*(br-qr)/br,'samples':len(a)}
   arrays[f'{test}_{mid}_baseline']=b;arrays[f'{test}_{mid}_corrected']=q
  out[str(mid)]={'fit_sine_only':fit,'frozen_validation':metrics}
 np.savez(ROOT/'results/replay.npz',**arrays)
 return out

def sensitivity():
 a=load('chirp',1);rows=[]
 for ms,ars in [(1.,1.),(2.,1.),(1.,2.),(1.,.5)]:
  q=replay(a,1,mass_scale=ms,armature_scale=ars)
  rows.append({'moving_mass_scale':ms,'armature_scale':ars,'chirp_rmse_deg':float(np.sqrt(np.mean((q-a['pos_deg'])**2)))})
 return rows

def manifest():
 files={}
 for directory in ('data','models','source/fonts','code'):
  for p in sorted((ROOT/directory).rglob('*')):
   if p.is_file() and '__pycache__' not in str(p):files[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
 return {'files':files,'python':platform.python_version(),'numpy':np.__version__,'mujoco':mujoco.__version__,'platform':platform.platform()}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('task',choices=['analyse','inspect','identify','sensitivity','all']);args=ap.parse_args();(ROOT/'results').mkdir(exist_ok=True)
 result={}
 for name,fn in [('analyse',analyse),('inspect',inspect_models),('identify',identify),('sensitivity',sensitivity)]:
  if args.task in ('all',name):result[name]=fn();(ROOT/'results'/f'{name}.json').write_text(json.dumps(result[name],indent=2));print(name,json.dumps(result[name])[:400])
 (ROOT/'MANIFEST.json').write_text(json.dumps(manifest(),indent=2))
 (ROOT/'evidence/environment.json').write_text(json.dumps(manifest()|{'task':args.task},indent=2))
 return 0
if __name__=='__main__':sys.exit(main())
