"""從實際 report 畫出靜態 HTML；先看逾時時的觀察與之後的查回結果。"""
from __future__ import annotations
from html import escape
from pathlib import Path
from typing import Any


def build_report(report: dict[str, Any], path: Path) -> None:
    e = lambda value: escape(str(value))
    case_rows = []
    for case in report.get('cases', []):
        for index, step in enumerate(case.get('steps', []), 1):
            result = step['result']
            case_rows.append('<tr>' + ''.join('<td>'+e(v)+'</td>' for v in
                (case['name'], index, step['phase'], result.get('status'),
                 result.get('observation', '—'), result.get('request_id', '—'), step['rows_after'])) + '</tr>')
    table = ('<table><thead><tr><th>案例</th><th>步驟</th><th>動作</th><th>回條狀態</th>'
             '<th>查回觀察</th><th>回傳單號</th><th>操作後總筆數</th></tr></thead><tbody>'
             + ''.join(case_rows) + '</tbody></table>')
    model_text = ''.join('<h3>'+e(t.get('phase'))+'</h3><pre>'+e(t.get('final_text', ''))+'</pre>'
                         for case in report.get('cases', []) for t in case.get('model_turns', []))
    status = '列出的檢查通過' if report.get('success') else '未通過／未完整執行'
    body = f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>LOCAL Day 10 實驗紀錄</title>
<style>body{{font-family:system-ui,sans-serif;margin:36px;line-height:1.7;background:#f5f7fb;color:#172438}}main{{max-width:1280px;margin:auto}}table{{width:100%;border-collapse:collapse;background:white;font-size:14px}}th,td{{text-align:left;padding:14px;border-bottom:1px solid #d9e0ea}}pre{{white-space:pre-wrap;background:white;padding:16px}}code{{overflow-wrap:anywhere}}.note{{border-left:4px solid #587295;padding:12px;background:white}}</style>
<main><p>{e(report.get('mode'))}｜{e(report.get('execution', {}).get('origin'))}</p>
<h1>逾時後到底有沒有送出？</h1><p>{status}</p>
<p class="note">本機合成傳輸故障＋真實 SQLite；確認由測試入口代送。這是靜態結果報告，資料筆數是測試端觀察，不是模型可見參數。</p>
{table}<p>未知回條只記「待查證」；單號要等成功寫入或唯讀查回後才呈現。資料列的 pending_human_review 是待真人處理標記，本篇沒有真人通知。</p>
<h2>模型可見文字（如有）</h2>{model_text or '<p>此份核心報告沒有模型呼叫。</p>'}
<p>原始來源：同資料夾 report.json、各案例 events.jsonl、各步 SQLite 快照與 handoff.sqlite3。</p></main></html>'''
    with path.open('x', encoding='utf-8') as f:
        f.write(body)
