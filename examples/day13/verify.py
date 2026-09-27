"""Run explicit local suites; JSON summary is not a replacement for logs/DB observations."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import unittest

GROUPS = {
    'renderer': ['examples.day13.test_flex'],
    'integration': ['examples.day13.test_flow', 'examples.day13.test_packaging'],
    'previous': ['examples.day12.test_core'],
}

def run(group, out, origin):
    out.mkdir(parents=True, exist_ok=False)
    selected = list(GROUPS) if group == 'all' else [group]
    results = []
    for name in selected:
        stream=io.StringIO()
        suite=unittest.defaultTestLoader.loadTestsFromNames(GROUPS[name])
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        (out/(name+'.log')).write_text(stream.getvalue(),encoding='utf-8')
        results.append({'group':name,'modules':GROUPS[name], 'run':result.testsRun,
                        'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
                        'passed':result.wasSuccessful() and not result.skipped})
    packages={}
    for name in ('fastapi','starlette','httpx','pydantic','google-adk','google-genai','google-cloud-firestore'):
        try: packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: packages[name]=None
    report={'origin':origin,'time_utc':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),
            'groups':results,'packages':packages,'passed':all(x['passed'] for x in results),
            'scope':'offline renderer + real inherited SQLite service + ASGI; model and LINE sender are stubs',
            'not_run':['LINE validation API','LINE device rendering','screen reader','Firestore service','Cloud Run','Gemini API',
                       'Day 12 three real-ADK tests (separate existing command)']}
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--group',choices=['all',*GROUPS],default='all')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--origin',choices=['assistant_check','author_local','ci'],default='author_local')
    a=p.parse_args();raise SystemExit(0 if run(a.group,a.out,a.origin)['passed'] else 1)
