"""Declared synthetic camera-to-hand transform example; no tracking measurements."""
from pathlib import Path
import argparse,sys,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'source'))
from figure_typography import apply_publication_style
p=argparse.ArgumentParser();p.add_argument('--font-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,default=R/'media');a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
receipt=apply_publication_style([a.font_dir/'MiSans-Regular.ttf',a.font_dir/'MiSans-Semibold.ttf']);B='#0072B2';O='#D55E00';K='#243448'
for suffix,fs in [('',9),('-classroom',13)]:
 plt.rcParams.update({'font.family':'MiSans','font.size':fs,'axes.labelsize':fs,'xtick.labelsize':fs-1,'ytick.labelsize':fs-1,'pdf.fonttype':42,'svg.fonttype':'none'})
 f,(ax,tx)=plt.subplots(1,2,figsize=(10.8,5),gridspec_kw={'width_ratios':[1.15,1]});tx.axis('off')
 ax.set(xlim=(-.025,.22),ylim=(-.025,.27),aspect='equal',xlabel='Hand-frame x (m)',ylabel='Hand-frame y (m)');ax.spines[['top','right']].set_visible(False)
 for origin,vector,label,col in [((0,0),(.17,0),'x_H',B),((0,0),(0,.245),'y_H',B),((.1,0),(0,.14),'x_C',O),((.1,0),(-.085,0),'y_C',O)]:
  end=np.array(origin)+vector;ax.annotate('',xy=end,xytext=origin,arrowprops={'arrowstyle':'->','color':col,'lw':1.5});ax.annotate(label,end,xytext=(3,4),textcoords='offset points',color=col)
 point=(.07,.2);ax.plot([0,.07],[0,.2],'--',color=B,lw=1.1);ax.plot([.1,.07],[0,.2],':',color=O,lw=1.4);ax.scatter([0,.1,.07],[0,0,.2],color=[B,O,K],s=35,zorder=6)
 ax.annotate('H origin',(0,0),xytext=(-2,-17),textcoords='offset points',color=B);ax.annotate('C origin',(.1,0),xytext=(2,-17),textcoords='offset points',color=O);ax.annotate('O: same object point',point,xytext=(3,10),textcoords='offset points',color=K)
 text=[('Camera relative to hand',True),('Origin: (0.10, 0, 0) m',False),('Camera +x points along hand +y.',False),('Camera +y points along hand −x.',False),('',False),('Object point in camera coordinates',True),('(0.20, 0.03, 0.40) m',False),('',False),('Rotate, then translate',True),('Hand x = 0.10 − 0.03 = 0.07 m',False),('Hand y = 0.20 m; hand z = 0.40 m',False),('',False),('Plot: x–y projection; +z out of page.',False)]
 for i,(line,bold) in enumerate(text):tx.text(0,.97-i*.072,line,ha='left',va='top',fontsize=fs if bold else fs*.94,weight='semibold' if bold else 'normal',color=K)
 f.tight_layout(pad=1.6)
 if not suffix:f.set_size_inches(7.165,3.8)
 for ext in ['png','pdf','svg']:
  dest=a.output_dir/f'frame-chain{suffix}.{ext}';f.savefig(dest,dpi=240 if suffix else 450,facecolor='white')
  if ext=='svg':dest.write_text('\n'.join(l.rstrip() for l in dest.read_text().splitlines())+'\n')
 plt.close(f)
(a.output_dir/'frame-font-check.json').write_text(json.dumps(receipt,indent=2)+'\n')
