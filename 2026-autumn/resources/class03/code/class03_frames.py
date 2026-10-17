from pathlib import Path
import argparse,json,sys
import numpy as np,mujoco
ROOT=Path(__file__).resolve().parents[1]
def trace(model_path,q_deg):
 m=mujoco.MjModel.from_xml_path(str(model_path));d=mujoco.MjData(m)
 lid=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,'Link');pid=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,'Pin_1')
 jid=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_JOINT,'actuator_joint')
 d.qpos[0]=0;mujoco.mj_forward(m,d);rotation_zero=d.xmat[lid].reshape(3,3).copy();anchor=d.xanchor[jid].copy()
 p=m.body_pos[pid].copy();j=m.jnt_pos[jid].copy();axis=m.jnt_axis[jid].copy();axis/=np.linalg.norm(axis)
 theta=np.deg2rad(q_deg);cross=np.array([[0,-axis[2],axis[1]],[axis[2],0,-axis[0]],[-axis[1],axis[0],0]])
 rotation=np.eye(3)*np.cos(theta)+(1-np.cos(theta))*np.outer(axis,axis)+np.sin(theta)*cross
 predicted=anchor+rotation_zero@rotation@(p-j)
 d.qpos[0]=theta;mujoco.mj_forward(m,d);actual=d.xpos[pid].copy();assert np.allclose(actual,predicted,atol=1e-12)
 return {'q_deg':q_deg,'q_rad':theta,'point_in_Link_m':p.tolist(),'joint_in_Link_m':j.tolist(),'joint_anchor_world_m':anchor.tolist(),'point_world_calculated_m':predicted.tolist(),'point_world_MuJoCo_m':actual.tolist(),'position_error_m':float(np.linalg.norm(actual-predicted)),'scope':'Declared model coordinates, not hardware measurements'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--q-deg',type=float,default=30);p.add_argument('--model',type=Path,default=ROOT/'consolidation/additional_material/models/1DOF-B2.xml');p.add_argument('--output',type=Path);args=p.parse_args()
 result={'mujoco_version':mujoco.__version__,'trace':trace(args.model,args.q_deg)};txt=json.dumps(result,indent=2)
 if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(txt+'\n')
 print(txt)
if __name__=='__main__':main()
