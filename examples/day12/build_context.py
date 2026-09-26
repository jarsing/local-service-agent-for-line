"""只匯出列明原始碼。不要把作者整個 Repo／金鑰／證據上傳到容器建置。"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]

RUNTIME=['__init__.py','inherit.py','settings.py','identity.py','catalog_view.py','tasks.py',
         'delivery.py','messages.py','query.py','adk_query.py','main.py']

def export(out):
    out=out.resolve()
    if out.exists() or out.is_relative_to(REPO):
        raise ValueError('建置輸出須為 Repo 外尚不存在的資料夾。')
    files=[REPO/'LICENSE',REPO/'docs/day01/handoff-timeout-001.json',REPO/'examples/day05/catalog.py',
        REPO/'examples/day08/confirmation.py',REPO/'examples/day11/dependency-lock.json']
    files += [REPO/'examples/day09'/n for n in ('dependencies.py','day08_gateway.py','handoff.py','fixtures.json')]
    files += [REPO/'examples/day11'/n for n in ('upstream.py','domain.py','store.py','service.py',
                                              'confirmation_gate.py','jobs.py','firestore_store.py')]
    files += [HERE/n for n in RUNTIME+['requirements.txt','requirements-core.txt']]
    if not all(p.is_file() and not p.is_symlink() for p in files):raise ValueError('來源缺檔或含符號連結。')
    out.mkdir(parents=True)
    hashes={}
    for p in files:
        rel=p.relative_to(REPO);target=out/rel;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(p.read_bytes());hashes[str(rel)]=hashlib.sha256(p.read_bytes()).hexdigest()
    for n in ('Dockerfile','.dockerignore'):
        shutil.copy2(HERE/n,out/n)
    try:
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,stderr=subprocess.DEVNULL,text=True).strip()
        dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True))
    except (OSError,subprocess.CalledProcessError):head=None;dirty=None
    report={'files':hashes,'git_head':head,'working_tree_dirty':dirty,
            'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'meaning':'File hashes describe these exact bytes; git_head alone does not certify uncommitted source.'}
    (out/'SOURCE_MANIFEST.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    print(json.dumps(export(a.out),ensure_ascii=False,indent=2))
