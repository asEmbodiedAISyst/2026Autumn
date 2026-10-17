#!/usr/bin/env python3
"""Offline structural audit of the supplied 110 g Class03 fixture family."""
from pathlib import Path
import argparse
import json
import xml.etree.ElementTree as ET
import numpy as np
import mujoco

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'consolidation/additional_material/models'

def inspect(case='B2', radius_mm=None):
    if case not in {'M0', 'B0', 'B1', 'B2', 'G1'}:
        raise ValueError('Unknown fixture case')
    if radius_mm is not None and (case != 'B2' or not 10 <= radius_mm <= 100):
        raise ValueError('Radius changes require B2 and a radius from 10 to 100 mm')
    path = MODELS / f'1DOF-{case}.xml'
    root = ET.parse(path).getroot()
    for mesh in root.findall('./asset/mesh'):
        mesh.set('file', str((path.parent / mesh.attrib['file']).resolve()))
    if radius_mm is not None:
        for name, sign in [('Pin_1', 1), ('Pin_2', -1)]:
            body = root.find(f".//body[@name='{name}']")
            pos = [float(x) for x in body.attrib['pos'].split()]
            pos[0] = sign * radius_mm / 1000
            body.set('pos', ' '.join(map(str, pos)))
    model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding='unicode'))
    data = mujoco.MjData(model)
    data.qpos[0] = 0.4
    data.ctrl[:] = 0
    mujoco.mj_forward(model, data)
    inertia_column = np.zeros(model.nv)
    mujoco.mj_mulM(model, data, inertia_column, np.ones(model.nv))
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, 'actuator_joint')
    moving = []
    for bid in range(1, model.nbody):
        ancestor = bid
        while ancestor:
            if model.body_dofnum[ancestor] > 0:
                moving.append(bid)
                break
            ancestor = int(model.body_parentid[ancestor])
    return {
        'model_file': str(path.relative_to(ROOT)), 'case': case,
        'radius_override_mm': radius_mm,
        'nq': model.nq, 'nv': model.nv, 'nu': model.nu,
        'external_moving_mass_kg': float(model.body_mass[moving].sum()),
        'joint_axis_local': model.jnt_axis[jid].tolist(),
        'joint_range_rad': model.jnt_range[jid].tolist(),
        'timestep_s': float(model.opt.timestep),
        'collision_enabled_geom_count': int(np.count_nonzero(model.geom_contype | model.geom_conaffinity)),
        'gravity_probe_q_rad': 0.4,
        'joint_inertia_kg_m2': float(inertia_column[0]),
        'gravity_bias_Nm': float(data.qfrc_bias[0]),
        'zero_control_qacc_rad_s2': float(data.qacc[0]),
        'scope': 'declared structural model, not a hardware motion prediction'
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['M0', 'B0', 'B1', 'B2', 'G1'], default='B2')
    parser.add_argument('--radius-mm', type=float)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    baseline = inspect(args.case)
    result = {'mujoco_version': mujoco.__version__, 'base': baseline}
    if args.radius_mm is not None:
        changed = inspect(args.case, args.radius_mm)
        result['modified'] = changed
        result['inertia_change_kg_m2'] = changed['joint_inertia_kg_m2'] - baseline['joint_inertia_kg_m2']
        result['point_mass_expected_change_kg_m2'] = 2 * 0.044 * ((args.radius_mm / 1000)**2 - 0.100**2)
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + '\n')
    print(text)

if __name__ == '__main__':
    main()
