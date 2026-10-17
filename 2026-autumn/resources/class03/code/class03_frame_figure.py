"""Model-derived frame/units schematic. No hardware measurements.
Run from resources/class03; supply licensed MiSans locally.
"""
from pathlib import Path
import argparse,sys,json
import numpy as np,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'source'))
from figure_typography import apply_publication_style
from class03_frames import trace
B='#0072B2';O='#D55E00';K='#243448'
def main():
 p=argparse.ArgumentParser();p.add_argument('--font-dir',type=Path,required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
 receipt=apply_publication_style([a.font_dir/'MiSans-Regular.ttf',a.font_dir/'MiSans-Semibold.ttf'])
 zero=trace(a.model,0);turned=trace(a.model,30);a.output_dir.mkdir(parents=True,exist_ok=True)
 for variant in ['paper','classroom']:
  w=182/25.4 if variant=='paper' else 11.5;fs=7 if variant=='paper' else 12
  plt.rcParams.update({'font.family':'MiSans','font.size':fs,'pdf.fonttype':42,'svg.fonttype':'none'})
  fig=plt.figure(figsize=(w,w*.52));ax=fig.add_axes([.06,.18,.46,.70]);note=fig.add_axes([.59,.12,.39,.80]);note.axis('off')
  ax.set(xlim=(-15,122),ylim=(-65,36),aspect='equal',xlabel='Displacement from joint along world x (mm)',ylabel='Displacement from joint along world z (mm)')
  ax.spines[['right','top']].set_visible(False);ax.set_xticks([0,50,100]);ax.set_yticks([-50,0,25]);ax.tick_params(labelsize=fs*.85)
  z=np.array(zero['point_world_MuJoCo_m'])-np.array(zero['joint_anchor_world_m']);t=np.array(turned['point_world_MuJoCo_m'])-np.array(turned['joint_anchor_world_m'])
  ax.plot([0,z[0]*1000],[0,z[2]*1000],'o--',color=B,lw=1,label='q = 0 deg')
  ax.plot([0,t[0]*1000],[0,t[2]*1000],'o-',color=O,lw=1.2,label='q = +30 deg')
  ax.scatter(0,0,facecolors='white',edgecolors=K,s=35,zorder=5);ax.plot(0,0,'x',color=K,ms=4,mew=.6,zorder=6)
  ax.annotate('J: fixed pivot\n+y into page',(0,0),xytext=(4,23),fontsize=fs*.85,color=K)
  ax.annotate('P at zero pose',(100,0),xytext=(56,14),fontsize=fs*.85,color=B)
  ax.annotate('P after rotation',(t[0]*1000,t[2]*1000),xytext=(23,-57),fontsize=fs*.85,color=O)
  theta=np.linspace(0,-np.pi/6,25);ax.plot(24*np.cos(theta),24*np.sin(theta),color=K,lw=.7);ax.add_patch(FancyArrowPatch((24*np.cos(theta[-3]),24*np.sin(theta[-3])),(24*np.cos(theta[-1]),24*np.sin(theta[-1])),arrowstyle='->',mutation_scale=7,color=K,lw=.7))
  ax.text(33,-14,'+30 deg',fontsize=fs*.85,color=K)
  ax.set_title('Same payload point, two joint poses',fontsize=fs,fontweight='semibold',loc='left',pad=12)
  lines=[('Read the model',True),('Pin_1 origin in Link:',False),('P = (0.100, 0, 0) m',False),('This local coordinate stays fixed.',False),('',False),('Convert units once',True),('100 mm = 0.100 m',False),('30 deg = 0.5236 rad',False),('Mesh scale 0.001 applies to vertices.',False),('',False),('Check the world position',True),('q = 0: (-110, -3.5, 370) mm',False),('q = 30: (-123.4, -3.5, 320) mm',False)]
  for i,(s,bold) in enumerate(lines):note.text(0,1-i*.071,s,va='top',ha='left',fontsize=fs*.94,fontweight='semibold' if bold else 'normal',color=K)
  fig.text(.5,.02,'B2 model coordinates; x-z projection. The -7 mm axial offset from J to P is out of this view.',ha='center',fontsize=fs*.78,color=K)
  for ext in ['png','pdf','svg']:fig.savefig(a.output_dir/f'frames-and-units-{variant}.{ext}',dpi=450 if variant=='paper' else 180)
  plt.close(fig)
 (a.output_dir/'frame-figure-check.json').write_text(json.dumps({'zero_pose':zero,'turned_pose':turned,'fonts':receipt,'model_derived':True,'not_hardware_measurement':True},indent=2)+'\n')
if __name__=='__main__':main()
