"""Simulation-only deterministic replay example; not policy or hardware validation.
Run from additional_material: python code/replay_state_check.py --out results/replay-state.json
Restores MuJoCo's integration state and replays the same joint targets with identical model and timestep.
"""
from pathlib import Path
import sys,json,argparse
import numpy as np
import mujoco
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'rebot_pusher'))
from rebot_sim.sim import RebotSim
from rebot_sim.robot import PUSHER_HOME_QPOS

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,default=Path('results/replay-state.json'));args=ap.parse_args()
 sim=RebotSim('pusher_push_cube',cameras=());sim.reset(PUSHER_HOME_QPOS)
 for _ in range(30):sim.set_targets(PUSHER_HOME_QPOS);sim.step()
 spec=mujoco.mjtState.mjSTATE_INTEGRATION
 initial=np.empty(mujoco.mj_stateSize(sim.model,spec));mujoco.mj_getState(sim.model,sim.data,initial,spec)
 commands=[PUSHER_HOME_QPOS+np.array([.015*np.sin(k/15),0,0,0,0,0]) for k in range(60)]
 def rollout():
  traj=[]
  for q in commands:sim.set_targets(q);sim.step();traj.append(np.r_[sim.data.qpos.copy(),sim.data.qvel.copy()])
  return np.array(traj)
 first=rollout();mujoco.mj_setState(sim.model,sim.data,initial,spec);second=rollout()
 maximum=float(np.max(np.abs(first-second)))
 report={'scope':'constructed full-integration-state replay with identical MuJoCo model and scripted joint targets; not a policy rollout or hardware comparison','mujoco':mujoco.__version__,'control_steps':60,'duration_s':60*sim.control_dt,'physics_timestep_s':sim.model.opt.timestep,'finite':bool(np.isfinite(first).all()),'max_abs_state_difference':maximum,'passed':bool(np.isfinite(first).all() and maximum<1e-12)}
 args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));sim.close()
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()
