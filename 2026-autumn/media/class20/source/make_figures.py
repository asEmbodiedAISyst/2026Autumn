"""Assemble selected retained course frames; does not run a simulation."""
from pathlib import Path
import argparse
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from PIL import Image
from figure_typography import apply_publication_style

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent


def storyboard(font_dir):
    receipt = apply_publication_style([font_dir / 'MiSans-Regular.ttf', font_dir / 'MiSans-Semibold.ttf'])
    regular = FontProperties(fname=font_dir / 'MiSans-Regular.ttf')
    semibold = FontProperties(fname=font_dir / 'MiSans-Semibold.ttf')
    labels = ['Establish the task', 'Explain the changing goal', 'State the evidence boundary']
    notes = ['Held cube and displayed goal\nare different objects.', 'A target can update after an event;\ncheck the retained event log.', 'Selected episode: 2 goal events, timeout.\nNo across-trial reliability estimate.']
    inputs = [ROOT/'frames'/f'step-{s:04d}.png' for s in [1,356,1000]]
    for kind, width, font in [('paper',182/25.4,7), ('classroom',13.2,12)]:
        scale = width / (182/25.4)
        fig = plt.figure(figsize=(width,3.10*scale))
        for j, (path,label,note) in enumerate(zip(inputs,labels,notes)):
            left=.022+j*.329
            ax=fig.add_axes([left,.33,.307,.52])
            # Identical crop removes blank floor above, keeps full hand and goal.
            frame=Image.open(path).crop((400,440,1460,1080))
            ax.imshow(frame)
            ax.set_axis_off()
            fig.text(left,.94,chr(97+j),fontproperties=semibold,fontsize=font+1,va='top')
            fig.text(left+.028,.94,label,fontproperties=regular,fontsize=font,va='top')
            fig.text(left,.31,f'Control step {[1,356,1000][j]}',fontsize=font,fontproperties=semibold,va='top')
            fig.text(left,.205,note,fontproperties=regular,fontsize=font-0.3,va='top',linespacing=1.45)
            if j==0:
                # Pixel coordinates after the declared crop; labels avoid the contacts.
                ax.annotate('held cube',xy=(550,200),xytext=(250,55),fontproperties=regular,fontsize=font-0.6,
                            color='#173e5e',arrowprops={'arrowstyle':'->','color':'#173e5e','lw':.7*scale},
                            bbox={'facecolor':'white','edgecolor':'none','alpha':.9,'pad':1.6})
                ax.annotate('visual goal',xy=(900,190),xytext=(760,45),fontproperties=regular,fontsize=font-0.6,
                            color='#173e5e',arrowprops={'arrowstyle':'->','color':'#173e5e','lw':.7*scale},
                            bbox={'facecolor':'white','edgecolor':'none','alpha':.9,'pad':1.6})
        base=OUT/f'course-video-storyboard-{kind}'
        for ext in ('svg','pdf','png'):
            fig.savefig(base.with_suffix('.'+ext),dpi=450 if kind=='paper' else 170)
        plt.close(fig)
    provenance={
        'figure':'course-video-storyboard',
        'purpose':'Explain source identity, selected episode and conclusion scope in a scientific video.',
        'kind':'Course-authored annotation of retained simulation frames; not RSS author footage.',
        'font_receipt':receipt,
        'inputs':{str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        'frame_steps':[1,356,1000],
        'crop_xyxy':[400,440,1460,1080],
        'source_identity':{'course_class':'06','seed':9204,'observation_noise':0,
            'native_render':[1920,1080],'control_dt_s':.05,'steps':1000,
            'event_steps':[356,761], 'goal_events':2,'termination':'timeout',
            'scope':'Selected native-MuJoCo episode using supplied ONNX policy. No training, hardware operation or reliability estimate.',
            'policy_sha256':'1893e4a0f3b95f1657ce5e11745db0ac8749c8780d83013859082c414cb5f97f',
            'playground_commit':'ef4fefc13033c0468af4ef651847f5348af0c7d7',
            'mujoco':'3.6.0'},
        'dependencies':{'matplotlib':matplotlib.__version__,'pillow':Image.__version__},
        'processing':'Same crop for all three frames. No pose edits, filters, color adjustment, simulation or training. Paper and classroom variants use identical inputs and text.',
        'outputs':[f'course-video-storyboard-{k}.{e}' for k in ('paper','classroom') for e in ('svg','pdf','png')]
    }
    (OUT/'figure-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--font-dir',type=Path,required=True)
    args=parser.parse_args()
    storyboard(args.font_dir)
