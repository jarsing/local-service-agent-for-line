"""不用 Google 套件或金鑰，重用 Day 8 確認核心並真正寫入 SQLite。"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any
from day08_gateway import Actor, Day08Gateway
from handoff import HandoffService
from provenance import create_run, source_snapshot, environment, write_json, sha256
from reporting import build_report

QUESTION = '請問花壇場次的集合地點在哪裡？'
DEMO_ACTOR = Actor('local-demo','demo-user','day09-session')

def tool_args(offer: dict[str,Any]) -> dict[str,str]:
    return {'idempotency_key':offer['idempotency_key'],
            'confirmation_id':offer['confirmation_id'],
            'request_text':offer['operation']['request_text'],
            'event_id':offer['operation']['event_id']}

def run_core_demo(output: Path, origin: str) -> dict[str, Any]:
    sources = source_snapshot()
    gateway = Day08Gateway()
    service = HandoffService(output/'handoff.sqlite3',gateway,lambda actor:actor == DEMO_ACTOR)
    offer = gateway.prepare(DEMO_ACTOR,QUESTION)
    # 明確模擬使用者確認；使用 Day 8 decide()，不是手動寫入確認成功 JSON。
    confirmation_result = gateway.record_user_decision(DEMO_ACTOR,offer['confirmation_id'],approved=True)
    if confirmation_result['status'] != 'confirmation_recorded':
        raise RuntimeError('Day 8 前置確認未成立。')
    args = tool_args(offer)
    entries = []
    for label, changed in [('第一次送出',{}),('同鍵同內容再送一次',{}),
                           ('同鍵改成另一個問題',{'request_text':'請問附近停車位置？'})]:
        result = service.create(actor=DEMO_ACTOR,**{**args,**changed})
        entries.append({'label':label,'result':result,'rows_after':service.count()})
    pending = gateway.prepare(DEMO_ACTOR,'請問雨天備案？')
    result = service.create(actor=DEMO_ACTOR,**tool_args(pending))
    entries.append({'label':'另一份尚未確認的草稿','result':result,'rows_after':service.count()})
    # 對照組：刻意省略查重。同一份教學內容連續 INSERT 兩次。
    naive_path = output/'naive.sqlite3'
    conn = sqlite3.connect(naive_path)
    try:
        conn.execute('CREATE TABLE naive_requests(id INTEGER PRIMARY KEY, request_text TEXT)')
        for _ in range(2):
            conn.execute('INSERT INTO naive_requests(request_text) VALUES (?)',(QUESTION,))
        conn.commit()
        naive_count = conn.execute('SELECT COUNT(*) FROM naive_requests').fetchone()[0]
    finally:
        conn.close()
    expected = ['request_created','already_created','idempotency_conflict','unconfirmed_operation']
    success = ([x['result']['status'] for x in entries] == expected
               and entries[0]['result'].get('request_id') == entries[1]['result'].get('request_id')
               and service.count() == 1 and naive_count == 2 and source_snapshot() == sources)
    return {'mode':'OFFLINE_CORE','origin':origin,'success':success,
            'timestamp':datetime.now(timezone.utc).isoformat(),'environment':environment(),
            'confirmation_origin':'Day 8 原始核心，本次程式明確模擬 approved=True',
            'confirmation_result':confirmation_result,'results':entries,
            'naive_count':naive_count,'final_count':service.count(),'database_rows':service.inspect_rows(),
            'model_calls':0,'external_api_calls':0,'semantic_review':'not_applicable',
            'source_files':sources,'database_sha256':sha256(output/'handoff.sqlite3')}

def main() -> int:
    parser=argparse.ArgumentParser(description='Day 9 離線核心示範')
    parser.add_argument('--out',type=Path,default=Path(__file__).parent/'output')
    parser.add_argument('--origin',choices=['author_local','assistant_check','reader_local'],default='reader_local')
    args=parser.parse_args()
    output=create_run(args.out,'core')
    report=run_core_demo(output,args.origin)
    write_json(output/'report.json',report)
    build_report(report,output/'REPORT.html')
    print('報告：',output/'REPORT.html')
    for row in report['results']:
        print(row['label'],row['result']['status'],row['result'].get('request_id','—'),row['rows_after'])
    return 0 if report['success'] else 1

if __name__=='__main__':
    raise SystemExit(main())
