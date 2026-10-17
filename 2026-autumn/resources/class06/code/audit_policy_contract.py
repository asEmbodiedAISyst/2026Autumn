"""Numerical contract checks against the pinned upstream native player."""
import argparse, json
from pathlib import Path
import mujoco
import numpy as np
import onnxruntime as rt
from native_task import NativeReorient
from test_upstream_onnx import controller_class, REF

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if a.output.exists():p.error('Use a new output file.')
rt.disable_telemetry_events();mujoco.set_mjcb_control(None)
env=NativeReorient(noise_level=0.);state=env.reset_seed(9203)
reset_sensor_norm=float(np.linalg.norm(state.data.raw.sensor('cube_orientation').data))
mujoco.mj_forward(env.mj_model,state.data.raw)
cls=controller_class();player=cls(str(REF/'leap_reorient_policy.onnx'),env._hand_qids,env._hand_dqids,
 state.data.raw.ctrl.copy(),env._lowers,env._uppers,env.n_substeps)
obs=env._get_obs(state.data,state.info)['state']
np.testing.assert_allclose(obs,player.get_obs(env.mj_model,state.data.raw),atol=2e-6,rtol=0)
action=player._policy.run(player._output_names,{'obs':np.asarray(obs,dtype=np.float32).reshape(1,57)})[0][0]
old_ctrl=state.data.raw.ctrl.copy();state=env.step(state,action)
np.testing.assert_allclose(state.data.raw.ctrl,np.clip(old_ctrl+.5*action,env._lowers,env._uppers),atol=3e-7,rtol=0)
player._motor_targets=state.data.raw.ctrl.copy();player._last_action=action.copy()
player_obs=player.get_obs(env.mj_model,state.data.raw)
np.testing.assert_allclose(np.asarray(state.obs['state'])[:41],player_obs[:41],atol=2e-6,rtol=0)
# Task's returned observation is built before last_act is updated.
np.testing.assert_array_equal(np.asarray(state.obs['state'])[41:],np.zeros(16))
np.testing.assert_array_equal(player_obs[41:],action)
result={'passed':True,'actor_shape':57,'action_shape':16,'observation_blocks':[16,16,3,6,16],
 'observation_geometry_agrees_after_forward_and_equal_history':True,
 'incremental_control_scaling_and_clipping_agree':True,
 'actor_previous_action_difference':{'task':'returned observation includes action from one control step before the action just executed',
  'player':'next control observation includes action just executed','max_abs_difference_in_probe':float(np.max(np.abs(action)))},
 'physics_timing':{'task':{'dt':.01,'substeps':5},'native_player':{'dt':.002,'substeps':25},'control_dt':.05},
 'reset':{'task':'random joints, random cube pose and target; make_data has no forward call',
  'player':'home keyframe reset; callback observes sensors during stepping',
  'reset_cube_orientation_sensor_norm_native':reset_sensor_norm},
 'normalization':'both pass raw57-input observation to same ONNX; no external normalization; exact ONNX training configuration unavailable',
 'interpretation':'Verified interface differences, not proven causes; preserve original task history for task-to-task comparison.'}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
