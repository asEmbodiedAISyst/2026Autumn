"""Generate poster teaching examples from retained Class 06 evidence; no simulation."""
from pathlib import Path
import argparse
import hashlib
import json
import textwrap

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import Rectangle, FancyArrowPatch
from matplotlib.text import Text
from PIL import Image

from figure_typography import apply_publication_style

ROOT = Path(__file__).resolve().parents[1]
BLUE = '#17618c'
INK = '#172932'
GRAY = '#5b6870'
PALE = '#eaf1f4'
ORANGE = '#a95b12'
RED = '#a33132'
AUDIT = []
SUMMARY = json.loads((ROOT/'inputs/summary.json').read_text())
EPISODES = [json.loads(line) for line in (ROOT/'inputs/episodes.jsonl').read_text().splitlines()]
assert len(EPISODES) == 100
assert sum(e['first_goal_success'] for e in EPISODES) == SUMMARY['first_goal_successes'] == 88
assert sum(e['timeout'] for e in EPISODES) == 12
assert sum(e['fall'] for e in EPISODES) == 0
assert sorted(e['seed'] for e in EPISODES) == list(range(20000,20100))


def text(ax, x, y, content, size=25, width=None, color=INK, weight='normal', **kwargs):
    if width:
        content = '\n'.join(textwrap.fill(p, width=width, break_long_words=False,
                                         break_on_hyphens=False) for p in content.split('\n'))
    return ax.text(x, y, content, va='top', fontsize=size, color=color,
                   fontweight=weight, linespacing=1.28, **kwargs)


def panel(ax, x, y, w, h, heading, body=None, bodywidth=35, size=25):
    ax.add_patch(Rectangle((x,y-h),w,h,facecolor='white',edgecolor='#cbd6dc',lw=1))
    ax.add_patch(Rectangle((x,y-28),w,28,facecolor=PALE,edgecolor='none'))
    text(ax,x+11,y-4,heading,size=29,weight='semibold',color=BLUE)
    if body:
        text(ax,x+11,y-41,body,size=size,width=bodywidth)


def draw_poster(ax, revised, scale=1):
    """A complete A0 canvas. Font scaling preserves the same content in miniatures."""
    before_text = set(ax.texts)
    ax.set(xlim=(0,841),ylim=(0,1189),aspect='equal')
    ax.axis('off')
    ax.add_patch(Rectangle((0,0),841,1189,facecolor='white',edgecolor='#a7b8c2',lw=1))
    if revised:
        ax.add_patch(Rectangle((0,1018),841,171,facecolor=BLUE,edgecolor='none'))
        text(ax,32,1164,'Auditing a pretrained cube-\nreorientation policy in simulation',size=76,
             color='white',weight='semibold')
        text(ax,34,1040,'ROB7103/8103 teaching example · Retained Class 06 evidence',size=23,color='white')
        text(ax,32,997,'A fixed policy reached the first target in 88/100\nretained native-MuJoCo trials; 12 timed out.',size=35,weight='semibold')
        panel(ax,32,907,375,180,'Question and contribution',
              'How well does the supplied policy reach its first orientation goal under a declared simulation protocol?\nThis poster analyses retained evaluations; it does not introduce or train the policy.',bodywidth=40,size=25)
        panel(ax,432,907,377,180,'System and interface')
        for y,label in [(858,'57-value actor observation'),(813,'Supplied pretrained policy'),(768,'16 targets → native MuJoCo hand')]:
            ax.add_patch(Rectangle((448,y-28),345,31,facecolor=PALE,edgecolor='#c3d3dc'))
            text(ax,620,y-3,label,size=24,ha='center')
        for y in [820,775]:
            ax.add_patch(FancyArrowPatch((620,y+6),(620,y-6),arrowstyle='-|>',mutation_scale=15*scale,color=GRAY))
        panel(ax,32,699,375,267,'Task and selected view')
        image=Image.open(ROOT/'inputs/selected-step-0356.png')
        ax.imshow(image,extent=(69,369,488,656.75),aspect='auto',zorder=2)
        text(ax,45,478,'Selected simulation frame, seed 9204.\nThe image illustrates behavior; it is not\nthe 100-trial performance measure.',size=23)
        panel(ax,432,699,377,267,'First-goal evaluation')
        bar(ax,449,644,344,55,100,88)
        text(ax,449,568,'88 successes · 12 timeouts · 0 falls',size=26,weight='semibold')
        text(ax,449,521,'100 trials, seeds 20000–20099.\nFirst target below 0.1 rad before fall\nor 50 s limit. This is the observed\nresult under the stated protocol.',size=24)
        panel(ax,32,405,777,160,'Conditions that define the number')
        text(ax,45,362,'Native-task adapter · MuJoCo 3.6.0 · original observation noise\nPhysics step 0.01 s · control interval 0.05 s · fixed pretrained actor\nAll 100 outcomes retained. No training, threshold relaxation or hardware run.',size=27)
        panel(ax,32,221,777,128,'Conclusion and next justified test')
        text(ax,45,178,'The policy is a working, imperfect simulation example under these conditions.\nThis result does not establish physical-hand reliability. Test one declared\nchange, such as observation delay, using a fresh evaluation seed set.',size=26)
        text(ax,32,73,'Sources: Class 06 retained evaluation and selected native rendering.\nPolicy/task: MuJoCo Playground, commit ef4fefc… · Policy SHA-256: 1893e4a…\nFull protocol, source attribution and records accompany the course example.',size=20,color=GRAY)
    else:
        ax.add_patch(Rectangle((0,1113),841,76,facecolor='#f9e7e6',edgecolor='none'))
        text(ax,24,1170,'DELIBERATELY FLAWED TEACHING EXAMPLE',size=34,color=RED,weight='semibold')
        text(ax,24,1129,'Unsupported claims and missing context below are errors to diagnose.',size=23,color=RED)
        text(ax,24,1089,'Reliable real-world cube manipulation',size=49,weight='semibold')
        text(ax,24,1020,'Error: the title claims physical evidence that these records do not contain.',size=24,color=RED)
        panel(ax,24,963,248,870,'Background')
        body=('Robot hands have many joints and contact interactions. Learning can produce complex behavior. '
              'A poster can describe every implementation detail, but readers must still determine the question, '
              'the contribution and what was actually tested. ')
        text(ax,35,918,body*7,size=23,width=26)
        panel(ax,291,963,250,450,'Method')
        text(ax,303,916,'Policy\n\nSimulator\n\nResults',size=38,weight='semibold')
        text(ax,303,660,'Error: observation/action meaning,\nsource and conditions are absent.',size=23,color=RED)
        panel(ax,561,963,256,450,'Results')
        text(ax,578,914,'88%',size=100,color=BLUE,weight='semibold')
        text(ax,578,805,'It works!',size=43,weight='semibold')
        text(ax,578,732,'Error: no denominator,\ntimeout count, criterion\nor evaluation scope.',size=23,color=RED)
        panel(ax,291,491,526,398,'Example')
        ax.imshow(Image.open(ROOT/'inputs/selected-step-0356.png'),extent=(306,802,163,442),aspect='auto',zorder=2)
        text(ax,306,147,'Error: selected simulation image presented without identity or limits.',size=22,color=RED)
        text(ax,24,66,'The number and image come from retained evidence; the framing is intentionally wrong.\nUse this poster to diagnose communication and scientific-scope errors.',size=21,color=RED)
    for item in set(ax.texts)-before_text:
        item.set_fontsize(item.get_fontsize()*scale)


def bar(ax,x,y,w,h,total,success):
    ax.add_patch(Rectangle((x,y-h),w*success/total,h,facecolor=BLUE,edgecolor='white',lw=1))
    ax.add_patch(Rectangle((x+w*success/total,y-h),w*(total-success)/total,h,facecolor=ORANGE,edgecolor='white',lw=1,hatch='///'))
    text(ax,x+w*.40,y-13,'88 reached',size=27,color='white',ha='center',weight='semibold')
    text(ax,x+w*.94,y-13,'12',size=25,color='white',ha='center',weight='semibold')


def export(fig, name, dpi=160):
    fig.canvas.draw()
    fonts=set()
    for item in fig.findobj(Text):
        if not item.get_text():
            continue
        path=Path(fm.findfont(item.get_fontproperties(),fallback_to_default=False))
        font=fm.get_font(str(path))
        if font.family_name!='MiSans':
            raise RuntimeError(f'Unexpected font {font.family_name}')
        missing={c for c in item.get_text() if not c.isspace() and ord(c) not in font.get_charmap()}
        if missing:
            raise RuntimeError(f'Missing MiSans glyphs {missing}')
        fonts.add(path.name)
    for ext in ('png','svg','pdf'):
        fig.savefig(ROOT/f'{name}.{ext}',dpi=dpi,facecolor='white')
    AUDIT.append({'name':name,'width_mm':round(fig.get_figwidth()*25.4,3),
                  'height_mm':round(fig.get_figheight()*25.4,3),'png_dpi':dpi,'fonts':sorted(fonts)})
    plt.close(fig)


def posters():
    for revised in (False,True):
        fig=plt.figure(figsize=(841/25.4,1189/25.4))
        draw_poster(fig.add_axes([0,0,1,1]),revised)
        export(fig,'poster-after-a0' if revised else 'poster-before-a0',dpi=100)


def comparison(mode):
    width=182 if mode=='paper' else 364
    ratio=width/182
    fig=plt.figure(figsize=(width/25.4,142*ratio/25.4))
    for k,revised in enumerate((False,True)):
        ax=fig.add_axes([.015+k*.5,.055,.47,.89])
        draw_poster(ax,revised,scale=.1005*ratio)
        fig.text(.25+k*.5,.978,'a  Before: diagnose the errors' if not revised else 'b  After: bound the argument',
                 ha='center',va='top',fontsize=8*ratio,weight='semibold',color=INK)
    export(fig,f'poster-comparison-{mode}',dpi=450 if mode=='paper' else 200)


def evidence_detail(mode):
    ratio=1 if mode=='paper' else 2
    fig,axes=plt.subplots(1,2,figsize=(182*ratio/25.4,88*ratio/25.4))
    fig.subplots_adjust(left=.02,right=.985,bottom=.05,top=.97,wspace=.09)
    for ax in axes:
        ax.set(xlim=(0,100),ylim=(0,100));ax.axis('off')
    a,b=axes
    text(a,0,98,'a  Percentage without its experiment',size=8*ratio,weight='semibold')
    text(a,4,82,'88%',size=39*ratio,color=BLUE,weight='semibold')
    text(a,4,51,'“It works!”',size=15*ratio)
    text(a,4,30,'Missing: denominator, failures,\nsuccess rule and simulation scope.\nThis is an intentionally incomplete caption.',size=7*ratio,color=RED)
    text(b,0,98,'b  Evidence with an interpretable caption',size=8*ratio,weight='semibold')
    b.add_patch(Rectangle((4,67),80*.88,13,facecolor=BLUE,edgecolor='white'))
    b.add_patch(Rectangle((4+80*.88,67),80*.12,13,facecolor=ORANGE,hatch='///',edgecolor='white'))
    text(b,4,60,'88/100 first targets reached',size=11*ratio,weight='semibold')
    text(b,4,44,'12 timeouts; 0 falls. Native MuJoCo 3.6.0,\noriginal observation noise; seeds 20000–20099.\nFirst goal below 0.1 rad before fall or 50 s.\nAll 100 trial outcomes are retained.',size=7*ratio)
    text(b,4,15,'Supports this simulated first-goal protocol.\nPhysical-hand reliability remains untested.',size=7*ratio,color=BLUE)
    export(fig,f'evidence-detail-{mode}',dpi=450 if mode=='paper' else 200)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font',type=Path,action='append',required=True)
    args=parser.parse_args()
    # A host font cache can contain other MiSans faces with nonstandard weight
    # numbers. Resolve this document only against the explicitly supplied pair.
    fm.fontManager.ttflist = [entry for entry in fm.fontManager.ttflist if entry.name != 'MiSans']
    fm.fontManager._findfont_cached.cache_clear()
    fonts=apply_publication_style(args.font)
    plt.rcParams.update({'svg.fonttype':'none','pdf.fonttype':42})
    posters()
    for mode in ('paper','classroom'):
        comparison(mode);evidence_detail(mode)
    paths=[p for p in ROOT.rglob('*') if p.is_file() and p.name!='provenance.json' and '__pycache__' not in str(p)]
    result={'generator':'source/generate_class18.py','matplotlib':matplotlib.__version__,
            'fonts':fonts,'exports':AUDIT,'retained_outcomes':{'successes':88,'timeouts':12,'falls':0,'total':100},
            'sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}}
    (ROOT/'provenance.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Six figure canvases exported as PNG/SVG/PDF; outcomes and MiSans glyph preflight passed.')
