"""離線驗證：預設跑核心；--sdk 加真實 ADK 介接，缺套件明確失敗，不當略過通過。"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import socket
import unittest
from provenance import create_run, source_snapshot, environment, write_json

@contextmanager
def no_network():
    def blocked(*args,**kwargs):
        raise RuntimeError('OFFLINE_NETWORK_BLOCKED')
    original=(socket.socket.connect,socket.socket.connect_ex,socket.create_connection,socket.getaddrinfo)
    socket.socket.connect=blocked
    socket.socket.connect_ex=blocked
    socket.create_connection=blocked
    socket.getaddrinfo=blocked
    try:yield
    finally:
        socket.socket.connect,socket.socket.connect_ex,socket.create_connection,socket.getaddrinfo=original

def run_group(case):
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(case)
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    return {'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'skipped':len(result.skipped),'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
            'success':result.wasSuccessful() and result.testsRun>0 and not result.skipped},stream.getvalue()

def main():
    p=argparse.ArgumentParser(description='Day 9 離線驗證')
    p.add_argument('--sdk',action='store_true',help='連同真實 ADK 的離線整合測試')
    p.add_argument('--out',type=Path,default=Path(__file__).parent/'output')
    p.add_argument('--origin',choices=['author_local','assistant_check','reader_local'],default='reader_local')
    args=p.parse_args()
    output=create_run(args.out,'verify')
    os.environ['OTEL_SDK_DISABLED']='true'
    sources=source_snapshot();logs=[]
    report={'mode':'OFFLINE_VERIFICATION','origin':args.origin,'timestamp':datetime.now(timezone.utc).isoformat(),
            'environment':environment(),'source_files':sources,'network':'socket connect and DNS blocked',
            'sdk':{'status':'not_requested'},'success':False}
    with no_network():
        from test_handoff import HandoffTests
        report['core'],log=run_group(HandoffTests);logs.append(log)
        from test_reporting import ReportingTests
        report['reporting'],log=run_group(ReportingTests);logs.append(log)
        if args.sdk:
            try:
                from test_adk_offline import AdkTests
                report['sdk'],log=run_group(AdkTests);logs.append(log)
            except (ModuleNotFoundError,ImportError) as exc:
                report['sdk']={'status':'dependency_unavailable','error_type':type(exc).__name__}
                logs.append('ADK 相依套件不可用；SDK 測試未執行，不能算通過。\n')
    report['source_unchanged']=sources==source_snapshot()
    report['success']=(report['core']['success'] and report['reporting']['success'] and report['source_unchanged']
                       and (not args.sdk or report['sdk'].get('success') is True))
    groups=[report['core'],report['reporting']]
    if 'run' in report['sdk']: groups.append(report['sdk'])
    report['totals']={name:sum(g[name] for g in groups)
                      for name in ('run','passed','failures','errors','skipped')}
    write_json(output/'verification.json',report)
    with (output/'tests.txt').open('x',encoding='utf-8') as f:f.write('\n'.join(logs))
    print('\n'.join(logs));print('驗證報告：',output/'verification.json')
    return 0 if report['success'] else 1

if __name__=='__main__':
    raise SystemExit(main())
