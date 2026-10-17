"""Generate the Class05 teaching figures. Pass a local licensed MiSans font folder.
From resources/class05: python code/draw_figures.py --font-dir /path/to/fonts
Data plots use bundled CSVs; diagrams and matrix example are conceptual.
"""
from pathlib import Path
import sys,argparse,csv,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'source'))
from figure_typography import apply_publication_style
p=argparse.ArgumentParser();p.add_argument('--font-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,default=R/'media');a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
font=apply_publication_style([a.font_dir/'MiSans-Regular.ttf',a.font_dir/'MiSans-Semibold.ttf'])
B='#0072B2';O='#D55E00';K='#243448';G='#667785'
def box(ax,x,y,w,h,text,color=B):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.015',facecolor='#F2F6F8',edgecolor=color,lw=1.2));ax.text(x+w/2,y+h/2,text,ha='center',va='center',color=K)
def arrow(ax,start,end):ax.add_patch(FancyArrowPatch(start,end,arrowstyle='-|>',mutation_scale=13,lw=1.2,color=G))
def canvas():
 f,ax=plt.subplots(figsize=(10.8,4.5));ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off');return f,ax
S=json.loads((R/'results/lesson-summary.json').read_text());params=list(csv.DictReader((R/'data/fitted_parameters.csv').open()));tr=list(csv.DictReader((R/'data/paired-trace.csv').open()))
for variant,fs in [('classroom',13),('paper',9)]:
 plt.rcParams.update({'font.family':'MiSans','font.size':fs,'axes.labelsize':fs,'xtick.labelsize':fs-1,'ytick.labelsize':fs-1,'legend.fontsize':fs-1,'pdf.fonttype':42,'svg.fonttype':'none'})
 def save(fig,name):
  fig.tight_layout(pad=1.5)
  if variant=='paper':fig.set_size_inches(7.165,3.4)
  for ext in ['png','pdf','svg']:
   dst=a.output_dir/f'{name}-{variant}.{ext}';fig.savefig(dst,dpi=240 if variant=='classroom' else 450,facecolor='white')
   if ext=='svg':dst.write_text('\n'.join(l.rstrip() for l in dst.read_text().splitlines())+'\n')
  plt.close(fig)
 f,ax=canvas();box(ax,.03,.64,.24,.24,'One actuator\nOne fixture');box(ax,.38,.64,.24,.24,'16 independent\nfixtures');box(ax,.73,.64,.24,.24,'Connected robot\nCoupled joints')
 arrow(ax,(.28,.76),(.36,.76));arrow(ax,(.63,.76),(.71,.76))
 ax.text(.15,.40,'Device + controller\n+ fixture + task',ha='center');ax.text(.5,.40,'Motor identity\nBus / supply / clocks',ha='center');ax.text(.85,.40,'Configuration\nInertia / contact',ha='center')
 ax.text(.5,.10,'Each change needs its own evidence; actuator count alone does not establish coupling.',ha='center',fontsize=fs-1)
 save(f,'evidence-scale')
 f,ax=canvas();box(ax,.04,.60,.25,.25,'Logged internal\nreferences');box(ax,.38,.60,.25,.25,'Actuator model\n+ rigid fixture');box(ax,.72,.60,.24,.25,'Predicted\nencoder angle');arrow(ax,(.30,.72),(.36,.72));arrow(ax,(.64,.72),(.70,.72))
 box(ax,.14,.12,.72,.24,'Outside this replay: request-to-reference generation,\nshared electrical supply, bus scheduling and rack flexibility',O)
 save(f,'replay-boundary')
 f,ax=canvas();box(ax,.02,.64,.27,.24,'Recent reference error\n+ joint velocity');box(ax,.37,.64,.25,.24,'Learned actuator\nmapping');box(ax,.71,.64,.27,.24,'Predicted torque\ninto mechanics');arrow(ax,(.30,.76),(.35,.76));arrow(ax,(.63,.76),(.69,.76))
 ax.text(.5,.43,'Supervised actuator model: predicts actuation',ha='center',weight='semibold')
 box(ax,.16,.07,.68,.22,'Control policy: observes the task and chooses targets\nA separate mapping, with a separate evaluation',O)
 save(f,'neural-actuator')
 f,ax=canvas();box(ax,.03,.63,.25,.22,'30 held-out events');box(ax,.38,.63,.25,.22,'16 motors / event');box(ax,.73,.63,.24,.22,'480 motor records');arrow(ax,(.29,.74),(.36,.74));arrow(ax,(.64,.74),(.71,.74))
 ax.text(.5,.39,'Two predictions per record: baseline and fitted',ha='center');ax.text(.5,.19,'960 scored rows ≠ 960 physical trials',ha='center',weight='semibold',color=O)
 save(f,'experiment-units')
 f,ax=plt.subplots(figsize=(10.8,4.5));x=np.arange(16)
 for j,(c,col) in enumerate([('H1',B),('H2',O)]):
  cells=[v for v in S['cells'] if v['controller']==c];ax.bar(x+(j-.5)*.36,[v['fitted'] for v in cells],.36,label=c,color=col)
 ax.set(xlabel='Motor ID (categorical)',ylabel='Mean held-out position RMSE (rad)',xticks=x,ylim=(0,.032));ax.legend(frameon=False,ncol=2);ax.spines[['top','right']].set_visible(False);save(f,'population-errors')
 f,ax=plt.subplots(figsize=(10.8,4.5))
 for c,col,marker in [('H1',B,'o'),('H2',O,'s')]:
  rr=[v for v in params if v['controller_id']==c];ax.scatter([int(v['motor_id']) for v in rr],[float(v['armature_kg_m2'])*1000 for v in rr],label=c,color=col,marker=marker,s=45)
 ax.set(xlabel='Motor ID (categorical)',ylabel='Effective armature (10⁻³ kg m²)',xticks=x);ax.legend(frameon=False,ncol=2);ax.spines[['top','right']].set_visible(False);save(f,'effective-armature')
 f,axes=plt.subplots(2,1,figsize=(10.8,6.5),sharex=True)
 for ax,m in zip(axes,[0,9]):
  rr=[r for r in tr if int(r['motor_id'])==m];tt=[float(r['time_s']) for r in rr]
  for key,label,col,style in [('hardware_position_rad','Encoder',K,'-'),('synthetic_baseline_position_rad','Baseline',O,'--'),('hardware_fitted_position_rad','Fitted',B,'-')]:ax.plot(tt,[float(r[key]) for r in rr],label=label,color=col,ls=style,lw=1.3)
  ax.set(ylabel='Position (rad)',title=f'Motor {m}');ax.spines[['top','right']].set_visible(False)
 axes[0].legend(ncol=3,frameon=False,loc='upper left');axes[-1].set_xlabel('Recorded time (s)');save(f,'paired-traces')
 f,ax=canvas();box(ax,.03,.64,.36,.23,'Encoder reading\n+ sign / zero / units');box(ax,.61,.64,.36,.23,'Camera → marker pose\n+ calibration / body transform');arrow(ax,(.22,.61),(.40,.33));arrow(ax,(.78,.61),(.60,.33));box(ax,.21,.07,.58,.25,'Common joint angle and clock\nThen compare, including uncertainty');save(f,'measurement-chain')
(a.output_dir/'figure-font-check.json').write_text(json.dumps(font,indent=2)+'\n')
