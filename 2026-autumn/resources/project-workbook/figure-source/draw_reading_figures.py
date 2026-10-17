"""Course reading figures. Original schematics and explicitly invented teaching fixtures.
Matplotlib/Pillow/NumPy; requires locally licensed MiSans; no simulation, training or hardware access.
"""
from pathlib import Path
import argparse,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.text import Text
from matplotlib.patches import Rectangle,FancyArrowPatch
ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--fonts',type=Path,required=True);a=ap.parse_args();out=a.out
for name in ['MiSans-Regular.ttf','MiSans-Semibold.ttf']:font_manager.fontManager.addfont(str(a.fonts/name))
plt.rcParams.update({'font.family':'MiSans','font.size':14,'axes.labelsize':14,'legend.fontsize':12,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
B='#0072B2';G='#177E89';O='#D48020';K='#303740';GRAY='#7F8992';RED='#B44D45';records=[]
def blank(h=3.8):
 f,ax=plt.subplots(figsize=(12.8,h));ax.axis('off');ax.set(xlim=(0,1),ylim=(0,1));return f,ax
def box(ax,x,y,w,h,t,c=B):
 ax.add_patch(Rectangle((x,y),w,h,facecolor=c+'10',edgecolor=c,lw=1.4));ax.text(x+w/2,y+h/2,t,ha='center',va='center',color=K,fontsize=13)
def arrow(ax,p,q,c=K):ax.add_patch(FancyArrowPatch(p,q,arrowstyle='-|>',mutation_scale=15,color=c,lw=1.5))
def save(f,n,name,kind,inputs):
 f.tight_layout(pad=1.2);d=out/f'class{n}';d.mkdir(parents=True,exist_ok=True)
 for variant,width in [('classroom',12.8),('paper',7.17)]:
  ratio=width/f.get_figwidth();f.set_size_inches(width,f.get_figheight()*ratio)
  for t in f.findobj(Text):t.set_fontsize(t.get_fontsize()*ratio)
  for ext in ['png','pdf','svg']:
   p=d/f'{name}-{variant}.{ext}';f.savefig(p,dpi=300,facecolor='white')
   if ext=='svg':p.write_text('\n'.join(x.rstrip() for x in p.read_text().splitlines())+'\n')
 plt.close(f);records.append({'class':n,'name':name,'kind':kind,'inputs':inputs})
f,ax=blank(4)
for i,(t,c) in enumerate([('Interaction\nbody + environment',B),('Retained record\nobservations + context',G),('Intended use\nquestion or method',O),('Bounded claim\nmeasure + comparator',B)]):
 x=.015+i*.25;box(ax,x,.54,.22,.30,t,c)
 if i<3:arrow(ax,(x+.22,.69),(x+.25,.69))
box(ax,.29,.08,.43,.24,'Downstream policy improvement\nrequires a separate evaluation',GRAY);arrow(ax,(.62,.54),(.62,.32),GRAY)
save(f,12,'claim-chain','conceptual schema',[])
f,aa=plt.subplots(1,2,figsize=(12.8,4.3),sharey=True)
for ax,counts,title,c in [(aa[0],[4,4,0,0],'Convenient resets: 2/4 bins',B),(aa[1],[2,2,2,2],'Stratified resets: 4/4 bins',G)]:
 ax.bar(list('ABCD'),counts,color=c,width=.58);ax.set(title=title,ylabel='Usable episodes (invented)',xlabel='Declared start–goal bin',ylim=(0,5),yticks=range(6))
 for i,v in enumerate(counts):ax.text(i,v+.12,str(v),ha='center')
save(f,12,'coverage','invented equal-eight-attempt fixture',{'convenient':[4,4,0,0],'stratified':[2,2,2,2]})
f,ax=blank(4.4)
labels=['Declared\nreset','Operator\ncommands','Robot push\nthen stall','Manual cube\nrelocation','Final target\nimage']
for i,t in enumerate(labels):
 x=.012+i*.20;box(ax,x,.59,.176,.26,t,RED if i==3 else B)
 if i<4:arrow(ax,(x+.176,.72),(x+.20,.72))
ax.plot([.02,.59],[.42,.42],color=G,lw=2);ax.text(.30,.30,'Pre-intervention segment: preserve for declared analysis',ha='center',fontsize=13,color=G)
ax.plot([.61,.98],[.42,.42],color=RED,lw=2);ax.text(.79,.27,'Final position does not establish\nunassisted completion',ha='center',fontsize=12,color=RED)
ax.text(.5,.08,'Record the intervention and termination; retain the original attempt.',ha='center',fontsize=13)
save(f,13,'episode','constructed episode with external intervention',[])
f,ax=blank(3.5)
for x,t,c in [(.02,'Observe o[k]\nstate + image',B),(.27,'Associate row k\nwith issued a[k]',G),(.52,'Apply action\ntransition',O),(.77,'Observe o[k+1]\nnext response',B)]:
 box(ax,x,.41,.21,.39,t,c)
 if x<.77:arrow(ax,(x+.21,.61),(x+.25,.61))
ax.text(.5,.16,'Declared pre-transition convention; capture-time equality is a separate question.',ha='center',fontsize=13)
save(f,13,'alignment','conceptual observation/action convention',[])
f,ax=blank(5)
for x,t,c in [(.02,'World / body\ninteraction',B),(.27,'Sensing\nobservations',G),(.52,'Computation\ncontroller',O),(.77,'Admitted action\nlimits + mapping',B)]:
 box(ax,x,.60,.21,.25,t,c)
 if x<.77:arrow(ax,(x+.21,.73),(x+.25,.73))
ax.plot([.875,.875,.125],[.60,.45,.45],color=K,lw=1.5);arrow(ax,(.125,.45),(.125,.60));ax.text(.5,.94,'Solid loop: action and world response',ha='center',fontsize=12)
box(ax,.02,.08,.25,.23,'Human authority\nenable / reset / recover',GRAY);box(ax,.34,.08,.62,.23,'Recorder: observations + admitted actions\nidentity, timing and values',G)
arrow(ax,(.07,.31),(.07,.59),GRAY)
for xx in [.375,.875]:ax.add_patch(FancyArrowPatch((xx,.59),(xx,.31),arrowstyle='-|>',mutation_scale=14,color=G,lw=1.4,linestyle='--'))
save(f,14,'system-loop','conceptual feedback and record boundaries',[])
f,aa=plt.subplots(1,2,figsize=(12.8,4.3))
aa[0].bar(['Raw action','Observed motor'],[-30,29],color=[O,B]);aa[0].axhline(0,color=K,lw=.7);aa[0].set(title='Different conventions',ylabel='Declared channel values (degrees)',ylim=(-40,40))
aa[1].bar(['Motor target','Observed motor'],[30,29],color=[G,B]);aa[1].set(title='Convert first: target = (−1) × (−30°)',ylabel='Motor angle (degrees)',ylim=(0,40));aa[1].text(.5,34,'State − target = −1°',ha='center',color=G)
save(f,14,'conversion','invented unit/sign diagnostic',{'action_command_deg':-30,'direction':-1,'motor_state_deg':29})
f,ax=plt.subplots(figsize=(12.8,3.8));ax.axvspan(5,15,color=G,alpha=.08);ax.axvspan(15,23,color=O,alpha=.08);ax.axvline(15,color=O,ls='--',lw=2,label='Chosen boundary: 15 mm');ax.errorbar(14,0,xerr=3,fmt='o',color=B,elinewidth=3,capsize=9);ax.text(14,.30,'Estimate 14 mm; assumed bound ±3 mm',ha='center',color=B);ax.text(10,-.32,'Inside criterion',ha='center',color=G);ax.text(19,-.32,'Outside criterion',ha='center',color=O);ax.set(xlim=(5,23),ylim=(-.65,.75),yticks=[],xlabel='Cube-centre distance to goal (mm)');ax.legend(loc='upper left')
save(f,15,'uncertainty','invented bounded-uncertainty fixture',{'estimate_mm':14,'bound_mm':3,'criterion_mm':15})
f,ax=blank(4.5)
rows=[(.68,'Digital consistency','Same model/state\n+ declared commands','Implementation / state\nconsistency',B),(.37,'Sensor correspondence','Aligned estimate\n+ suitable reference','Measurement validity\nin tested conditions',G),(.06,'Physical response','Matched command/load\n+ physical measurement','Bounded model–hardware\nresponse comparison',O)]
for y,title,inp,claim,c in rows:
 box(ax,.01,y,.25,.23,title,c);box(ax,.33,y,.29,.23,inp,c);box(ax,.70,y,.29,.23,claim,c);arrow(ax,(.26,y+.115),(.33,y+.115));arrow(ax,(.62,y+.115),(.70,y+.115))
save(f,15,'correspondence','comparison boundaries, not evidence ranking',[])
f,ax=blank(4)
for i,t in enumerate(['Interaction\ndata generation','Data quality\n+ coverage checks','Use in training,\ninference or analysis','Downstream\ntask evaluation']):
 x=.015+i*.25;box(ax,x,.49,.22,.34,t,[B,G,O,B][i])
 if i<3:arrow(ax,(x+.22,.66),(x+.25,.66))
ax.text(.5,.22,'A finding at one link does not establish every later contribution.',ha='center',fontsize=14)
ax.text(.5,.06,'Name the method, comparator, evaluation conditions and missing dependencies.',ha='center',fontsize=12,color=GRAY)
save(f,16,'contribution','conceptual evidence dependency chain',[])
f,ax=plt.subplots(figsize=(12.8,4));vals=np.array([[12,0,2,6],[6,6,8,0]]);colors=[G,O,B,GRAY];labels=['Both succeed','A only','B only','Both fail'];left=np.zeros(2)
for k in range(4):
 ax.barh([1,0],vals[:,k],left=left,color=colors[k],label=labels[k],height=.45)
 for y,v,l in zip([1,0],vals[:,k],left):
  if v:ax.text(l+v/2,y,str(v),ha='center',va='center',color='white',fontsize=14)
 left+=vals[:,k]
ax.set(yticks=[1,0],yticklabels=['Fixture X','Fixture Y'],xlabel='Paired evaluation layouts (invented)',xlim=(0,20),ylim=(-.65,1.7),xticks=range(0,21,2));ax.legend(ncol=4,loc='upper center');ax.text(10,-.47,'Both fixtures: A = 12/20; B = 14/20',ha='center',fontsize=13)
save(f,16,'paired-outcomes','invented paired outcomes',{'X':[12,0,2,6],'Y':[6,6,8,0]})
f,ax=blank(4.5)
for y,action,need,status,c in [(.69,'Release inspected\ndigital analysis','Accessible records, valid\nanalysis, scoped claims','Can be supported\nif critical checks pass',G),(.38,'Claim learned-policy\nreproduction','Exact checkpoint/processors\n+ repeated evaluation','Blocked if required\nartifacts are absent',O),(.07,'Deploy controller\non physical hardware','Physical interfaces, setup\n+ appropriate task evidence','Unsupported by\ndigital analysis alone',RED)]:
 box(ax,.01,y,.27,.23,action,c);box(ax,.35,y,.32,.23,need,c);box(ax,.74,y,.25,.23,status,c);arrow(ax,(.28,y+.115),(.35,y+.115));arrow(ax,(.67,y+.115),(.74,y+.115))
save(f,17,'action-boundary','hypothetical action-specific dependencies',[])
f,ax=blank(4.1)
box(ax,.02,.22,.44,.57,'Scoped proposition: digital replay repeats\nEvidence: inspected simulation trace\nContext: E2\nSupport: can be adequate (3)',B)
box(ax,.54,.22,.44,.57,'Scoped proposition: broad reliability\nEvidence: one physical demonstration\nContext: E3\nSupport: may be weak (1)',O)
ax.text(.5,.07,'Illustrative judgements depend on the proposition; context is not a quality ladder.',ha='center',fontsize=12)
save(f,17,'evidence-dimensions','illustrative context/support separation',[])
(out/'figure-records.json').write_text(json.dumps(records,indent=2)+'\n');print('Rendered',len(records),'families,72assets')
