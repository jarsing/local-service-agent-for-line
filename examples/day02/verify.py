"""Run real offline tests and produce a local HTML report (no network/AI APIs).

Run from repository root:
    python3 examples/day02/verify.py --output ../editorial/evidence/day02
The output argument is a PRIVATE evidence directory; each run gets a new folder.
This script never invokes Git, publishes files, installs packages, or deploys.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]


def run_command(args: list[str]) -> dict:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    try:
        completed = subprocess.run(
            [sys.executable, *args], cwd=ROOT, capture_output=True,
            text=True, encoding="utf-8", errors="replace", env=env, timeout=60,
        )
        return {"command": "python " + " ".join(args), "exit_code": completed.returncode,
                "stdout": completed.stdout, "stderr": completed.stderr}
    except subprocess.TimeoutExpired as exc:
        def text(value):
            return value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")
        return {"command": "python " + " ".join(args), "exit_code": 124,
                "stdout": text(exc.stdout), "stderr": text(exc.stderr) + "\nTimed out after 60 seconds."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        print("BLOCKED: use an existing Python 3.10+ interpreter; do not auto-install.", file=sys.stderr)
        return 2
    if sqlite3.sqlite_version_info < (3, 24, 0):
        print("BLOCKED: SQLite 3.24+ is required for the demonstrated UPSERT syntax.", file=sys.stderr)
        return 2
    spec = ROOT / "docs/day01/handoff-timeout-001.json"
    if not spec.is_file():
        print("BLOCKED: original Day 1 JSON missing at repo root. Read START_HERE; do not invent it.", file=sys.stderr)
        return 2
    # Unique run directory; never overwrite earlier evidence.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = args.output.resolve() / ("run-" + stamp + "-" + uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    tests = run_command(["-m", "unittest", "discover", "-s", "examples/day02", "-p", "test_demo.py", "-v"])
    demo = run_command(["examples/day02/demo.py"])
    match = re.search(r"Ran (\d+) tests?", tests["stderr"] + tests["stdout"])
    count = int(match.group(1)) if match else None
    passed = tests["exit_code"] == 0 and count is not None and count > 0 and demo["exit_code"] == 0
    files = ["examples/day02/demo.py", "examples/day02/test_demo.py", "examples/day02/verify.py",
             "docs/day01/handoff-timeout-001.json"]
    hashes = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}
    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Synthetic fault injection + real local SQLite; no Gemini, LINE or cloud calls.",
        "operator": "Not authenticated by this script. Record author review separately.",
        "python": platform.python_version(), "platform": platform.system(),
        "sqlite": sqlite3.sqlite_version, "test_count": count,
        "overall": "PASS" if passed else "FAIL", "tests": tests, "demo": demo,
        "sha256": hashes, "author_review": "not_recorded", "published": False,
    }
    (folder/"verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (folder/"tests.txt").write_text(tests["stdout"]+tests["stderr"], encoding="utf-8")
    (folder/"demo.txt").write_text(demo["stdout"]+demo["stderr"], encoding="utf-8")
    lines = ["# LOCAL Day 2｜本次實際執行交接", "", f"判定：{result['overall']}",
             f"測試數：{count}", f"Python：{result['python']}；SQLite：{result['sqlite']}；OS：{result['platform']}",
             f"UTC：{result['generated_at_utc']}", "", "範圍：合成故障＋真實本機 SQLite，沒有 Gemini／LINE／雲端呼叫。",
             "此檔由實際執行產生，但不能證明作者身分或代替作者審閱。", "", "## 命令與退出碼",
             f"- `{tests['command']}` → {tests['exit_code']}", f"- `{demo['command']}` → {demo['exit_code']}",
             "", "## Demo 實際輸出", "```text", demo['stdout'].rstrip(), "```", "", "## 作者待核對",
             "本機重現者／審閱時間：待填", "Antigravity 的實際操作或修正：待填（沒有就寫沒有）",
             "GitHub 公開 commit／URL：待填；此程式沒有推送任何內容。", "iThome 發布／Day 計數：未由本程式查核。",
             "", "## 原始紀錄", "同資料夾 tests.txt、demo.txt、verification.json。"]
    (folder/"CHATGPT_HANDOFF.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    e = html.escape
    heading = "實際執行通過" if passed else "實際執行失敗：不可當作通過發布"
    details = e(tests['stdout']+tests['stderr'])
    page = f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>LOCAL Day 2 驗證報告</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1050px;margin:40px auto;padding:0 24px;line-height:1.7}}h1{{font-size:30px}}header{{border-bottom:3px solid;padding-bottom:16px}}pre{{border:1px solid;padding:18px;white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}}td,th{{padding:10px;border-bottom:1px solid;text-align:left}}table{{width:100%;border-collapse:collapse}}.note{{border-left:4px solid;padding:10px 18px}}small{{font-size:13px}}</style>
<header><small>LOCAL · DAY 02 · GENERATED FROM EXECUTED COMMANDS</small><h1>缺少完成證據時，先核對，不猜測。</h1>
<p><b>{heading}</b>｜測試數 {count}｜Python {e(result['python'])}｜SQLite {e(result['sqlite'])}</p></header>
<p class="note">真實本機 SQLite＋刻意注入的合成逾時。沒有 Gemini、LINE 或 Google Cloud 呼叫。<br>這不是終端機截圖，也不是生成的成功畫面；它是本次命令輸出的 HTML 彙整。作者審閱與發布尚未記錄。</p>
<h2>本次實際 Demo 輸出</h2><pre>{e(demo['stdout']+demo['stderr'])}</pre>
<table><tr><th>驗收問題</th><th>判定方式</th></tr><tr><td>送出後逾時，能說完成嗎？</td><td>查看 after_timeout 是否保留 pending_verification 與 claim_completed=false。</td></tr><tr><td>重新開啟資料庫，能查回什麼？</td><td>查看 after_reconciliation 的 request_created 與 awaiting_acceptance。</td></tr><tr><td>同鍵再送一次，是否重複？</td><td>查看 same_request_id 與 stored_request_count，不只看回覆文字。</td></tr></table>
<h2>單元測試實際紀錄</h2><pre>{details}</pre>
<p><small>產生時間（UTC）：{e(result['generated_at_utc'])}。原始退出碼、來源檔案 SHA-256 與環境在 verification.json。範圍以本次案例為限，不是模型或正式服務的全面可靠性保證。</small></p></html>'''
    (folder/"REPORT.html").write_text(page, encoding="utf-8")
    print(json.dumps({"result": result['overall'], "test_count": count,
                      "report": str(folder/'REPORT.html'), "handoff": str(folder/'CHATGPT_HANDOFF.md')},
                     ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
