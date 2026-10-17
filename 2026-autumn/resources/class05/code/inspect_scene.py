"""Inspect bundled independent-hinge scene. No hardware or viewer required."""
from pathlib import Path
import argparse,json
import mujoco
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--controller',choices=['H1','H2'],default='H1');a=p.parse_args()
f=Path(__file__).resolve().parents[1]/f'models/combined/B2_{a.controller}.xml'
m=mujoco.MjModel.from_xml_path(str(f));d=mujoco.MjData(m);mujoco.mj_forward(m,d)
H=np.zeros((m.nv,m.nv));mujoco.mj_fullM(m,H,d.qM)
off=H-np.diag(np.diag(H))
# An explicit example of the force-like general-actuator input, not an angle slot.
kp={'H1':1.579836,'H2':2.106448}[a.controller];kv=.202115
qref=.1;vref=.2
d.ctrl[:]=kp*qref+kv*vref;mujoco.mj_forward(m,d)
result={'controller':a.controller,'nq':m.nq,'nv':m.nv,'nu':m.nu,'contact_enabled_geom_count':int(np.count_nonzero(m.geom_contype|m.geom_conaffinity)),'largest_off_diagonal_inertia_kg_m2':float(np.max(np.abs(off))),'requested_effort_at_zero_state_Nm':kp*qref+kv*vref,'applied_effort_motor0_Nm':float(d.qfrc_actuator[0]),'scope':'Declared independent-hinge model; no hardware validation or replay.'}
assert m.nq==m.nv==m.nu==16 and result['contact_enabled_geom_count']==0
assert result['largest_off_diagonal_inertia_kg_m2']<1e-12
for _ in range(100):mujoco.mj_step(m,d)
assert np.isfinite(d.qpos).all()
print(json.dumps(result,indent=2))
