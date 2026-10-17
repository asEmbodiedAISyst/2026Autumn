"""CPU experiments using the unchanged PhyIntel hardware replay engines.

Example: python code/phyintel_lab.py replay --actuator both
The mandatory path evaluates frozen released models, never silently refits.
"""
from __future__ import annotations
import argparse
import dataclasses
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
import numpy as np
import mujoco

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'data/phyintel'
OUT = ROOT/'results/phyintel'
OUT.mkdir(parents=True, exist_ok=True)
SCRIPTS = {'xc330':'run_chapter02_real_position_identification_v2.py',
           'rs06':'run_appendix_b_rs06_hardware_identification_v1.py'}

def write(name, obj):
    (OUT/name).write_text(json.dumps(obj, indent=2, allow_nan=False))

def load(kind):
    path = ROOT/'code/upstream'/SCRIPTS[kind]
    provenance = json.loads((DATA/kind/'provenance.json').read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest()==provenance['runner_sha256']
    for relative,expected in provenance['export_file_hashes'].items():
        assert hashlib.sha256((DATA/kind/relative).read_bytes()).hexdigest()==expected, relative
    spec = importlib.util.spec_from_file_location('upstream_'+kind, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    metadata = json.loads((DATA/kind/'episodes.json').read_text())
    episodes = []
    with np.load(DATA/kind/'episodes.npz', allow_pickle=False) as arrays:
        for item in metadata:
            row = dict(item)
            prefix = row.pop('array_prefix')
            for field in dataclasses.fields(m.Episode):
                key = prefix+'_'+field.name
                if key in arrays:
                    row[field.name] = arrays[key]
            episodes.append(m.Episode(**row))
    assert len(episodes)==provenance['episode_count']
    fixtures = m.fixture_properties() if kind=='xc330' else m.load_fixture_metadata(DATA/kind)
    engine = m.ReplayEngine(fixtures,m.FIXED_CONTROLLER_GAINS) if kind=='xc330' else m.ReplayEngine(DATA/kind)
    published = json.loads((DATA/kind/'published/result.json').read_text())
    return m, episodes, fixtures, engine, published

def identity(kind, e):
    return (e.controller_id,e.fixture_id,e.profile_id.split("_")[0],e.role) if kind=='xc330' else (e.controller,e.fixture,e.profile.split("_")[0],e.split)

def candidates(kind):
    import csv
    rows=list(csv.DictReader((DATA/kind/'published/joint-parameter-estimates.csv').open()))
    result={method:{h:np.zeros(3) for h in ('H1','H2')} for method in ('method1','method2')}
    for row in rows:
        i=('armature','damping','frictionloss').index(row['parameter'])
        for method in result:
            for h in ('H1','H2'):
                if kind=='xc330': result[method][h][i]=float(row[f'{method}_{h}'])
                elif row['method']==method and row['controller']==h: result[method][h][i]=float(row['value'])
    return result

def audit(kind):
    m, episodes, fixtures, engine, published=load(kind)
    ids=[e.episode_id for e in episodes]
    assert len(ids)==len(set(ids))
    for e in episodes:
        assert np.all(np.diff(e.time)>0)
        assert np.isfinite(e.position).all()
    counts=Counter('|'.join(identity(kind,e)) for e in episodes)
    roles=Counter(identity(kind,e)[3] for e in episodes)
    result={'actuator':kind,'episode_count':len(episodes),'samples':sum(len(e.time) for e in episodes),
            'roles':dict(roles),'matrix':dict(sorted(counts.items())),
            'unique_ids':True,'strictly_increasing_episode_times':True,
            'source':json.loads((DATA/kind/'provenance.json').read_text())}
    write(kind+'-audit.json',result)
    print(kind, 'audit', result['episode_count'], 'episodes',result['roles'],flush=True)

def inspect(kind):
    m, episodes, fixtures, engine, published=load(kind)
    params=candidates(kind)['method2']
    rows=[]
    for h in ('H1','H2'):
        for fixture in fixtures:
            if kind=='xc330':
                model=engine._make_model(fixture,h)
                model.dof_armature[0],model.dof_damping[0],model.dof_frictionloss[0]=params[h]
            else: model=engine.model(fixture,h,params[h])
            data=mujoco.MjData(model)
            mujoco.mj_setConst(model,data)
            mujoco.mj_forward(model,data)
            mass=np.empty((model.nv,model.nv))
            mujoco.mj_fullM(model,mass,data.qM)
            rows.append({'controller':h,'fixture':fixture,'nq':model.nq,'nv':model.nv,
                'timestep_s':float(model.opt.timestep),'total_inertia_kg_m2':float(mass[0,0]),
                'armature_kg_m2':float(model.dof_armature[0]),
                'fixture_inertia_kg_m2':float(mass[0,0]-model.dof_armature[0]),
                'gravity_bias_at_zero_Nm':float(data.qfrc_bias[0]),'parameters':params[h].tolist()})
    write(kind+'-models.json',rows)
    print(kind,'models',len(rows),'loaded',flush=True)

def simulate(kind,m,engine,e,p):
    return engine.replay(e,p) if kind=='xc330' else engine.simulate(e,p)

def score(kind,e,pred):
    valid=np.ones(len(e.time),dtype=bool) if kind=='xc330' else e.valid & ~e.saturated
    error=pred[valid]-e.position[valid]
    return float(np.sqrt(np.mean(error**2)))

def replay(kind,all_episodes=False):
    m, episodes, fixtures, engine, published=load(kind)
    params=candidates(kind)
    if all_episodes: selected=episodes
    else:
        selected=[]
        for h in ('H1','H2'):
            for f in ('B1','G1'):
                matches=[e for e in episodes if identity(kind,e)==(h,f,'P06','held_out')]
                selected.append(sorted(matches,key=lambda e:e.episode_id)[0])
    traces,rows={},[]
    import csv
    reference=list(csv.DictReader((DATA/kind/'published/episode-metrics.csv').open()))
    for i,e in enumerate(selected):
        h,f,p,role=identity(kind,e)
        traces[f'e{i}_time']=e.time
        traces[f'e{i}_position']=e.position
        traces[f'e{i}_command']=e.external_goal if kind=='xc330' else e.command
        traces[f'e{i}_reference']=e.controller_trajectory if kind=='xc330' else e.command
        for method in params:
            pred=simulate(kind,m,engine,e,params[method][h])
            assert np.isfinite(pred).all()
            traces[f'e{i}_{method}']=pred
            gap=score(kind,e,pred)
            match=next(row for row in reference if row['episode_id']==e.episode_id and row.get('candidate',row.get('method'))==method)
            expected=float(match['output_gap_rmse_rad'])
            row={'episode_id':e.episode_id,'index':i,'controller':h,'fixture':f,'profile':p,'split':role,
                 'method':method,'rmse_rad':gap,'published_rmse_rad':expected,'absolute_difference_rad':abs(gap-expected)}
            rows.append(row)
            if not all_episodes: print(kind,h,f,p,method,f'RMSE={gap:.8f} rad; published difference={abs(gap-expected):.2e}',flush=True)
    if all_episodes:
        write(kind+'-evaluation.json',{'episode_count':len(selected),'method_count':2,'metrics':rows,'max_published_difference_rad':max(r['absolute_difference_rad'] for r in rows)})
        print(kind,'complete frozen evaluation',len(selected),'episodes; max difference',max(r['absolute_difference_rad'] for r in rows),flush=True)
    np.savez_compressed(OUT/(kind+'-replay.npz'),**traces)
    write(kind+'-replay.json',{'mode':'all' if all_episodes else 'four representative held-out episodes',
        'parameter_source':'frozen published parameters; no refitting','metrics':rows,
        'max_published_difference_rad':max(r['absolute_difference_rad'] for r in rows)})

def fit(kind,method,controller):
    m,episodes,fixtures,engine,published=load(kind)
    if method=='integral':
        values,details=(m.fit_method1(episodes,fixtures,m.FIXED_CONTROLLER_GAINS,controller) if kind=='xc330'
                        else m.fit_integral_regression(episodes,fixtures,engine,controller))
    elif kind=='xc330': values,details=m.fit_method2(episodes,engine,controller,multi_start=True)
    else:
        integral,_=m.fit_integral_regression(episodes,fixtures,engine,controller)
        starts=[np.array([0.0012484886,0.0004377347686,0.0481937007]),integral,np.array([0.01,0.10,0.10])]
        values,details=m.fit_output_error(episodes,engine,controller,starts)
    # Freeze the returned calibration fit and score other episodes without any refit.
    evaluation=[]
    for e in episodes:
        h,f,profile,role=identity(kind,e)
        if h==controller:
            pred=simulate(kind,m,engine,e,values)
            evaluation.append({'episode_id':e.episode_id,'fixture':f,'split':role,'rmse_rad':score(kind,e,pred)})
    means={role:float(np.mean([row['rmse_rad'] for row in evaluation if row['split']==role])) for role in ('calibration','model_selection','held_out')}
    write(f'{kind}-{controller}-fit-{method}.json',{'actuator':kind,'controller':controller,
        'method':method,'parameters':dict(zip(('armature','damping','frictionloss'),values.tolist())),
        'diagnostics':details,'frozen_evaluation':evaluation,'equal_episode_rmse_rad':means,'fit_scope':'calibration only; no validation refitting'})
    print(kind,controller,method,values,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['audit','inspect','replay','evaluate','fit-integral','fit-output-error','all'])
    parser.add_argument('--actuator',choices=['xc330','rs06','both'],default='both')
    parser.add_argument('--controller',choices=['H1','H2'],default='H1')
    args=parser.parse_args()
    for kind in ('xc330','rs06') if args.actuator=='both' else (args.actuator,):
        if args.action in ('audit','all'):audit(kind)
        if args.action in ('inspect','all'):inspect(kind)
        if args.action in ('replay','all'):replay(kind)
        if args.action=='evaluate':replay(kind,all_episodes=True)
        if args.action.startswith('fit-'):fit(kind,args.action.removeprefix('fit-'),args.controller)
