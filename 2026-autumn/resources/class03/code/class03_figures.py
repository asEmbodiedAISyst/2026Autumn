"""Declared teaching schematics; no hardware measurements or simulation runs.
python code/class03_figures.py --font-dir /path/to/MiSans --output-dir media
"""
from pathlib import Path
import argparse,json,sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,Circle,FancyArrowPatch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'source'))
from figure_typography import apply_publication_style
B='#0072B2';O='#D55E00';K='#243448';GRAY='#536170'

def canvas(variant):
    width=182/25.4 if variant=='paper' else 11.5
    plt.rcParams.update({'font.family':'MiSans','font.size':7 if variant=='paper' else 12,'pdf.fonttype':42,'svg.fonttype':'none','text.usetex':False})
    fig,ax=plt.subplots(figsize=(width,width*.47));fig.subplots_adjust(left=.025,right=.975,bottom=.04,top=.96)
    ax.set(xlim=(0,100),ylim=(0,47));ax.axis('off');return fig,ax

def text(ax,x,y,s,**kw):return ax.text(x,y,s,color=K,ha=kw.pop('ha','center'),va='center',**kw)
def line(ax,a,b,**kw):ax.plot([a[0],b[0]],[a[1],b[1]],color=kw.pop('color',K),lw=kw.pop('lw',.8),**kw)
def arrow(ax,a,b):ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=7,lw=.8,color=K))
def box(ax,x,y,w,h,s):
    ax.add_patch(Rectangle((x,y),w,h,facecolor='#F3F7FA',edgecolor=GRAY,lw=.6));text(ax,x+w/2,y+h/2,s)

def body_tree(variant):
    fig,ax=canvas(variant)
    text(ax,23,44,'Physical grouping',fontweight='semibold');text(ax,75,44,'Executable body tree',fontweight='semibold')
    ax.add_patch(Rectangle((17,23),12,12,facecolor='#E6EBEF',edgecolor=K,lw=.8));text(ax,23,29,'Fixed\nhousing')
    line(ax,(6,20),(40,20),color=B,lw=2);ax.add_patch(Circle((23,20),2,facecolor='white',edgecolor=K,lw=.8))
    for x in [8,38]:ax.add_patch(Circle((x,20),3,facecolor='#D9EAF5',edgecolor=B,lw=.8))
    text(ax,23,10,'Link + attached payloads\nmove about one hinge')
    box(ax,60,32,30,7,'World / fixed housing');arrow(ax,(75,32),(75,26));box(ax,60,18,30,8,'Rotating link')
    text(ax,52,28,'Hinge',ha='left');line(ax,(75,18),(75,14));line(ax,(61,14),(89,14))
    for x in [61,89]:line(ax,(x,14),(x,11))
    box(ax,49,3,24,8,'Pin + payload 1');box(ax,77,3,22,8,'Pin + payload 2')
    text(ax,75,.8,'Rigid attachments: no extra joints',fontsize=plt.rcParams['font.size']*.8)
    return fig

def geometry_roles(variant):
    fig,ax=canvas(variant)
    for i,(title,desc) in enumerate([('Visual geometry','Recognize surfaces'),('Collision geometry','Specify contact shape'),('Inertial properties','Specify mass distribution')]):
        cx=17+i*33;text(ax,cx,42,title,fontweight='semibold');text(ax,cx,5,desc)
        if i==0:
            ax.add_patch(Rectangle((cx-13,20),26,8,facecolor='#D9EAF5',edgecolor=B,lw=.8))
            for x in [cx-9,cx-3,cx+3,cx+9]:ax.add_patch(Circle((x,24),1.3,facecolor='white',edgecolor=B,lw=.6))
            text(ax,cx,13,'Detailed mesh')
        elif i==1:
            ax.add_patch(Rectangle((cx-13,20),26,8,facecolor='none',edgecolor=O,lw=1,linestyle='--'))
            text(ax,cx,13,'Simplified candidate')
        else:
            line(ax,(cx-13,24),(cx+13,24),color=GRAY)
            for x in [cx-11,cx+11]:ax.add_patch(Circle((x,24),3,facecolor='#D9EAF5',edgecolor=B,lw=.8))
            ax.plot(cx,24,'+',color=O,ms=6,mew=1);text(ax,cx,13,'Mass, COM, inertia')
    text(ax,50,34,'Same conceptual link; three different modeling roles',fontsize=plt.rcParams['font.size']*.85)
    return fig

def evidence_chain(variant):
    fig,ax=canvas(variant)
    box(ax,1,19,21,10,'Declared input\nand settings')
    box(ax,34,29,26,9,'Physical mechanism');box(ax,34,10,26,9,'Digital model')
    arrow(ax,(22,26),(34,33));arrow(ax,(22,22),(34,14));arrow(ax,(60,33),(73,33));arrow(ax,(60,14),(73,14))
    text(ax,84,33,'Measured output');text(ax,84,14,'Predicted output')
    arrow(ax,(84,29),(84,26));arrow(ax,(84,18),(84,21));text(ax,84,23.5,'Align + compare')
    text(ax,47,43,'Correspondence requires matched conditions',fontweight='semibold')
    for x,s in [(17,'Implementation\nIntended model?'),(50,'Physical checks\nBuilt counterpart?'),(83,'Behavioral test\nOutput agreement?')]:text(ax,x,3,s)
    return fig

def printed_interface(variant):
    fig,ax=canvas(variant)
    for cx,title in [(24,'Nominal CAD interface'),(75,'As-built interface')]:
        text(ax,cx,43,title,fontweight='semibold');ax.add_patch(Rectangle((cx-18,17),36,18,facecolor='#F3F7FA',edgecolor=K,lw=.8))
        ax.add_patch(Circle((cx,26),5,facecolor='white',edgecolor=B,lw=.8))
        line(ax,(cx-10,26),(cx+10,26),color=GRAY,linestyle='--');line(ax,(cx,16),(cx,36),color=GRAY,linestyle='--')
    ax.add_patch(Circle((76,26),4.1,facecolor='none',edgecolor=O,lw=1,linestyle='--'))
    text(ax,24,10,'Designed diameter\nand material');text(ax,75,10,'Measure fit, clearance\nand complete moving mass')
    text(ax,50,2,'Declared schematic: clearance exaggerated; no measured tolerances',fontsize=plt.rcParams['font.size']*.85)
    return fig

FUNCTIONS={'body-tree':body_tree,'geometry-roles':geometry_roles,'validation-chain':evidence_chain,'printed-interface':printed_interface}
def main():
    p=argparse.ArgumentParser();p.add_argument('--font-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);args=p.parse_args()
    receipt=apply_publication_style([args.font_dir/'MiSans-Regular.ttf',args.font_dir/'MiSans-Semibold.ttf']);args.output_dir.mkdir(parents=True,exist_ok=True)
    for variant in ['paper','classroom']:
        for stem,fn in FUNCTIONS.items():
            fig=fn(variant)
            for ext in ['png','pdf','svg']:fig.savefig(args.output_dir/f'{stem}-{variant}.{ext}',dpi=450 if variant=='paper' else 180)
            plt.close(fig)
    (args.output_dir/'figure-font-check.json').write_text(json.dumps({'fonts':receipt,'matplotlib':matplotlib.__version__,'schematic':True,'seed':'not applicable; deterministic geometry'},indent=2)+'\n')
if __name__=='__main__':main()
