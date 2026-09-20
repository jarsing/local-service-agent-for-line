"""執行本機測試與合成反例；可加做 SDK 型別與設定的離線檢查。"""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import platform
import unittest
from reporting import now,dump_json,new_folder,packages,sources_sha,error_info
from counterexample import demonstrate,fixture


def sdk_check():
    from google.genai import types
    from run import make_config,parse_response
    config=make_config()
    part=types.Part.from_bytes(data=b'OFFLINE_BYTE_FIXTURE',mime_type='image/png')
    assert part.inline_data.mime_type=='image/png'
    assert config.response_mime_type=='application/json'
    response=types.GenerateContentResponse.model_validate({'candidates':[{'content':{'role':'model','parts':[{'text':json.dumps(fixture(),ensure_ascii=False)}]},'finish_reason':'STOP'}]})
    assert parse_response(response)['status']=='EXTRACTED'
    return {'status':'PASS','scope':'SDK 型別、schema 組態與離線回覆轉換；未呼叫 API'}


def main(argv=None):
    p=argparse.ArgumentParser(description='LOCAL Day 6 離線驗證')
    p.add_argument('--sdk',action='store_true');p.add_argument('--output',type=Path,default=Path('output/day06'))
    p.add_argument('--origin',default='operator_not_recorded');a=p.parse_args(argv)
    folder=new_folder(a.output,'offline');buf=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_day06.py')
    result=unittest.TextTestRunner(stream=buf,verbosity=2).run(suite)
    sdk={'status':'NOT_REQUESTED'}
    if a.sdk:
        try:sdk=sdk_check()
        except Exception as exc:sdk={'status':'BLOCKED','error':error_info(exc)}
    demo=demonstrate()
    ok=result.wasSuccessful() and result.testsRun>0 and not result.skipped and (not a.sdk or sdk['status']=='PASS')
    record={'kind':'LOCAL_DAY06_OFFLINE','origin':a.origin,'created_at':now(),
        'python':platform.python_version(),'platform':platform.system(),'packages':packages(),
        'tests':{'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped)},
        'sdk':sdk,'counterexample':demo,'code_sha256':sources_sha(),'overall':'PASS' if ok else 'NEEDS_ATTENTION'}
    dump_json(folder/'verification.json',record);dump_json(folder/'counterexample.json',demo)
    (folder/'tests.txt').write_text(buf.getvalue(),encoding='utf-8')
    print(buf.getvalue());print(json.dumps(record,ensure_ascii=False,indent=2));print(f'紀錄位置：{folder}')
    return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
