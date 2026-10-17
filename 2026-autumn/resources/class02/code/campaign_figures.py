"""MiSans paper and classroom figures for the two PhyIntel campaigns."""
import csv
import json
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Rectangle
from phyintel_lab import ROOT, DATA, OUT, load, identity

variant=sys.argv[1] if len(sys.argv)>1 else 'classroom'
if variant not in ('classroom','paper'): raise ValueError(variant)
for weight in ('Regular','Semibold'):
    fm.fontManager.addfont(str(ROOT/f'source/fonts/MiSans-{weight}.ttf'))
family=fm.FontProperties(fname=str(ROOT/'source/fonts/MiSans-Regular.ttf')).get_name()
assert family=='MiSans'
for weight in ('normal','semibold'):
    assert 'MiSans' in Path(fm.findfont(fm.FontProperties(family=family,weight=weight),fallback_to_default=False)).name
size=7 if variant=='paper' else 12
width=182/25.4 if variant=='paper' else 11.5
plt.rcParams.update({'font.family':family,'font.size':size,'axes.labelsize':size,
    'xtick.labelsize':size,'ytick.labelsize':size,'legend.fontsize':size,
    'axes.titlesize':size,'pdf.fonttype':42,'svg.fonttype':'none',
    'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,
    'lines.linewidth':1.0,'legend.frameon':False,'savefig.facecolor':'white'})
C={'hardware':'#0072B2','command':'#333333','reference':'#E69F00',
   'method1':'#D55E00','method2':'#009E73'}
MEDIA=ROOT/'media'
def save(fig,name):
    axes=[ax for ax in fig.axes if ax.axison]
    if len(axes)>1:
        for letter,ax in zip("abcdefghijklmnopqrstuvwxyz",axes):
            ax.text(0,1.035,letter,transform=ax.transAxes,fontweight="semibold",fontsize=size+1)
    fig.tight_layout(pad=1.2)
    for ext in ('png','pdf','svg'):
        fig.savefig(MEDIA/f'{name}-{variant}.{ext}',dpi=450 if variant=='paper' else 180)
    plt.close(fig)

def boundaries():
    fig,axes=plt.subplots(2,1,figsize=(width,width*.6))
    for kind,ax in zip(('xc330','rs06'),axes):
        _,episodes,_,_,_=load(kind)
        e=next(e for e in episodes if identity(kind,e)[0:2]==('H1','B1') and identity(kind,e)[2].startswith('P03'))
        if kind=='xc330':
            ax.plot(e.time,e.external_goal,'--',color=C['command'],label='External goal')
            ax.plot(e.time,e.controller_trajectory,':',color=C['reference'],label='Internal position reference')
        else: ax.plot(e.time,e.command,'--',color=C['command'],label='Applied position command')
        ax.plot(e.time,e.position,color=C['hardware'],label='Measured position')
        ax.set(xlabel='Episode time (s)',ylabel='Position (rad)',title=f'{kind.upper()} · H1 · B1 · P03 · first recorded repeat')
        ax.set_ylim(-.85,1.02)
        ax.legend(loc='upper left',ncol=3 if kind=='xc330' else 2)
    save(fig,'campaign-boundaries')

def matrix():
    fig,axes=plt.subplots(1,2,figsize=(width,width*.4))
    roles=('calibration','model_selection','held_out')
    for kind,ax in zip(('xc330','rs06'),axes):
        _,episodes,_,_,_=load(kind)
        counts=[sum(identity(kind,e)[3]==role for e in episodes) for role in roles]
        bars=ax.bar(range(3),counts,color=['#0072B2','#E69F00','#009E73'],width=.65)
        ax.set(xticks=range(3),xticklabels=['Calibration','Selection','Held out'],ylabel='Complete episodes',title=kind.upper(),ylim=(0,max(counts)*1.25))
        for bar,value in zip(bars,counts):ax.text(bar.get_x()+bar.get_width()/2,value+1,str(value),ha='center')
    save(fig,'campaign-splits')

def inertia():
    fig,axes=plt.subplots(2,2,figsize=(width,width*.65))
    for row,kind in enumerate(('xc330','rs06')):
        records=json.loads((OUT/(kind+'-models.json')).read_text())
        items=[r for r in records if r['controller']=='H1']
        names=[r['fixture'] for r in items]
        ax=axes[row,0]
        fixture=np.array([r['fixture_inertia_kg_m2'] for r in items])
        arm=np.array([r['armature_kg_m2'] for r in items])
        ax.bar(names,fixture*1000,color=C['hardware'],label='Declared fixture')
        ax.bar(names,arm*1000,bottom=fixture*1000,color=C['method2'],label='Released effective armature')
        ax.set(ylabel='Joint inertia (10⁻³ kg m²)',title=kind.upper()+' · H1 · Method 2')
        ax.set_ylim(0,float(max((fixture+arm)*1000))*1.40)
        if row==0:ax.legend(loc='upper left',ncol=1)
        ax=axes[row,1]
        ax.bar(names,[abs(r['gravity_bias_at_zero_Nm']) for r in items],color=C['reference'])
        ax.set(ylabel='Absolute gravity bias at q = 0 (N m)',title='Compiled model check')
    save(fig,'campaign-inertia')

def pipeline():
    fig,ax=plt.subplots(figsize=(width,width*.32))
    ax.set(xlim=(0,10),ylim=(0,2.3));ax.axis('off')
    boxes=[(.1,'Declared boundary\nunits, clocks, fixture'),(2.65,'Calibration\nM1 regression / M2 replay'),(5.2,'Freeze each H model\nselection → held out'),(7.75,'Decision\nresidual + valid scope')]
    for x,text in boxes:
        ax.add_patch(Rectangle((x,.8),2.1,.9,fill=False,lw=.8))
        ax.text(x+1.05,1.25,text,ha='center',va='center')
    for x in (2.2,4.75,7.3):ax.annotate('',xy=(x+.45,1.25),xytext=(x,1.25),arrowprops={'arrowstyle':'->'})
    ax.text(5,.25,'Selection and held-out records never enter the parameter fit',ha='center')
    save(fig,'identification-pipeline')

def replay(kind):
    report=json.loads((OUT/(kind+'-replay.json')).read_text())
    z=np.load(OUT/(kind+'-replay.npz'),allow_pickle=False)
    metrics=[]
    for fixture in ('B1','G1'):
        matches=[row for row in report['metrics'] if row['method']=='method2' and row['controller']=='H1' and row['fixture']==fixture and row['profile']=='P06' and row['split']=='held_out']
        metrics.append(sorted(matches,key=lambda row:row['episode_id'])[0])
    fig,axes=plt.subplots(2,2,figsize=(width,width*.62),sharex='col')
    for col,row in enumerate(metrics):
        i=row['index'];t=z[f'e{i}_time'];q=z[f'e{i}_position']
        axes[0,col].plot(t,z[f'e{i}_reference'],'--',color=C['reference'],label='Controller reference')
        axes[0,col].plot(t,q,color=C['hardware'],label='Hardware')
        for method,ls in [('method1',':'),('method2','-.')]:
            pred=z[f'e{i}_{method}']
            axes[0,col].plot(t,pred,ls,color=C[method],label='M1' if method=='method1' else 'M2')
            axes[1,col].plot(t,pred-q,ls,color=C[method])
        axes[0,col].set(title=f'{kind.upper()} · H1 · {row["fixture"]} · P06',ylabel='Position (rad)')
        axes[1,col].set(xlabel='Episode time (s)',ylabel='Model − hardware (rad)')
        axes[1,col].axhline(0,color='#888888',lw=.5)
    for ax in axes[0,:]:
        lo,hi=ax.get_ylim();ax.set_ylim(lo,hi+.35*(hi-lo))
    axes[0,0].legend(loc='upper left',ncol=2)
    save(fig,kind+'-campaign-replay')

def transfer():
    fig,axes=plt.subplots(1,2,figsize=(width,width*.42),sharey=True)
    for kind,ax in zip(('xc330','rs06'),axes):
        name='fixture-split-metrics.csv' if kind=='xc330' else 'fixture-metrics.csv'
        rows=list(csv.DictReader((DATA/kind/'published'/name).open()))
        for j,h in enumerate(('H1','H2')):
            values=[]
            for fixture in ('B1','G1'):
                r=next(r for r in rows if r.get('controller_id',r.get('controller'))==h and r.get('candidate',r.get('method'))=='method2' and r['split']=='held_out' and r.get('fixture_id',r.get('fixture'))==fixture)
                values.append(1000*float(r['equal_episode_output_gap_rmse_rad']))
            bars=ax.bar(np.arange(2)+(j-.5)*.34,values,.34,label=h,color=C['hardware'] if j==0 else C['method2'])
            for bar,value in zip(bars,values):ax.text(bar.get_x()+bar.get_width()/2,value+.35,f'{value:.2f}',ha='center')
        ax.set(xticks=[0,1],xticklabels=['Balanced B1','Eccentric G1'],ylabel='Mean episode RMSE (mrad)',title=kind.upper()+' · frozen Method 2')
        ax.legend(loc='upper left')
    axes[0].set_ylim(0,28)
    save(fig,'campaign-transfer')


def simulation_check():
    rows=list(csv.DictReader((DATA/'simulation-reference/sim-position-aggregate-metrics.csv').open()))
    fig,ax=plt.subplots(figsize=(width,width*.4))
    splits=('calibration','model_selection','held_out')
    for j,(candidate,title,color) in enumerate([('nominal_model','Nominal', '#888888'),('sim_position_m1','M1', C['method1']),('sim_position_m2','M2', C['method2'])]):
        values=[1000*float(next(r for r in rows if r['candidate']==candidate and r['split']==split)['equal_episode_output_gap_rmse_rad']) for split in splits]
        ax.bar(np.arange(3)+(j-1)*.24,values,.24,color=color,label=title)
    ax.set(xticks=range(3),xticklabels=['Calibration','Selection','Held out'],ylabel='Mean episode gap to Source Model (mrad)',ylim=(0,6.4))
    ax.legend(loc='upper left',ncol=3)
    save(fig,'simulation-method-check')

number=json.loads((ROOT/'class.json').read_text())['number']
if number==2:boundaries();matrix()
elif number==3:inertia()
elif number==4:simulation_check();pipeline();replay('xc330');replay('rs06');transfer()
else:raise ValueError(number)
print(f'Class {number:02d} campaign figures: {variant}, MiSans',flush=True)
