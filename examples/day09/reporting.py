"""由同一份 JSON 產生靜態報告；沒有操作按鈕，也不預填成功或作者心得。"""
from __future__ import annotations
import html
import json
from pathlib import Path
from typing import Any

TITLES = {'request_created':'請求已建立','already_created':'回傳同一筆',
          'idempotency_conflict':'同鍵異內容：請重新確認',
          'unconfirmed_operation':'尚未確認：沒有建單'}

def build_report(report: dict[str, Any], output: Path) -> None:
    esc = lambda x: html.escape(str(x))
    rows = []
    for entry in report.get('results', []):
        result = entry['result']
        rows.append('<tr><td data-label="動作">'+esc(entry['label'])+'</td><td data-label="工具判定">'+esc(TITLES.get(result.get('status'),result.get('status')))+
            '<br><code>'+esc(result.get('status'))+'</code></td><td data-label="請求單號">'+esc(result.get('request_id','—'))+
            '</td><td data-label="資料筆數">'+esc(entry['rows_after'])+'</td></tr>')
    original = report.get('model_turns', [])
    model_html = ''.join('<h3>'+esc(x['label'])+'</h3><p class="reply">'+esc(x.get('final_text',''))+'</p>' for x in original)
    labels = {'OFFLINE_CORE':'離線核心實驗｜實際 SQLite 寫入',
              'OFFLINE_ADK':'真實 ADK＋離線模型替身', 'LIVE_GEMINI':'Gemini API 實驗'}
    mode = report.get('mode','未指定模式')
    baseline = report.get('naive_count')
    note = ('同一份內容送出兩次：未防重複範例留下 '+str(baseline)+' 筆，受控工具留下 '+str(report.get('final_count'))+' 筆。') if baseline is not None else '狀態取自工具結果，單號與筆數取自本次 SQLite 資料庫。'
    metadata = json.dumps({k:report.get(k) for k in ('mode','origin','success','environment','model_calls','usage','semantic_review','error')},ensure_ascii=False,indent=2)
    outcome_note = (
        '已建立資料的狀態為 pending_human_review（等待真人受理）；本次寫入位置是本機 SQLite。'
        if report.get('final_count',0)>0 else
        '本次尚無可核對的已建立資料；請先查看 success 與 error。')
    outcome_label = '檢查通過' if report.get('success') is True else '未通過／未完整執行'
    document = """<!doctype html><html lang="zh-Hant-TW"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>LOCAL Day 9｜送出兩次，同一張回條</title>
<style>body{font:17px/1.7 system-ui,sans-serif;margin:0;background:#f5f7fb;color:#172334}main{max-width:1120px;margin:30px auto;padding:24px}h1{font-size:29px}h2{font-size:22px}small,.muted{color:#526173}.card{background:white;border:1px solid #dbe2eb;border-radius:14px;padding:24px;margin:20px 0}.badge{padding:5px 12px;background:#e5efff;border-radius:18px;display:inline-block}table{border-collapse:collapse;width:100%}th,td{text-align:left;border-bottom:1px solid #dbe2eb;padding:13px;vertical-align:top}code{font-size:14px;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}.reply{white-space:pre-wrap}@media(max-width:700px){main{padding:12px}.card{padding:18px}table{font-size:15px}thead{display:none}table,tbody,tr,td{display:block}tbody tr{border:1px solid #dbe2eb;border-radius:10px;margin:14px 0;padding:10px}td{border:0;padding:8px;overflow-wrap:anywhere}td::before{content:attr(data-label);display:block;color:#526173;font-size:12px;font-weight:600}code{font-size:13px}.scroll{overflow:auto}h1{font-size:24px}}</style>
<main><div class="badge">"""+esc(labels.get(mode,mode))+"""</div><h1>按了送出又按一次，會不會多一筆？</h1>
<p><strong>"""+esc(outcome_label)+"""</strong></p><p>"""+esc(note)+"""</p><div class="card scroll"><h2>送出紀錄與資料庫結果</h2><table><thead><tr><th>動作</th><th>工具判定</th><th>請求單號</th><th>資料筆數</th></tr></thead><tbody>"""+''.join(rows)+"""</tbody></table>
<p class="muted">"""+esc(outcome_note)+"""</p></div>"""+('<div class="card"><h2>模型實際回覆</h2>'+model_html+'</div>' if original else '')+"""<div class="card"><h2>執行來源</h2><pre>"""+esc(metadata)+"""</pre><p>這是靜態結果報告。確認由測試程式明確代送，狀態由實際工具與資料庫核對；模式與執行者分開記錄。</p></div></main></html>"""
    with output.open('x',encoding='utf-8') as f:
        f.write(document)
