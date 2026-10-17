"""Recreate paper and classroom figures from the retained inputs."""
import json,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import FancyArrowPatch,Rectangle
from course_lab import ROOT,load,response
for name in ('Regular','Semibold'):fm.fontManager.addfont(str(ROOT/f'source/fonts/MiSans-{name}.ttf'))
font=fm.FontProperties(fname=str(ROOT/'source/fonts/MiSans-Regular.ttf')).get_name()
if font!='MiSans':raise RuntimeError(f'Unexpected font: {font}')
for weight in ('normal','semibold'):
 resolved=Path(fm.findfont(fm.FontProperties(family=['MiSans'],weight=weight),fallback_to_default=False))
 if 'MiSans' not in resolved.name:raise RuntimeError(f'Font substitution: {resolved}')
plt.rcParams.update({'font.family':font,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,'lines.linewidth':.8,'mathtext.fontset':'custom','mathtext.rm':'MiSans','mathtext.it':'MiSans','mathtext.bf':'MiSans','mathtext.fallback':None})
C={'command':'#333333','weighted':'#0072B2','light':'#D55E00','baseline':'#888888','corrected':'#009E73'}
P=ROOT/'media';P.mkdir(exist_ok=True)
variant=sys.argv[1] if len(sys.argv)>1 else 'paper';classnum=int(json.loads((ROOT/'class.json').read_text())['number']);fs=7 if variant=='paper' else 12
plt.rcParams.update({'font.size':fs,'axes.labelsize':fs,'xtick.labelsize':fs,'ytick.labelsize':fs,'legend.fontsize':fs,'axes.titlesize':fs,'legend.frameon':False})
W=182/25.4 if variant=='paper' else 11.5

def save(fig,name):
 fig.tight_layout(pad=1.1)
 for ext in ('png','pdf','svg'):fig.savefig(P/f'{name}-{variant}.{ext}',dpi=450 if variant=='paper' else 180)
 plt.close(fig)
def label(ax,s):ax.text(0,1.06,s,transform=ax.transAxes,fontweight='semibold')

def actuator_chain():
 fig,ax=plt.subplots(figsize=(W,W*.29));ax.set(xlim=(0,10),ylim=(0,2));ax.axis('off')
 blocks=[('Command\nu',.1),('Internal reference\nr',2.65),('Controller + motor\nactuator effort',5.2),('Mechanism\nmeasured q',7.75)]
 for text,x in blocks:
  ax.add_patch(Rectangle((x,.8),2.1,.8,fill=False,lw=.8));ax.text(x+1.05,1.2,text,ha='center',va='center')
 for x in (2.2,4.75,7.3):ax.annotate('',xy=(x+.45,1.2),xytext=(x,1.2),arrowprops={'arrowstyle':'->'})
 ax.plot([8.8,8.8,6.2],[.8,.48,.48],color='#333333',lw=.8);ax.annotate('',xy=(6.2,.8),xytext=(6.2,.48),arrowprops={'arrowstyle':'->'});ax.text(7.4,.25,'Feedback path',ha='center')
 save(fig,'actuator-chain')

def recorded_step():
 fig,axes=plt.subplots(1,2,figsize=(W,W*.37))
 for mid,name in [(1,'weighted'),(2,'light')]:
  a=load('step',mid);a=a[np.isclose(a['amplitude'],30)]
  axes[0].plot(a['time'],a['pos_deg']-180,color=C[name],ls='-' if mid==1 else '-.',label=f'{name}, ID {mid}')
  if mid==1:axes[0].plot(a['time'],a['goal_deg']-180,'--',color=C['command'],label='Command')
  dt=np.diff(a['time']);axes[1].plot(a['time'][1:],dt*1000,color=C[name],ls='-' if mid==1 else '-.')
 axes[0].set(xlabel='Block time (s)',ylabel='Position from centre (deg)');axes[0].legend();axes[1].set(xlabel='Block time (s)',ylabel='Sample interval (ms)');label(axes[0],'a');label(axes[1],'b');save(fig,'recorded-step')

def frequency():
 fig,axes=plt.subplots(2,1,figsize=(W,W*.64),sharex=True)
 for mid,name in [(1,'weighted'),(2,'light')]:
  a=load('sine',mid);f,h=response(a,a['pos_deg']);axes[0].semilogx(f,20*np.log10(abs(h)),'o-' if mid==1 else 's--',color=C[name],label=f'{name}, ID {mid}');axes[1].semilogx(f,-np.rad2deg(np.angle(h)),'o-' if mid==1 else 's--',color=C[name])
 axes[0].axhline(-3,ls=':',color=C['baseline']);axes[0].set(ylabel='Gain (dB)');axes[1].set(xlabel='Command frequency (Hz)',ylabel='Phase lag (deg)');axes[0].legend();label(axes[0],'a');label(axes[1],'b');save(fig,'frequency-response')

def geometry():
 fig,axes=plt.subplots(1,2,figsize=(W,W*.4))
 ax=axes[0];ax.set_aspect('equal');ax.set(xlim=(-.3,1.25),ylim=(-.3,1.15));ax.axis('off')
 ax.plot([0,.95],[0,.55],color=C['weighted'],lw=3);ax.scatter([0,.95],[0,.55],s=[30,100],color=C['weighted']);ax.annotate('Hinge O',xy=(0,0),xytext=(-.25,-.22));ax.annotate('Centre of mass C',xy=(.95,.55),xytext=(.2,1.));ax.annotate('',xy=(.95,-.05),xytext=(.95,.5),arrowprops={'arrowstyle':'->','color':C['light']});ax.text(1.,.15,'mg');ax.text(.3,.35,'r');ax.annotate('',xy=(.55,0),xytext=(0,0),arrowprops={'arrowstyle':'->'});ax.annotate('',xy=(0,.55),xytext=(0,0),arrowprops={'arrowstyle':'->'});ax.text(.55,-.13,'x');ax.text(-.15,.55,'y');ax.text(.35,-.28,'Schematic vertical-plane example')
 m=json.loads((ROOT/'results/inspect.json').read_text());ax=axes[1];mass=[m[str(i)]['moving_mass_kg']*1000 for i in (1,2)];J=[m[str(i)]['generalized_inertia_kg_m2']*1e6 for i in (1,2)];ax.bar([0,1],mass,color=[C['weighted'],C['light']]);ax.set(xticks=[0,1],xticklabels=['Weighted','Light'],ylabel='CAD moving mass (g)');
 for i in (0,1):ax.text(i,mass[i]+3,f'{mass[i]:.2f}',ha='center')
 label(axes[0],'a');label(axes[1],'b');save(fig,'geometry-mass')

def inertia():
 m=json.loads((ROOT/'results/inspect.json').read_text());fig,ax=plt.subplots(figsize=(W,W*.37));arm=[m[str(i)]['armature_kg_m2']*1e6 for i in (1,2)];rig=[m[str(i)]['generalized_inertia_kg_m2']*1e6-arm[i-1] for i in (1,2)]
 ax.bar([0,1],arm,label='Assumed reflected armature',color=C['baseline']);ax.bar([0,1],rig,bottom=arm,label='CAD mechanism contribution',color=C['weighted']);ax.set(xticks=[0,1],xticklabels=['Weighted','Light'],ylabel='Generalized inertia (10⁻⁶ kg m²)');ax.legend(loc='upper center',bbox_to_anchor=(.5,1.24),ncol=2);save(fig,'inertia-budget')

def sensitivity():
 rows=json.loads((ROOT/'results/sensitivity.json').read_text());fig,ax=plt.subplots(figsize=(W,W*.4));ax.bar(range(4),[r['chirp_rmse_deg'] for r in rows],color=[C['baseline'],C['light'],C['weighted'],C['corrected']]);ax.set(xticks=range(4),xticklabels=['Baseline','2× moving mass','2× armature','0.5× armature'],ylabel='Chirp replay RMSE (deg)');save(fig,'model-sensitivity')

def validation():
 a=load('chirp',1);r=np.load(ROOT/'results/replay.npz');fig,axes=plt.subplots(2,1,figsize=(W,W*.58),sharex=True);sel=(a['time']>=20)&(a['time']<=23)
 axes[0].plot(a['time'][sel],a['pos_deg'][sel]-180,color=C['weighted'],label='Hardware, ID 1')
 for key in ('baseline','corrected'):
  q=r[f'chirp_1_{key}'];axes[0].plot(a['time'][sel],q[sel]-180,ls='--' if key=='baseline' else '-.',color=C[key],label=key.capitalize());axes[1].plot(a['time'][sel],(q-a['pos_deg'])[sel],color=C[key],ls='--' if key=='baseline' else '-.')
 axes[0].set(ylabel='Position from centre (deg)');axes[1].set(xlabel='Recorded block time (s)',ylabel='Replay error (deg)');axes[0].legend(ncol=3,loc='upper left');label(axes[0],'a');label(axes[1],'b');save(fig,'frozen-chirp')

def metrics():
 d=json.loads((ROOT/'results/identify.json').read_text());fig,axes=plt.subplots(1,2,figsize=(W,W*.42))
 for ax,test in zip(axes,('step','chirp')):
  base=[d[str(i)]['frozen_validation'][test]['baseline_rmse_deg'] for i in (1,2)];cor=[d[str(i)]['frozen_validation'][test]['corrected_rmse_deg'] for i in (1,2)];x=np.arange(2);ax.bar(x-.17,base,.34,color=C['baseline'],label='Baseline');ax.bar(x+.17,cor,.34,color=C['corrected'],label='Sine-fitted correction');ax.set(xticks=x,xticklabels=['Weighted','Light'],ylabel=f'{test.capitalize()} RMSE (deg)');
  for i in range(2):ax.text(x[i]+.17,cor[i]+.1,f'{cor[i]:.2f}',ha='center')
 axes[0].legend(loc='upper center',bbox_to_anchor=(.5,1.25),ncol=2);label(axes[0],'a');label(axes[1],'b');save(fig,'validation-metrics')

def rs06():
 a=np.genfromtxt(ROOT/'data/rs06/R02_micro_sines.csv',delimiter=',',names=True);fig,axes=plt.subplots(1,2,figsize=(W,W*.4));sel=(a['time']>=10)&(a['time']<=20)
 axes[0].plot(a['time'][sel],a['q_target'][sel],color=C['command'],ls='--',label='Target');axes[0].plot(a['time'][sel],a['q'][sel],color=C['weighted'],label='Hardware');axes[0].set(xlabel='Time (s)',ylabel='RS06 position (rad)');axes[0].legend();axes[1].plot(a['time'][sel],a['torque'][sel],color=C['light']);axes[1].set(xlabel='Time (s)',ylabel='Torque feedback (N m)');label(axes[0],'a');label(axes[1],'b');save(fig,'rs06-recording')

if classnum==2:actuator_chain();recorded_step();frequency()
elif classnum==3:geometry();inertia();sensitivity()
elif classnum==4:validation();metrics();rs06()
else:raise ValueError(classnum)
print(f'Class {classnum:02d}: {variant} figures generated using {font}')
