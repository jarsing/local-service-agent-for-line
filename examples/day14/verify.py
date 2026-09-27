"""原始 unittest log 是結果依據；summary 只索引。缺相依不跳過算成功。"""
import argparse
from datetime import datetime,timezone
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import unittest

GROUPS={
 'core':['examples.day14.test_places','examples.day14.test_memory','examples.day14.test_engine','examples.day14.test_messages','examples.day14.test_packaging','examples.day14.test_model_contract','examples.day14.test_trace_contract'],
 'flow':['examples.day14.test_flow'],
 'adk':['examples.day14.test_adk'],
 'emulator':['examples.day14.test_emulator'],
 'previous':['examples.day12.test_core','examples.day13.test_flex','examples.day13.test_flow','examples.day13.test_packaging'],
}

def run(group,out,origin):
    out.mkdir(parents=True,exist_ok=False);groups=['core','flow'] if group=='all' else [group];results=[]
    for name in groups:
        stream=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromNames(GROUPS[name])
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        (out/(name+'.log')).write_text(stream.getvalue())
        results.append({'group':name,'modules':GROUPS[name],'run':result.testsRun,'failures':len(result.failures),
                        'errors':len(result.errors),'skipped':len(result.skipped),'passed':result.wasSuccessful() and not result.skipped})
    packages={}
    for k in ('fastapi','starlette','httpx','pydantic','google-adk','google-genai','google-cloud-firestore'):
        try:packages[k]=importlib.metadata.version(k)
        except importlib.metadata.PackageNotFoundError:packages[k]=None
    report={'origin':origin,'executed_at':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),
            'packages':packages,'groups':results,'passed':all(x['passed'] for x in results),
            'scope':'Group labels distinguish core/ASGI, real ADK scripted model, and Firestore Emulator. No group invokes real Gemini or LINE API.'}
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2));return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--group',choices=['all',*GROUPS],default='all');p.add_argument('--out',type=Path,required=True)
    p.add_argument('--origin',choices=['assistant_check','author_local','ci'],default='author_local');a=p.parse_args()
    raise SystemExit(0 if run(a.group,a.out,a.origin)['passed'] else 1)
