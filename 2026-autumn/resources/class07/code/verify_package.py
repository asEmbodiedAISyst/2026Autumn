"""Check the extracted student package manifest using only the standard library."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parent.parent
manifest=json.loads((root/'package-manifest.json').read_text())
for name,digest in manifest['files'].items():
    p=root/name
    if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
        raise SystemExit('Package verification failed: '+name)
print('Verified',len(manifest['files']),'packaged files')
