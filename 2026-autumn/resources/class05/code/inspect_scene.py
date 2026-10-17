"""Inspect a declared independent-hinge scene. No hardware, viewer or recorded-data replay."""
from pathlib import Path
import argparse,json
import mujoco
import numpy as np

def inspect(controller):
    root=Path(__file__).resolve().parents[1]
    model=mujoco.MjModel.from_xml_path(str(root/f'models/combined/B2_{controller}.xml'))
    data=mujoco.MjData(model);mujoco.mj_forward(model,data)
    H=np.zeros((model.nv,model.nv));mujoco.mj_fullM(model,H,data.qM)
    off=H-np.diag(np.diag(H))
    # Read gains from the XML affine bias instead of introducing another hard-coded mapping.
    kp=-model.actuator_biasprm[:,1];kv=-model.actuator_biasprm[:,2]
    joints=model.actuator_trnid[:,0].astype(int)
    dofs=model.jnt_dofadr[joints];qpos=model.jnt_qposadr[joints]
    if not np.allclose(model.actuator_gainprm[:,0],1) or not np.allclose(model.actuator_gear[:,0],1):
        raise ValueError('The demonstration requires unit gain and transmission')
    qref=.1;vref=.2
    data.ctrl[:]=kp*qref+kv*vref;mujoco.mj_forward(model,data)
    result={'controller':controller,'nq':model.nq,'nv':model.nv,'nu':model.nu,
            'timestep_s':float(model.opt.timestep),
            'contact_enabled_geom_count':int(np.count_nonzero(model.geom_contype|model.geom_conaffinity)),
            'largest_off_diagonal_inertia_kg_m2':float(np.max(np.abs(off))),
            'nominal_moving_fixture_mass_motor0_kg':float(model.body_subtreemass[model.jnt_bodyid[joints[0]]]),
            'requested_effort_at_zero_state_Nm':float(kp[0]*qref+kv[0]*vref),
            'applied_effort_motor0_Nm':float(data.qfrc_actuator[dofs[0]]),
            'scope':'Declared independent-hinge model; no hardware validation or campaign replay.'}
    assert model.nq==model.nv==model.nu==16 and result['contact_enabled_geom_count']==0
    assert result['largest_off_diagonal_inertia_kg_m2']<1e-12
    assert abs(result['nominal_moving_fixture_mass_motor0_kg']-.113)<1e-12
    data.qpos[qpos]=.2;data.qvel[dofs]=.4
    data.ctrl[:]=kp*.3+kv*.2;mujoco.mj_forward(model,data)
    raw=kp[0]*(.3-.2)+kv[0]*(.2-.4)
    bounded=float(np.clip(raw,*model.actuator_forcerange[0]))
    result['moving_example']={
        'general_actuator_input_Nm':float(data.ctrl[0]),
        'state_bias_Nm':float(-kp[0]*.2-kv[0]*.4),
        'unlimited_effort_Nm':float(raw),
        'applied_effort_Nm':float(data.qfrc_actuator[dofs[0]]),
        'computed_bounded_effort_Nm':bounded}
    assert abs(data.qfrc_actuator[dofs[0]]-bounded)<1e-12
    # Demonstrate the double-feedback error on an in-memory state, then restore the proper input.
    data.ctrl[:]=kp*(.3-.2)+kv*(.2-.4);mujoco.mj_forward(model,data)
    result['wrong_input_applied_effort_motor0_Nm']=float(data.qfrc_actuator[dofs[0]])
    data.ctrl[:]=kp*.3+kv*.2
    for _ in range(100):mujoco.mj_step(model,data)
    assert np.isfinite(data.qpos).all()
    result['finite_after_steps']=100
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controller',choices=['H1','H2'],default='H1')
    args=parser.parse_args();print(json.dumps(inspect(args.controller),indent=2))
