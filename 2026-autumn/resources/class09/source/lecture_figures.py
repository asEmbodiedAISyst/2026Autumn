"""Reproducible Class08–11 illustrations. Run from a class folder:
python source/lecture_figures.py --class-root .
Inputs live in data/, results/ and the retained consolidation package. This script plots only; raw simulation/video inputs are collected separately.
"""
from pathlib import Path
import argparse,json,hashlib,textwrap,re
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,FancyArrowPatch
from matplotlib import font_manager as fm
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
 if name in ['arm-poses','pilot-views','failure-frames']:
  f.subplots_adjust(bottom=.18,top=.98)
 # Native 640px video crops need <=2.13in panels for >=300dpi in paper masters.
 if VARIANT=='paper' and name=='pilot-views':f.subplots_adjust(left=.20,right=.80,wspace=.12)
 if VARIANT=='paper' and name=='failure-frames':f.subplots_adjust(left=.07,right=.93,wspace=.18)
 stem=ROOT/'media'/(name+('-classroom' if VARIANT=='classroom' else ''))
 for ext in ['png','pdf','svg']:f.savefig(stem.with_suffix('.'+ext),dpi=450,bbox_inches=None,facecolor='white')
 plt.close(f)
 if VARIANT=='paper':RECORDS.append({'id':name,'kind':kind,'function':f'main() → specs[{int(ROOT.name[-2:])}] entry {name}','inputs':inputs})

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

def phone_axes():
 f,a=blank(2.35)
 left=['Phone x: top','Phone y: left','Phone z: out of screen'];right=['TCP +y: opening axis','TCP +x: across fingers','TCP −z: opposite approach']
 for i,(l,r) in enumerate(zip(left,right)):
  y=.82-i*.30;box(a,.03,y-.10,.35,.20,l,B);box(a,.59,y-.10,.38,.20,r,G);arrow(a,(.39,y),(.58,y))
 return f
def motion_limit():
 f,aa=fig(2.45);a=aa[0,0];requests=np.linspace(0,40,101);applied=np.minimum(requests,1000*.25/30)
 a.plot(requests,requests,'--',color=GREY,label='Unbounded request');a.plot(requests,applied,color=B,label='Speed-limited step');a.axhline(1000*.25/30,color=O,ls=':',label='8.33mm per nominal tick');a.set(xlabel='Requested displacement in one tick (mm)',ylabel='Commanded displacement (mm)');a.legend();return f
def command_state():
 d=pd.read_csv(ROOT/'data/recorded/circle/frames.csv');f,aa=fig(3.0,1,3);t=d.timestamp;state=d['state.elbow_flex'];action=d['action.elbow_flex']
 aa[0,0].plot(t,state,color=B,label='State');aa[0,0].plot(t,action,'--',color=O,label='Raw action');aa[0,0].set_ylabel('Elbow channel (degrees)');aa[0,0].legend()
 aa[0,1].plot(t,state,color=B);aa[0,1].plot(t,-action,'--',color=O);aa[0,1].set_ylabel('State and motor target (degrees)')
 aa[0,2].plot(t,state+action,color=G);aa[0,2].set_ylabel('State − motor target (degrees)')
 for a in aa[0]:a.set_xlabel('Wall-clock time (s)')
 return f
def stream_record():
 c=pd.read_csv(ROOT/'data/recorded/circle/frames.csv');d=pd.read_csv(ROOT/'data/recorded/dropout/frames.csv');f,aa=fig(3.1,2,1)
 aa[0,0].plot(c.timestamp.iloc[1:],np.diff(c.timestamp)*1000,color=B,label='Recorded intervals');aa[0,0].axhline(1000/30,color=O,ls='--',label='Nominal 30Hz');aa[0,0].set_ylabel('Frame interval (ms)');aa[0,0].legend(ncol=2)
 aa[1,0].plot(d.timestamp,d.phone_age,color=G,label='Phone sample age');aa[1,0].axhline(.25,color=O,ls='--',label='Timeout');aa[1,0].set(xlabel='Wall-clock time (s)',ylabel='Phone age (s)');aa[1,0].legend(ncol=2);return f

def tool_schema():
 f,a=blank(2.2)
 box(a,.03,.58,.27,.28,'Position\n3 values in metres',B);box(a,.36,.58,.27,.28,'Rotation columns\n6 unitless values',G);box(a,.69,.58,.28,.28,'Tool camera\n480 × 640 RGB',O)
 a.text(.33,.30,'9D state/action: [x, y, z, column1, column2]',ha='center');a.text(.5,.08,'Episode frame and tool geometry must agree',ha='center');return f
def learning_records():
 f,a=blank(2.5)
 for y,title,content,c in [(.7,'Demonstration','Observation → selected action',B),(.4,'RL transition','Observation, action, reward, next state',G),(.1,'Evaluation','Frozen policy, conditions, outcome',O)]:
  box(a,.03,y,.25,.23,title,c);box(a,.36,y,.60,.23,content,c);arrow(a,(.29,y+.115),(.35,y+.115))
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
def pilot_views():
 f,aa=fig(2.8,1,2)
 for a,name,label in zip(aa[0],['nominal','turned'],['(a) Episode 0, first frame','(b) Episode 2, first frame']):a.imshow(Image.open(ROOT/f'data/pilot-{name}.png'));a.axis('off');a.text(.5,-.04,label,transform=a.transAxes,ha='center',va='top',fontsize=8 if VARIANT=='paper' else 16,weight='semibold')
 return f
def split_episodes():
 f,a=blank(2.0)
 for k,(label,c) in enumerate([('Training\nepisodes A–F',B),('Validation\nepisodes G–H',G),('Test\nepisodes I–J',O)]):box(a,.03+k*.33,.44,.28,.40,label,c)
 a.text(.5,.17,'Keep all frames from one episode together',ha='center');return f
def action_chunks():
 f,aa=fig(2.4);a=aa[0,0]
 for y,n,c in [(2,1,B),(1,10,G),(0,30,O)]:
  t=np.arange(0,61,n)/30;a.plot(t,np.full(len(t),y),'o-',color=c,label=f'Execute {n} steps before replan')
 a.set(xlabel='Control time (s)',yticks=[]);a.legend(loc='upper left',bbox_to_anchor=(0,1.4));return f

def evidence_checks():return flow(['Interface','Full-state\nreplay','Open-loop\nprediction','Shadow\ncheck','Physical\nrollout'],'Different checks answer different questions; hardware evidence stays distinct')
def replay_components():return flow(['Model +\ntimestep','Integration\nstate','Same joint\ncommands','Repeated\ntrajectory'],'Constructed replay: 60 steps, maximum absolute state difference = 0')
def outcomes():
 x=j('results/recorded-policy-summary.json');p=ROOT/'consolidation/package/additional_material/data/videos/results_act_ip17_cube300_handheld_060000_pusher_n100.json';es=json.loads(p.read_text())['episodes'];f,aa=fig(2.6,1,2)
 a=aa[0,0];v=np.array([e['success'] for e in es]).reshape(5,10);a.imshow(v,cmap=matplotlib.colors.ListedColormap(['#E9EDF0',B]),vmin=0,vmax=1)
 for row in range(5):
  for col in range(10):a.text(col,row,'✓' if v[row,col] else '×',ha='center',va='center',color='white' if v[row,col] else K)
 a.set(xticks=[],yticks=[]);a.set_xlabel('50 stored outcomes: blue/check = success')
 a=aa[0,1];lo,hi=x['wilson_95_descriptive_interval'];a.errorbar([.64],[0],xerr=[[.64-lo],[hi-.64]],fmt='o',color=G,capsize=3);a.set(xlim=(0,1),ylim=(-.4,.4),yticks=[],xlabel='Stored success fraction');a.text(.64,.18,'32/50',ha='center');return f
def failure_frames():
 f,aa=fig(2.35,1,3)
 for a,name,label in zip(aa[0],['start','middle','end'],['(a) Frame 0','(b) Frame 225','(c) Frame 449']):im=Image.open(ROOT/f'data/video-frame-{name}.png');a.imshow(im.crop((0,0,im.width//2,im.height)));a.axis('off');a.text(.5,-.04,label,ha='center',transform=a.transAxes,va='top',fontsize=8 if VARIANT=='paper' else 16,weight='semibold')
 return f
def reference_choice():
 t=np.arange(11);r_command=[];r_measured=[];xc=xm=0.;rc=rm=0.
 for k in t:
  r_command.append(xc);r_measured.append(xm);rc+=.01;rm=xm+.01;xc+=.5*(rc-xc);xm+=.5*(rm-xm)
 f,aa=fig(2.5);a=aa[0,0];a.plot(t,np.array(r_command)*1000,'o-',color=B,label='Delta from prior command');a.plot(t,np.array(r_measured)*1000,'s--',color=O,label='Delta from measured pose');a.set(xlabel='Toy control tick',ylabel='Toy measured position (mm)');a.legend();return f

def main():
 global ROOT,VARIANT
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--class-root',type=Path,default=Path(__file__).resolve().parents[1]);a=ap.parse_args();ROOT=a.class_root.resolve();n=int(ROOT.name[-2:]);receipt=apply_publication_style([ROOT/'source/fonts/MiSans-Regular.ttf',ROOT/'source/fonts/MiSans-Semibold.ttf'],ROOT/'source/publication.mplstyle')
 specs={8:[('arm-poses',arm_poses,'native simulation render',['data/arm-zero.png','data/arm-home.png']),('model-pipeline',lambda:flow(['URDF\nmechanism','MJCF\nactuation','Configured\nsimulation','Logged\nexperiment']),'schematic',[]),('joint-limits',joint_limits,'compiled model and code declarations',['results/inspection.json']),('control-loop',feedback_loop,'schematic',[]),('joint-response',joint_response,'new simulation trace',['results/joint2-trace.csv']),('control-clock',control_clock,'constructed arithmetic',[])],9:[('teleop-path',lambda:flow(['Phone pose','Clutch +\nframes','Limits +\nIK','Joint\nactuation','Recorder']),'schematic',[]),('phone-axes',phone_axes,'declared coordinate mapping',[]),('motion-limit',motion_limit,'constructed speed-bound arithmetic',[]),('command-state',command_state,'recorded local fake-phone simulation',['data/recorded/circle/frames.csv']),('stream-record',stream_record,'recorded wall-clock and stream-loss evidence',['data/recorded/circle/frames.csv','data/recorded/dropout/frames.csv']),('recording-order',lambda:flow(['Observe\nstate k','Choose\naction k','Save row\nand images','Step\nphysics'],'This recorder stamps the row after image rendering; it is not a hardware synchronization guarantee'),'schematic from code',[])],10:[('learning-records',learning_records,'conceptual comparison',[]),('tool-schema',tool_schema,'declared feature schema',[]),('pilot-views',pilot_views,'supplied simulation video frames',['data/pilot-nominal.png','data/pilot-turned.png']),('pilot-audit',pilot_audit,'computed current audit',['results/pilot-audit.json']),('pilot-reach',pilot_reach,'recorded canonical-frame IK check',['data/target-frame-reachability.txt']),('episode-splits',split_episodes,'illustrative split; not an actual dataset partition',[]),('action-chunks',action_chunks,'constructed replan timing example',[])],11:[('evidence-checks',evidence_checks,'conceptual progression',[]),('replay-components',replay_components,'constructed full-state replay',['data/class11-full-state-replay.json']),('stored-outcomes',outcomes,'recorded evaluation with descriptive Wilson interval',['results/recorded-policy-summary.json']),('failure-frames',failure_frames,'selected supplied failure video frames',['data/video-frame-start.png','data/video-frame-middle.png','data/video-frame-end.png']),('reference-choice',reference_choice,'constructed one-dimensional lag model; not robot data',[]),('next-experiment',lambda:flow(['Observed\nfailure','Competing\nhypotheses','One changed\nfactor','Measured\nprediction','Update\nclaim']),'conceptual experiment design',[])]}
 for VARIANT in ['paper','classroom']:
  plt.rcParams.update({'font.size':7 if VARIANT=='paper' else 14,'axes.labelsize':7 if VARIANT=='paper' else 14,'xtick.labelsize':7 if VARIANT=='paper' else 13,'ytick.labelsize':7 if VARIANT=='paper' else 13,'legend.fontsize':7 if VARIANT=='paper' else 12,'lines.linewidth':.8 if VARIANT=='paper' else 1.5,'axes.linewidth':.6 if VARIANT=='paper' else 1.1})
  for name,fn,kind,inputs in specs[n]:save(fn(),name,kind,inputs)
 (ROOT/'evidence/figure-fonts.json').write_text(json.dumps(receipt,indent=2));(ROOT/'evidence/figures.json').write_text(json.dumps(RECORDS,indent=2));print('Rendered',len(specs[n]),'figures in both sizes')
if __name__=='__main__':main()
