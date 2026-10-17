#!/usr/bin/env python3
"""Analyse a saved Class 04 XC330 frozen prediction; no MuJoCo is needed.

From the Class04 resource directory:
  python code/analyze_episode.py
  python code/analyze_episode.py --no-plot
  python code/analyze_episode.py --episode data/xc330-98g-H1-B1-P06-R01.csv

Metrics use only the Python standard library. Plotting additionally needs
Matplotlib (and its NumPy dependency). The default case is H1/G1/P06/R01.
This script evaluates saved predictions: it never fits or reruns a simulator.
"""
from __future__ import annotations
import argparse, csv, json, math, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ('time_s','external_goal_rad','internal_position_reference_rad',
            'physical_position_rad','simulated_M1_position_rad',
            'simulated_M2_position_rad','M1_residual_rad','M2_residual_rad')

def summarize(values):
    n=len(values)
    return {'rmse_rad':math.sqrt(math.fsum(x*x for x in values)/n),
            'mae_rad':math.fsum(abs(x) for x in values)/n,
            'mean_signed_residual_rad':math.fsum(values)/n,
            'max_abs_residual_rad':max(abs(x) for x in values)}

def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--episode',type=Path,default=ROOT/'data/xc330-98g-H1-G1-P06-R01.csv')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'activity-output')
    parser.add_argument('--no-plot',action='store_true',help='Use the standard-library metric path only.')
    args=parser.parse_args()
    with args.episode.open(newline='',encoding='utf-8') as f:
        reader=csv.DictReader(f)
        missing=set(REQUIRED)-set(reader.fieldnames or [])
        if missing: raise ValueError('Missing columns: '+', '.join(sorted(missing)))
        rows=[{k:float(v) for k,v in row.items()} for row in reader]
    if len(rows)<2: raise ValueError('An episode needs at least two samples.')
    if any(not all(math.isfinite(v) for v in row.values()) for row in rows): raise ValueError('Non-finite values in episode.')
    t=[r['time_s'] for r in rows]
    if any(b<=a for a,b in zip(t,t[1:])): raise ValueError('Episode times must strictly increase.')
    d={k:[r[k] for r in rows] for k in rows[0]}
    methods={}
    for method in ('M1','M2'):
        residual=[s-y for s,y in zip(d[f'simulated_{method}_position_rad'],d['physical_position_rad'])]
        if max(abs(x-y) for x,y in zip(residual,d[method+'_residual_rad']))>1e-12:
            raise ValueError(f'{method} stored residual disagrees with simulation minus physical position.')
        methods[method]=summarize(residual)
    score={
        'episode_file':args.episode.name,'sample_count':len(rows),'first_time_s':t[0],'last_time_s':t[-1],
        'residual_definition':'simulated position minus measured physical position',
        'tracking_error_definition':'reference minus measured physical position; external and internal scored separately',
        'scoring':'All supplied processed active-episode samples; no extra filtering, shifting, alignment, burn-in removal or masking.',
        'methods':methods,
        'physical_external_tracking_rmse_rad':summarize([g-y for y,g in zip(d['physical_position_rad'],d['external_goal_rad'])])['rmse_rad'],
        'physical_internal_tracking_rmse_rad':summarize([r-y for y,r in zip(d['physical_position_rad'],d['internal_position_reference_rad'])])['rmse_rad'],
    }
    args.output_dir.mkdir(parents=True,exist_ok=True)
    out=args.output_dir/'metrics.json'
    out.write_text(json.dumps(score,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(f'{args.episode.name}: {len(rows)} samples, {t[0]:g}–{t[-1]:g} s')
    for method,stats in methods.items():
        print(f'{method}: position RMSE = {stats["rmse_rad"]:.9f} rad; mean signed residual = {stats["mean_signed_residual_rad"]:+.9f} rad; peak absolute residual = {stats["max_abs_residual_rad"]:.9f} rad')
    print('Residual = simulated position − measured physical position.')
    print('Saved metrics:',out.resolve())
    if args.no_plot: return
    os.environ.setdefault('MPLCONFIGDIR',str(args.output_dir/'.matplotlib'))
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError as exc:
        print('Metrics are complete. To make the optional plot, install Matplotlib in your prepared environment.');return
    for path in (ROOT/'code/fonts').glob('*.ttf'):font_manager.fontManager.addfont(path)
    plt.rcParams.update({'font.family':'MiSans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'path'})
    fig,(a,b)=plt.subplots(2,1,figsize=(11,7),sharex=True,gridspec_kw={'height_ratios':[2,1]},layout='constrained')
    for k,label,color,style,width in [
        ('external_goal_rad','External goal','#555c63','--',1),
        ('internal_position_reference_rad','Internal position reference','#d29000',':',1.5),
        ('physical_position_rad','Physical position','#1d5e8a','-',2),
        ('simulated_M1_position_rad','M1 integral fit','#159b80','-',1.3),
        ('simulated_M2_position_rad','M2 output-error fit','#9b4a9a','-',1.3),
    ]:a.plot(t,d[k],label=label,color=color,ls=style,lw=width)
    positions=[v for k in ('external_goal_rad','internal_position_reference_rad','physical_position_rad','simulated_M1_position_rad','simulated_M2_position_rad') for v in d[k]]
    a.set_ylim(min(positions)-.04,max(positions)+.22)
    a.set_title(args.episode.stem+' · frozen predictions',pad=20);a.set_ylabel('Joint position (rad)');a.legend(ncol=3,fontsize=9);a.grid(alpha=.25)
    for method,color in [('M1','#159b80'),('M2','#9b4a9a')]:
        b.plot(t,d[method+'_residual_rad'],label=f'{method} RMSE {methods[method]["rmse_rad"]:.6f} rad',color=color,lw=1.3)
    b.axhline(0,color='#66737b',lw=.7);b.set_ylabel('Simulation − physical (rad)');b.set_xlabel('Time from processed active episode start (s)');b.legend(ncol=2,fontsize=10);b.grid(alpha=.25);a.set_xlim(t[0],t[-1])
    residuals=d['M1_residual_rad']+d['M2_residual_rad']
    b.set_ylim(min(residuals)-.005,max(residuals)+.025)
    for ext in ('png','svg'):fig.savefig(args.output_dir/('overlay-residual.'+ext),dpi=180,bbox_inches='tight',facecolor='white')
    plt.close(fig);print('Saved plot:',(args.output_dir/'overlay-residual.png').resolve())

if __name__=='__main__':main()
