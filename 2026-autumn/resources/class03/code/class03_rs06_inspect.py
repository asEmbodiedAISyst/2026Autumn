"""Offline inspection of the bundled RS06 models; no hardware communication."""
from pathlib import Path
import argparse,json
import mujoco,numpy as np
ROOT=Path(__file__).resolve().parents[1]
def inspect(case):
 path=ROOT/f'preparation/rs06_fixtures/model-sources/{case}.xml'
 m=mujoco.MjModel.from_xml_path(str(path));d=mujoco.MjData(m);d.qpos[0]=.4;d.ctrl[:]=0
 mujoco.mj_forward(m,d);gravity_on=d.qfrc_bias.copy();effort_on=d.qfrc_actuator.copy()
 moving=[]
 for bid in range(1,m.nbody):
  ancestor=bid
  while ancestor:
   if m.body_dofnum[ancestor]>0:moving.append(bid);break
   ancestor=int(m.body_parentid[ancestor])
 m.opt.gravity[:]=0;mujoco.mj_forward(m,d)
 return {'case':case,'model_file':str(path.relative_to(ROOT)),'nq':m.nq,'nv':m.nv,'nu':m.nu,'moving_mass_kg':float(m.body_mass[moving].sum()),'joint_axis_local':m.jnt_axis[0].tolist(),'range_rad':m.jnt_range[0].tolist(),'probe_q_rad':.4,'control_position_rad':0,'gravity_on_bias_Nm':float(gravity_on[0]),'gravity_off_bias_Nm':float(d.qfrc_bias[0]),'actuator_effort_at_zero_position_command_Nm':float(effort_on[0]),'scope':'Model inspection; not measured motion. Zero position command does not mean zero actuator effort.'}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',choices=['M0','B0','B1','G1','all'],default='all');p.add_argument('--output',type=Path);a=p.parse_args();cases=['M0','B0','B1','G1'] if a.case=='all' else [a.case]
 text=json.dumps({'mujoco_version':mujoco.__version__,'models':[inspect(x) for x in cases]},indent=2)
 if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text+'\n')
 print(text)
if __name__=='__main__':main()
