"""Generate the Class04 conceptual signal-boundary diagram (not hardware evidence)."""
from pathlib import Path
import argparse,os
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir',type=Path,default=ROOT/'figure-output')
args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR',str(args.output_dir/'.matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib import font_manager
for f in (ROOT/'code/fonts').glob('*.ttf'):
    font_manager.fontManager.addfont(f)
plt.rcParams.update({'font.family':'MiSans','font.size':11,'svg.fonttype':'path'})
fig,ax=plt.subplots(figsize=(12,6.4))
ax.set(xlim=(0,12),ylim=(0,6.4));ax.axis('off')
def box(x,y,w,h,title,detail,fc):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.04,rounding_size=0.07',facecolor=fc,edgecolor='#8091a0',linewidth=1.1))
    ax.text(x+w/2,y+h*.68,title,ha='center',va='center',weight='bold',fontsize=12,color='#172d41')
    ax.text(x+w/2,y+h*.28,detail,ha='center',va='center',fontsize=10,color='#314a5a')
def arrow(a,b,label='',dy=.13):
    ax.annotate('',xy=b,xytext=a,arrowprops={'arrowstyle':'->','lw':1.5,'color':'#536b7b'})
    if label:ax.text((a[0]+b[0])/2,(a[1]+b[1])/2+dy,label,ha='center',va='bottom',fontsize=10,color='#314a5a')
ax.text(.2,6.1,'One recorded experiment and one conditional prediction',fontsize=17,weight='bold',color='#172d41')
ax.text(.2,5.7,'Conceptual signal map · 98 g XC330 campaign · free motion',fontsize=11,color='#536b7b')
box(.25,4.25,2.25,1.0,'External goal','Application request q_d','#f0f3f6')
box(3.4,4.25,3.0,1.0,'Device controller + rig','Internal references; physical motion','#e8f1f8')
box(8.0,4.25,3.55,1.0,'Timestamped motor record','q_d, q_r, v_r and measured y_q','#e8f1f8')
arrow((2.55,4.75),(3.32,4.75))
arrow((6.45,4.75),(7.93,4.75),'Recorded fields')
box(.25,1.8,2.25,1.05,'Replay inputs','Recorded q_r, v_r\nInitial measured state','#f7efd9')
box(3.4,1.8,3.0,1.05,'Fixed controller map','Limited effort from\nsimulated feedback','#f7efd9')
box(8.0,1.8,3.55,1.05,'Reduced MuJoCo model','98 g properties + fitted joint fields','#e7f2ec')
arrow((2.55,2.32),(3.32,2.32))
arrow((6.45,2.32),(7.93,2.32),'Effort')
ax.plot([9.0,9.0,1.38],[4.17,3.2,3.2],color='#a27b19',lw=1.2)
ax.annotate('',xy=(1.38,2.92),xytext=(1.38,3.2),arrowprops={'arrowstyle':'->','lw':1.2,'color':'#a27b19'})
ax.text(3.6,3.5,'Adapter: align, convert, crop; select references',fontsize=10,color='#806116')
ax.annotate('',xy=(5.1,1.7),xytext=(9.3,1.7),arrowprops={'arrowstyle':'->','lw':1.3,'color':'#4a8065','connectionstyle':'arc3,rad=-.3'})
ax.text(7.3,.92,'Simulated state feeds back to the replay controller',ha='center',fontsize=10,color='#376c51')
ax.text(.3,.28,'Comparison: simulated position − measured position. Measured state initializes replay once.',fontsize=11,color='#172d41')
for ext in ('png','svg','pdf'):
    fig.savefig(args.output_dir/('comparison-boundary.'+ext),dpi=180,bbox_inches='tight',facecolor='white')
plt.close(fig)
