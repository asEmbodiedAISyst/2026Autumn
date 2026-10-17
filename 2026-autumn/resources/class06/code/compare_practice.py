"""Compare matched native simulation traces; no dependencies or simulation."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('reference',type=Path);p.add_argument('letters',type=Path);a=p.parse_args()
def read(folder):
 s=json.loads((folder/'summary.json').read_text());t=[json.loads(x) for x in (folder/'trace.jsonl').read_text().splitlines()];return s,t
sa,ta=read(a.reference);sb,tb=read(a.letters)
for field in ['noise_level','physics_dt','control_dt','policy_sha256','playground_commit','versions']:assert sa[field]==sb[field],field
assert sa['variant']=='reference' and sb['variant']=='letters'
assert ta and ta==tb,'Trace mismatch: inspect the first differing row'
assert all(x['engine_warnings']==0 for s in [sa,sb] for x in s['episodes'])
print(json.dumps(dict(passed=True,rows_per_variant=len(ta),saved_fields_identical=True,engine_warnings=0,scope='Matched display intervention only'),indent=2))
