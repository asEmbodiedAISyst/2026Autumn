"""Class09 explanatory figures. Requires Matplotlib, Pillow and locally licensed MiSans. No hardware access."""
from pathlib import Path
import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle,FancyArrowPatch
from PIL import Image
ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--fonts',type=Path,required=True);args=ap.parse_args();root=args.root
for name in ['MiSans-Regular.ttf','MiSans-Semibold.ttf']:font_manager.fontManager.addfont(str(args.fonts/name))
plt.rcParams.update({'font.family':'MiSans','pdf.fonttype':42,'svg.fonttype':'none','font.size':13})
B='#0072B2';G='#177E89';O='#D48020';K='#303740'
def box(a,x,y,w,h,text,c):
 a.add_patch(Rectangle((x,y),w,h,facecolor=c+'12',edgecolor=c,lw=1.3));a.text(x+w/2,y+h/2,text,ha='center',va='center',color=K)
def arrow(a,x,y,c=K):a.add_patch(FancyArrowPatch(x,y,arrowstyle='-|>',mutation_scale=14,lw=1.4,color=c))
def save(f,name):
 f.tight_layout(pad=1)
 for suffix,width in [('-classroom',12.8),('',7.17)]:
  ratio=width/f.get_figwidth();f.set_size_inches(width,f.get_figheight()*ratio)
  from matplotlib.text import Text
  for text in f.findobj(Text):text.set_fontsize(text.get_fontsize()*ratio)
  for ext in ['png','pdf','svg']:f.savefig(root/'media'/f'{name}{suffix}.{ext}',dpi=300,facecolor='white')
 plt.close(f)
f,a=plt.subplots(figsize=(12.8,4.8));a.axis('off');a.set(xlim=(0,1),ylim=(0,1))
labels=['Phone pose\noperator input','Clutch + mapping\nTCP request','Bounds + IK\naccepted target','Simulation\nrobot response']
for i,label in enumerate(labels):
 x=.015+i*.25;box(a,x,.61,.22,.26,label,[B,G,O,K][i]);
 if i<3:arrow(a,(x+.22,.74),(x+.25,.74))
box(a,.26,.08,.48,.26,'Episode: issued action + observed state\nfront/side images + timing + flags',B)
# Action branch and state branch keep separate lanes.
a.plot([.625,.625,.50,.50],[.61,.43,.43,.34],color=O,lw=1.4);arrow(a,(.50,.40),(.50,.34),O)
a.text(.37,.46,'command record',color=O,ha='center')
a.plot([.875,.875,.74],[.61,.21,.21],color=K,lw=1.4);arrow(a,(.80,.21),(.74,.21))
a.text(.945,.41,'response\nrecord',ha='center',color=K)
a.text(.05,.12,'A request can\nbe changed\nor rejected',color=G)
save(f,'teleop-path')
f,a=plt.subplots(figsize=(12.8,2.6));a.axis('off');a.set(xlim=(0,1),ylim=(0,1))
for i,label in enumerate(['Choose action k','Observe state k','Render images\nand save row','Apply command\nand step physics']):
 x=.015+i*.25;box(a,x,.43,.22,.40,label,[B,G,O,K][i])
 if i<3:arrow(a,(x+.22,.63),(x+.25,.63))
a.text(.5,.15,'Saved state precedes this action’s transition; row timestamp is sampled after rendering.',ha='center',fontsize=12)
save(f,'recording-order')
f,aa=plt.subplots(1,2,figsize=(12.8,5.2),subplot_kw={'projection':'3d'})
for a,title,labels in [(aa[0],'Phone body P',['+x: top','+y: left','+z: screen normal']),(aa[1],'TCP frame E',['+x: across fingers','+y: opening','+z: approach'])]:
 a.set_title(title,pad=14);a.set(xlim=(-.1,1.3),ylim=(-.1,1.3),zlim=(-.1,1.3));a.set_axis_off();a.view_init(elev=23,azim=35)
 for k,(label,c) in enumerate(zip(labels,[B,G,O])):
  v=[0,0,0];v[k]=1;a.quiver(0,0,0,*v,color=c,arrow_length_ratio=.12,linewidth=2.6);q=[v[j]*1.27 for j in range(3)];a.text(*q,label,color=c,ha='center',fontsize=12)
f.text(.5,.08,'Phone +x → TCP +y     ·     Phone +y → TCP +x     ·     Phone +z → TCP −z',ha='center',fontsize=13)
f.subplots_adjust(bottom=.18);save(f,'phone-axes')
f,aa=plt.subplots(1,2,figsize=(12.8,5.4))
for a,cam in zip(aa,['front','side']):
 a.imshow(Image.open(root/f'data/recorded/circle/{cam}/000000.jpg'));a.axis('off');a.set_title(f'{cam} / frame 000000',fontsize=14)
save(f,'episode-views')
print('Created 4 figure families, 24 files')
