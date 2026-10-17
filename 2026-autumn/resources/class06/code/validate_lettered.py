"""Matched rollout check: visual labels must leave task dynamics unchanged."""
import json,sys
from pathlib import Path
import numpy as np
from lettered_cube import make_env,physics_contract

a,b=make_env(False),make_env(True)
contract=physics_contract(a.mj_model,b.mj_model)
sa,sb=a.reset_seed(9203),b.reset_seed(9203)
for k in range(40):
 action=np.sin(np.arange(16)*.3+k*.2)*.08
 sa,sb=a.step(sa,action),b.step(sb,action)
 np.testing.assert_array_equal(sa.data.raw.qpos,sb.data.raw.qpos)
 np.testing.assert_array_equal(sa.data.raw.qvel,sb.data.raw.qvel)
 np.testing.assert_array_equal(sa.obs['state'],sb.obs['state'])
 np.testing.assert_array_equal(sa.reward,sb.reward)
 np.testing.assert_array_equal(sa.done,sb.done)
result={'physics_contract':contract,'matched_rollout_steps':40,'qpos_qvel_actor_obs_reward_done_bit_identical':True}
Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
