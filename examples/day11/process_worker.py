"""一個命令一個新行程。接續行程只收可信 actor，原參數由資料庫 Session 取回。"""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
from datetime import datetime,timedelta
from domain import SendArgs,iso
from upstream import Actor
from targets import open_store
from service import HandoffService
from fixtures import seed_authority,sample_operation
from jobs import RecoveryWorker
from evidence import Trace,dump,no_network
from contextlib import nullcontext


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--action',choices=['first','resume'],required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--adk',action='store_true')
    ns=p.parse_args();cfg=json.loads(ns.config.read_text('utf-8'))
    ns.out.mkdir(parents=True,exist_ok=True)
    trace=Trace(ns.out/'events.jsonl');trace.emit('PROCESS_STARTED',action=ns.action)
    actor=Actor(**cfg['actor']);store=open_store(cfg)
    # 可重現的測試時鐘。是邏輯時間前移，不是實際等待或擅改系統時間。
    instant=datetime.fromisoformat(cfg['clock'])+timedelta(seconds=0 if ns.action=='first' else cfg['resume_advance_seconds'])
    clock=lambda:instant
    service=HandoffService(store,clock=clock)
    worker=RecoveryWorker(service,clock=clock,lease_seconds=cfg['lease_seconds'],emit=trace.emit)
    if ns.action=='first':
        seed_authority(store,actor)
        args=service.prepare(actor,sample_operation(),ttl_seconds=cfg['ttl_seconds'],approved=True)
        trace.emit('CONFIRMATION_STORED',source='test_entry_explicit_approval',args=args.values())
        def crash():
            trace.emit('PROCESS_CRASH_INJECTED',exit_code=73)
            os._exit(73)  # 不執行 finally，證明後續進度沒有靠正常退出保存。
        result=worker.step(actor,args,fault=cfg['fault'],crash=crash if cfg['crash'] else None)
        results=[result]
    else:
        if cfg['backend']=='memory-control':
            seed_authority(store,actor)
            trace.emit('SYNTHETIC_AUTHORITY_READY',scope='grant_and_catalog_only_no_confirmation')
        restored=service.restore_session(actor)
        trace.emit('TASK_SESSION_RESTORED',value=restored)
        if restored['status']!='session_restored':
            if cfg['backend']!='memory-control' or restored['status']!='session_not_found':
                raise RuntimeError('不能恢復原任務。')
            results=[restored]
            trace.emit('PROCESS_FINISHED',results=results)
            dump(ns.out/'memory-observation.json',store.inspect())
            dump(ns.out/'result.json',{'pid':os.getpid(),'action':ns.action,'backend':store.mode,
                 'clock_mode':'test_logical_clock','logical_now':iso(instant),'results':results})
            return 0
        args=SendArgs(**restored['args'])
        if ns.adk:
            import asyncio
            from adk_bridge import run_recovery
            os.environ['OTEL_SDK_DISABLED']='true'
            with no_network() if cfg['backend']=='sqlite-test' else nullcontext():
                result=asyncio.run(run_recovery(service,actor,args,worker,emit=trace.emit,lookup_unavailable=cfg['lookup_unavailable']))
            dump(ns.out/'adk-report.json',result)
            results=result['results']
        elif cfg['fault']=='none':
            results=[service.lookup(actor,args)]
            trace.emit('LOOKUP_RESULT',result=results[0])
        else:
            results=worker.run(actor,args,lookup_unavailable=cfg['lookup_unavailable'])
    trace.emit('PROCESS_FINISHED',results=results)
    if cfg['backend']=='memory-control':
        dump(ns.out/'memory-observation.json',store.inspect())
    dump(ns.out/'result.json',{'pid':os.getpid(),'action':ns.action,'backend':store.mode,
                              'clock_mode':'test_logical_clock','logical_now':iso(instant),
                              'results':results})
    close=getattr(store,'close',None)
    if close:close()
    return 0

if __name__=='__main__':raise SystemExit(main())
