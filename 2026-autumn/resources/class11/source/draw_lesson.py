"""Reproduce Class11 constructed timing budget and measured reset-comparison figures.
Requires Matplotlib, NumPy and locally licensed MiSans; no training or hardware access.
"""
from pathlib import Path
import argparse,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.text import Text
import numpy as np
ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--fonts',type=Path,required=True);a=ap.parse_args();root=a.root
for name in ['MiSans-Regular.ttf','MiSans-Semibold.ttf']:font_manager.fontManager.addfont(str(a.fonts/name))
plt.rcParams.update({'font.family':'MiSans','font.size':14,'axes.labelsize':14,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
B='#0072B2';G='#177E89';O='#D48020'
def save(f,name):
 f.tight_layout(pad=1.2)
 for suffix,width in [('-classroom',12.8),('',7.17)]:
  ratio=width/f.get_figwidth();f.set_size_inches(width,f.get_figheight()*ratio)
  for t in f.findobj(Text):t.set_fontsize(t.get_fontsize()*ratio)
  for ext in ['png','pdf','svg']:f.savefig(root/'media'/f'{name}{suffix}.{ext}',dpi=300,facecolor='white')
 plt.close(f)
f,aa=plt.subplots(2,1,figsize=(12.8,5.8),gridspec_kw={'height_ratios':[1,1.6]});ax,bx=aa
for left,width,label,c in [(0,20,'Capture / transport\n20 ms',B),(20,40,'Preprocessing / inference\n40 ms',G),(60,20,'Schedule / execute\n20 ms',O)]:
 ax.barh(0,width,left=left,height=.7,color=c);ax.text(left+width/2,0,label,color='white',ha='center',va='center',fontsize=13)
ax.set(xlim=(0,80),yticks=[],ylim=(-.7,.7),xlabel='Illustrative elapsed time (ms)')
x=np.arange(81);bx.plot(x,x*.10,color=B,lw=2);bx.plot([80],[8],'o',color=O);bx.text(58,7.9,'80 ms → 8 mm',color=O,ha='center');bx.set(xlim=(0,84),ylim=(0,9),xlabel='Observation-to-action delay (ms)',ylabel='Travel at constant 0.10 m/s (mm)');bx.grid(alpha=.2)
save(f,'latency-budget')
r=json.loads((root/'results/reset-comparison.json').read_text());v=[r['full_restore_max_cube_xy_difference_m']*1000,r['qpos_only_max_cube_xy_difference_m']*1000]
f,ax=plt.subplots(figsize=(12.8,3.6));ax.barh([1,0],v,color=[G,O],height=.48);ax.scatter([v[0]],[1],color=G,s=45,zorder=5)
ax.set(yticks=[1,0],yticklabels=['Integration-state restore','qpos-only restore'],xlabel='Maximum cube xy separation from the reference (mm)',xlim=(0,6.2),ylim=(-.55,1.55))
for y,z in zip([1,0],v):ax.text(z+.14,y,f'{z:.2f} mm',va='center',color=G if y==1 else O)
ax.text(2.1,1,'Same initial velocity and state',va='center',color=G);ax.text(1.3,.43,'Identical joint commands; initial cube velocity = +0.20 m/s',fontsize=12)
save(f,'reset-comparison');print('Rendered 2 figure families, 12 files')
