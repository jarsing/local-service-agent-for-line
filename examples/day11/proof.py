"""核對兩個行程、實際文件快照與回條；不信 report.success。"""
from pathlib import Path
import json,sqlite3
from domain import key


def require(test,message):
    if not test:raise AssertionError(message)


def load_events(directory):
    p=Path(directory)/'events.jsonl'
    return [json.loads(x) for x in p.read_text('utf-8').splitlines() if x]


def check_case(directory,name):
    d=Path(directory)
    a=load_events(d/'process-a');b=load_events(d/'process-b')
    ids_a={e['pid'] for e in a};ids_b={e['pid'] for e in b}
    require(len(ids_a)==len(ids_b)==1 and ids_a!=ids_b,'必須為不同 PID 的兩個行程。')
    before=json.loads((d/'after-a.json').read_text('utf-8'))
    after=json.loads((d/'after-b.json').read_text('utf-8'))
    config=json.loads((d/'config.json').read_text('utf-8'))
    if config['backend']=='memory-control':
        require(name=='normal','記憶體對照只驗正常案例。')
        require(len(before.get('requests',{}))==1,'A 應已完成記憶體建單。')
        require(len(after.get('requests',{}))==0 and not after.get('sessions'),
                'B 應沒有 A 的記憶體任務與回條。')
        result=json.loads((d/'process-b/result.json').read_text('utf-8'))['results'][-1]
        require(result['status']=='session_not_found' and 'request_id' not in result,
                '找不到任務不得從 A 匯出的觀察檔拼回單號。')
        require(not any(e['kind']=='CONFIRMATION_STORED' for e in b),'B 不得重發同意。')
        require(not after.get('confirmations'),'B 不應有新確認。')
        for label in ('a','b'):
            require(json.loads((d/f'process-{label}.execution.json').read_text('utf-8'))['returncode']==0,
                    '記憶體對照應正常退出。')
        return {'case':name,'pids':[next(iter(ids_a)),next(iter(ids_b))],
                'rows_after_a':1,'rows_after_b':0,'status':result['status'],
                'request_id':None,'writes':None,'lookups':None,
                'evidence_kind':'in_process_observation_not_persistent_database'}
    if config['backend']=='sqlite-test':
        # 獨立直接 SQL 讀快照，不把 JSON 摘要和另一次 JSON 當相互證明。
        def sql_snapshot(path):
            conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
            try:
                docs={}
                for kind,ident,body in conn.execute('SELECT kind,ident,body FROM docs'):
                    docs.setdefault(kind,{})[ident]=json.loads(body)
                return docs
            finally:conn.close()
        raw_a=sql_snapshot(d/'after-a.sqlite3');raw_b=sql_snapshot(d/'after-b.sqlite3')
        require(raw_a==before and raw_b==after,'SQLite 資料列與匯出文件不一致。')
        before=raw_a;after=raw_b
    first=before.get('requests',{});last=after.get('requests',{})
    expected_before=0 if name in ('before_write','expired_before_write') else 1
    expected_after=0 if name=='expired_before_write' else 1
    require(len(first)==expected_before,'第一行程後真實文件數不符。')
    require(len(last)==expected_after,'接續後真實文件數不符。')
    for label,expected_exit in [('a',73 if config['crash'] else 0),('b',0)]:
        actual_exit=json.loads((d/f'process-{label}.execution.json').read_text('utf-8'))['returncode']
        require(actual_exit==expected_exit,'子行程退出碼不符。')
    require(not any(e['kind']=='CONFIRMATION_STORED' for e in b),'接續行程不得重新取得同意。')
    result=json.loads((d/'process-b/result.json').read_text('utf-8'))['results'][-1]
    status={'normal':'already_created','after_commit':'already_created','before_write':'request_created',
            'expired_before_write':'expired','expired_after_commit':'already_created',
            'lookup_unavailable':'pending_verification'}[name]
    require(result['status']==status,'接續後狀態不符。')
    if first:require(first==last,'已提交的請求不應被接續修改。')
    binding=next(iter(after['bindings'].values()))
    oid=binding['operation_id'];actor=binding['actor'];args=binding['args']
    require(oid==key(actor['tenant_id'],actor['user_id'],args['idempotency_key']),'操作文件 ID 不符。')
    require(after['confirmations']==before['confirmations'],'重啟不得重新同意或修改期限。')
    require(all(c['execution_allowed'] is False for c in after['confirmations'].values()),'確認不能變通行證。')
    if result['status'] in ('already_created','request_created'):
        require(oid in last and result['request_id']==last[oid]['request_id'],'回條與文件對不上。')
        require(last[oid]['args']==args and last[oid]['actor']==actor,'回條內容或身分改變。')
    else:require('request_id' not in result,'未知或拒絕結果不可從測試端偷塞單號。')
    job=after['jobs'][oid]
    require(job['writes']<=2 and job['lookups']<=1,'超出持久化重試預算。')
    if name in ('after_commit','expired_after_commit','lookup_unavailable'):
        require(job['writes']==1,'已提交情境不應再次建單。')
    return {'case':name,'pids':[next(iter(ids_a)),next(iter(ids_b))],
            'rows_after_a':len(first),'rows_after_b':len(last),'status':result['status'],
            'request_id':result.get('request_id'),'writes':job['writes'],'lookups':job['lookups']}
