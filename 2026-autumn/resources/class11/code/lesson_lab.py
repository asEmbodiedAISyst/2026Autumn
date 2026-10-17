"""Class11 full-state replay and recorded-result inspection; no learned-policy inference."""
from pathlib import Path
import argparse,json,runpy,sys,math
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'consolidation/package/additional_material'
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('mode',choices=['replay','results']);ap.add_argument('--out',type=Path,default=ROOT/'results/replay-state.json');a=ap.parse_args()
 if a.mode=='replay':
  sys.argv=['replay_state_check.py','--out',str(a.out)];runpy.run_path(str(A/'code/replay_state_check.py'),run_name='__main__');return
 p=A/'data/videos/results_act_ip17_cube300_handheld_060000_pusher_n100.json';x=json.loads(p.read_text());es=x['episodes'];n=len(es);k=sum(e['success'] for e in es);v=k/n;z=1.959963984540054;den=1+z*z/n;mid=(v+z*z/(2*n))/den;half=z*math.sqrt(v*(1-v)/n+z*z/(4*n*n))/den
 report={'source':p.name,'episodes':n,'successes':k,'success_rate':v,'wilson_95_descriptive_interval':[mid-half,mid+half],'failure_episode_0':next(e for e in es if e['episode']==0),'scope':'stored evaluation outcomes only; binomial interval assumes independent comparable trials; policy not rerun'}
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
