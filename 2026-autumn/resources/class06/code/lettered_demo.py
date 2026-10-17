"""Pretrained ONNX policy on the pinned continuous native task; no training/hardware."""
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
import mujoco
import onnxruntime as rt
from lettered_cube import make_env, physics_contract, FACE_LETTERS
from test_upstream_onnx import ROOT, REF, controller_class

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seed',type=int,default=9203)
    p.add_argument('--episodes',type=int,default=5)
    p.add_argument('--steps',type=int,default=1000)
    p.add_argument('--variant',choices=['reference','letters'],default='letters')
    p.add_argument('--record',action='store_true')
    p.add_argument('--viewer',action='store_true')
    p.add_argument('--noise-level',type=float,choices=[0.,1.],default=1.)
    args=p.parse_args()
    if args.output.exists():p.error('Use a fresh output directory; existing evidence is preserved.')
    if not 1<=args.steps<=1000 or args.episodes<1:p.error('steps must be 1..1000 and episodes positive')
    args.output.mkdir(parents=True)
    rt.disable_telemetry_events();mujoco.set_mjcb_control(None)
    cls=controller_class();env=make_env(args.variant=='letters',args.noise_level)
    original=make_env(False,args.noise_level)
    contract=physics_contract(original.mj_model,env.mj_model)
    frames=[];results=[];traces=[];renderer=None;view=None
    if args.record:
        from PIL import Image
        renderer=mujoco.Renderer(env.mj_model,height=360,width=640)
        camera=mujoco.MjvCamera();camera.azimuth=120;camera.elevation=-25;camera.distance=.52;camera.lookat[:]=[.15,.04,.06]
    started=time.monotonic()
    try:
        for k in range(args.episodes):
            seed=args.seed+k;state=env.reset_seed(seed)
            policy=cls(str(REF/'leap_reorient_policy.onnx'),env._hand_qids,env._hand_dqids,
                       state.data.raw.ctrl.copy(),env._lowers,env._uppers,env.n_substeps)
            assert policy._policy.get_inputs()[0].shape[-1]==57
            if args.viewer:
                from mujoco import viewer as native_viewer
                if view:view.close()
                view=native_viewer.launch_passive(env.mj_model,state.data.raw)
                view.cam.azimuth=120;view.cam.elevation=-25;view.cam.distance=.52;view.cam.lookat[:]=[.15,.04,.06]
            trace=[];goals=0;total_return=0.;min_error=float('inf')
            for step in range(args.steps):
                tick=time.monotonic()
                # Use upstream task observations (including noise/history), not
                # the player's noiseless sensor reconstruction. ONNX contains
                # its preprocessing; no extra external normalization is applied.
                obs=np.asarray(state.obs['state'],dtype=np.float32).reshape(1,57)
                action=policy._policy.run(policy._output_names,{'obs':obs})[0][0]
                if not np.isfinite(action).all():raise ValueError('Nonfinite action')
                previous_goal=state.data.raw.mocap_quat[0].copy()
                state=env.step(state,action)
                data=state.data.raw
                if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():raise ValueError('Nonfinite state')
                success=bool(float(state.metrics['reward/success']))
                goals+=success;total_return+=float(state.reward)
                # Measure against the goal used for this action, before upstream
                # goal motion. A diagnostic forward pass uses a separate data.
                diagnostic=mujoco.MjData(env.mj_model);mujoco.mj_copyData(diagnostic,env.mj_model,data)
                diagnostic.mocap_quat[0]=previous_goal;mujoco.mj_forward(env.mj_model,diagnostic)
                cube=diagnostic.sensor('cube_orientation').data
                render_error=float(2*np.arccos(np.clip(abs(np.dot(cube,previous_goal)),0.,1.)))
                error=float(env._cube_orientation_error(state.data))
                min_error=min(min_error,error)
                row={'seed':seed,'step':step+1,'goal_event':success,'goals':goals,'orientation_error_rad':error,
                     'render_pose_error_rad':render_error,'done':bool(state.done),'reward':float(state.reward),'goal_quat_wxyz':previous_goal.tolist(),
                     'next_goal_quat_wxyz':data.mocap_quat[0].tolist(),'action':np.asarray(action).tolist(),
                     'cube_position':data.qpos[env._cube_qids[:3]].tolist()}
                trace.append(row)
                if (step+1)%200==0:print(f'seed {seed}: step {step+1}, goals {goals}, error {error:.3f}',flush=True)
                if renderer and k==0 and step%4==0:
                    # Forward only render copy: never overwrite the task's
                    # sensordata semantics during model stepping.
                    render_data=mujoco.MjData(env.mj_model);mujoco.mj_copyData(render_data,env.mj_model,data);mujoco.mj_forward(env.mj_model,render_data)
                    renderer.update_scene(render_data,camera=camera)
                    frame=Image.fromarray(renderer.render())
                    # Keep the scene unobscured; metrics are saved in trace.jsonl.
                    frames.append(frame)
                if view:
                    if not view.is_running():break
                    # Passive viewer owns its original data allocation; copy
                    # updated state into it for display without changing state.
                    with view.lock():
                        mujoco.mj_copyData(view.d,env.mj_model,data)
                        mujoco.mj_forward(env.mj_model,view.d)
                    view.sync();time.sleep(max(0.,env.dt-(time.monotonic()-tick)))
                if bool(state.done):break
            result={'seed':seed,'steps':step+1,'goals':goals,'fall_or_nonfinite_termination':bool(state.done),
                    'timeout':not bool(state.done) and step+1==args.steps,'return':total_return,
                    'min_goal_error_rad':min_error,'engine_warnings':sum(w.number for w in state.data.raw.warning)}
            results.append(result);traces.extend(trace);print(json.dumps(result),flush=True)
    finally:
        if renderer:renderer.close()
        if view:view.close()
    with (args.output/'trace.jsonl').open('w') as f:
        for row in traces:f.write(json.dumps(row,allow_nan=False)+'\n')
    if frames:
        frames[0].save(args.output/'demo.gif',save_all=True,append_images=frames[1:],duration=200,loop=0)
        frames[0].save(args.output/'preview.png');frames[-1].save(args.output/'final.png')
    summary={'scope':'Pinned changing-goal Playground task using native MuJoCo; ONNX supplied upstream, no training or domain randomization',
             'variant':args.variant,'face_letters':FACE_LETTERS,'noise_level':args.noise_level,
             'physics_dt':env.sim_dt,'control_dt':env.dt,'physics_contract':contract,
             'policy_sha256':hashlib.sha256((REF/'leap_reorient_policy.onnx').read_bytes()).hexdigest(),
             'playground_commit':json.loads((ROOT/'provenance.json').read_text())['playground_commit'],
             'versions':{'mujoco':mujoco.__version__,'onnxruntime':rt.__version__},
             'episodes':results,'episodes_with_goal':sum(x['goals']>0 for x in results),
             'total_goals':sum(x['goals'] for x in results),'wall_seconds':time.monotonic()-started}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__':main()
