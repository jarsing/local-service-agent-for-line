"""真正執行離線測試；SDK 可用性另列，不把安裝缺漏當作模型結果。"""
from __future__ import annotations
import argparse
import contextlib
import importlib.metadata
import io
from pathlib import Path
import platform
import unittest
from bridge import hashes, schema
from versioning import folder,save,now


def sdk_check():
    try:
        from google.genai import types
        part=types.Part.from_bytes(data=b'\x89PNG\r\n\x1a\n',mime_type='image/png')
        cfg=types.GenerateContentConfig(response_mime_type='application/json',response_json_schema=schema().Extraction.model_json_schema(),
            max_output_tokens=8192,thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW))
        return {'status':'PASS','scope':'SDK 型別與組態；未送出 API','version':importlib.metadata.version('google-genai'),
                'image_mime':part.inline_data.mime_type,'thinking_level':str(cfg.thinking_config.thinking_level)}
    except Exception as exc:
        return {'status':'BLOCKED','type':type(exc).__name__,'detail':str(exc),'scope':'SDK 型別與組態，未呼叫 API'}


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--sdk',action='store_true');p.add_argument('--origin',default='operator_not_recorded')
    p.add_argument('--output',type=Path,default=Path('output/day07'));a=p.parse_args(argv)
    out=folder(a.output,'offline');stream=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_day07.py')
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (out/'tests.txt').write_text(stream.getvalue(),encoding='utf-8')
    report={'kind':'LOCAL_DAY07_OFFLINE','created_at':now(),'origin':a.origin,'python':platform.python_version(),
            'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'skipped':len(result.skipped),'status':'PASS' if result.testsRun>0 and result.wasSuccessful() else 'FAIL',
            'source_hashes':hashes(),'sdk':sdk_check() if a.sdk else {'status':'NOT_RUN'}}
    save(out/'verification.json',report)
    print(stream.getvalue());print('紀錄：',out);print('SDK：',report['sdk']['status'])
    return 0 if report['status']=='PASS' and report['sdk']['status'] in ('NOT_RUN','PASS') else 2

if __name__=='__main__':raise SystemExit(main())
