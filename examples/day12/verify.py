"""具名分層驗證；缺相依是 unavailable，不是成功略過。"""
import argparse
import os
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import io
import json
import platform
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent

def verify(group,out,origin):
    out.mkdir(parents=True,exist_ok=False)
    report={'origin':'github_actions' if os.environ.get('GITHUB_ACTIONS')=='true' else origin,
        'requested_origin':origin,'github_run_id':os.environ.get('GITHUB_RUN_ID'),
        'github_run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),
        'source_commit':os.environ.get('GITHUB_SHA'), 'group':group,'python':sys.version,'platform':platform.platform(),
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'status':'not_executed','success':False,
        'source_files':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')},
        'installed_packages':{}}
    for name in ('fastapi','httpx','uvicorn','google-adk','google-genai','google-cloud-firestore'):
        try:report['installed_packages'][name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:report['installed_packages'][name]=None
    try:
        import fastapi,httpx
        if group=='adk':
            import google.adk,google.genai
        elif group=='emulator':
            import google.cloud.firestore
        module={'core':'test_core','adk':'test_adk','emulator':'test_emulator'}[group]
        suite=unittest.defaultTestLoader.loadTestsFromName('examples.day12.'+module)
        log=io.StringIO();result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        (out/'tests.txt').write_text(log.getvalue(),encoding='utf-8')
        report.update(status='executed',run=result.testsRun,failures=len(result.failures),
            errors=len(result.errors),skipped=len(result.skipped),
            passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
            success=result.wasSuccessful() and not result.skipped,
            failed_tests=[str(t) for t,_ in result.failures+result.errors])
    except ImportError as exc:
        report.update(status='dependency_unavailable',run=0,passed=0,failures=0,errors=0,skipped=0,
                      error_type=type(exc).__name__,reason=str(exc))
    report['exit_code']=0 if report['success'] else 2 if report['status']=='dependency_unavailable' else 1
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));return report['exit_code']

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--group',choices=['core','adk','emulator'],default='core')
    p.add_argument('--origin',choices=['reader_local','author_local','assistant_check'],default='reader_local')
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();raise SystemExit(verify(a.group,a.out,a.origin))
