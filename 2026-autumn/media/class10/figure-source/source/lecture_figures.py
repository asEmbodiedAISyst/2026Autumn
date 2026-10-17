"""Portable Class 10 classroom plotting subset.

Drawing functions are retained from the course source. The portable entry point
sets ROOT and VARIANT and supplies external licensed MiSans font files.
"""
from pathlib import Path
import json, re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch
from PIL import Image
from figure_typography import apply_publication_style
B='#0072B2';O='#D48020';G='#177E89';K='#303740';GREY='#89939D'
ROOT=None;VARIANT=None;RECORDS=[]

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




def learning_records():
 f,a=blank(2.5)
 for y,title,content,c in [(.7,'Demonstration','Observation → selected action',B),(.4,'RL transition','Observation, action, reward, next state',G),(.1,'Evaluation','Frozen policy, conditions, outcome',O)]:
  box(a,.03,y,.25,.23,title,c);box(a,.36,y,.60,.23,content,c);arrow(a,(.29,y+.115),(.35,y+.115))
 return f


def tool_schema():
 f,a=blank(2.2)
 box(a,.03,.58,.27,.28,'Position\n3 values in metres',B);box(a,.36,.58,.27,.28,'Rotation columns\n6 unitless values',G);box(a,.69,.58,.28,.28,'Tool camera\n480 × 640 RGB',O)
 a.text(.33,.30,'9D state/action: [x, y, z, column1, column2]',ha='center');a.text(.5,.08,'Episode frame and tool geometry must agree',ha='center');return f


def pilot_views():
 f,aa=fig(2.8,1,2)
 for a,name,label in zip(aa[0],['nominal','turned'],['(a) Episode 0, first frame','(b) Episode 2, first frame']):a.imshow(Image.open(ROOT/f'data/pilot-{name}.png'));a.axis('off');a.text(.5,-.04,label,transform=a.transAxes,ha='center',va='top',fontsize=8 if VARIANT=='paper' else 16,weight='semibold')
 return f


def pilot_audit():
 rows=j('results/pilot-audit.json')['episodes'];x=np.array([q['episode_index'] for q in rows]);f,aa=fig(2.7,1,3)
 aa[0,0].bar(x,[q['frames'] for q in rows],color=B);aa[0,0].set_ylabel('Saved frames')
 aa[0,1].bar(x,[q['peak_command_speed'] for q in rows],color=G);aa[0,1].axhline(.25,color=O,ls='--');aa[0,1].set_ylabel('Peak commanded speed (m/s)')
 aa[0,2].bar(x,np.array([q['final_recorded_distance_m'] for q in rows])*1000,color=B);aa[0,2].axhline(15,color=O,ls='--');aa[0,2].set_ylabel('Final saved distance (mm)')
 for a in aa[0]:a.set(xticks=[0,2,4,6,8],xlabel='Episode ID')
 return f


def pilot_reach():
 data=[]
 for line in (ROOT/'data/target-frame-reachability.txt').read_text().splitlines():
  m=re.match(r'\s*(\d+)\s+(\d+)\s+(\d+)%\s+([\d.]+)\s+m/s\s+([\d.]+)\s+m/s\s+([\d.]+)\s+deg\s+(-?\d+)\s+~\s+(-?\d+)\s+deg',line)
  if m:data.append([float(v) for v in m.groups()])
 d=np.array(data);f,aa=fig(2.5,1,2);aa[0,0].bar(d[:,0],d[:,2],color=B);aa[0,0].axhline(98,color=O,ls='--');aa[0,0].set_ylabel('Target-frame IK reachability (%)')
 aa[0,1].bar(d[:,0],np.maximum(abs(d[:,-1]),abs(d[:,-2])),color=G);aa[0,1].axhline(60,color=O,ls='--');aa[0,1].set_ylabel('Peak absolute yaw (degrees)')
 for a in aa[0]:a.set_xlabel('Episode ID')
 return f


def split_episodes():
 f,a=blank(2.0)
 for k,(label,c) in enumerate([('Training\nepisodes A–F',B),('Validation\nepisodes G–H',G),('Test\nepisodes I–J',O)]):box(a,.03+k*.33,.44,.28,.40,label,c)
 a.text(.5,.17,'Keep all frames from one episode together',ha='center');return f


def action_chunks():
 f,aa=fig(2.4);a=aa[0,0]
 for y,n,c in [(2,1,B),(1,10,G),(0,30,O)]:
  t=np.arange(0,61,n)/30;a.plot(t,np.full(len(t),y),'o-',color=c,label=f'Execute {n} step{"" if n==1 else "s"} before replan')
 a.set(xlabel='Control time (s)',yticks=[]);a.legend(loc='upper left',bbox_to_anchor=(0,1.4));return f

