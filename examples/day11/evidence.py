"""真正執行來源、輸出檔與測試端觀察；不用報告欄位自證。"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,platform,secrets,socket,sys


def dump(path: Path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_manifest():
    here=Path(__file__).resolve().parent
    root=here.parents[1]
    paths=list(here.glob('*.py'))+list(here.glob('*.json'))+list(here.glob('*.txt'))+list(here.glob('*.rules'))
    for day in ('day02','day08','day09','day10'):
        paths.extend(q for q in (root/'examples'/day).glob('*') if q.suffix in ('.py','.json','.txt'))
    paths.append(root/'docs/day01/handoff-timeout-001.json')
    paths.extend((root/'.github/workflows').glob('*.yml'))
    return {str(p.relative_to(root)):sha(p) for p in sorted(paths) if p.is_file()}


def execution(origin):
    import subprocess
    from importlib.metadata import version,PackageNotFoundError
    ci=os.getenv('GITHUB_ACTIONS')=='true';root=Path(__file__).resolve().parents[2]
    commit=os.getenv('GITHUB_SHA');dirty=None
    if not ci and (root/'.git').exists():
        try:
            r=subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True,timeout=5)
            if r.returncode==0:commit=r.stdout.strip()
            status=subprocess.run(['git','status','--porcelain'],cwd=root,capture_output=True,text=True,timeout=5)
            if status.returncode==0:dirty=bool(status.stdout.strip())
        except (OSError,subprocess.TimeoutExpired):pass
    packages={}
    for name in ('google-cloud-firestore','google-adk','google-genai'):
        try:packages[name]=version(name)
        except PackageNotFoundError:packages[name]=None
    return {'origin':'github_actions' if ci else origin,'requested_origin':origin,
            'environment':'github_actions' if ci else 'local_process',
            'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),
            'platform':platform.platform(),'pid':os.getpid(),'installed_packages':packages,
            'source_commit':commit,'working_tree_dirty':dirty,'run_id':os.getenv('GITHUB_RUN_ID'),
            'run_attempt':os.getenv('GITHUB_RUN_ATTEMPT'),'job':os.getenv('GITHUB_JOB')}


def new_run(root, prefix):
    path=Path(root)/(prefix+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(4))
    path.mkdir(parents=True,exist_ok=False);return path


class Trace:
    def __init__(self,path):
        self.path=Path(path);self.seq=0
    def emit(self,kind,**values):
        self.seq+=1
        item={'seq':self.seq,'kind':kind,'pid':os.getpid(),**values}
        with self.path.open('a',encoding='utf-8') as f:
            f.write(json.dumps(item,ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())


@contextmanager
def no_network():
    """封鎖本Python行程的網路連線/DNS；保留socket類別與asyncio自用socketpair。"""
    os.environ['OTEL_SDK_DISABLED']='true'
    targets=[(socket.socket,'connect'),(socket.socket,'connect_ex'),
             (socket,'create_connection'),(socket,'getaddrinfo')]
    old=[(owner,name,getattr(owner,name)) for owner,name in targets]
    def blocked(*a,**kw):raise RuntimeError('NETWORK_BLOCKED_IN_OFFLINE_TEST')
    try:
        for owner,name,_ in old:setattr(owner,name,blocked)
        yield
    finally:
        for owner,name,value in old:setattr(owner,name,value)
