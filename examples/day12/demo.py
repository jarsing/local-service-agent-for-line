"""兩個獨立應用行程的離線 Webhook 演練；不冒充手機／Cloud Run。"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from fastapi.testclient import TestClient
from .inherit import REPO,SQLiteTestStore
from .identity import make_actor
from .main import Application,create_app
from .query import StubQuery
from .testing import settings,ReplyRecorder,event,post,RAW_USER


def child(folder,step,crash=False):
    config=settings(folder/'store.sqlite3');store=SQLiteTestStore(config.sqlite_path)
    def emit(kind,**values):
        with (folder/(step+'.events.jsonl')).open('a',encoding='utf-8') as f:
            f.write(json.dumps({'kind':kind,**values},ensure_ascii=False)+'\n');f.flush()
    class Sender(ReplyRecorder):
        async def send(self, token, messages):
            if crash and any('已保存這份詢問' in m['text'] for m in messages):
                emit('SYNTHETIC_PROCESS_EXIT',code=73,point='after_business_commit_before_line_reply')
                os._exit(73)
            result=await super().send(token,messages)
            with (folder/(step+'.replies.jsonl')).open('a',encoding='utf-8') as f:
                f.write(json.dumps({'mode':'REPLY_RECORDER','messages':messages},ensure_ascii=False)+'\n')
            return result
    engine=Application(config,store,StubQuery(),Sender(),emit=emit)
    actor=make_actor(config,RAW_USER)
    if step=='a': engine.tasks.seed([actor])
    with TestClient(create_app(engine)) as client:
        if step=='a':
            assert post(client,config,event('query','花壇場次在哪裡集合？')).status_code==200
            assert post(client,config,event('offer','需要協助：請協助確認集合點。')).status_code==200
            # 合成測試者從實際回覆卡讀確認 ID；不是建單工具自行同意。
            item=engine.sender.sent[-1][0]['quickReply']['items'][0]['action']['data']
            assert post(client,config,event('confirm',data=item)).status_code==200
        else:
            # B 唯一輸入是新的查詢事件與共用資料庫位置；沒有 A 的 args/request_id。
            assert post(client,config,event('status-after-restart','剛才那單有成功嗎？')).status_code==200
    result=engine.tasks.status(actor)
    (folder/(step+'.result.json')).write_text(json.dumps({
        'pid':os.getpid(),'boot_id':engine.boot_id,'mode':'ASGI_SQLITE_STUB',
        'result':result},ensure_ascii=False,indent=2),encoding='utf-8')


def sql_rows(path):
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
        return [json.loads(r[0]) for r in conn.execute("SELECT body FROM docs WHERE kind='requests'")]


def run(out):
    out.mkdir(parents=True,exist_ok=False);cases=[]
    for name,crash in [('normal',False),('reply_lost',True)]:
        folder=out/name;folder.mkdir()
        before=[];processes=[]
        for step in ('a','b'):
            cmd=[sys.executable,'-m','examples.day12.demo','--child',step,'--out',str(folder)]
            if crash and step=='a':cmd.append('--crash')
            p=subprocess.run(cmd,cwd=REPO,text=True,capture_output=True,timeout=40)
            (folder/(step+'.stdout.txt')).write_text(p.stdout,encoding='utf-8')
            (folder/(step+'.stderr.txt')).write_text(p.stderr,encoding='utf-8')
            expected=73 if step=='a' and crash else 0
            if p.returncode!=expected:raise RuntimeError(f'{name}/{step}: {p.returncode}: {p.stderr}')
            snapshot=folder/(step+'.sqlite3');shutil.copy2(folder/'store.sqlite3',snapshot)
            rows=sql_rows(snapshot.resolve());before.append(rows)
            events=[json.loads(x) for x in (folder/(step+'.events.jsonl')).read_text().splitlines()]
            boot=next(x for x in events if x['kind']=='PROCESS_STARTED')
            processes.append({'pid':boot['pid'],'boot_id':boot['boot_id'],'exit_code':p.returncode})
        b=json.loads((folder/'b.result.json').read_text())['result']
        assert len(before[0])==len(before[1])==1
        assert before[0][0]['request_id']==before[1][0]['request_id']==b['request_id']
        assert before[0][0]['operation_id']==before[1][0]['operation_id']
        assert processes[0]['pid']!=processes[1]['pid']
        assert processes[0]['boot_id']!=processes[1]['boot_id']
        cases.append({'case':name,'processes':processes,'counts':[len(x) for x in before],
            'request_id':b['request_id'],'operation_id':b['request']['operation_id'],'b_status':b['status']})
    report={'mode':'ASGI_SQLITE_STUB','status':'executed','success':True,
        'evidence_basis':'Actual subprocesses, signed synthetic webhook bytes, SQLite rows and reply-recorder events',
        'not_executed':['Gemini','Google ADK','LINE API','Firestore SDK','Docker','Cloud Run'], 'cases':cases}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--child',choices=['a','b']);p.add_argument('--crash',action='store_true');args=p.parse_args()
    if args.child:child(args.out,args.child,args.crash)
    else:print(json.dumps(run(args.out),ensure_ascii=False,indent=2))
