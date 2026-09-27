"""沿用 Day 13 的白名單，加入 Day 14 與兩筆公開資料；不動前篇。"""
import argparse
import hashlib
import json
from pathlib import Path
from examples.day13.build_context import export as export_day13

HERE=Path(__file__).resolve().parent
RUNTIME=('__init__.py','places.py','memory.py','engine.py','model_contract.py','trace_contract.py','adk_router.py','messages.py','main.py','data/places.json')

def export(out:Path):
    for name in (*RUNTIME,'Dockerfile'):
        path=HERE/name
        if not path.is_file() or path.is_symlink(): raise ValueError('MISSING_OR_LINKED_SOURCE')
    report=export_day13(out)
    for name in RUNTIME:
        target=out/'examples/day14'/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((HERE/name).read_bytes())
        report['files']['examples/day14/'+name]=hashlib.sha256(target.read_bytes()).hexdigest()
    (out/'Dockerfile').write_bytes((HERE/'Dockerfile').read_bytes())
    report['files']['Dockerfile']=hashlib.sha256((out/'Dockerfile').read_bytes()).hexdigest()
    report['day14_entrypoint']='examples.day14.main:app'
    report['day14_privacy']='Fresh model Session per turn; no persisted reply plan or personal query trace'
    (out/'SOURCE_MANIFEST.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    print(json.dumps(export(p.parse_args().out),ensure_ascii=False,indent=2))
