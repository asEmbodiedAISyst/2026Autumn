"""Original Class02 visual explanations. Run: python code/visual_lessons.py classroom|paper.
Schematics are illustrative, not calibrated XC330/RS06 models. Frequency panels
recompute the original recorded-data harmonic estimates through course_lab.response.
"""
from pathlib import Path
import sys,numpy as np,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Rectangle
from course_lab import ROOT,load,response
variant=sys.argv[1] if len(sys.argv)>1 else 'classroom'
assert variant in ('paper','classroom')
for weight in ('Regular','Semibold'):fm.fontManager.addfont(str(ROOT/f'source/fonts/MiSans-{weight}.ttf'))
fs=19 if variant=='classroom' else 7;W=11.5 if variant=='classroom' else 182/25.4
plt.rcParams.update({'font.family':'MiSans','font.size':fs,'axes.labelsize':fs,'axes.titlesize':fs,'xtick.labelsize':fs,'ytick.labelsize':fs,'legend.fontsize':fs,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'legend.frameon':False,'lines.linewidth':1.8})
blue,orange,green='#0072B2','#D55E00','#009E73'
def save(fig,name):
 fig.tight_layout(pad=1.1)
 for ext in ('png','pdf','svg'):fig.savefig(ROOT/f'media/{name}-{variant}.{ext}',dpi=180 if variant=='classroom' else 450)
 plt.close(fig)
def diagram(name,items,subtitle):
 fig,ax=plt.subplots(figsize=(W,W*.36));ax.set(xlim=(0,10),ylim=(0,3));ax.axis('off')
 for i,t in enumerate(items):
  x=.15+i*2.5;ax.add_patch(Rectangle((x,1),2.2,1.4,fill=False,edgecolor=blue));ax.text(x+1.1,1.7,t,ha='center',va='center',fontsize=fs)
  if i<3:ax.annotate('',xy=(x+2.5,1.7),xytext=(x+2.2,1.7),arrowprops={'arrowstyle':'->'})
 ax.text(5,.4,subtitle,ha='center',fontsize=fs*.85);save(fig,name)
diagram('energy-path',['Supply\nvoltage V','Drive + motor\ncurrent i','Transmission\nratio N','Joint + load\nposition q'],'Energy flows through the drive; the position command carries information.')
fig,ax=plt.subplots(figsize=(W,W*.38));e=np.linspace(-.16,.16,401);d=1.579836*e+.202115*.2
ax.plot(e,d,'--',color=orange,label='Requested effort');ax.plot(e,np.clip(d,-.1551,.1551),color=blue,label='Limited model effort');ax.axhline(.1551,color='#777',ls=':');ax.axhline(-.1551,color='#777',ls=':')
for x in [.05,.1]:ax.scatter([x],[np.clip(1.579836*x+.202115*.2,-.1551,.1551)],color=green,s=55)
ax.set(xlabel='Internal position error (rad)',ylabel='Effort (N m)',ylim=(-.25,.33));ax.legend(loc='upper left',ncol=2,fontsize=fs*.85);save(fig,'effort-limit')
t=np.linspace(0,2,600);u=np.where(t>=.2,30,0);rr=30*(1-np.exp(-np.maximum(t-.2,0)/.12));q=30*(1-np.exp(-np.maximum(t-.2,0)/.30))
fig,ax=plt.subplots(figsize=(W,W*.38));ax.plot(t,u,'--',color='#333',label='Host goal u');ax.plot(t,rr,':',color=orange,label='Illustrative reference r');ax.plot(t,q,color=blue,label='Illustrative response q');ax.set(xlabel='Time (s)',ylabel='Position (deg)',ylim=(-2,42));ax.legend(ncol=3,fontsize=fs*.8);save(fig,'three-signals')
fig,ax=plt.subplots(figsize=(W,W*.38));ts=np.array([0,.016,.032,.048,.064,.080,.096]);ys=30*(1-np.exp(-ts/.022));td=np.linspace(0,.096,400)
ax.plot(td,30*(1-np.exp(-td/.022)),color='#888',label='Constructed continuous curve');ax.scatter(ts,ys,color=blue,s=60,label='Samples every 16 ms');ax.set(xlabel='Time (s)',ylabel='Position (deg)',ylim=(-2,43));ax.legend(fontsize=fs*.8);save(fig,'sampling-resolution')
fig,ax=plt.subplots(figsize=(W,W*.38));errors=np.array([0,2,-2,0]);ax.bar(np.arange(1,5),errors,color=blue);ax.axhline(0,color='#555');ax.set(xlabel='Sample index',ylabel='Measured − command (deg)',xticks=[1,2,3,4],ylim=(-3,3.5));ax.text(.03,.92,'Mean = 0 deg; RMSE = 1.414 deg',transform=ax.transAxes,fontsize=fs);save(fig,'error-cancellation')
fig,ax=plt.subplots(figsize=(W,W*.40));ax.axis('off');table=ax.table(cellText=[['Motor 1','Light','Weighted'],['Motor 2','Light','Weighted']],colLabels=['Device','Condition A','Condition B'],loc='center',cellLoc='center');table.auto_set_font_size(False);table.set_fontsize(fs);table.scale(1,2.8);ax.text(.5,.90,'Proposed crossover: each device experiences both loads',ha='center',transform=ax.transAxes,fontsize=fs*.85);ax.text(.5,.06,'Repeat; keep settings fixed; counterbalance order; record temperature and voltage.',ha='center',transform=ax.transAxes,fontsize=fs*.75);save(fig,'load-crossover')
for kind in ('gain','phase'):
 fig,ax=plt.subplots(figsize=(W,W*.40))
 for mid,col,mark in [(1,blue,'o-'),(2,orange,'s--')]:
  a=load('sine',mid);f,h=response(a,a['pos_deg']);yy=20*np.log10(abs(h)) if kind=='gain' else -np.rad2deg(np.angle(h));ax.plot(f,yy,mark,color=col,label=f'{"Weighted" if mid==1 else "Light"}, ID {mid}')
 ax.set(xlabel='Command frequency (Hz)',ylabel='Gain (dB)' if kind=='gain' else 'Phase lag (deg)',xticks=[.1,.5,1,2,3,5],xlim=(0,5.3),ylim=(-3.4,.7) if kind=='gain' else (-5,125));ax.legend(ncol=2,fontsize=fs*.85)
 if kind=='gain':ax.axhline(-3,color='#777',ls=':')
 save(fig,'frequency-'+kind)
