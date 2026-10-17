"""First-goal qualification of a pinned ONNX policy across physics backends."""
import argparse, hashlib, importlib.metadata, json, math, os, subprocess, sys, time
from pathlib import Path
import numpy as np
import mujoco
import onnxruntime as rt
ROOT=Path(__file__).resolve().parent


def wilson(k,n):
    z=1.959963984540054
    center=(k/n+z*z/(2*n))/(1+z*z/n)
    half=z*math.sqrt((k/n)*(1-k/n)/n+z*z/(4*n*n))/(1+z*z/n)
    return [max(0.,center-half),min(1.,center+half)]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend',choices=['native-task','native-player','playground'],required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--upstream-dir',type=Path,default=ROOT/'upstream')
    p.add_argument('--seed',type=int,default=20000)
    p.add_argument('--episodes',type=int,default=100)
    p.add_argument('--steps',type=int,default=1000)
    p.add_argument('--sim-dt',type=float,choices=[.002,.01],default=.01)
    p.add_argument('--noise-level',type=float,choices=[0.,1.],default=0.)
    a=p.parse_args()
    if sys.prefix==sys.base_prefix:p.error('Use an isolated virtual environment.')
    if a.output.exists():p.error('Use a fresh output directory.')
    if a.episodes<1 or not 1<=a.steps<=1000:p.error('Invalid episode or step count.')
    if a.backend=='native-player' and a.noise_level!=0:p.error('The upstream player has ideal observations only.')
    a.output.mkdir(parents=True)
    rt.disable_telemetry_events();mujoco.set_mjcb_control(None)
    policy_file=ROOT/'upstream-training-guide/leap_reorient_policy.onnx'
    audit=json.loads((ROOT/'upstream-training-guide/source-audit.json').read_text())
    assert hashlib.sha256(policy_file.read_bytes()).hexdigest()==audit['files'][policy_file.name]['sha256']
    policy=rt.InferenceSession(str(policy_file),providers=['CPUExecutionProvider'])
    config={'backend':a.backend,'seed':a.seed,'episodes':a.episodes,'steps':a.steps,
            'sim_dt':a.sim_dt,'control_dt':.05,'noise_level':a.noise_level,'success_threshold_rad':.1,
            'policy_sha256':hashlib.sha256(policy_file.read_bytes()).hexdigest(),
            'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'playground_commit':json.loads((ROOT/'provenance.json').read_text())['playground_commit'],
            'metric':'first target reached within episode; stops at first success, upstream task fall or time limit',
            'versions':{n:importlib.metadata.version(n) for n in ('mujoco','mujoco-mjx','jax','onnxruntime')},
            'native_adaptation':'native-task and native-player use identical original task random reset distribution; player observations/control callback are supplied upstream',
            'scope':'evaluation only; no training, model randomization, hardware or success-threshold relaxation'}
    (a.output/'configuration.json').write_text(json.dumps(config,indent=2)+'\n')
    if a.backend=='playground':
        assert sys.platform.startswith('linux'),'Original GPU route runs on Linux.'
        import jax
        import warp as wp
        if os.environ.get('CLASS06_CACHE_DIR'):
            wp.config.kernel_cache_dir=str(Path(os.environ['CLASS06_CACHE_DIR'])/'warp')
        import jax.numpy as jp
        source=a.upstream_dir.resolve()
        sys.path.insert(0,str(source))
        from mujoco_playground import registry
        actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
        assert actual==config['playground_commit'],'Playground pin mismatch.'
        assert not subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no'],text=True),'Modified upstream source.'
        import mujoco_playground
        assert source.resolve() in Path(mujoco_playground.__file__).resolve().parents,'Wrong Playground import path.'
        assert any(d.platform=='gpu' for d in jax.devices()),'GPU required for reference test.'
        env=registry.load('LeapCubeReorient',config_overrides={'impl':'warp','sim_dt':a.sim_dt,'obs_noise.level':a.noise_level,'njmax':512,'naconmax':16384})
        # Check that the installed original task compiles the pinned physical model.
        from native_task import NativeReorient
        reference=NativeReorient(noise_level=a.noise_level)
        fields=('body_mass','body_inertia','body_ipos','body_iquat','body_pos','body_quat',
                'dof_armature','dof_damping','dof_frictionloss','jnt_type','jnt_pos','jnt_axis','jnt_range',
                'actuator_gainprm','actuator_biasprm','actuator_ctrlrange','actuator_forcerange',
                'actuator_forcelimited','jnt_actfrcrange','jnt_actfrclimited','qpos0',
                'geom_type','geom_size','geom_pos','geom_quat','geom_bodyid','geom_contype','geom_conaffinity',
                'geom_friction','geom_solref','geom_solimp','sensor_type','sensor_objid','sensor_objtype',
                'sensor_adr','sensor_dim')
        for field in fields:
            np.testing.assert_array_equal(getattr(reference.mj_model,field),getattr(env.mj_model,field),err_msg=field)
        config['compiled_physical_model_contract']={'passed':True,'array_fields':list(fields)}
        reset=jax.jit(env.reset);step_fn=jax.jit(env.step)
        config['jax_devices']=[str(x) for x in jax.devices()]
        config['gpu_buffer_allocation']={'njmax':512,'naconmax':16384,'worlds':1}
        (a.output/'configuration.json').write_text(json.dumps(config,indent=2)+'\n')
    else:
        from native_task import NativeReorient
        from test_upstream_onnx import controller_class, orientation_error
        env=NativeReorient(noise_level=a.noise_level)
        env._config.unlock();env._config.sim_dt=a.sim_dt;env._config.lock()
        env.mj_model.opt.timestep=a.sim_dt
        reset=env.reset_seed
        step_fn=env.step
        cls=controller_class()
    rows=[];started=time.monotonic()
    try:
        for k in range(a.episodes):
            seed=a.seed+k
            if a.backend=='playground':state=reset(jax.random.PRNGKey(seed))
            else:state=reset(seed)
            initial={'qpos':np.asarray(state.data.qpos).tolist(),'qvel':np.asarray(state.data.qvel).tolist(),
                     'ctrl':np.asarray(state.data.ctrl).tolist(),'goal_quat_wxyz':np.asarray(state.data.mocap_quat)[0].tolist(),
                     'actor_observation':np.asarray(state.obs['state']).tolist()}
            if a.backend=='native-player':
                data=state.data.raw;mujoco.mj_forward(env.mj_model,data)
                controller=cls(str(policy_file),env._hand_qids,env._hand_dqids,data.ctrl.copy(),env._lowers,env._uppers,env.n_substeps)
                mujoco.set_mjcb_control(controller.get_control)
            success=False;fall=False;min_error=float('inf');max_motion=0.;last_pose=np.asarray(state.data.qpos)[-7:].copy();trace=[]
            for t in range(a.steps):
                if a.backend=='native-player':
                    for _ in range(env.n_substeps):mujoco.mj_step(env.mj_model,data)
                    error=orientation_error(data);success=error<.1
                    fall=bool(data.sensor('cube_position').data[2]<-.05)
                    action=controller._last_action
                    pose=data.qpos[-7:]
                    finite=np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all()
                else:
                    obs=np.asarray(state.obs['state'],dtype=np.float32).reshape(1,57)
                    if not np.isfinite(obs).all():raise ValueError('Nonfinite observation')
                    action=policy.run(['continuous_actions'],{'obs':obs})[0][0]
                    state=step_fn(state,jp.asarray(action) if a.backend=='playground' else action)
                    error=float(env._cube_orientation_error(state.data))
                    success=bool(float(state.metrics['reward/success']));fall=bool(state.done)
                    pose=np.asarray(state.data.qpos)[-7:]
                    finite=np.isfinite(np.asarray(state.data.qpos)).all() and np.isfinite(np.asarray(state.data.qvel)).all()
                if not finite or not np.isfinite(action).all() or not np.isfinite(error):raise ValueError('Nonfinite rollout')
                success=success and not fall
                min_error=min(min_error,error);max_motion=max(max_motion,float(np.max(np.abs(pose-last_pose))));last_pose=pose.copy()
                trace.append({'step':t+1,'error_rad':error,'goal_event':success,'fall':fall,'action':np.asarray(action).tolist()})
                if success or fall:break
            warnings=sum(w.number for w in state.data.raw.warning) if a.backend!='playground' else None
            # Timeout identifies an unresolved first goal, not proof of mechanical wedging.
            row={'seed':seed,'steps':t+1,'first_goal_success':success,'fall':fall,'timeout':not(success or fall),
                 'first_goal_time_s':(t+1)*.05 if success else None,'min_error_rad':min_error,'final_error_rad':error,
                 'native_engine_warnings':warnings,'initial_state':initial}
            rows.append(row)
            with (a.output/'episodes.jsonl').open('a') as f:f.write(json.dumps(row,allow_nan=False)+'\n')
            with (a.output/f'trace-{seed}.jsonl').open('w') as f:
                for item in trace:f.write(json.dumps(item,allow_nan=False)+'\n')
            print(json.dumps({k:v for k,v in row.items() if k!='initial_state'}),flush=True)
            mujoco.set_mjcb_control(None)
    finally:mujoco.set_mjcb_control(None)
    count=sum(x['first_goal_success'] for x in rows)
    result={'configuration':config,'completed_episodes':len(rows),'first_goal_successes':count,'first_goal_success_rate':count/len(rows),
            'wilson_95_interval':wilson(count,len(rows)),'falls':sum(x['fall'] for x in rows),
            'timeouts':sum(x['timeout'] for x in rows),'wall_seconds':time.monotonic()-started,
            'status':'complete','meets_observed_80_percent_teaching_baseline':len(rows)>=100 and count/len(rows)>=.80,
            'repeated_goal_qualification':'not measured by this first-goal evaluator; use continuous lettered_demo separately'}
    (a.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
