#!/usr/bin/env python3
"""Regenerate the four existing 98 g plots from packaged CSVs; no fit/replay."""
from pathlib import Path
import argparse,csv,json,os
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir',type=Path,default=ROOT/'figure-output')
args=parser.parse_args();MEDIA=args.output_dir;MEDIA.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR',str(MEDIA/'.matplotlib'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
for font in (ROOT/'code/fonts').glob('*.ttf'):font_manager.fontManager.addfont(font)
plt.rcParams.update({'font.family':'MiSans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'grid.alpha':.25,'svg.fonttype':'path'})
tables={}
for fixture in ('B1','G1'):
    with (ROOT/f'data/xc330-98g-H1-{fixture}-P06-R01.csv').open() as f: rows=list(csv.DictReader(f))
    tables[fixture]={key:np.array([float(row[key]) for row in rows]) for key in rows[0]}
metrics=json.loads((ROOT/'data/xc330-98g-selected-episode-metrics.json').read_text())
metrics=metrics['metrics']
with (ROOT/'data/xc330-98g-heldout-condition-metrics.csv').open() as f: condition_rows=list(csv.DictReader(f))
for row in condition_rows: row['equal_episode_rmse_rad']=float(row['equal_episode_rmse_rad'])
C={'physical':'#1d5e8a','M1':'#159b80','M2':'#9b4a9a','external':'#4f545b','reference':'#d29000'}
def savefig(fig,name):
    for ext in ('png','svg','pdf'): fig.savefig(MEDIA/(name+'.'+ext),dpi=180,bbox_inches='tight',facecolor='white')
    plt.close(fig)

def episode_figure(f):
    d=tables[f];t=d['time_s']
    fig,(a,b)=plt.subplots(2,1,figsize=(11.7,7.8),sharex=True,gridspec_kw={'height_ratios':[2.15,1]},layout='constrained')
    a.plot(t,d['external_goal_rad'],ls='--',lw=1,color=C['external'],label='External goal $q_d$')
    a.plot(t,d['internal_position_reference_rad'],ls=':',lw=1.6,color=C['reference'],label='Internal reference $q_r$')
    a.plot(t,d['physical_position_rad'],lw=2,color=C['physical'],label='Physical position $y_q$')
    a.plot(t,d['simulated_M1_position_rad'],lw=1.3,color=C['M1'],label='M1 integral fit')
    a.plot(t,d['simulated_M2_position_rad'],lw=1.3,color=C['M2'],label='M2 output-error fit')
    all_position=np.concatenate([d[k] for k in ('external_goal_rad','internal_position_reference_rad','physical_position_rad','simulated_M1_position_rad','simulated_M2_position_rad')])
    a.set_ylim(float(all_position.min())-.04,float(all_position.max())+.22)
    a.set_ylabel('Joint position (rad)');a.grid();a.legend(ncol=3,loc='upper center',bbox_to_anchor=(0.5,1.01))
    a.set_title(f'XC330 98 g campaign · H1 · {f} · P06 composite · R01',pad=24,weight='semibold')
    for method in ('M1','M2'):
        r=next(x for x in metrics if x['fixture']==f and x['method']==('method1' if method=='M1' else 'method2'))
        b.plot(t,d[method+'_residual_rad'],color=C[method],lw=1.3,label=f'{method} RMSE = {r["rmse_rad"]:.6f} rad')
    b.axhline(0,color='#66737b',lw=0.8);b.set_ylabel('Simulation − physical (rad)');b.set_xlabel('Time from processed active episode start (s)');b.grid();b.legend(ncol=2,loc='upper center',bbox_to_anchor=(0.5,1.0))
    all_residual=np.concatenate([d['M1_residual_rad'],d['M2_residual_rad']])
    b.set_ylim(float(all_residual.min())-.005,float(all_residual.max())+.025)
    a.set_xlim(t[0],t[-1]);savefig(fig,f'xc330-H1-{f}-P06')
for f in ('B1','G1'): episode_figure(f)

# Side-by-side comparison preserves H1, P06 and R01 while changing fixture.
fig,axs=plt.subplots(2,2,figsize=(12.8,8.0),sharex='col',sharey='row',gridspec_kw={'height_ratios':[1.5,1]},layout='constrained')
for col,f in enumerate(('B1','G1')):
    d=tables[f];t=d['time_s'];a=axs[0,col];b=axs[1,col]
    a.plot(t,d['internal_position_reference_rad'],color=C['reference'],ls=':',lw=1.5,label='Internal reference')
    a.plot(t,d['physical_position_rad'],color=C['physical'],lw=2,label='Physical')
    for method in ('M1','M2'):
        a.plot(t,d[f'simulated_{method}_position_rad'],color=C[method],lw=1.2,label=method)
        rmse=next(r['rmse_rad'] for r in metrics if r['fixture']==f and r['method']==('method1' if method=='M1' else 'method2'))
        b.plot(t,d[f'{method}_residual_rad'],color=C[method],lw=1.2,label=f'{method}: {rmse:.6f} rad')
    a.set_title(f'{f}: '+('balanced, −80 / +80 mm' if f=='B1' else 'eccentric, +60 / +100 mm'),weight='semibold',pad=10)
    b.axhline(0,lw=0.7,color='#66737b');a.grid();b.grid();b.legend(loc='upper right',fontsize=10)
    b.set_xlabel('Time (s)');a.set_xlim(t[0],t[-1])
axs[0,0].set_ylabel('Joint position (rad)');axs[1,0].set_ylabel('Simulation − physical (rad)')
fig.suptitle('Same controller and profile: H1 · P06 · R01 · 98 g per fixture',fontsize=17,weight='semibold')
handles,labels=axs[0,0].get_legend_handles_labels();fig.legend(handles,labels,ncol=4,loc='outside lower center',frameon=False)
savefig(fig,'xc330-matched-P06')

# Separate matched P06 and unmatched profile-mixture summaries explicitly.
fig,axs=plt.subplots(1,2,figsize=(12.8,5.6),sharey=True,layout='constrained')
for a,h in zip(axs,('H1','H2')):
    labels=['B1\nP06\n5 repeats','G1\nP06\n5 repeats','G1\nP07\n5 repeats','G1\nP06 + P07\n10 episodes']
    keys=[('B1','P06'),('G1','P06'),('G1','P07'),('G1','P06+P07')]
    x=np.arange(4);width=.34
    for j,method in enumerate(('method1','method2')):
        vals=[next(r['equal_episode_rmse_rad'] for r in condition_rows if r['controller']==h and r['method']==method and (r['fixture'],r['profiles'])==k) for k in keys]
        bars=a.bar(x+(j-.5)*width,vals,width,color=C['M1' if method=='method1' else 'M2'],label='M1 integral' if j==0 else 'M2 output-error')
        for bar,v in zip(bars,vals):a.text(bar.get_x()+bar.get_width()/2,v+0.0005,f'{v:.4f}',ha='center',va='bottom',fontsize=9)
    a.set_xticks(x,labels);a.set_title(h+' fixed controller context',weight='semibold');a.grid(axis='y');a.axvline(1.5,color='#9ba5ad',ls='--',lw=1);a.set_ylim(0,.045)
axs[0].set_ylabel('Mean of episode position RMSEs (rad)')
fig.suptitle('Held-out error by condition · 98 g campaign\nMatched P06 groups and different profile mixtures are shown separately',fontsize=16,weight='semibold')
fig.legend(*axs[0].get_legend_handles_labels(),ncol=2,loc='outside lower center',frameon=False)
savefig(fig,'xc330-condition-means')

print("Saved four existing plot variants to",MEDIA)
