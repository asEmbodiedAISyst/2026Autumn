"""Eight paper and classroom figure sets."""
import argparse, hashlib, json, os, tempfile
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'class06-matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Rectangle, Circle
from matplotlib.text import Text
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
from PIL import Image
from figure_typography import apply_publication_style
MEDIA=Path(__file__).resolve().parents[1];CODE=MEDIA.parent/'code'
BLUE='#245C8A';TEAL='#007C78';ORANGE='#D8952B';RED='#B74646';PALE='#EDF3F5'
MODE='paper';AUDIT=[]
def canvas(height=65,width=182,**kwargs):
 s=1 if MODE=='paper' else 1.25
 return plt.subplots(figsize=(width/25.4*s,height/25.4*s),**kwargs)
def panel(ax,letter):
 ax.text(-.02,1.05,letter,transform=ax.transAxes,weight='semibold',fontsize=8 if MODE=='paper' else 13)
def save(fig,name):
 fig.canvas.draw();fonts=set()
 for item in fig.findobj(Text):
  if not item.get_visible() or not item.get_text():continue
  path=fm.findfont(item.get_fontproperties(),fallback_to_default=False);font=fm.get_font(path)
  if font.family_name!='MiSans':raise RuntimeError('Unexpected font: '+font.family_name)
  missing=[c for c in item.get_text() if not c.isspace() and ord(c) not in font.get_charmap()]
  if missing:raise RuntimeError(f'Missing MiSans glyphs {missing}')
  fonts.add(Path(path).name)
 out=MEDIA/'figures'/('' if MODE=='paper' else 'classroom');out.mkdir(parents=True,exist_ok=True)
 for suffix in ('png','pdf','svg'):fig.savefig(out/f'{name}.{suffix}',dpi=450 if MODE=='paper' else 200)
 AUDIT.append({'figure':name,'variant':MODE,'width_mm':fig.get_figwidth()*25.4,'height_mm':fig.get_figheight()*25.4,'fonts':sorted(fonts),'dpi':450 if MODE=='paper' else 200})
 plt.close(fig)
def arrow(ax,start,end):ax.annotate('',xy=end,xytext=start,arrowprops={'arrowstyle':'->','lw':.8,'color':BLUE})
def feedback_loop():
 fig,ax=canvas(58);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
 for x,title,body in [(.02,'Observe','Joint state\nCube pose + target'),(.28,'Policy','57 inputs\n16 actions'),(.54,'Joint targets','Increment + clip\n20 Hz'),(.80,'MuJoCo','Actuators\nContact dynamics')]:
  ax.add_patch(Rectangle((x,.50),.18,.30,fc=PALE,ec=BLUE,lw=.6));ax.text(x+.09,.71,title,ha='center',weight='semibold');ax.text(x+.09,.59,body,ha='center',va='center')
 for x in [.20,.46,.72]:arrow(ax,(x,.65),(x+.08,.65))
 for a,b in [((.89,.5),(.89,.19)),((.89,.19),(.11,.19)),((.11,.19),(.11,.5))]:arrow(ax,a,b)
 ax.text(.5,.26,'Finger and cube motion → next measurement',ha='center');ax.text(.11,.96,'Target',ha='center');arrow(ax,(.11,.91),(.11,.8))
 fig.subplots_adjust(left=.01,right=.99,bottom=.04,top=.98);save(fig,'feedback-loop')
def full_orientation():
 s=1 if MODE=='paper' else 1.25;fig=plt.figure(figsize=(182/25.4*s,70/25.4*s))
 verts=np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]])*.65;faces=[[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
 for k,deg in enumerate([0,45]):
  ax=fig.add_subplot(1,2,k+1,projection='3d',computed_zorder=False);a=np.deg2rad(deg);R=np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]]);v=verts@R.T
  ax.add_collection3d(Poly3DCollection([v[f] for f in faces],facecolors=['#CCD8E2','#B2D7D2','#93B2CB','#E8C894','#CCD8E2','#CCD8E2'],edgecolors=BLUE,linewidths=.6))
  ax.text(0,0,.71,'M',ha='center',weight='semibold',fontsize=13*s,zorder=20);center=np.array([0,-.69,0])@R.T;ax.text(*center,'B',ha='center',weight='semibold',fontsize=12*s,zorder=20)
  for vector,label,color in [([1.3,0,0],'x',BLUE),([0,1.3,0],'y',TEAL),([0,0,1.3],'z',ORANGE)]:ax.quiver(0,0,0,*vector,color=color,linewidth=.7);ax.text(*(np.array(vector)*1.1),label)
  ax.set(xlim=(-1,1.5),ylim=(-1,1.5),zlim=(-.8,1.5));ax.set_box_aspect((1,1,1));ax.view_init(25,-55);ax.axis('off');ax.text2D(.03,.92,'ab'[k],transform=ax.transAxes,weight='semibold',fontsize=8*s);ax.text2D(.5,.04,f'Yaw: {deg}°; M upward',transform=ax.transAxes,ha='center')
 fig.subplots_adjust(left=.01,right=.99,bottom=.02,top=.99,wspace=.02);save(fig,'full-orientation')
def contact_wrench():
 fig,ax=canvas(60);ax.set(xlim=(-1.3,2.9),ylim=(-1.1,1.1));ax.set_aspect('equal');ax.axis('off')
 ax.add_patch(Rectangle((-.7,-.7),1.4,1.4,fc='#E3F0ED',ec=TEAL,lw=.8));ax.scatter([0,.7],[0,.45],s=[12,18],color=[BLUE,ORANGE],zorder=3);arrow(ax,(0,0),(.7,.45));ax.text(.31,.13,'r')
 ax.annotate('',xy=(-.1,.45),xytext=(.7,.45),arrowprops={'arrowstyle':'->','color':ORANGE,'lw':1.2});ax.text(.3,.58,'Force f',ha='center',color=ORANGE);ax.add_patch(Circle((0,0),.10,fill=False,ec=TEAL,lw=.7));ax.text(0,-.85,'Cube center O',ha='center')
 ax.text(1.02,.45,'Moment: τ = r × f',weight='semibold');ax.text(1.02,.03,'Here, the moment points\nout of the page.',va='center');ax.text(1.02,-.5,'Lever arm and force must\nuse the same frame.',va='center')
 fig.subplots_adjust(left=.02,right=.98,bottom=.02,top=.98);save(fig,'contact-wrench')
def policy_and_clock():
 fig,(ax,t)=canvas(70,nrows=2,gridspec_kw={'height_ratios':[1,1.1]});start=0
 for size,label,color in zip([16,16,3,6,16],['Joint\npositions','Joint-target\nerror','Position\nerror','Orientation\nfeatures','Action\nhistory'],[BLUE,TEAL,ORANGE,'#76ABA4','#718BA1']):
  ax.barh(0,size,left=start,height=.6,color=color,edgecolor='white',lw=.6);ax.text(start+size/2,0,str(size),ha='center',va='center',color='white',weight='semibold');label_y=-.5 if size!=6 else -1.22
  ax.text(start+size/2,label_y,label,ha='center',va='top')
  if size==6:ax.plot([start+size/2,start+size/2],[-.32,-1.15],color=BLUE,lw=.6)
  start+=size
 ax.set(xlim=(0,57),ylim=(-2.05,.55));ax.axis('off');panel(ax,'a')
 for i in range(5):t.add_patch(Rectangle((i*10,.1),10,.45,fc=PALE,ec=BLUE,lw=.6));t.text(i*10+5,.33,str(i+1),ha='center',va='center')
 t.annotate('',xy=(50,.80),xytext=(0,.80),arrowprops={'arrowstyle':'<->','color':BLUE,'lw':.8});t.text(25,.94,'One action interval: 50 ms (20 Hz)',ha='center');t.set(xlim=(0,50),ylim=(0,1.25),xticks=range(0,51,10),yticks=[],xlabel='Elapsed simulation time (ms)');t.spines[['left','bottom']].set_visible(False);panel(t,'b')
 fig.subplots_adjust(left=.05,right=.97,bottom=.17,top=.92,hspace=.55);save(fig,'policy-and-clock')
def qualification_results():
 paths=['native-task-10ms-noisy-heldout','playground-noise-1','playground-noise-0'];records=[json.loads((CODE/'results'/p/'summary.json').read_text()) for p in paths];names=['Mac native / noisy','Playground / noisy','Playground / ideal']
 fig,(ax,bx)=canvas(82,ncols=2,gridspec_kw={'width_ratios':[1.45,1]});y=np.arange(3);rates=np.array([r['first_goal_success_rate']*100 for r in records]);bounds=np.array([r['wilson_95_interval'] for r in records])*100
 ax.errorbar(rates,y,xerr=np.stack([rates-bounds[:,0],bounds[:,1]-rates]),fmt='o',color=BLUE,capsize=2,lw=.8)
 for i,r in enumerate(rates):ax.text(r-1,i-.20,f'{round(r)}/100',ha='right')
 ax.set(xlim=(40,100),ylim=(2.5,-.5),yticks=y,yticklabels=names,xlabel='First-goal success (%)',xticks=[40,60,80,100]);panel(ax,'a');left=np.zeros(3)
 for key,label,color,hatch in [('first_goal_successes','Success',TEAL,''),('timeouts','Timeout',ORANGE,'///'),('falls','Fall',RED,'xxx')]:
  vals=np.array([r[key] for r in records]);bx.barh(y,vals,left=left,height=.5,color=color,hatch=hatch,edgecolor='white',lw=.4,label=label)
  for j,(v,l) in enumerate(zip(vals,left)):
   if v>=5:bx.text(l+v/2,j,str(v),ha='center',va='center',color='white' if key=='first_goal_successes' else 'black')
  left+=vals
 assert np.all(left==100)
 bx.set(xlim=(0,100),ylim=(2.5,-.5),yticks=[],xlabel='Episodes',xticks=[0,50,100]);panel(bx,'b');bx.legend(loc='upper center',bbox_to_anchor=(.45,-.23),ncol=3,columnspacing=.7,handlelength=1)
 fig.subplots_adjust(left=.25,right=.985,bottom=.25,top=.91,wspace=.28);save(fig,'qualification-results')
def paired_noise():
 p=json.loads((CODE/'results/reference-backend-comparison.json').read_text())['paired_noise_comparison'];m=np.array([[p['both_success'],p['ideal_only_success']],[p['noisy_only_success'],100-p['both_success']-p['ideal_only_success']-p['noisy_only_success']]]);assert m.tolist()==[[54,4],[35,7]]
 fig,ax=canvas(80,width=88.9);ax.imshow(m,cmap='Blues',vmin=0,vmax=60)
 for (r,c),v in np.ndenumerate(m):ax.text(c,r,str(v),ha='center',va='center',weight='semibold',color='white' if v>28 else 'black',fontsize=10 if MODE=='paper' else 16)
 ax.set(xticks=[0,1],xticklabels=['Success','No success'],yticks=[0,1],yticklabels=['Success','No success'],xlabel='Original noisy observations',ylabel='Ideal observations');ax.tick_params(length=0);ax.spines[:].set_visible(False);fig.subplots_adjust(left=.26,right=.96,bottom=.23,top=.98);save(fig,'paired-noise')
def continuous_trace():
 rows=json.loads((MEDIA/'data/continuous-example.json').read_text())['trace'];x=np.array([r['step']*.05 for r in rows]);events=[r for r in rows if r['goal_event']];assert [r['step'] for r in events]==[356,761]
 fig,(ax,bx)=canvas(82,nrows=2,sharex=True,gridspec_kw={'height_ratios':[3,1]});ax.plot(x,[r['orientation_error_rad'] for r in rows],color=BLUE);ax.axhline(.1,color=RED,ls='--',label='0.1 rad threshold');ax.set(ylabel='Orientation error (rad)',ylim=(0,3.35));panel(ax,'a');ax.text(49,.8,'0.1 rad threshold',ha='right',color=RED)
 for r in events:ax.axvline(r['step']*.05,color=TEAL,ls=':',lw=.7);ax.text(r['step']*.05+.5,3.23,f"{r['step']*.05:.2f} s",color=TEAL)
 bx.step(x,[r['goals'] for r in rows],where='post',color=TEAL);bx.set(xlim=(0,50),ylim=(-.1,2.3),yticks=[0,1,2],ylabel='Events',xlabel='Simulation time (s)');panel(bx,'b');fig.subplots_adjust(left=.11,right=.98,bottom=.15,top=.92,hspace=.35);save(fig,'continuous-trace')
def demo_storyboard():
 fig,axes=canvas(112,nrows=2,ncols=2)
 for ax,step,letter in zip(axes.flat,[1,356,761,1000],'abcd'):
  with Image.open(MEDIA/'data/frames'/f'step-{step:04d}.png') as im:
   assert im.size==(1920,1080),'Use native renders, not enlarged historical frames.'
   ax.imshow(im)
  ax.axis('off');ax.text(.015,.97,letter,transform=ax.transAxes,weight='semibold',va='top',color='black',fontsize=8 if MODE=='paper' else 13);ax.text(.5,-.02,f't = {step*.05:.2f} s',transform=ax.transAxes,ha='center',va='top')
 fig.subplots_adjust(left=.01,right=.99,bottom=.06,top=.99,wspace=.05,hspace=.13);save(fig,'demo-storyboard')
FUNCTIONS=[feedback_loop,full_orientation,contact_wrench,policy_and_clock,qualification_results,paired_noise,continuous_trace,demo_storyboard]
def main():
 global MODE
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--font',type=Path,action='append',required=True);args=p.parse_args();fonts=apply_publication_style(args.font)
 for MODE in ['paper','classroom']:
  apply_publication_style(args.font)
  if MODE=='classroom':plt.rcParams.update({k:11.2 for k in ['font.size','axes.labelsize','axes.titlesize','xtick.labelsize','ytick.labelsize','legend.fontsize']})
  for function in FUNCTIONS:function()
 sources=[MEDIA/'data/continuous-example.json',MEDIA/'data/media-replay.json',*sorted((MEDIA/'data/frames').glob('*.png')),*[CODE/'results'/p/'summary.json' for p in ['native-task-10ms-noisy-heldout','playground-noise-1','playground-noise-0']],CODE/'results/reference-backend-comparison.json']
 outputs=[f for f in sorted((MEDIA/'figures').rglob('*')) if f.is_file() and f.suffix in {'.png','.pdf','.svg'}]
 receipt={'generator':'source/generate_class06_figures.py','matplotlib':matplotlib.__version__,'fonts':fonts,'style_sha256':hashlib.sha256((MEDIA/'source/publication.mplstyle').read_bytes()).hexdigest(),'exports':AUDIT,'inputs':{str(f.relative_to(MEDIA.parent)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},'output_sha256':{str(f.relative_to(MEDIA)):hashlib.sha256(f.read_bytes()).hexdigest() for f in outputs}}
 (MEDIA/'figures-provenance.json').write_text(json.dumps(receipt,indent=2)+'\n');print('Generated 8 paper and 8 classroom PNG/PDF/SVG sets; MiSans glyph preflight passed.')
if __name__=='__main__':main()
