"""Check supplied paired metrics and saved traces. No fitting, simulation or hardware IO."""
from pathlib import Path
import csv,json,math
from collections import defaultdict
R=Path(__file__).resolve().parents[1]
METHODS={'synthetic_baseline','hardware_fitted'}

def analyse():
    rows=list(csv.DictReader((R/'data/episode_metrics.csv').open()))
    pairs=defaultdict(dict);event_motors=defaultdict(set);roles=defaultdict(set)
    metadata={}
    for row in rows:
        event=row['simultaneous_episode_id'];motor=int(row['motor_id'])
        event_motors[event].add(motor);roles[event].add(row['split'])
        key=row['episode_id'];method=row['model'];value=float(row['position_rmse_rad'])
        if method not in METHODS or not math.isfinite(value) or value<0:
            raise ValueError('Unknown method or invalid position RMSE')
        if method in pairs[key]:
            raise ValueError('Duplicate prediction for one physical record')
        pairs[key][method]=row
        fields=tuple(row[k] for k in ['simultaneous_episode_id','motor_id','split','fixture_id','controller_id','profile_id','repeat_id','sample_count','duration_s'])
        if key in metadata and metadata[key]!=fields:
            raise ValueError('Paired predictions describe different physical records')
        metadata[key]=fields
    if len(event_motors)!=125 or any(v!=set(range(16)) for v in event_motors.values()):
        raise ValueError('Unexpected event/motor coverage')
    if any(len(v)!=1 for v in roles.values()):
        raise ValueError('One collection event crosses split boundaries')
    counts={k:sum(v=={k} for v in roles.values()) for k in ['calibration','model_selection','held_out']}
    if counts!={'calibration':72,'model_selection':23,'held_out':30}:
        raise ValueError('Unexpected split counts')
    if len(pairs)!=2000 or any(set(v)!=METHODS for v in pairs.values()):
        raise ValueError('Every physical record must have two paired predictions')
    parameters=list(csv.DictReader((R/'data/fitted_parameters.csv').open()))
    selected=[v for v in parameters if v['model']=='hardware_fitted']
    if len(selected)!=32 or len({(v['controller_id'],v['motor_id']) for v in selected})!=32:
        raise ValueError('Unexpected selected-vector coverage')
    held=[v for v in pairs.values() if v['synthetic_baseline']['split']=='held_out']
    if len(held)!=480:
        raise ValueError('Unexpected held-out record count')
    b=math.fsum(float(v['synthetic_baseline']['position_rmse_rad']) for v in held)/len(held)
    f=math.fsum(float(v['hardware_fitted']['position_rmse_rad']) for v in held)/len(held)
    cells=[]
    for controller in ['H1','H2']:
        for motor in range(16):
            rr=[v for v in held if v['synthetic_baseline']['controller_id']==controller and int(v['synthetic_baseline']['motor_id'])==motor]
            if len(rr)!=15:
                raise ValueError('Expected fifteen held-out records per cell')
            vals={method:math.fsum(float(v[method]['position_rmse_rad']) for v in rr)/len(rr) for method in sorted(METHODS)}
            cells.append(dict(motor=motor,controller=controller,baseline=vals['synthetic_baseline'],fitted=vals['hardware_fitted'],reduction=100*(1-vals['hardware_fitted']/vals['synthetic_baseline'])))
    trace_rows=list(csv.DictReader((R/'data/paired-trace.csv').open()))
    traces=defaultdict(list)
    for row in trace_rows:
        traces[row['episode_id']].append(row)
    if len(traces)!=2:
        raise ValueError('Expected the two supplied activity motor records')
    trace_checks=[]
    for episode,rr in sorted(traces.items()):
        times=[float(v['time_s']) for v in rr]
        if not all(math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
            raise ValueError('Trace time must be finite and strictly increasing')
        for method in sorted(METHODS):
            reference=pairs[episode][method]
            residual=[float(v[method+'_position_rad'])-float(v['hardware_position_rad']) for v in rr]
            if any(not math.isfinite(v) for v in residual):
                raise ValueError('Invalid trace residual')
            score=math.sqrt(math.fsum(v*v for v in residual)/len(rr));expected=float(reference['position_rmse_rad'])
            if len(rr)!=int(reference['sample_count']) or abs(score-expected)>5e-12:
                raise ValueError('Saved trace disagrees with its published episode score')
            trace_checks.append(dict(episode_id=episode,motor=int(reference['motor_id']),method=method,sample_count=len(rr),start_s=times[0],end_s=times[-1],rmse_rad=score,published_rmse_rad=expected,absolute_difference_rad=abs(score-expected)))
    result=dict(scope='Supplied metric reaggregation and RMSE checks on saved prediction traces; no fitting or new simulation',
                events=30,records=480,baseline=b,fitted=f,reduction=100*(1-f/b),cells=cells,
                all_events=125,all_motor_records=2000,all_paired_prediction_rows=len(rows),
                event_roles=counts,selected_vectors=32,selected_trace_checks=trace_checks)
    if not math.isclose(result['reduction'],31.985323,abs_tol=1e-5):
        raise ValueError('Unexpected held-out aggregate')
    (R/'results').mkdir(exist_ok=True)
    (R/'results/lesson-summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result

if __name__=='__main__':
    result=analyse()
    print(json.dumps({k:v for k,v in result.items() if k not in ['cells','selected_trace_checks']},indent=2))
    for cell in result['cells']:
        if cell['motor'] in [0,9]:print(cell)
    for check in result['selected_trace_checks']:
        print(f"Motor {check['motor']} {check['method']}: {check['sample_count']} saved samples, RMSE {check['rmse_rad']:.10f} rad; table difference {check['absolute_difference_rad']:.2e} rad")
