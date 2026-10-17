"""Optional native MuJoCo viewer; no physical actuator access."""
import argparse,time
from pathlib import Path
import numpy as np
import mujoco
import mujoco.viewer
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--model',choices=['weighted','light','pendulum'],default='weighted');p.add_argument('--seconds',type=float,default=10);a=p.parse_args()
 names={'weighted':'XC330withWeightedLever.xml','light':'XC330withLever.xml','pendulum':'pendulum_teaching.xml'}
 m=mujoco.MjModel.from_xml_path(str(ROOT/'models'/names[a.model]));d=mujoco.MjData(m);d.qpos[0]=.4 if a.model=='pendulum' else np.pi;mujoco.mj_forward(m,d)
 with mujoco.viewer.launch_passive(m,d) as viewer:
  start=time.monotonic()
  while viewer.is_running() and time.monotonic()-start<a.seconds:
   tick=time.monotonic()
   if a.model!='pendulum':d.ctrl[0]=np.pi+.2*np.sin(2*np.pi*.2*d.time)
   mujoco.mj_step(m,d);viewer.sync();time.sleep(max(0,m.opt.timestep-(time.monotonic()-tick)))
if __name__=='__main__':main()
