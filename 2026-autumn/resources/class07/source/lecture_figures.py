"""Class07 paper/classroom plots and schematic figures. No simulation/training."""
from pathlib import Path
import json,hashlib,csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle
from figure_typography import apply_publication_style
R=Path(__file__).resolve().parents[1];font=apply_publication_style(list((R/'source/fonts').glob('*.ttf')))
S=json.loads((R/'results/perception-summary.json').read_text());BLUE='#0072b2';ORANGE='#d55e00';TEAL='#007c78'
def diagram(ax,labels,links):
 ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
 for x,y,t in labels:ax.text(x,y,t,ha='center',va='center',bbox=dict(boxstyle='round,pad=.5',facecolor='#edf3f5',edgecolor=BLUE))
 for a,b in links:ax.annotate('',xy=b,xytext=a,arrowprops=dict(arrowstyle='->',color='#627786'))
def draw(name):
 fig,ax=plt.subplots(figsize=(182/25.4,3.2))
 if name=='vision-loop':
  diagram(ax,[(.12,.7,'Image + time'),(.38,.7,'Pose estimator'),(.65,.7,'Frame + age check'),(.9,.7,'Policy'),(.52,.18,'Actuators → contacts → cube motion → camera')],[((.23,.7),(.27,.7)),((.49,.7),(.52,.7)),((.78,.7),(.84,.7)),((.9,.58),(.78,.22)),((.26,.18),(.12,.57))])
 elif name=='frame-chain':
  diagram(ax,[(.15,.72,'Object → Camera'),(.5,.72,'Camera → Hand'),(.85,.72,'Object → Hand'),(.5,.25,'T_HO = T_HC × T_CO'),(.5,.05,'Phone world pose alone does not supply object pose')],[((.29,.72),(.35,.72)),((.65,.72),(.72,.72))])
 elif name=='pinhole-points':
  px=np.array(S['projected_pixels']);closed=np.vstack([px,px[0]]);ax.plot(closed[:,0],closed[:,1],'-o',color=BLUE)
  for i,(x,y) in enumerate(px):ax.annotate(str(i),(x,y),xytext=(5,5),textcoords='offset points')
  ax.set(xlim=(0,640),ylim=(480,0),xlabel='Image u (px)',ylabel='Image v (px)');ax.set_aspect('equal');ax.text(12,35,'Synthetic known corners; not image detections',fontsize=7)
 elif name=='pnp-sensitivity':
  plt.close(fig);fig,axes=plt.subplots(1,2,figsize=(182/25.4,3.2));x=[v['pixel_sigma'] for v in S['trials']]
  axes[0].plot(x,[v['median_translation_mm'] for v in S['trials']],'o-',color=BLUE);axes[0].set(xlabel='Corner noise SD (px)',ylabel='Median translation error (mm)')
  axes[1].plot(x,[v['median_rotation_deg'] for v in S['trials']],'o-',color=BLUE,label='Median');axes[1].plot(x,[v['p90_rotation_deg'] for v in S['trials']],'s--',color=ORANGE,label='90th percentile');axes[1].set(xlabel='Corner noise SD (px)',ylabel='Rotation error (deg)');axes[1].legend(frameon=False)
 elif name=='packet-age':
  plt.close(fig);fig,axes=plt.subplots(2,1,sharex=True,figsize=(182/25.4,3.9));p=S['packets'];x=[v['time_s'] for v in p]
  axes[0].plot(x,[v['true_yaw_rad'] for v in p],label='True yaw',color=BLUE);axes[0].plot(x,[v['delivered_yaw_rad'] for v in p],'--',label='Delivered / held',color=ORANGE);axes[0].set(ylabel='Yaw (rad)');axes[0].legend(frameon=False,ncol=2,loc='upper center',bbox_to_anchor=(.5,1.22))
  axes[1].plot(x,[v['age_s']*1000 for v in p],color=TEAL);axes[1].axhline(200,color=ORANGE,ls='--');axes[1].set(xlabel='Simulation time (s)',ylabel='Feature age (ms)')
  for a in axes:a.axvspan(1.75,2.20,alpha=.12,color='#777')
 elif name=='feedback-diagnostic':
  plt.close(fig);fig,axes=plt.subplots(2,1,sharex=True,figsize=(182/25.4,3.9))
  for name,label,color,style in [('baseline','Unchanged input',BLUE,'-'),('delay150','150 ms packet delay',ORANGE,'--'),('dropout30','30% packet loss',TEAL,':')]:
   rows=[json.loads(x) for x in (R/'results'/name/'trace.jsonl').read_text().splitlines()];x=[v['time_s'] for v in rows];axes[0].plot(x,[v['error_rad'] for v in rows],label=label,color=color,ls=style);axes[1].plot(x,[v['feature_age_s']*1000 for v in rows],color=color,ls=style)
  axes[0].axhline(.1,color='#666',ls='--',lw=.6);axes[0].set(ylabel='Orientation error (rad)');axes[0].legend(frameon=False,ncol=1,fontsize=6);axes[1].set(xlabel='Simulation time (s)',ylabel='Packet age (ms)')
 elif name=='observation-interface':
  sizes=[16,16,9,16];labels=['Joint positions','Joint-target error','Pose-error packet','Action history'];start=0
  for size,label,col in zip(sizes,labels,[BLUE,TEAL,ORANGE,'#627786']):
   ax.barh(0,size,left=start,height=.4,color=col);ax.text(start+size/2,0,str(size),ha='center',va='center',color='white');ax.text(start+size/2,-.35,label,ha='center',va='top');start+=size
  ax.set(xlim=(0,57),ylim=(-1,.7));ax.axis('off');ax.text(28.5,.5,'Only indices32–40 are delayed or held',ha='center')
 elif name=='retargeting':
  diagram(ax,[(.2,.75,'Hand landmarks'),(.5,.75,'Task-space objective'),(.8,.75,'Robot joints'),(.5,.35,'Correspondence + scale + limits + optimization'),(.5,.08,'Phone pose → target motion is teleoperation, not finger retargeting')],[((.33,.75),(.36,.75)),((.64,.75),(.70,.75))])
 return fig
names=['vision-loop','frame-chain','pinhole-points','pnp-sensitivity','packet-age','feedback-diagnostic','observation-interface','retargeting']
for suffix,size in [('',7),('-classroom',14)]:
 plt.rcParams.update({'font.family':'MiSans','font.size':size,'axes.labelsize':size,'xtick.labelsize':size,'ytick.labelsize':size,'legend.fontsize':size,'pdf.fonttype':42,'svg.fonttype':'none'})
 for name in names:
  fig=draw(name)
  if suffix:
   fig.set_size_inches(12.75,6.3 if name in ['packet-age','feedback-diagnostic'] else 5.7)
   for t in fig.findobj(matplotlib.text.Text):t.set_fontsize(max(13,t.get_fontsize()))
  fig.tight_layout(pad=1.3)
  for ext in ['png','pdf','svg']:fig.savefig(R/'media'/f'{name}{suffix}.{ext}',dpi=450,bbox_inches=None,facecolor='white')
  plt.close(fig)
inputs=[R/'results/perception-summary.json',R/'results/pnp-trials.csv',*[R/'results'/n/'trace.jsonl' for n in ['baseline','delay150','dropout30']]]
receipt=dict(fonts=font,inputs={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (R/'media').glob('*.*') if p.suffix in ['.png','.pdf','.svg']})
(R/'evidence/figure-provenance.json').write_text(json.dumps(receipt,indent=2));print('Generated8figure sets with paper and classroom exports')
