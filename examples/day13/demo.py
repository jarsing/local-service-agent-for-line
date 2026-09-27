"""Signed ASGI + real SQLite scenario export. No phone, Google API or simulated UI image."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch
from fastapi.testclient import TestClient
from examples.day12.testing import settings, ReplyRecorder, event, post, RAW_USER
from examples.day12.identity import make_actor
from examples.day12.query import StubQuery
from examples.day12.inherit import SQLiteTestStore, pending
from .bridge import FlexApplication
from .main import create_app


def run(out: Path, origin: str):
    out.mkdir(parents=True, exist_ok=False)
    timeline = []
    scenarios = ('repeat', 'cancel', 'expired', 'superseded', 'text', 'pending')
    for scenario in scenarios:
        folder = out/scenario; folder.mkdir()
        config = settings(folder/'tasks.sqlite3')
        clock = [datetime(2026,9,27,1,tzinfo=timezone.utc)]
        records=[]; sender=ReplyRecorder();store=SQLiteTestStore(config.sqlite_path)
        app=FlexApplication(config,store,StubQuery(),sender,clock=lambda:clock[0],
                            emit=lambda k,**v:records.append({'kind':k,**v}))
        actor=make_actor(config,RAW_USER);app.tasks.seed([actor])
        with TestClient(create_app(app)) as client:
            step=[0]
            def perform(label,text=None,data=None):
                step[0]+=1; ident=f'{scenario}-{step[0]}'
                response=post(client,config,event(ident,text,data))
                if response.status_code != 200:
                    raise AssertionError((scenario,response.status_code,response.text))
                # Independent SQL query and SQLite backup, rather than counting the reply's claims.
                with sqlite3.connect(config.sqlite_path) as source:
                    rows=source.execute("SELECT ident,body FROM docs WHERE kind='requests' ORDER BY ident").fetchall()
                    with sqlite3.connect(folder/f'{step[0]:02d}.sqlite3') as dest:
                        source.backup(dest)
                result=[r for r in records if r['kind']=='BUSINESS_RESULT'][-1]
                raw={'label':label,'event_id':ident,'result':result,'messages':sender.sent[-1],
                     'database_rows':[{'ident':i,'body':json.loads(b)} for i,b in rows]}
                (folder/f'{step[0]:02d}.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf-8')
                timeline.append({'scenario':scenario,'step':step[0],'operation':label,'status':result['status'],
                                 'request_id':result.get('request_id'),'rows':len(rows)})
                return result,len(rows)
            perform('提出詢問','需要協助：需要手語志工支援')
            args=app.tasks.current(actor)['args'];cid=args['confirmation_id']
            if scenario=='repeat':
                first,n=perform('首次確認',data='confirm:'+cid);assert n==1
                again,n=perform('另一事件再次確認',data='confirm:'+cid)
                assert n==1 and first['request_id']==again['request_id']
            elif scenario=='cancel':
                perform('取消',data='cancel:'+cid)
                r,n=perform('再按已取消舊卡',data='confirm:'+cid);assert n==0 and r['status']=='cancelled'
            elif scenario=='expired':
                clock[0]+=timedelta(seconds=301)
                r,n=perform('邏輯時鐘超過原期限',data='confirm:'+cid);assert n==0 and r['status']=='expired'
            elif scenario=='superseded':
                perform('明確提出新需求','新需求：另一份詢問')
                r,n=perform('按較早卡片',data='confirm:'+cid);assert n==0 and r['status']=='superseded'
            elif scenario=='text':
                before=store.inspect()['confirmations']
                r,n=perform('切換原確認文字版',data='text:'+cid)
                assert n==0 and store.inspect()['confirmations']==before
                perform('同一確認送出',data='confirm:'+cid)
                r,n=perform('查回原單文字版',data='text:'+cid);assert n==1
            else:
                with patch.object(app.tasks.original,'lookup',return_value=pending('lookup_unavailable')):
                    r,n=perform('明示注入查詢受阻',data='status:'+cid)
                assert n==0 and r['status']=='pending_verification' and r['request_id'] is None
        (folder/'events.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    report={'origin':origin,'time_utc':datetime.now(timezone.utc).isoformat(),
            'scope':'signed ASGI + SQLite; StubQuery and ReplyRecorder; not LINE device or Firestore',
            'clock':'fixed logical clock; only expiry scenario advances 301 seconds',
            'pending_fault':'lookup return value substituted explicitly, not a real outage',
            'timeline':timeline}
    (out/'observations.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'SHA256.json').write_text(json.dumps({str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
                                              for p in sorted(out.rglob('*')) if p.is_file()},indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--origin',choices=['assistant_check','author_local'],default='author_local')
    a=p.parse_args();print(json.dumps(run(a.out,a.origin),ensure_ascii=False,indent=2))
