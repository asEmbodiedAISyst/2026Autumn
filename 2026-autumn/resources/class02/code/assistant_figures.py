"""Portable Class 02 source-figure reproduction with MiSans.

Adapted from Mohamad Halwani's generate_specification_plots.py, Assistants
students commit f7c118edaadc9f33498669736fa9d99160ff629a. The original is
retained under source/assistant/. No hardware is connected or commanded.
"""
from pathlib import Path
import argparse
import csv
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'source'))
from figure_typography import apply_publication_style


def architecture(regular,semibold):
    """Original functional command path, not a physical sensor-location map."""
    fig,ax=plt.subplots(figsize=(13,4),dpi=220)
    ax.set(xlim=(0,13),ylim=(0,4));ax.axis('off')
    boxes=[(.3,'Host','bounded command\nconfigured limits','#dbeafe'),
           (2.9,'Protocol 2.0','ID + instruction\nCRC','#cffafe'),
           (5.5,'Embedded control','mode + profile\nfeedback','#ede9fe'),
           (8.1,'Drive + motor','electrical effort','#ffedd5'),
           (10.7,'Transmission','motion + load','#dcfce7')]
    width,height,y=2,1.2,2.15
    for x,title,detail,color in boxes:
        ax.add_patch(FancyBboxPatch((x,y),width,height,boxstyle='round,pad=0.08,rounding_size=0.10',linewidth=1.5,edgecolor='#1f4b67',facecolor=color))
        ax.text(x+width/2,y+.78,title,ha='center',va='center',fontproperties=semibold,fontsize=11,color='#102a43')
        ax.text(x+width/2,y+.34,detail,ha='center',va='center',fontproperties=regular,fontsize=8.8,color='#243b53')
    for left,right in zip(boxes,boxes[1:]):
        ax.add_patch(FancyArrowPatch((left[0]+width+.08,y+height/2),(right[0]-.08,y+height/2),arrowstyle='-|>',mutation_scale=14,linewidth=1.6,color='#1f4b67'))
    ax.add_patch(FancyArrowPatch((11.75,2.03),(1.25,2.03),connectionstyle='arc3,rad=-.30',arrowstyle='-|>',mutation_scale=16,linewidth=1.8,color='#b45309'))
    ax.text(6.5,.38,'measured position, velocity, input current, PWM, voltage, temperature and status',ha='center',va='center',fontproperties=regular,fontsize=9.2,color='#92400e',bbox={'facecolor':'white','edgecolor':'none','pad':2.5})
    ax.text(6.5,3.72,'command  →  internal reference  →  physical response',ha='center',va='center',fontproperties=semibold,fontsize=15,color='#102a43')
    return fig


def telemetry(regular,semibold):
    """Same 2,601 observations as the source, read from the audited CSV."""
    with (ROOT/'data/xc330-hardware-demo/telemetry_events.csv').open(newline='') as f:
        data=list(csv.DictReader(f))
    assert len(data)==2601
    assert {r['source_type'] for r in data}=={'physical_hardware_telemetry'}
    t=np.array([float(r['t_state_s']) for r in data]);t-=t[0]
    fields=[('Position','present_position_raw','position_meas_rad','ticks','rad'),
            ('Velocity','present_velocity_raw','velocity_meas_rad_s','raw','rad/s'),
            ('Input current','present_current_raw','current_meas_A','raw','A'),
            ('PWM','present_pwm_raw','pwm_meas_fraction','raw','fraction'),
            ('Input voltage','input_voltage_raw','input_voltage_V','raw','V'),
            ('Temperature','temperature_C','temperature_C','°C','°C')]
    colors=['#2563eb','#0891b2','#dc2626','#7c3aed','#ea580c','#16a34a']
    fig,axes=plt.subplots(6,2,figsize=(10.8,12.4),sharex=True,dpi=220)
    for i,((name,raw,decoded,raw_unit,unit),color) in enumerate(zip(fields,colors)):
        for j,(field,label,heading) in enumerate([(raw,raw_unit,'Raw control-table value'),(decoded,unit,'Decoded engineering value')]):
            ax=axes[i,j];ax.plot(t,[float(r[field]) for r in data],color=color,linewidth=.9)
            ax.grid(True,color='#cbd5e1',linewidth=.5,alpha=.65)
            ax.set_ylabel(f'{name}\n[{label}]',fontproperties=regular,fontsize=8);ax.tick_params(labelsize=7)
            if i==0:ax.set_title(heading,fontproperties=semibold,fontsize=10.5)
            if i==5:ax.set_xlabel('Host receive-end time from first row [s]',fontproperties=semibold,fontsize=9)
    fig.suptitle('XC330-M288-T physical hardware telemetry',fontproperties=semibold,fontsize=13,y=.995)
    fig.text(.5,.004,'2,601 device reads; ID 5; motor-only fixture. Present Current is input-supply current, not output torque.',ha='center',va='bottom',fontproperties=regular,fontsize=7.6,color='#334155')
    fig.tight_layout(rect=(0,.025,1,.98),h_pad=.65,w_pad=.8)
    return fig


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--figure',choices=['architecture','telemetry','both'],default='both')
    parser.add_argument('--font-dir',type=Path,default=ROOT/'source/fonts')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'media/generated-assistant')
    args=parser.parse_args()
    paths=[args.font_dir/f'MiSans-{w}.ttf' for w in ['Regular','Semibold']]
    apply_publication_style(paths)
    plt.rcParams.update({'font.family':'MiSans','pdf.fonttype':42,'svg.fonttype':'none'})
    regular,semibold=[FontProperties(fname=str(p)) for p in paths]
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for name,fn in [('architecture',architecture),('telemetry',telemetry)]:
        if args.figure not in ['both',name]:continue
        fig=fn(regular,semibold)
        for text in fig.findobj(matplotlib.text.Text):
            if text.get_text():
                from matplotlib import font_manager
                path=font_manager.findfont(text.get_fontproperties(),fallback_to_default=False)
                assert font_manager.get_font(path).family_name=='MiSans'
        for ext in ['png','pdf','svg']:
            fig.savefig(args.output_dir/f'{name}.{ext}',dpi=300,bbox_inches='tight')
        plt.close(fig)
        print(name,'generated with MiSans')


if __name__=='__main__':main()
