"""將實際回合轉為 JSON、HTML 與可貼回文章的比較表。"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import re
import threading
import uuid

HERE = Path(__file__).resolve().parent
PACKAGES = ("google-adk", "google-genai", "httpx", "fastapi", "starlette", "uvicorn", "pydantic")


def versions():
    result = {}
    for name in PACKAGES:
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = None
    return result


def hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.iterdir())
            if p.is_file() and p.suffix in (".py", ".json", ".txt")}


def read_key(path: Path | None) -> str:
    if path is None:
        value = os.environ.get("GEMINI_API_KEY", "")
    else:
        value = ""
        for raw in path.read_text(encoding="utf-8").splitlines():
            name, sep, item = raw.strip().partition("=")
            if sep and name.strip() == "GEMINI_API_KEY":
                value = item.strip()
                if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
    if not value or "YOUR_" in value or any(c.isspace() for c in value):
        raise ValueError("請設定 GEMINI_API_KEY，或使用 --env-file 指向已有的私人設定。")
    return value


def safe_cell(value):
    # HTML 跳脫亦避免模型文字被 Markdown 表格當成標記執行。
    return html.escape(str(value or "（本回合未取得文字，詳見錯誤紀錄）")).replace("|", "&#124;").replace("\n", "<br>").replace("`", "&#96;")


def comparison_markdown(data):
    rows = ["| 問題 | 無工具：本次模型原文 | 有工具：本次模型原文 |", "|---|---|---|"]
    grouped = {}
    for turn in data.get("turns", []):
        grouped.setdefault(turn["case_id"], {})[turn["condition"]] = turn
    for group in grouped.values():
        first = next(iter(group.values()))
        cells = []
        for condition in ("without_tool", "with_tool"):
            turn = group.get(condition)
            if turn:
                answer = turn.get("final_text") or "（本回合未取得文字，詳見錯誤紀錄）"
                if turn.get("status") != "RECORDED":
                    answer = "[" + str(turn.get("status")) + "] " + answer
                cells.append(safe_cell(answer))
            else:
                cells.append("尚未執行")
        rows.append(f'| {safe_cell(first["question"])} | {cells[0]} | {cells[1]} |')
    return "\n".join(rows)


LABELS = {"MODEL_CALL": "請求模型", "MODEL_RESPONSE": "收到模型回應",
          "TOOL_SCHEMA": "ADK 的工具宣告", "TOOL_REQUESTED": "模型提出查詢",
          "TOOL_EXECUTED": "Python 執行查詢", "TOOL_RESPONSE": "ADK 交回工具結果",
          "FINAL_TEXT": "模型整理回答", "TOOL_REJECTED": "搜尋參數需要修正",
          "TURN_ERROR": "本回合錯誤"}


def render_report(data):
    esc = lambda x: html.escape(str(x))
    dump = lambda x: html.escape(json.dumps(x, ensure_ascii=False, indent=2))
    grouped = {}
    for turn in data.get("turns", []):
        grouped.setdefault(turn["case_id"], {})[turn["condition"]] = turn
    table_rows = []
    for group in grouped.values():
        first = next(iter(group.values()))
        cells = []
        for condition in ("without_tool", "with_tool"):
            turn = group.get(condition)
            if turn is None:
                cells.append("尚未執行")
            else:
                answer = turn.get("final_text") or "本回合尚未取得文字"
                label = "" if turn.get("status") == "RECORDED" else "[" + str(turn.get("status")) + "] "
                cells.append(esc(label + answer))
        table_rows.append(f'<tr><td>{esc(first["question"])}</td><td class="answer">{cells[0]}</td><td class="answer">{cells[1]}</td></tr>')
    cards = []
    for turn in data.get("turns", []):
        events = []
        for event in turn.get("events", []):
            if event["kind"] not in ("TOOL_REQUESTED", "TOOL_EXECUTED", "TOOL_RESPONSE", "FINAL_TEXT"):
                continue
            details = {k:v for k,v in event.items() if k != "kind"}
            events.append(f'<li><strong>{esc(LABELS[event["kind"]])}</strong><pre>{dump(details)}</pre></li>')
        title = "有工具" if turn["condition"] == "with_tool" else "無工具"
        cards.append(f'<section><h2>{esc(turn["case_id"])} · {title}</h2><p>{esc(turn["question"])}</p>'
                     f'<p>模型請求 {turn["model_calls"]} 次 · 工具 {turn["tool_calls"]} 次 · {turn["duration_seconds"]} 秒 · {esc(turn["status"])}</p>'
                     f'<pre class="hero">{esc(turn.get("final_text") or "本回合尚未取得文字")}</pre>'
                     f'<ol>{"".join(events)}</ol><details><summary>查看完整回合與用量</summary><pre>{dump(turn)}</pre></details></section>')
    checks = ""
    if "tests" in data:
        checks = f'<section><h2>離線檢查</h2><pre>{dump(data["tests"])}</pre></section>'
    env = {k:data.get(k) for k in ("origin", "generated_at_utc", "python", "platform", "packages", "source_sha256", "sdk_check", "sdk_error", "sdk_result", "error")}
    title = "問活動，讓 LOCAL 先去查" if data['mode'] != 'OFFLINE_CHECKS' else "LOCAL Day 5 離線檢查"
    intro = "同一個模型、四個問題。比較有沒有活動資料入口，並沿著事件查看答案如何產生。" if data['mode'] != 'OFFLINE_CHECKS' else "搜尋邏輯、報告與 LINE 路由測試；ADK 介面檢查另用腳本化模型執行。"
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>LOCAL Day 5｜活動查詢與對照</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1180px;margin:30px auto;padding:0 24px;background:#f6f7f9;color:#203040;line-height:1.7}}
header{{border-bottom:4px solid #356f80;padding-bottom:18px}}h1{{font-size:30px}}h2{{font-size:22px}}
section{{background:white;padding:24px;margin:24px 0;border:1px solid #d5dde4;border-radius:12px}}table{{width:100%;border-collapse:collapse;table-layout:fixed}}
td,th{{border-bottom:1px solid #d5dde4;padding:12px;text-align:left;vertical-align:top;overflow-wrap:anywhere}}td:first-child{{width:24%}}
pre,.answer{{white-space:pre-wrap;overflow-wrap:anywhere}}pre{{font-size:14px}}.hero{{background:#eaf3f4;padding:18px;font-size:17px}}li{{margin:12px 0}}summary{{cursor:pointer}}small{{color:#526779}}</style></head>
<body><header><small>LOCAL · DAY 05 · {esc(data['mode'])} · {esc(data['origin'])}</small><h1>{esc(title)}</h1>
<p>{esc(intro)}</p><p>本份紀錄：{esc(data['status'])}</p></header>
<section id="comparison"><h2>有工具、無工具，這次各自怎麼回答？</h2><p>表中保留各回合原文；這是執行報告，手機顯示另行觀察。</p>
<table><thead><tr><th>問題</th><th>無工具</th><th>有工具</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></section>
{checks}{''.join(cards)}<section><details><summary>環境、版本與其他事件</summary><pre>{dump(env)}</pre><pre>{dump(data.get('events', []))}</pre></details></section>
</body></html>"""


class Report:
    def __init__(self, parent: Path, mode: str, *, origin="operator_not_recorded", secrets=()):
        now = datetime.now(timezone.utc)
        self.folder = parent.resolve() / (now.strftime("run-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6])
        self.folder.mkdir(parents=True, exist_ok=False)
        self.secrets = tuple(x for x in secrets if x)
        self.lock = threading.RLock()
        self.data = {"day":5, "mode":mode, "origin":origin, "generated_at_utc":now.isoformat(),
                     "python":platform.python_version(), "platform":platform.system(), "packages":versions(),
                     "source_sha256":hashes(), "status":"STARTED", "turns":[], "events":[],
                     "author_review":"not_recorded", "phone_review":"not_recorded", "error":None}
        self.save()

    def scrub(self, value):
        # 遞迴處理文字，避免替換 JSON 原文時破壞跳脫字元。
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            return re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED]", value)
        if isinstance(value, list):
            return [self.scrub(x) for x in value]
        if isinstance(value, dict):
            return {k:self.scrub(v) for k,v in value.items()}
        return value

    def __call__(self, kind, **fields):
        with self.lock:
            self.data["events"].append(self.scrub({"kind":kind, **fields}))
            self.save()

    def add_turn(self, turn):
        with self.lock:
            self.data["turns"].append(self.scrub(turn))
            self.save()

    def update(self, **fields):
        with self.lock:
            self.data.update(self.scrub(fields))
            self.save()

    def save(self):
        with self.lock:
            data = self.scrub(self.data)
            temporary = self.folder / "verification.tmp"
            temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
            temporary.replace(self.folder / "verification.json")
            (self.folder / "REPORT.html").write_text(render_report(data),encoding="utf-8")
            (self.folder / "COMPARISON.md").write_text(comparison_markdown(data)+"\n",encoding="utf-8")
