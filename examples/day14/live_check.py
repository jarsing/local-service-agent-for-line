"""核准後才執行的 Gemini 開發檢查；每次最多四回合，沒有自動重試。

只用合成句子、獨立 SQLite。確認由測試程式代送，不是真人或手機驗收。
預期答案不送給模型；保存原模型請求、ADK 工具三聯事件及 SQLite 前後快照。
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import secrets
import sqlite3
from dataclasses import replace
from examples.day12.testing import settings, RAW_USER
from examples.day12.identity import make_actor
from examples.day12.inherit import SQLiteTestStore
from examples.day12.catalog_view import CatalogView
from examples.day12.tasks import LineTasks
from .memory import PreferenceMemory
from .engine import TurnTools
from .places import PlacesCatalog
from .model_contract import INSTRUCTION, POLICY_VERSION, SUITES, instruction_sha256
from .trace_contract import check_development_case


def snapshot(db_path, destination):
    """Read the real local database directly, and make an independent SQLite backup."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as source:
        rows = [{'kind': k, 'ident': i, 'body': json.loads(b)}
                for k, i, b in source.execute(
                    'SELECT kind,ident,body FROM docs WHERE kind=? ORDER BY ident',
                    ('consented_preferences',)).fetchall()]
        with sqlite3.connect(destination.with_suffix('.sqlite3')) as target:
            source.backup(target)
    destination.with_suffix('.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    return rows


async def run(model_id, out, suite='lifecycle', origin='author_local'):
    out.mkdir(parents=True,exist_ok=False)
    catalog=PlacesCatalog(); db_path=out/'synthetic.sqlite3'
    store=SQLiteTestStore(db_path)
    config=settings(db_path); actor=make_actor(config,RAW_USER)
    LineTasks(store,CatalogView()).seed([actor])
    memory=PreferenceMemory(store,secrets.token_hex(32))
    packages={}
    for name in ('google-adk','google-genai','google-cloud-firestore'):
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]=None
    report={'origin':origin,'layer':'real_gemini_synthetic_development_check',
            'executed_at':datetime.now(timezone.utc).isoformat(),'model':model_id,
            'suite':suite,'maximum_model_calls':4,'python':platform.python_version(),'packages':packages,
            'configuration':{'temperature':0,'max_output_tokens':512,'thinking_level':'LOW','max_attempts':1},
            'confirmation_source':'test_program_not_human','policy_version':POLICY_VERSION,
            'instruction_sha256':instruction_sha256(),'catalog_sha256':catalog.sha256,
            'cases':[],'passed':False,'execution_state':'starting',
            'limits':'No LINE/Cloud Run, no broad accuracy, no held-out benchmark. Saved dietary values are not injected into the prompt. Raw model inputs are retained here only because all cases/actors are synthetic.'}
    (out/'instruction.txt').write_text(INSTRUCTION,encoding='utf-8')
    sessions=set()
    try:
        from .adk_router import AdkInterpreter
        router=AdkInterpreter(model_id)
        report['execution_state']='running'
        for index,case in enumerate(SUITES[suite],start=1):
            name=case['case']
            item={'case':name,'input':case['input'],'expectation':case,'passed':False}
            prefix=out/'snapshots'/f'{index:02d}-{name}'
            if name=='after_forget':
                item['forget_action']=memory.forget(actor,'synthetic-explicit-forget')
                item['forget_source']='test_program_explicit_command'
            before=snapshot(db_path,Path(str(prefix)+'-before'))
            turn_actor=replace(actor,session_id='synthetic-'+name)
            tools=TurnTools(memory,turn_actor,places=catalog,events=CatalogView())
            try:
                actual=await router.ask(case['input'],turn_actor,name,tools)
                item['actual']=actual
                if actual['session_id'] in sessions:raise AssertionError('SESSION_NOT_NEW')
                sessions.add(actual['session_id'])
                check_development_case(case,tools.calls)
                after=snapshot(db_path,Path(str(prefix)+'-after-model'))
                if before!=after:raise AssertionError('MODEL_CHANGED_PREFERENCE_STORAGE')
                if not actual['trace_linkage']['trace_linked']:raise AssertionError('TRACE_NOT_LINKED')
                if name=='propose':
                    if memory.inspect(actor)['status']!='empty':raise AssertionError('EARLY_PREFERENCE')
                    proposal=memory.propose(actor,tools.last['dietary_type'],'synthetic-consent')
                    consent=memory.approve(actor,proposal['token'])
                    item['explicit_confirmation']={'source':'test_program','result':consent}
                    snapshot(db_path,Path(str(prefix)+'-after-test-consent'))
                # Boundary proposals intentionally remain unconfirmed.
                item['passed']=True
            except Exception as exc:
                item.update(error_type=type(exc).__name__,
                            actual=getattr(exc,'report',item.get('actual')))
                snapshot(db_path,Path(str(prefix)+'-after-failure'))
                report['cases'].append(item)
                break
            report['cases'].append(item)
        report['passed']=len(report['cases'])==4 and all(x['passed'] for x in report['cases'])
        report['execution_state']='passed' if report['passed'] else 'failed'
    except Exception as exc:
        report['execution_state']='dependency_or_startup_failure'
        report['startup_error_type']=type(exc).__name__
        # Error text may contain provider/private details; do not copy arbitrary exception text.
    finally:
        report['model_calls_observed']=sum((x.get('actual') or {}).get('model_calls',0) for x in report['cases'])
        report['distinct_reported_session_count']=len(sessions)
        report['actual_modes']=sorted({(x.get('actual') or {}).get('mode','unknown') for x in report['cases']})
        report['real_gemini_executed']=bool(report['cases']) and all((x.get('actual') or {}).get('mode')=='ADK_GEMINI' for x in report['cases'])
        if report['cases'] and not report['real_gemini_executed']:
            report['layer']='explicit_test_double_harness_not_gemini_or_adk'
        (out/'live-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        close=getattr(store,'close',None)
        if close:close()
        files={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
               for p in out.rglob('*') if p.is_file() and p.name!='MANIFEST.sha256.json'}
        (out/'MANIFEST.sha256.json').write_text(json.dumps(files,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--suite',choices=tuple(SUITES),default='lifecycle')
    parser.add_argument('--origin',choices=('author_local','assistant_check'),default='author_local')
    parser.add_argument('--approve-live',action='store_true')
    args=parser.parse_args()
    if not args.approve_live:parser.error('需要 --approve-live；每次只跑選定的一組，至多四個模型回合，可能產生費用。')
    if not (os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')):parser.error('請使用既有私人金鑰環境，不要將值貼入命令。')
    if os.getenv('GOOGLE_GENAI_USE_VERTEXAI','false').lower() not in ('','false','0'):parser.error('沿用 Gemini Developer API 路線。')
    result=asyncio.run(run(args.model,args.out,args.suite,args.origin))
    print(json.dumps({'passed':result['passed'],'output':str(args.out)},ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
