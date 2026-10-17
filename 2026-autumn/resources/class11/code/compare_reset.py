"""Controlled simulation replay: integration-state versus deliberately incomplete qpos-only reset.
The initial cube velocity is +0.20m/s in base x. No policy, cameras or powered hardware.
"""
from pathlib import Path
import sys,json,csv,argparse
import numpy as np
import mujoco
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'consolidation/package/additional_material/rebot_pusher'))
from rebot_sim.sim import RebotSim
from rebot_sim.robot import PUSHER_HOME_QPOS

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,default=ROOT/'results/reset-comparison.json');a=ap.parse_args()
 sim=RebotSim('pusher_push_cube',cameras=());sim.reset(PUSHER_HOME_QPOS)
 try:
  for _ in range(30):sim.set_targets(PUSHER_HOME_QPOS);sim.step()
  jid=sim.model.joint('cube_joint').id;qa=int(sim.model.jnt_qposadr[jid]);va=int(sim.model.jnt_dofadr[jid]);sim.data.qvel[va]=.20
  spec=mujoco.mjtState.mjSTATE_INTEGRATION;initial=np.empty(mujoco.mj_stateSize(sim.model,spec));mujoco.mj_getState(sim.model,sim.data,initial,spec);qpos=sim.data.qpos.copy()
  commands=[PUSHER_HOME_QPOS+np.array([.015*np.sin(k/15),0,0,0,0,0]) for k in range(60)]
  def run():
   xy=[]
   for q in commands:sim.set_targets(q);sim.step();xy.append(sim.data.qpos[qa:qa+2].copy())
   return np.array(xy)
  reference=run();mujoco.mj_setState(sim.model,sim.data,initial,spec);full=run()
  mujoco.mj_resetData(sim.model,sim.data);sim.data.qpos[:]=qpos;mujoco.mj_forward(sim.model,sim.data);partial=run()
  ef=np.linalg.norm(full-reference,axis=1);ep=np.linalg.norm(partial-reference,axis=1)
  report={'scope':'constructed replay reset experiment in the same simulator; no policy or hardware claim','mujoco':mujoco.__version__,'steps':60,'duration_s':60*sim.control_dt,'initial_cube_vx_m_per_s':.20,'full_restore_max_cube_xy_difference_m':float(ef.max()),'qpos_only_max_cube_xy_difference_m':float(ep.max()),'interpretation':'qpos-only comparison omits velocity and other integration state; state-completeness contrast, not friction identification'}
  assert np.isfinite(reference).all() and np.isfinite(partial).all();assert ef.max()<1e-12;assert ep.max()>1e-6
  a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n')
  with a.out.with_suffix('.csv').open('w',newline='') as f:
   out=csv.writer(f);out.writerow(['time_s','full_restore_cube_xy_error_mm','qpos_only_cube_xy_error_mm']);out.writerows(zip(np.arange(1,61)*sim.control_dt,ef*1000,ep*1000))
  print(json.dumps(report,indent=2))
 finally:sim.close()
if __name__=='__main__':main()
