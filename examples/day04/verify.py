"""執行 Day 4 離線測試並保存紀錄；不讀取金鑰，不呼叫外部 API。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import io
import json
from pathlib import Path
import platform
import sys
import unittest
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    start = datetime.now(timezone.utc)
    folder = args.output.resolve() / (start.strftime("run-%Y%m%dT%H%M%SZ-offline-") + uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_day04.py")
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    ok = result.wasSuccessful() and result.testsRun > 0 and not result.skipped
    try:
        from app import versions, source_hashes
        packages, hashes = versions(), source_hashes()
    except Exception:
        packages, hashes = {}, {}
        ok = False
    record = {"mode": "OFFLINE_TESTS", "generated_at_utc": start.isoformat(),
              "python": platform.python_version(), "platform": platform.system(),
              "test_count": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "skipped": len(result.skipped),
              "overall": "PASS" if ok else "FAIL", "packages": packages,
              "source_sha256": hashes, "google_live_calls": 0, "line_live_calls": 0,
              "scope": "合成簽章、事件、模型替身、LINE HTTP 替身與 ASGI 路由。",
              "author_review": "not_recorded", "published": False}
    (folder/"verification.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder/"tests.txt").write_text(stream.getvalue(), encoding="utf-8")
    (folder/"REPORT.html").write_text(
        '<!doctype html><html lang="zh-Hant"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>LOCAL Day 4 離線驗收</title>'
        '<style>body{font-family:system-ui,sans-serif;max-width:1000px;margin:30px auto;padding:0 20px;line-height:1.7}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        f'<h1>LOCAL Day 4｜離線驗收 {record["overall"]}</h1>'
        f'<p>實際執行 {result.testsRun} 項；失敗 {len(result.failures)}，錯誤 {len(result.errors)}，略過 {len(result.skipped)}。</p>'
        '<p>這不是 LINE 手機截圖。外部 Google／LINE 呼叫皆為零；測試替身不能證明真實金鑰、HTTPS 或手機顯示可用。</p>'
        f'<pre>{html.escape(json.dumps(record,ensure_ascii=False,indent=2))}</pre>'
        f'<h2>原始測試輸出</h2><pre>{html.escape(stream.getvalue())}</pre></html>', encoding="utf-8")
    (folder/"CHATGPT_HANDOFF.md").write_text(
        f'# LOCAL Day 4 離線驗證交接\n\n模式：OFFLINE_TESTS\n結果：{record["overall"]}\n'
        f'測試數：{result.testsRun}\nPython：{record["python"]}\n'
        '請讀 verification.json 與 tests.txt。不把這些案例寫成真實 LINE／Gemini 呼叫。\n'
        '手機截圖、真人操作、作者審閱與發布狀態需另外提供。\n', encoding="utf-8")
    print(f"離線驗收：{record['overall']}；測試數：{result.testsRun}")
    print(f"報告：{folder/'REPORT.html'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
