"""僅操作者 CLI：建立已核准測試者／目錄，或匯出指定任務；不是公開 HTTP 路由。"""
import argparse
import json
from pathlib import Path
from .settings import Settings
from .main import open_store
from .catalog_view import CatalogView
from .tasks import LineTasks
from .identity import make_actor
from .inherit import key,operation_id,SendArgs

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['seed','inspect'])
    p.add_argument('--approve-seed',action='store_true');p.add_argument('--user-index',type=int,default=0)
    p.add_argument('--query-event-id',help='選擇匯出受限的原始 query trace；不要公開實際 LINE 使用者內容')
    p.add_argument('--out',type=Path);a=p.parse_args()
    s=Settings.from_env();store=open_store(s);tasks=LineTasks(store,CatalogView())
    actors=[make_actor(s,u) for u in s.allowed_users]
    if a.action=='seed':
        if not a.approve_seed:raise SystemExit('建立 grant／catalog 需 --approve-seed。')
        tasks.seed(actors);print('已核對並建立尚未存在的測試者及教學目錄；不重設既有撤權。')
    else:
        if a.out is None or a.out.exists():raise SystemExit('請用 --out 指定新的私人證據檔。')
        actor=actors[a.user_index];active=tasks.current(actor);result=tasks.status(actor)
        data={'mode':store.mode,'task':active,'result':result,'project':s.project,'namespace':s.namespace}
        if active.get('args'):
            oid=operation_id(actor,SendArgs(**active['args']))
            def read(tx):return tx.get('requests',oid)
            data['direct_request_document']=store.atomic(read,read_only=True)
            data['request_path']=f'local_day11_demo/{s.namespace}/requests/{oid}'
        if a.query_event_id:
            tid=key(actor.tenant_id,a.query_event_id)
            data['query_trace']=store.atomic(lambda tx:tx.get('line_traces',tid),read_only=True)
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        print('已匯出。單一文件的讀回不是整個集合的原子快照，筆數另由授權操作者核對。')
    close=getattr(store,'close',None)
    if close:close()
