"""Audit the pinned upstream ONNX controller on static first-goal native trials."""
import argparse,ast,hashlib,json,time
from pathlib import Path
import mujoco
import numpy as np
import onnxruntime as rt
from native_task import NativeReorient

ROOT=Path(__file__).resolve().parent
REF=ROOT/'upstream-training-guide'


def controller_class():
    audit=json.loads((REF/'source-audit.json').read_text())
    for name in ('play_leap_reorient.py','leap_reorient_policy.onnx'):
        assert hashlib.sha256((REF/name).read_bytes()).hexdigest()==audit['files'][name]['sha256']
    node=next(n for n in ast.parse((REF/'play_leap_reorient.py').read_text()).body if isinstance(n,ast.ClassDef) and n.name=='OnnxController')
    namespace={'np':np,'mujoco':mujoco,'rt':rt}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(REF/'play_leap_reorient.py'),'exec'),namespace)
    return namespace['OnnxController']


def orientation_error(data):
    cube=data.sensor('cube_orientation').data;goal=data.sensor('cube_goal_orientation').data
    inverse=np.zeros(4);difference=np.zeros(4)
    mujoco.mju_negQuat(inverse,goal);mujoco.mju_mulQuat(difference,cube,inverse)
    difference/=np.linalg.norm(difference)
    return float(2*np.arcsin(np.clip(np.linalg.norm(difference[1:]),0,1)))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sim-dt',type=float,default=.002);p.add_argument('--episodes',type=int,default=10)
    p.add_argument('--seed',type=int,default=9203);p.add_argument('--record',type=Path)
    args=p.parse_args();assert not args.output.exists()
    assert args.sim_dt in (.002,.01) and args.episodes>0
    rt.disable_telemetry_events()
    cls=controller_class();episodes=[];started=time.monotonic()
    for k in range(args.episodes):
        env=NativeReorient();env.mj_model.opt.timestep=args.sim_dt
        state=env.reset_seed(args.seed+k);data=state.data.raw
        mujoco.set_mjcb_control(None);mujoco.mj_forward(env.mj_model,data)
        policy=cls(str(REF/'leap_reorient_policy.onnx'),env._hand_qids,env._hand_dqids,
                   data.ctrl.copy(),env._lowers,env._uppers,int(round(.05/args.sim_dt)))
        assert policy._policy.get_inputs()[0].name=='obs'
        assert policy._policy.get_inputs()[0].shape[-1]==57
        trace=[];frames=[];renderer=None
        if args.record and k==0:
            from PIL import Image,ImageDraw
            renderer=mujoco.Renderer(env.mj_model,height=360,width=640)
            camera=mujoco.MjvCamera();camera.azimuth=120;camera.elevation=-25;camera.distance=.52;camera.lookat[:]=[.1,0,.05]
        initial=orientation_error(data)
        assert abs(initial-float(env._cube_orientation_error(state.data)))<1e-5
        mujoco.set_mjcb_control(policy.get_control)
        try:
            for step in range(1000):
                for _ in range(policy._n_substeps):mujoco.mj_step(env.mj_model,data)
                error=orientation_error(data)
                if not np.isfinite(data.qpos).all() or not np.isfinite(policy._last_action).all():raise ValueError('Nonfinite simulation/action')
                terminated=bool(data.sensor('cube_position').data[2]<-.05)
                success=error<.1
                trace.append(dict(step=step+1,orientation_error_rad=error,success=success,terminated=terminated))
                if renderer and (step%2==0 or success or terminated or step==999):
                    renderer.update_scene(data,camera=camera);frame=Image.fromarray(renderer.render());draw=ImageDraw.Draw(frame)
                    draw.rectangle((0,0,640,54),fill=(12,18,26));draw.text((10,7),'Playground bundled ONNX | native MuJoCo | seed '+str(args.seed),fill='white')
                    draw.text((10,27),f'Step {step+1} | error {error:.3f} rad | target reached {success}',fill='white');frames.append(frame)
                if success or terminated:break
        finally:
            mujoco.set_mjcb_control(None)
            if renderer:renderer.close()
        episode=dict(seed=args.seed+k,steps=step+1,success=success,terminated=terminated,
                     initial_error_rad=initial,final_error_rad=error,min_error_rad=min(x['orientation_error_rad'] for x in trace),
                     engine_warnings=sum(w.number for w in data.warning))
        episodes.append(episode);print(json.dumps(episode),flush=True)
        if frames:
            args.record.parent.mkdir(parents=True,exist_ok=True)
            frames[0].save(args.record.with_suffix('.gif'),save_all=True,append_images=frames[1:],duration=[100]*(len(frames)-1)+[2000],loop=0)
            frames[-1].save(args.record.with_suffix('.png'))
            args.record.with_suffix('.json').write_text(json.dumps(dict(episode=episode,trace=trace),indent=2)+'\n')
    result=dict(scope='Upstream bundled ONNX controller; static first-goal diagnostic, noiseless native-player observations; not our trained policy or full continuous task',
                mujoco=mujoco.__version__,onnxruntime=rt.__version__,physics_dt=args.sim_dt,control_dt=.05,
                policy_sha256=hashlib.sha256((REF/'leap_reorient_policy.onnx').read_bytes()).hexdigest(),
                episodes=episodes,episodes_reaching_goal=sum(e['success'] for e in episodes),wall_seconds=time.monotonic()-started)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('Goals:',result['episodes_reaching_goal'],'/',args.episodes,flush=True)

if __name__=='__main__':main()
