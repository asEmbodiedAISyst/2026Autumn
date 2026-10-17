"""Class08 inspection and a reproducible smooth joint2 trace; simulation only."""
from pathlib import Path
import sys,argparse,json,csv
import numpy as np
import mujoco
ROOT=Path(__file__).resolve().parents[1]
from controlled_motion import ArmSim,HOME_QPOS,SOFT_LIMITS_DEG,cosine_profile

def inspect():
 sim=ArmSim();m=sim.model;rows=[]
 for i in range(6):
  j=m.joint(f'joint{i+1}');rows.append({'name':j.name,'model_range_rad':j.range.tolist(),'model_range_deg':np.degrees(j.range).tolist(),'software_motor_limit_deg':list(SOFT_LIMITS_DEG[i]),'home_rad':float(HOME_QPOS[i]),'home_deg':float(np.degrees(HOME_QPOS[i]))})
 home=sim.tcp_pos().tolist();sim.reset(np.zeros(6));zero=sim.tcp_pos().tolist()
 return {'nq':m.nq,'nv':m.nv,'nu':m.nu,'joints':rows,'home_tcp_m':home,'zero_tcp_m':zero,'control_hz':30,'physics_timestep_s':m.opt.timestep,'substeps':sim.n_sub,'control_period_s':sim.n_sub*m.opt.timestep,'scope':'compiled simulation only; motor limits are supplied code declarations'}

def trace(out):
 sim=ArmSim();i=1;home=HOME_QPOS[i];amp=np.radians(10);rows=[];n=45
 for sign in [1,-1]:
  for value in np.r_[cosine_profile(home,home+sign*amp,n),cosine_profile(home+sign*amp,home,n)]:
   q=HOME_QPOS.copy();q[i]=value
   rows.append([sim.data.time,np.degrees(value),np.degrees(sim.q()[i])]);sim.command(q);sim.step()
 out.parent.mkdir(parents=True,exist_ok=True)
 with out.open('w',newline='') as f:w=csv.writer(f);w.writerow(['time_s','target_deg','pre_step_position_deg']);w.writerows(rows)
 return {'frames':len(rows),'max_pre_step_tracking_error_deg':float(np.max(np.abs(np.array(rows)[:,1]-np.array(rows)[:,2]))),'scope':'smooth joint2 simulation, target and measured state aligned before each step'}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('mode',choices=['inspect','trace']);ap.add_argument('--out',type=Path);a=ap.parse_args()
 if a.mode=='inspect':
  report=inspect();p=a.out or ROOT/'results/inspection.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,indent=2)+'\n')
 else:report=trace(a.out or ROOT/'results/joint2-trace.csv')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
