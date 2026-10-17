"""Original mathematical teaching illustrations; not new hardware measurements.
Run python code/visual_lessons.py classroom|paper. MiSans fonts bundled locally.
"""
from pathlib import Path
import sys,numpy as np,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
ROOT=Path(__file__).resolve().parents[1]
variant=sys.argv[1] if len(sys.argv)>1 else 'classroom'
assert variant in ('paper','classroom')
for w in ('Regular','Semibold'):fm.fontManager.addfont(str(ROOT/f'source/fonts/MiSans-{w}.ttf'))
fs=19 if variant=='classroom' else 7;W=11.5 if variant=='classroom' else 182/25.4
plt.rcParams.update({'font.family':'MiSans','font.size':fs,'axes.labelsize':fs,'xtick.labelsize':fs,'ytick.labelsize':fs,'legend.fontsize':fs*.85,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'legend.frameon':False,'lines.linewidth':2})
b,o,g='#0072B2','#D55E00','#009E73'
def save(fig,name):
 fig.tight_layout(pad=1.1)
 for ext in ('png','pdf','svg'):fig.savefig(ROOT/f'media/{name}-{variant}.{ext}',dpi=180 if variant=='classroom' else 450)
 plt.close(fig)

r=np.linspace(.02,.12,101)
fig,ax=plt.subplots(figsize=(W,W*.40));ax.plot(r*1000,2*.046*r*r*1e6,color=b,label='Two 46 g point masses');ax.scatter([60,100],2*.046*np.array([.06,.10])**2*1e6,color=o,s=70);ax.set(xlabel='Distance from hinge (mm)',ylabel='Added inertia (10⁻⁶ kg m²)',ylim=(0,1550));ax.legend();save(fig,'radius-squared')
fig,ax=plt.subplots(figsize=(W,W*.40));angle=np.linspace(0,90,100);ax.plot(angle,.00736*9.81*np.sin(np.deg2rad(angle)),color=b);ax.scatter([0,90],[0,.0722016],color=o,s=70);ax.set(xlabel='Axis tilt from vertical (deg)',ylabel='Maximum gravity moment (N m)',xticks=[0,30,60,90]);save(fig,'axis-gravity')
fig,ax=plt.subplots(figsize=(W,W*.45));origin=np.array([.1,.02]);end=origin+np.array([0,.08]);ax.plot([0,.08],[0,0],'o-',color=b,label='Child point before transform');ax.plot([*origin[:1],end[0]],[origin[1],end[1]],'o-',color=o,label='After +90° rotation + translation');ax.scatter(*origin,color=g,s=80);ax.annotate('Child origin',origin,xytext=(.035,.035),fontsize=fs*.8,ha='center',arrowprops={'arrowstyle':'->','color':g});ax.set(xlabel='Parent x (m)',ylabel='Parent y (m)',xlim=(-.01,.15),ylim=(-.01,.14),aspect='equal');ax.legend(loc='upper left',fontsize=fs*.7);save(fig,'frame-transform')
