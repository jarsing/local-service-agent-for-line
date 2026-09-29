"""沿用 Day 14 白名單，僅加入 Day 15 執行接點；不動前篇。"""
import argparse
import hashlib
import json
from pathlib import Path
from examples.day14.build_context import export as export_day14

HERE=Path(__file__).resolve().parent
RUNTIME=('__init__.py','session_budget.py','context_store.py','token_counter.py',
         'policy.py','adk_budget_router.py','main.py')


def export(out:Path):
    for name in (*RUNTIME,'Dockerfile'):
        path=HERE/name
        if not path.is_file() or path.is_symlink(): raise ValueError('MISSING_OR_LINKED_SOURCE')
    report=export_day14(out)
    for name in RUNTIME:
        target=out/'examples/day15'/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((HERE/name).read_bytes())
        report['files']['examples/day15/'+name]=hashlib.sha256(target.read_bytes()).hexdigest()
    (out/'Dockerfile').write_bytes((HERE/'Dockerfile').read_bytes())
    report['files']['Dockerfile']=hashlib.sha256((out/'Dockerfile').read_bytes()).hexdigest()
    report['day15_entrypoint']='examples.day15.main:app'
    report['day15_privacy']='Public projections only; two exchanges and bounded goal; preference revision gate'
    (out/'SOURCE_MANIFEST.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    print(json.dumps(export(p.parse_args().out),ensure_ascii=False,indent=2))
