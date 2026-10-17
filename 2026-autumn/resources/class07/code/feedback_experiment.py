"""Native simulation diagnostic: delay/drop only nine pose-error feature values.
This is not image tracking or hardware control. Requires adjacent Class06/code.
Packet error features include the goal at capture; delayed goals are deliberately
not recomputed. Preserve this boundary when interpreting the experiment.
"""
from pathlib import Path
import argparse,json,sys,hashlib
import numpy as np
P=argparse.ArgumentParser(description=__doc__)
P.add_argument('--class06-code',type=Path,default=Path(__file__).resolve().parents[2]/'class06/code')
P.add_argument('--output',type=Path,required=True);P.add_argument('--seed',type=int,default=9204)
P.add_argument('--steps',type=int,default=1000);P.add_argument('--delay-steps',type=int,default=0)
P.add_argument('--dropout',type=float,default=0);P.add_argument('--noise-level',type=float,choices=[0.,1.],default=0.)

def run(args):
 if args.output.exists():raise ValueError('Use a fresh output directory')
 if not 1<=args.steps<=1000 or args.delay_steps<0 or not 0<=args.dropout<1:raise ValueError('Invalid experiment settings')
 sys.path.insert(0,str(args.class06_code.resolve()))
 import mujoco,onnxruntime as rt
 from lettered_cube import make_env
 from test_upstream_onnx import controller_class,REF
 rt.disable_telemetry_events();mujoco.set_mjcb_control(None)
 env=make_env(True,args.noise_level);state=env.reset_seed(args.seed)
 policy=controller_class()(str(REF/'leap_reorient_policy.onnx'),env._hand_qids,env._hand_dqids,state.data.raw.ctrl.copy(),env._lowers,env._uppers,env.n_substeps)
 rng=np.random.default_rng(args.seed+70000);packets=[];last=None;capture_step=0;rows=[];first=None
 for i in range(args.steps):
  obs=np.asarray(state.obs['state'],dtype=np.float32).copy();packets.append(obs[32:41].copy());source=max(0,i-args.delay_steps)
  dropped=i>0 and rng.random()<args.dropout
  if last is None or not dropped:last=packets[source].copy();capture_step=source
  delivered=obs.copy();delivered[32:41]=last
  assert np.array_equal(delivered[:32],obs[:32]) and np.array_equal(delivered[41:],obs[41:])
  action=policy._policy.run(policy._output_names,{'obs':delivered.reshape(1,57)})[0][0]
  assert np.isfinite(action).all();state=env.step(state,action)
  success=bool(float(state.metrics['reward/success']));error=float(env._cube_orientation_error(state.data))
  if success and first is None:first=(i+1)*.05
  row=dict(step=i+1,time_s=(i+1)*.05,error_rad=error,goal_event=success,feature_age_s=(i-capture_step)*.05,dropped=bool(dropped),feature_difference_l2=float(np.linalg.norm(delivered[32:41]-obs[32:41])),action=np.asarray(action).tolist())
  rows.append(row)
  if bool(state.done):break
 assert np.isfinite(state.data.raw.qpos).all()
 args.output.mkdir(parents=True)
 (args.output/'trace.jsonl').write_text(''.join(json.dumps(x,allow_nan=False)+'\n' for x in rows))
 summary=dict(scope='Single-seed simulated pose-error packet diagnostic; no image estimator, training, hardware or reliability qualification',seed=args.seed,steps=len(rows),delay_steps=args.delay_steps,dropout_probability=args.dropout,dropout_rng_seed=args.seed+70000,noise_level=args.noise_level,first_goal_time_s=first,goal_events=sum(x['goal_event'] for x in rows),dropped_packets=sum(x['dropped'] for x in rows),max_feature_age_s=max(x['feature_age_s'] for x in rows),fall=bool(state.done),engine_warnings=sum(w.number for w in state.data.raw.warning),pose_channels='obs[32:41]; position and orientation error at capture, including capture-time goal',drop_policy='hold last delivered packet; first packet always valid; delayed startup uses first packet',versions=dict(mujoco=mujoco.__version__,onnxruntime=rt.__version__),policy_sha256=hashlib.sha256((REF/'leap_reorient_policy.onnx').read_bytes()).hexdigest())
 (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':run(P.parse_args())
