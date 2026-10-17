"""Teaching figures: declared schematics and exact recorded-data selections.
Run from a class package: python code/teaching_figures.py classroom (or paper).
Source data selection and interpretation are documented in media/FIGURE-CODE.md.
"""
from pathlib import Path
import sys,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Circle
from phyintel_lab import ROOT,OUT,load,identity
variant=sys.argv[1] if len(sys.argv)>1 else 'classroom'
assert variant in ('paper','classroom')
for name in ('Regular','Semibold'):fm.fontManager.addfont(str(ROOT/f'source/fonts/MiSans-{name}.ttf'))
size=7 if variant=='paper' else 12; W=182/25.4 if variant=='paper' else 11.5
plt.rcParams.update({'font.family':'MiSans','font.size':size,'axes.labelsize':size,'axes.titlesize':size,'legend.fontsize':size,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'legend.frameon':False,'lines.linewidth':1.2})
C=['#0072B2','#E69F00','#009E73','#D55E00']
def save(fig,name):
 fig.tight_layout(pad=1.2)
 for ext in ('png','pdf','svg'):fig.savefig(ROOT/f'media/{name}-{variant}.{ext}',dpi=450 if variant=='paper' else 180)
 plt.close(fig)
def boundaries():
 for kind in ('xc330','rs06'):
  _,episodes,_,_,_=load(kind)
  e=next(e for e in episodes if identity(kind,e)[:2]==('H1','B1') and identity(kind,e)[2].startswith('P03'))
  fig,ax=plt.subplots(figsize=(W,W*.35))
  if kind=='xc330':
   ax.plot(e.time,e.external_goal,'--',color='#333333',label='External goal');ax.plot(e.time,e.controller_trajectory,':',color=C[1],label='Internal position reference')
  else:ax.plot(e.time,e.command,'--',color='#333333',label='Applied position command')
  ax.plot(e.time,e.position,color=C[0],label='Measured position');ax.set(xlabel='Episode time (s)',ylabel='Position (rad)',ylim=(-.85,1.05));ax.legend(loc='upper left',ncol=3 if kind=='xc330' else 2)
  save(fig,'boundary-'+kind)
def step():
 from course_lab import load as oldload
 a=oldload('step',1);a=a[np.isclose(a['amplitude'],30)]
 ix=np.flatnonzero(np.diff(a['goal_deg'])>20)[0]+1;t0=a['time'][ix]
 window=(a['time']>=t0-.10)&(a['time']<=t0+.7)
 x=a['time'][window]-t0;y=a['pos_deg'][window]-180;u=a['goal_deg'][window]-180
 base=float(np.median(a['pos_deg'][max(0,ix-5):ix])-180)
 tail=(a['time']>=t0+.45)&(a['time']<=t0+.7);end=float(np.median(a['pos_deg'][tail])-180)
 fig,ax=plt.subplots(figsize=(W,W*.36));ax.plot(x,u,'--',color='#333333',label='Command');ax.plot(x,y,'o-',ms=3,color=C[0],label='Measured samples')
 delta=end-base;ax.axhspan(end-.02*abs(delta),end+.02*abs(delta),color=C[2],alpha=.15,label='Illustrative ±2% band')
 for fraction,color in ((.1,C[1]),(.9,C[3])):
  level=base+fraction*delta;ax.axhline(level,color=color,ls=':',lw=.9)
  after=np.flatnonzero((x>=0)&(y>=level));cross=float(x[after[0]]) if len(after) else None
  ax.text(.38,level,f'{int(fraction*100)}% measured change',va='bottom',color=color)
  if cross is not None:ax.axvline(cross,color=color,ls=':',lw=.9)
 ax.set(xlabel='Time from command transition (s)',ylabel='Position from centre (deg)',xlim=(-.1,.7));ax.legend(loc='center right',ncol=1);save(fig,'step-transition')
def frames():
 fig,ax=plt.subplots(figsize=(W,W*.36));ax.set_aspect('equal');ax.set(xlim=(-.03,.21),ylim=(-.04,.15));ax.axis('off')
 def arrow(a,b,text,color):ax.annotate('',xy=b,xytext=a,arrowprops={'arrowstyle':'->','color':color,'lw':1.4});ax.text(*b,text,color=color,va='bottom')
 arrow((0,0),(.075,0),'xA',C[0]);arrow((0,0),(0,.075),'yA',C[0]);ax.text(-.018,-.014,'A origin')
 arrow((.10,.02),(.10,.075),'xB',C[3]);arrow((.10,.02),(.045,.02),'yB',C[3]);ax.text(.11,.017,'B origin')
 ax.plot([0,.10],[0,.02],':',color='#555555');ax.text(.028,-.022,'Translation: [0.10, 0.02, 0] m')
 ax.scatter([.10],[.10],color=C[2],s=45);ax.annotate('C: child [0.08, 0, 0] m\nparent [0.10, 0.10, 0] m',xy=(.10,.10),xytext=(.13,.10),fontsize=size-1,arrowprops={'arrowstyle':'->'})
 ax.text(.002,.12,'+z: out of page; +q: counterclockwise');arrow((.185,.065),(.185,.015),'Gravity', '#333333');save(fig,'frame-audit')
def fixtures():
 fig,axes=plt.subplots(1,2,figsize=(W,W*.35))
 for ax,places,title in zip(axes,[[-.08,.08],[.06,.10]],['Balanced B1','Eccentric G1']):
  ax.axhline(0,color='#777777',lw=2);ax.scatter([0],[0],color='#333333',s=30)
  for k,x in enumerate(places):ax.scatter([x],[0],color=C[k],s=150);ax.text(x,.013,'46 g',ha='center');ax.text(x,-.017,f'{x*1000:+.0f} mm',ha='center')
  ax.text(0,-.04,'Hinge: x = 0',ha='center');ax.set(xlim=(-.125,.125),ylim=(-.055,.06),title=title);ax.axis('off')
  ax.text(0,.043,'Signed first moments cancel' if title.startswith('Balanced') else 'Signed first moments add',ha='center',fontsize=size-1)
 save(fig,'fixture-design')
def inertia():
 for kind in ('xc330','rs06'):
  rows=[r for r in json.loads((OUT/(kind+'-models.json')).read_text()) if r['controller']=='H1'];names=[r['fixture'] for r in rows]
  fig,axes=plt.subplots(1,2,figsize=(W,W*.35));a=axes[0]
  f=np.array([r['fixture_inertia_kg_m2'] for r in rows])*1000;arm=np.array([r['armature_kg_m2'] for r in rows])*1000
  a.bar(names,f,color=C[0],label='Fixture');a.bar(names,arm,bottom=f,color=C[2],label='Effective armature');a.set(ylabel='Joint inertia (10⁻³ kg m²)',ylim=(0,max(f+arm)*1.45));a.legend(ncol=2,loc='upper left')
  axes[1].bar(names,[abs(r['gravity_bias_at_zero_Nm']) for r in rows],color=C[1]);axes[1].set(ylabel='|Gravity bias at q = 0| (N m)')
  save(fig,'inertia-'+kind)
def regression():
 fig,ax=plt.subplots(figsize=(W,W*.31));ax.axis('off')
 rows=[['1','0.5','0.1','0.2','0.072'],['2','1.0','0.1','0.2','0.077'],['3','0.5','0.2','0.2','0.079']]
 table=ax.table(cellText=rows,colLabels=['Window','Δvelocity (rad/s)','Δposition (rad)','Signed time (s)','Target (N m s)'],loc='center',cellLoc='center');table.auto_set_font_size(False);table.set_fontsize(size);table.scale(1,2)
 for (row,col),cell in table.get_celld().items():cell.set_linewidth(.5);cell.set_edgecolor('#aaaaaa');cell.set_facecolor('#eef4f8' if row==0 else 'white')
 ax.text(.5,.95,'Aθ = target: armature · damping · dry-friction magnitude',ha='center',transform=ax.transAxes)
 ax.text(.5,.03,'Row 2 − Row 1 → armature; Row 3 − Row 1 → damping; substitute → friction',ha='center',transform=ax.transAxes,fontsize=size-1);save(fig,'regression-example')
def candidate():
 fig,axes=plt.subplots(1,2,figsize=(W,W*.35));time=[0,1,2];y=np.array([0,.1,.2]);a=np.array([0,.08,.16]);b=np.array([0,.09,.19])
 for line,label,color,style in [(y,'Recorded (synthetic)','#333333','o--'),(a,'Candidate A',C[3],'s-'),(b,'Candidate B',C[0],'^-')]:axes[0].plot(time,line,style,label=label,color=color)
 axes[0].set(xlabel='Observation index',ylabel='Position (rad)');axes[0].legend(fontsize=size-1)
 axes[1].bar(['A','B'],[np.mean((a-y)**2),np.mean((b-y)**2)],color=[C[3],C[0]]);axes[1].set(ylabel='Calibration MSE (rad²)');save(fig,'candidate-objective')
def replay():
 for kind in ('xc330','rs06'):
  z=np.load(OUT/(kind+'-replay.npz'),allow_pickle=False);report=json.loads((OUT/(kind+'-replay.json')).read_text())
  for fixture in ('B1','G1'):
   rows=[r for r in report['metrics'] if r['method']=='method2' and r['controller']=='H1' and r['fixture']==fixture and r['profile']=='P06' and r['split']=='held_out']
   row=sorted(rows,key=lambda r:r['episode_id'])[0];i=row['index'];t=z[f'e{i}_time'];q=z[f'e{i}_position']
   fig,axes=plt.subplots(1,2,figsize=(W,W*.35))
   axes[0].plot(t,z[f'e{i}_reference'],'--',color='#777777',label='Reference');axes[0].plot(t,q,color=C[0],label='Hardware')
   for method,style,color in [('method1',':',C[3]),('method2','-.',C[2])]:
    pred=z[f'e{i}_{method}'];axes[0].plot(t,pred,style,color=color,label=method.replace('method','M'));axes[1].plot(t,pred-q,style,color=color)
   axes[0].set(xlabel='Episode time (s)',ylabel='Position (rad)');axes[1].set(xlabel='Episode time (s)',ylabel='Model − hardware (rad)');axes[1].axhline(0,color='#888888',lw=.5)
   lo,hi=axes[0].get_ylim();axes[0].set_ylim(lo,hi+.45*(hi-lo));axes[0].legend(loc='upper left',ncol=2,fontsize=size-1)
   save(fig,f'replay-{kind}-{fixture}')
   if kind=='xc330' and fixture=='G1':
    residual=z[f'e{i}_method2']-q;k=int(np.argmax(abs(residual)));start=max(t[0],t[k]-.5);stop=min(t[-1],t[k]+.5)
    fig,axes=plt.subplots(1,2,figsize=(W,W*.35));axes[0].plot(t,residual,color=C[2]);axes[0].axhspan(-.005,.005,color='#777777',alpha=.08);axes[0].axvspan(start,stop,color=C[1],alpha=.18);axes[0].set(xlabel='Full episode time (s)',ylabel='M2 − hardware (rad)')
    mask=(t>=start)&(t<=stop);axes[1].plot(t[mask],residual[mask],color=C[2]);axes[1].scatter([t[k]],[residual[k]],color=C[3]);axes[1].set(xlabel='Selected interval time (s)',ylabel='M2 − hardware (rad)');axes[1].annotate('Maximum |residual|',xy=(t[k],residual[k]),xytext=(.06,.88),textcoords='axes fraction',fontsize=size-1,arrowprops={'arrowstyle':'->'})
    for ax in axes:ax.axhline(0,color='#888888',lw=.5)
    save(fig,'residual-focus')

n=int(json.loads((ROOT/'class.json').read_text())['number'])
if n==2:boundaries();step()
if n==3:frames();fixtures();inertia()
if n==4:regression();candidate();replay()
