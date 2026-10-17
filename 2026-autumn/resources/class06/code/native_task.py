"""Execute pinned Playground LEAP task methods with native MuJoCo physics.

Task arithmetic/RNG remain upstream JAX CPU; no Playground installation needed.
Apache-2.0 upstream sources are unmodified in reference/. The native compatibility
layer changes construction and physics/data APIs only. Not a trained controller.
"""
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
import ast
import hashlib
import json
import jax
import jax.numpy as jp
from ml_collections import config_dict
import mujoco
from mujoco import mjx
from mujoco.mjx._src import math
import numpy as np

ROOT=Path(__file__).resolve().parent
PROVENANCE=json.loads((ROOT/'provenance.json').read_text())

def verify_sources():
    for name,digest in PROVENANCE['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Pinned source/asset changed: '+name)

def source_nodes(name, predicate):
    tree=ast.parse((ROOT/'reference'/name).read_text())
    return [n for n in tree.body if predicate(n)]

def execute(nodes, namespace, name):
    future=ast.parse('from __future__ import annotations').body
    module=ast.fix_missing_locations(ast.Module(body=future+nodes,type_ignores=[]))
    exec(compile(module,str(ROOT/'reference'/name),'exec'),namespace)

class NativeModel:
    def __init__(self,raw):
        self.raw=raw
        self.impl=SimpleNamespace(value='native')
    def __getattr__(self,name): return getattr(self.raw,name)

class NativeData:
    def __init__(self, model, raw=None):
        self.model=model
        self.raw=mujoco.MjData(model) if raw is None else raw
    def __getattr__(self,name):
        value=getattr(self.raw,name)
        return jp.asarray(value) if isinstance(value,(np.ndarray,float)) else value
    def clone(self):
        raw=mujoco.MjData(self.model)
        mujoco.mj_copyData(raw,self.model,self.raw)
        return NativeData(self.model,raw)
    def replace(self,**values):
        new=self.clone()
        for name,value in values.items():
            array=getattr(new.raw,name)
            array[:]=np.asarray(value).reshape(array.shape)
        return new

@dataclass
class State:
    data: NativeData
    obs: dict
    reward: object
    done: object
    metrics: dict
    info: dict
    def replace(self,**values): return replace(self,**values)

def make_data(model,**values):
    model=model.raw if isinstance(model,NativeModel) else model
    # Match upstream make_data: assign states, without a forward pass at reset.
    allowed={k:v for k,v in values.items() if k in ('qpos','qvel','ctrl','act','mocap_pos','mocap_quat')}
    return NativeData(model).replace(**allowed)

def step(model,data,action,n_substeps):
    model=model.raw if isinstance(model,NativeModel) else model
    new=data.replace(ctrl=action)
    for _ in range(n_substeps): mujoco.mj_step(model,new.raw)
    return new

def sensor(model,data,name):
    s=model.sensor(name)
    return jp.asarray(data.raw.sensordata[s.adr[0]:s.adr[0]+s.dim[0]])

def ids(model,names,kind):
    out=[]
    for name in names:
        joint=model.joint(name)
        start=int(getattr(joint,kind)[0])
        typ=int(joint.type[0])
        width=({0:7,1:4,2:1,3:1} if kind=='qposadr' else {0:6,1:3,2:1,3:1})[typ]
        out.extend(range(start,start+width))
    return np.asarray(out,dtype=int)

verify_sources()
consts=SimpleNamespace()
cn={}
execute(source_nodes('leap_hand_constants.py',lambda n:isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('JOINT_NAMES','FINGERTIP_NAMES','NQ','NV','NU') for t in n.targets)),cn,'leap_hand_constants.py')
consts.__dict__.update(cn)
reward_ns={'jp':jp,'warnings':__import__('warnings')}
execute(source_nodes('reward.py',lambda n:isinstance(n,(ast.FunctionDef,ast.Assign))),reward_ns,'reward.py')
reward=SimpleNamespace(**{k:v for k,v in reward_ns.items() if not k.startswith('__')})
compat=SimpleNamespace(State=State,make_data=make_data,step=step,get_sensor_data=sensor,
    get_qpos_ids=lambda m,n:ids(m,n,'qposadr'),get_qvel_ids=lambda m,n:ids(m,n,'dofadr'))

class NativeBase:
    @property
    def dt(self): return self._config.ctrl_dt
    @property
    def sim_dt(self): return self._config.sim_dt
    @property
    def n_substeps(self): return int(round(self.dt/self.sim_dt))

ns=dict(jax=jax,jp=jp,np=np,mujoco=mujoco,mjx=mjx,math=math,config_dict=config_dict,
        consts=consts,mjx_env=compat,reward=reward)
base=source_nodes('base.py',lambda n:isinstance(n,(ast.ClassDef,ast.FunctionDef)) and getattr(n,'name','') in ('LeapHandEnv','uniform_quat'))
for n in base:
    if isinstance(n,ast.ClassDef):
        n.bases=[ast.Name(id='NativeBase',ctx=ast.Load())]
        n.body=[b for b in n.body if not isinstance(b,ast.FunctionDef) or b.name!='__init__']
ns['NativeBase']=NativeBase
execute(base,ns,'base.py')
ns['leap_hand_base']=SimpleNamespace(LeapHandEnv=ns['LeapHandEnv'],uniform_quat=ns['uniform_quat'])
nodes=source_nodes('reorient.py',lambda n:isinstance(n,(ast.FunctionDef,ast.ClassDef)) and getattr(n,'name','') in ('default_config','CubeReorient'))
for n in nodes:
    if isinstance(n,ast.ClassDef):
        n.body=[b for b in n.body if not isinstance(b,ast.FunctionDef) or b.name!='__init__']
execute(nodes,ns,'reorient.py')

class NativeReorient(ns['CubeReorient']):
    def __init__(self,noise_level=1.):
        self._config=ns['default_config']()
        self._config.obs_noise.level=noise_level
        self._config.lock()
        assets={}
        for p in sorted((ROOT/'models').rglob('*')):
            if p.is_file():
                if p.name in assets and assets[p.name]!=p.read_bytes():
                    raise ValueError('Asset basename collision: '+p.name)
                assets[p.name]=p.read_bytes()
        self._mj_model=mujoco.MjModel.from_xml_string((ROOT/'models/xmls/scene_mjx_cube.xml').read_text(),assets=assets)
        self._mj_model.opt.timestep=self._config.sim_dt
        self._mj_model.opt.ccd_iterations=10
        self._mj_model.vis.global_.offwidth=3840
        self._mj_model.vis.global_.offheight=2160
        self._mjx_model=NativeModel(self._mj_model)
        self._post_init()
    def reset_seed(self,seed): return self.reset(jax.random.PRNGKey(seed))
    def metrics_native(self,state):
        return dict(orientation_error_rad=float(self._cube_orientation_error(state.data)),
            successes=int(state.info['success_count']),steps=int(state.info['step']),
            terminated=bool(state.done),cube_position=np.asarray(self.get_cube_position(state.data)).tolist(),
            reward=float(state.reward),warnings=sum(w.number for w in state.data.raw.warning))
