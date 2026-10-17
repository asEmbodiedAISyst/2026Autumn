"""Stream training logs and fail the run if fixed GPU buffers overflow."""
import json,os,re,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OVERFLOW=re.compile(r'(?:nefc|ncon|nacon|ncollision|njmax|nconmax|naconmax)\s+overflow|overflow.*(?:njmax|nconmax|naconmax|nefc|ncollision)',re.I)


def supervise(command,receipt):
    started=time.time()
    child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    try:
        for line in child.stdout:
            print(line,end='',flush=True)
            if OVERFLOW.search(line):
                child.terminate()
                try:child.wait(timeout=30)
                except subprocess.TimeoutExpired:child.kill();child.wait()
                Path(receipt).write_text(json.dumps(dict(status='rejected-buffer-overflow',line=line.strip(),
                     elapsed_seconds=time.time()-started,command=command),indent=2)+'\n')
                print('Training stopped: GPU buffer overflow. Preserve this run for diagnosis; do not resume these weights.',flush=True)
                return 86
        return child.wait()
    finally:
        if child.poll() is None:
            child.terminate()
            try:child.wait(timeout=30)
            except subprocess.TimeoutExpired:child.kill();child.wait()


def main():
    assert sys.platform.startswith('linux') and sys.prefix!=sys.base_prefix
    assert Path(sys.prefix).resolve()==(ROOT/'.venv-gpu').resolve()
    command=sys.argv[1:];assert command
    assert Path(command[0]).absolute()==ROOT/'.venv-gpu/bin/python'
    receipt=Path(os.environ['CLASS06_RUN_DIR'])/'overflow-failure.json'
    sys.exit(supervise(command,receipt))

if __name__=='__main__':main()
