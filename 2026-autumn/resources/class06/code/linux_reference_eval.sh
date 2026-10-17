#!/usr/bin/env bash
# Standalone original-Playground evaluation inside this Class06 directory.
set -euo pipefail
REUSE_VENV=""
if [[ $# == 2 && "$1" == --reuse-venv ]]; then
  REUSE_VENV=$(cd "$2" && pwd)
elif [[ $# != 0 ]]; then
  echo 'Usage: bash linux_reference_eval.sh [--reuse-venv /path/to/existing/.venv-gpu]'; exit 2
fi
[[ $(uname -s) == Linux ]] || { echo 'This GPU evaluation requires Linux.'; exit 2; }
ROOT=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT"
PYTHON=${CLASS06_PYTHON:-python3.12}
ENV_DIR="$ROOT/.venv-reference"
if [[ -n "$REUSE_VENV" ]]; then ENV_DIR="$REUSE_VENV"; PYTHON="$ENV_DIR/bin/python"; fi
exec 9>"$ROOT/.reference-eval.lock"
flock -n 9 || { echo "A Class06 evaluation is already running; no second run started."; exit 2; }
mkdir -p runs .cache/pip .cache/tmp .cache/cuda
RUN_DIR=$(mktemp -d "$ROOT/runs/reference-eval-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
finish() {
  CODE=$?
  trap - EXIT
  printf '%s\n' "$CODE" > "$RUN_DIR/exit-code.txt"
  tar -czf "$RUN_DIR-Results.tar.gz" -C "$ROOT/runs" "$(basename "$RUN_DIR")"
  printf '\nResults archive: %s-Results.tar.gz\n' "$RUN_DIR"
  exit "$CODE"
}
trap finish EXIT
export PYTHONNOUSERSITE=1
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export XDG_CACHE_HOME="$ROOT/.cache"
export JAX_COMPILATION_CACHE_DIR="$ROOT/.cache/jax"
export CLASS06_CACHE_DIR="$ROOT/.cache"
export TMPDIR="$ROOT/.cache/tmp"
export CUDA_CACHE_PATH="$ROOT/.cache/cuda"
export PYTHONPYCACHEPREFIX="$ROOT/.cache/pycache"
export PYTHONUNBUFFERED=1
unset PYTHONPATH
run_evaluation() {
"$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3,12), "Python3.12 required; use CLASS06_PYTHON to select it"'
[[ ! -L "$ENV_DIR" && ! -L upstream ]] || { echo "Environment/source symlinks are not used; existing targets preserved."; exit 2; }
if [[ -z "$REUSE_VENV" && -e "$ENV_DIR" && ! -f "$ENV_DIR/.class06-owned" ]]; then
  echo 'Existing .venv-reference has no Class06 ownership marker; refusing to modify it.'; exit 2
fi
if [[ -z "$REUSE_VENV" && ! -e "$ENV_DIR" ]]; then
  "$PYTHON" -m venv "$ENV_DIR"
  printf 'Class06 isolated reference environment\n' > "$ENV_DIR/.class06-owned"
fi
PYTHON="$ENV_DIR/bin/python"
"$PYTHON" - "$ENV_DIR" <<'PY'
import sys
from pathlib import Path
expected=Path(sys.argv[1]).resolve()
assert sys.prefix != sys.base_prefix and Path(sys.prefix).resolve()==expected
assert 'include-system-site-packages = false' in (expected/'pyvenv.cfg').read_text()
print('Isolated environment:',sys.prefix)
PY
"$PYTHON" verify_package.py
PIN=$("$PYTHON" -c 'import json; print(json.load(open("provenance.json"))["playground_commit"])')
if [[ -e upstream && ! -f upstream/.git/class06-owned ]]; then
  echo 'Existing upstream folder has no ownership marker; refusing to modify it.'; exit 2
fi
if [[ ! -e upstream ]]; then
  SOURCE_TMP=$(mktemp -d "$ROOT/.source-XXXXXX")
  git -C "$SOURCE_TMP" init -q
  git -C "$SOURCE_TMP" remote add origin https://github.com/google-deepmind/mujoco_playground.git
  git -C "$SOURCE_TMP" fetch --depth 1 origin "$PIN"
  git -C "$SOURCE_TMP" checkout --detach FETCH_HEAD
  printf 'Class06 pinned upstream source\n' > "$SOURCE_TMP/.git/class06-owned"
  mv "$SOURCE_TMP" upstream
fi
[[ $(git -C upstream rev-parse HEAD) == "$PIN" ]] || { echo 'Upstream pin mismatch; source preserved.'; exit 2; }
[[ -z $(git -C upstream status --porcelain --untracked-files=no) ]] || { echo 'Tracked upstream source has edits; source preserved.'; exit 2; }
if [[ -z "$REUSE_VENV" ]]; then
  "$PYTHON" -m pip --isolated install --cache-dir "$ROOT/.cache/pip" -r requirements-gpu-reference.txt
  "$PYTHON" -m pip --isolated install --cache-dir "$ROOT/.cache/pip" --constraint constraints-gpu-reference.txt -e ./upstream
  "$PYTHON" -m pip --isolated check
  OVERLAY_PATH=""
else
  # Validate reused runtime, without installing into it or changing its source.
  "$PYTHON" - <<'PYCODE'
import importlib.metadata
pins={'jax':'0.11.2','mujoco':'3.14.0','mujoco-mjx':'3.14.0','mujoco-warp':'3.14.0','warp-lang':'1.17.0','brax':'0.14.2'}
for name,version in pins.items():
 actual=importlib.metadata.version(name)
 assert actual==version, f'Reused runtime mismatch: {name} {actual}, expected {version}; no modification made. Use fresh mode.'
print('Reused GPU runtime versions verified; original installation unchanged.')
PYCODE
  "$PYTHON" -m pip --isolated freeze > "$RUN_DIR/reused-environment-before.txt"
  OVERLAY_PATH="$ROOT/.inference-deps"
  if [[ -L "$OVERLAY_PATH" || ( -e "$OVERLAY_PATH" && ! -f "$OVERLAY_PATH/.class06-owned" ) ]]; then
    echo 'Existing inference overlay is not owned by this launcher; preserved.'; exit 2
  fi
  mkdir -p "$OVERLAY_PATH"
  printf 'Class06 inference overlay\n' > "$OVERLAY_PATH/.class06-owned"
  "$PYTHON" -m pip --isolated install --cache-dir "$ROOT/.cache/pip" --target "$OVERLAY_PATH" --upgrade --no-deps \
    'onnxruntime==1.30.0' 'flatbuffers==25.12.19' 'packaging==26.3' 'protobuf==7.36.2' 'pillow==12.3.0'
fi
# Supply only the pinned LEAP meshes; avoid automatic Menagerie download.
mkdir -p upstream/mujoco_playground/external_deps/mujoco_menagerie/leap_hand/assets
for ASSET in models/assets/*.obj; do
  DEST="upstream/mujoco_playground/external_deps/mujoco_menagerie/leap_hand/assets/$(basename "$ASSET")"
  if [[ -e "$DEST" ]]; then
    cmp -s "$ASSET" "$DEST" || { echo "Existing asset differs: $DEST; preserved."; exit 2; }
  else cp "$ASSET" "$DEST"; fi
done
LICENSE_DEST=upstream/mujoco_playground/external_deps/mujoco_menagerie/leap_hand/LICENSE
if [[ -e "$LICENSE_DEST" ]]; then
  cmp -s models/MENAGERIE-LICENSE "$LICENSE_DEST" || { echo 'Existing license differs; preserved.'; exit 2; }
else cp models/MENAGERIE-LICENSE "$LICENSE_DEST"; fi
export PYTHONPATH="$ROOT/upstream"
if [[ -n "$OVERLAY_PATH" ]]; then export PYTHONPATH="$OVERLAY_PATH:$ROOT/upstream"; fi
"$PYTHON" -m pip --isolated freeze > "$RUN_DIR/requirements-lock.txt"
"$PYTHON" - <<'PY' > "$RUN_DIR/environment.json"
import json,sys,jax,importlib.metadata
print(json.dumps({'virtual_environment':sys.prefix,'python':sys.version,
 'devices':[str(d) for d in jax.devices()],
 'versions':{n:importlib.metadata.version(n) for n in ('jax','mujoco','mujoco-mjx','mujoco-warp','warp-lang','brax','onnxruntime')}},indent=2))
PY
"$PYTHON" - "$PYTHON" "$ROOT" "$RUN_DIR" <<'PY'
import sys
from pathlib import Path
from gpu_training_guard import supervise
python,root,out=sys.argv[1:]
for noise in (0,1):
 cmd=[python,str(Path(root)/'qualification.py'),'--backend','playground','--upstream-dir',str(Path(root)/'upstream'),
      '--noise-level',str(noise),'--sim-dt','.01','--seed','20000','--episodes','100','--output',str(Path(out)/f'playground-noise-{noise}')]
 code=supervise(cmd,str(Path(out)/'overflow-failure.json'))
 if code:raise SystemExit(code)
PY

if [[ -n "$REUSE_VENV" ]]; then
  PYTHONPATH="" "$PYTHON" -m pip --isolated freeze > "$RUN_DIR/reused-environment-after.txt"
  cmp "$RUN_DIR/reused-environment-before.txt" "$RUN_DIR/reused-environment-after.txt"
  printf 'Reused environment package list unchanged.\n' > "$RUN_DIR/reused-environment-verification.txt"
fi
}
run_evaluation 2>&1 | tee "$RUN_DIR/launcher.log"
