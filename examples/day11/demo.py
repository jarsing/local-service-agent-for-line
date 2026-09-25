"""先正常跨行程找回，再演練中斷；預設是明標 SQLite 測試 adapter。"""
from __future__ import annotations
import argparse,json,subprocess,sys,shutil,secrets,os
from dataclasses import asdict
from pathlib import Path
from datetime import datetime,timezone
from html import escape
from fixtures import ACTOR
from targets import open_store
from proof import check_case
from evidence import dump,new_run,execution,source_manifest

HERE=Path(__file__).resolve().parent
CASES=('normal','after_commit','before_write','expired_before_write','expired_after_commit','lookup_unavailable')


def run_demo(out,*,backend='sqlite-test',project='demo-local-day11',namespace=None,approve_cloud=False,
             origin='reader_local',selected=None,adk=False):
    if backend=='memory-control' and selected != ['normal']:
        raise ValueError('記憶體控制組只用 normal；用 --compare-memory 建立對照。')
    folder=new_run(out,'restart');before_sources=source_manifest()
    report={'execution':execution(origin),'backend':backend,'cases':[], 'success':False,
            'source_files':before_sources,'clock_mode':'test_logical_clock; second process +31 seconds',
            'process_termination':'os._exit(73) for crash cases; not host reboot'}
    for name in selected or CASES:
        d=folder/name;d.mkdir()
        fault='before_write' if 'before_write' in name else ('none' if name=='normal' else 'after_commit')
        cfg={'backend':backend,'db':str(d/'documents.sqlite3'),'actor':asdict(ACTOR),
             'project':project,'namespace':(namespace or 'day11-'+secrets.token_hex(8))+'-'+name,
             'approve_cloud':approve_cloud,'fault':fault,'crash':name!='normal',
             'ttl_seconds':10 if name.startswith('expired_') else 300,
             'lease_seconds':30,'resume_advance_seconds':31,
             'clock':datetime.now(timezone.utc).isoformat(),
             'lookup_unavailable':name=='lookup_unavailable','origin':origin}
        dump(d/'config.json',cfg)
        try:
            for action,label in [('first','a'),('resume','b')]:
                command=[sys.executable,str(HERE/'process_worker.py'),'--config',str(d/'config.json'),
                         '--action',action,'--out',str(d/f'process-{label}')]
                if adk and action=='resume':command.append('--adk')
                env=dict(os.environ);env['LOCAL_EXECUTION_ORIGIN']=origin
                result=subprocess.run(command,capture_output=True,text=True,timeout=180,env=env)
                (d/f'process-{label}.stdout.txt').write_text(result.stdout,encoding='utf-8')
                (d/f'process-{label}.stderr.txt').write_text(result.stderr,encoding='utf-8')
                dump(d/f'process-{label}.execution.json',{'returncode':result.returncode,
                    'command':command,'expected':73 if label=='a' and cfg['crash'] else 0})
                expected=73 if label=='a' and cfg['crash'] else 0
                if result.returncode!=expected:raise RuntimeError(f'process-{label} exit={result.returncode}, expected={expected}')
                if backend=='memory-control':
                    # 該行程退出前的測試端匯出，只供對照；B 不會讀這些觀察檔。
                    snap=json.loads((d/f'process-{label}/memory-observation.json').read_text('utf-8'))
                    dump(d/f'after-{label}.json',snap)
                else:
                    store=open_store(cfg)
                    dump(d/f'after-{label}.json',store.inspect())
                    if backend=='sqlite-test':shutil.copy2(d/'documents.sqlite3',d/f'after-{label}.sqlite3')
                    close=getattr(store,'close',None)
                    if close:close()
            report['cases'].append({**check_case(d,name),'success':True})
        except Exception as exc:
            report['cases'].append({'case':name,'success':False,'error_type':type(exc).__name__,
                                    'detail':str(exc) if backend=='sqlite-test' else '請核對本 run 的子行程紀錄。'})
    report['source_unchanged']=before_sources==source_manifest()
    report['success']=all(c['success'] for c in report['cases']) and bool(report['cases']) and report['source_unchanged']
    report['observer_scope']='isolated process snapshots; memory observations are not durable service storage'
    dump(folder/'report.json',report)
    rows=''.join('<tr>'+''.join('<td>'+escape(str(c.get(k,'—')))+'</td>' for k in
        ('case','pids','rows_after_a','rows_after_b','status','request_id'))+'</tr>' for c in report['cases'])
    html="""<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>LOCAL Day 11 跨行程查回</title>
<style>body{font-family:system-ui,sans-serif;margin:48px;line-height:1.65;background:#f6f7fa;color:#19283b}table{border-collapse:collapse;width:100%;background:white}td,th{padding:14px;border-bottom:1px solid #ccc;text-align:left}code{word-break:break-all}small{display:block;margin-top:20px}</style>
<h1>服務重啟，剛才的詢問還找得到嗎？</h1>"""+f'<p>{escape(backend)} | {escape(origin)} | 實際執行：{escape(report["execution"]["recorded_at_utc"])}</p>'+"""
<p>先核對 PID A／B 與回傳單號。memory-control 的結果應是新行程找不到任務；持久化後端的 normal 與 after_commit 應查回原單。</p>
<table><thead><tr><th>案例</th><th>PID A／B</th><th>A 後筆數</th><th>B 後筆數</th><th>B 結果</th><th>回傳單號</th></tr></thead><tbody>"""+rows+"""</tbody></table>
<small>合成教學操作；確認由測試入口明確代送。SQLite 測試 adapter、Firestore 模擬器與正式雲端分開記錄。租約測試使用邏輯時鐘前移；未重開宿主機或資料庫服務，未通知真人。</small></html>"""
    (folder/'REPORT.html').write_text(html,encoding='utf-8')
    return folder,report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--backend',choices=['sqlite-test','emulator','cloud'],default='sqlite-test')
    p.add_argument('--case',choices=CASES)
    p.add_argument('--compare-memory',action='store_true',help='normal 的記憶體控制組與選定持久化後端分開跑，並列比較')
    p.add_argument('--out',type=Path,default=HERE/'output')
    p.add_argument('--origin',choices=['reader_local','author_local','assistant_check'],default='reader_local')
    p.add_argument('--project',default='demo-local-day11')
    p.add_argument('--namespace')
    p.add_argument('--approve-cloud',action='store_true')
    p.add_argument('--adk',action='store_true')
    a=p.parse_args()
    if a.backend=='cloud' and (not a.approve_cloud or not a.namespace):p.error('正式雲端須另核准並明示 namespace。')
    if a.compare_memory:
        if a.case not in (None,'normal') or a.adk:
            p.error('--compare-memory 僅比較正常接續，不和 --adk／其他 --case 混用。')
        from comparison import run_comparison
        path,report=run_comparison(a.out,backend=a.backend,project=a.project,namespace=a.namespace,
            approve_cloud=a.approve_cloud,origin=a.origin)
        print('比較：',path/'REPORT.html');print('檢查：',report['success'])
        return 0 if report['success'] else 1
    path,report=run_demo(a.out,backend=a.backend,project=a.project,namespace=a.namespace,
        approve_cloud=a.approve_cloud,origin=a.origin,selected=[a.case] if a.case else None,adk=a.adk)
    print('報告：',path/'REPORT.html');print('通過：',report['success'])
    return 0 if report['success'] else 1

if __name__=='__main__':raise SystemExit(main())
