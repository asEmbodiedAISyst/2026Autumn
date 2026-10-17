"""Portable plotting functions for the six retained Class08 classroom figures.

These retain the source plotting operations and data selection. Use
../render_class08.py for the public plotting entry point.
"""
from pathlib import Path
import json
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,FancyArrowPatch
from PIL import Image
from figure_typography import apply_publication_style
B='#0072B2';O='#D48020';G='#177E89';K='#303740';GREY='#89939D'
ROOT=None;VARIANT=None
def j(p):return json.loads((ROOT/p).read_text())
def fig(height=2.5,nrows=1,ncols=1):
 scale=1 if VARIANT=='paper' else 1.78
 f,a=plt.subplots(nrows,ncols,figsize=(182/25.4*scale,height*scale),squeeze=False)
 return f,a
def blank(height=2.5):
 f,aa=fig(height);a=aa[0,0];a.axis('off');a.set(xlim=(0,1),ylim=(0,1));return f,a
def box(a,x,y,w,h,text,color=B):
 a.add_patch(Rectangle((x,y),w,h,facecolor=color+'10',edgecolor=color,lw=.8 if VARIANT=='paper' else 1.4))
 a.text(x+w/2,y+h/2,text,ha='center',va='center',wrap=True)
def arrow(a,p,q,color=K):a.add_patch(FancyArrowPatch(p,q,arrowstyle='-|>',mutation_scale=7 if VARIANT=='paper' else 12,color=color,lw=.8 if VARIANT=='paper' else 1.4))
def flow(labels,second=None):
 f,a=blank(1.75);n=len(labels);gap=.02;w=(.92-(n-1)*gap)/n
 for i,t in enumerate(labels):
  x=.04+i*(w+gap);box(a,x,.47,w,.4,t,[B,G,O,K,B][i%5])
  if i<n-1:arrow(a,(x+w+.002,.67),(x+w+gap-.003,.67))
 if second:a.text(.5,.18,second,ha='center',va='center')
 return f
def save(f,name,kind,inputs):
 f.tight_layout(pad=.7)
 # Reserve physical canvas space for labels placed below image axes.
 if name=='arm-poses':
  f.subplots_adjust(bottom=.18,top=.98)
 stem=ROOT/'media'/(name+('-classroom' if VARIANT=='classroom' else ''))
 for ext in ['png','pdf','svg']:f.savefig(stem.with_suffix('.'+ext),dpi=450,bbox_inches=None,facecolor='white')
 plt.close(f)

def arm_poses():
 f,aa=fig(2.6,1,2)
 for a,name,label in zip(aa[0],['zero','home'],['(a) Zero configuration','(b) Working home configuration']):
  a.imshow(Image.open(ROOT/f'data/arm-{name}.png'));a.axis('off');a.text(.5,-.04,label,transform=a.transAxes,ha='center',va='top',fontsize=8 if VARIANT=='paper' else 16,weight='semibold')
 return f
def joint_limits():
 x=j('results/inspection.json');f,aa=fig(2.6);a=aa[0,0]
 for k,row in enumerate(x['joints'][1:4]):
  lo,hi=row['model_range_deg'];sl,sh=row['software_motor_limit_deg'];a.plot([lo,hi],[k+.10]*2,color=GREY,lw=3,label='MJCF range' if k==0 else None)
  a.plot([max(lo,sl),min(hi,sh)],[k-.1]*2,color=B,lw=3,label='Intersection' if k==0 else None);a.plot(row['home_deg'],k,'o',color=O,label='Home' if k==0 else None)
 a.set(yticks=range(3),yticklabels=['joint2','joint3','joint4'],xlabel='Motor/model joint angle (degrees)');a.legend(ncol=3,loc='upper left',bbox_to_anchor=(0,1.22));return f
def joint_response():
 d=pd.read_csv(ROOT/'results/joint2-trace.csv');f,aa=fig(3.2,2,1);a,b=aa[:,0]
 a.plot(d.time_s,d.target_deg,color=B,label='Target');a.plot(d.time_s,d.pre_step_position_deg,'--',color=O,label='Pre-step state');a.set_ylabel('joint2 (degrees)');a.legend(ncol=2)
 b.plot(d.time_s,d.pre_step_position_deg-d.target_deg,color=G);b.set(xlabel='Simulation time (s)',ylabel='State − target (degrees)');return f
def control_clock():
 f,aa=fig(2.3);a=aa[0,0]
 for y,dt,label,color in [(2,.002,'Original: 17 × 2ms = 34ms',GREY),(1,1/510,'Corrected: 17 × 1/510s = 1/30s',B)]:
  t=np.arange(18)*dt*1000;a.plot(t,np.full(18,y),'|',ms=9,color=color);a.text(0,y+.2,label)
 a.axvline(1000/30,color=O,ls='--',label='30Hz boundary');a.set(xlim=(-1,36),ylim=(.5,2.6),yticks=[],xlabel='Elapsed simulation time (ms)');return f

def feedback_loop():
 f=flow(['Target q','Bounded\ncontroller','Multibody\ndynamics','Measured q'],'Feedback and compensation have distinct roles')
 a=f.axes[0];a.plot([.85,.85,.385],[.47,.34,.34],color=K,lw=.8 if VARIANT=='paper' else 1.4);arrow(a,(.385,.34),(.385,.47));return f
