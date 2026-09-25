"""兩種後端各跑一個 normal。比較儲存機制，不混用兩個案例的單號。"""
from __future__ import annotations
from pathlib import Path
from html import escape
from evidence import new_run, dump, sha, execution


def run_comparison(out, *, backend='sqlite-test', project='demo-local-day11',
                   namespace=None, approve_cloud=False, origin='reader_local'):
    from demo import run_demo
    folder = new_run(out, 'comparison')
    rows = []
    for kind in ('memory-control', backend):
        run, report = run_demo(folder, backend=kind, project=project, namespace=namespace,
            approve_cloud=approve_cloud, origin=origin, selected=['normal'])
        case = report['cases'][0]
        rows.append({'backend':kind, **case, 'run':str(run.relative_to(folder)),
                     'report_sha256':sha(run/'report.json')})
    result = {'execution':execution(origin), 'comparison':'application_process_restart',
              'rows':rows, 'success':all(row.get('success') is True for row in rows),
              'scope':'memory-control is a separate teaching control, not Day 10 SQLite',
              'firestore_emulator_passed':backend == 'emulator' and rows[1].get('success') is True,
              'firestore_cloud_passed':backend == 'cloud' and rows[1].get('success') is True}
    dump(folder/'comparison.json', result)
    body = ''.join('<tr>'+''.join('<td>'+escape(str(row.get(k,'—')))+'</td>'
        for k in ('backend','pids','rows_after_a','rows_after_b','status','request_id'))+'</tr>' for row in rows)
    html = ('<!doctype html><html lang="zh-Hant"><meta charset="utf-8">'
      '<title>LOCAL Day 11 記憶體與持久化對照</title>'
      '<style>body{font-family:system-ui;margin:40px;line-height:1.7}table{border-collapse:collapse}'
      'td,th{padding:14px;border:1px solid #ddd;text-align:left}</style>'
      '<h1>服務重啟，剛才的詢問還找得到嗎？</h1>'
      '<p>'+escape(origin)+'；每組各跑兩個不同 PID。先看 B 能不能查回，再看 B 的資料筆數。</p>'
      '<table><tr><th>後端</th><th>PID A／B</th><th>A 後筆數</th><th>B 後筆數</th>'
      '<th>B 結果</th><th>B 單號</th></tr>'+body+'</table>'
      '<p>記憶體控制組是獨立教學對照，不是 Day 10 的 SQLite。每組的單號各自產生，'
      '只比較同一組重啟前後。SQLite 測試 adapter、Firestore 模擬器及正式雲端分開記錄。</p></html>')
    (folder/'REPORT.html').write_text(html, encoding='utf-8')
    return folder, result
