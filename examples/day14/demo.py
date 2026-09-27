"""真實跨行程 SQLite 演練；確認由合成測試入口代送，不是假稱手機/Gemini。"""
from datetime import datetime, timezone
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from examples.day12.inherit import Actor, SQLiteTestStore, grant_key
from .memory import PreferenceMemory
from .engine import TurnTools

SECRET='SYNTHETIC-DEMO-ONLY-'+('d'*32)
NOW=datetime.fromisoformat('2026-09-28T10:00:00+08:00')

def child(db,phase):
    store=SQLiteTestStore(db);actor=Actor('synthetic-demo','synthetic-account','session-'+phase)
    memory=PreferenceMemory(store,SECRET,clock=lambda:NOW)
    base={'phase':phase,'pid':os.getpid(),'session_id':actor.session_id,'clock_scope':'synthetic_2026-09-28',
          'backend':'sqlite-test','model':'not_used','confirmation_source':'synthetic_trusted_test_entry'}
    if phase=='A':
        store.atomic(lambda tx:tx.put('grants',grant_key(actor),{'allowed':True,'actor':{'tenant_id':actor.tenant_id,'user_id':actor.user_id}}))
        p=memory.propose(actor,'vegetarian','initial');before=memory.inspect(actor)
        result=memory.approve(actor,p['token']);base.update(before_consent=before,result=result)
    elif phase=='C':
        p=memory.propose(actor,'ovo_lacto','update');base['result']=memory.approve(actor,p['token'])
    elif phase=='E': base['result']=memory.forget(actor,'forget')
    else:
        tools=TurnTools(memory,actor);base['result']=tools.execute('search_local_places',{'area':'花壇鄉'})
        base['tool_events']=tools.calls
    base['memory']=memory.inspect(actor)
    return base

def run(out,origin):
    out.mkdir(parents=True,exist_ok=False);db=out/'runtime.sqlite3';records=[]
    for phase in 'ABCDEF':
        proc=subprocess.run([sys.executable,'-m','examples.day14.demo','--child',phase,'--db',str(db.resolve())],capture_output=True,text=True)
        (out/(phase+'.stdout.txt')).write_text(proc.stdout);(out/(phase+'.stderr.txt')).write_text(proc.stderr)
        if proc.returncode: raise RuntimeError('child failed '+phase)
        value=json.loads(proc.stdout);records.append(value)
        # Independent observer queries the database; no previous child's JSON is fed to the next child.
        with sqlite3.connect(db) as conn:
            rows=[{'kind':k,'id':i,'body':json.loads(b)} for k,i,b in conn.execute('SELECT kind,ident,body FROM docs ORDER BY kind,ident')]
            with sqlite3.connect(out/(phase+'.sqlite3')) as dest: conn.backup(dest)
        (out/(phase+'.rows.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    assert len({r['pid'] for r in records})==6
    assert records[0]['before_consent']['dietary_type'] is None
    assert records[1]['result']['query']['dietary_type']=='vegetarian'
    assert records[3]['result']['query']['dietary_type']=='ovo_lacto'
    assert records[5]['result']['query']['dietary_type']=='any'
    assert records[5]['memory']['dietary_type'] is None
    result={'origin':origin,'executed_at':datetime.now(timezone.utc).isoformat(),'scope':'six subprocesses + actual SQLite; no Gemini/LINE/Firestore',
            'passed':True,'records':records}
    (out/'OBSERVATIONS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    table=''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in
        [r['phase'],r['pid'],r['session_id'],r['memory']['revision'],r['memory']['dietary_type'],r.get('result',{}).get('query',{}).get('dietary_type','—')])+'</tr>' for r in records)
    (out/'REPORT.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>Day 14 跨 Session</title>'
       '<h1>同意、更正、忘記：換行程後查什麼？</h1><p>'+html.escape(origin)+' | 真實 SQLite，合成確認入口；不是 Gemini 或手機結果。</p>'
       '<table border="1" cellpadding="8"><tr><th>行程</th><th>PID</th><th>Session</th><th>版本</th><th>目前偏好</th><th>實際工具條件</th></tr>'+table+'</table></html>')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path);p.add_argument('--origin',choices=['assistant_check','author_local','ci'],default='author_local')
    p.add_argument('--child',choices=list('ABCDEF'));p.add_argument('--db',type=Path);a=p.parse_args()
    if a.child:
        if not a.db:p.error('--db required')
        print(json.dumps(child(a.db,a.child),ensure_ascii=False))
    else:
        if not a.out:p.error('--out required')
        print(json.dumps({'out':str(a.out),'passed':run(a.out,a.origin)['passed']}))
