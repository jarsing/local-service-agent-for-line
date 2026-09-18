"""LOCAL Day 4 開發入口。只監聽 127.0.0.1；不提供靜態檔案或報告網頁。"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import html
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import threading
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core import Engine, MAX_BODY_BYTES, Settings
from adapters import load_settings, make_gemini, make_line_reply

HERE = Path(__file__).resolve().parent


def source_hashes():
    paths = [p for p in HERE.iterdir() if p.suffix in (".py", ".txt")]
    paths += [HERE.parent / "day03" / n for n in ("run.py", "case.json")]
    return {str(p.relative_to(HERE.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths if p.is_file()}


def versions():
    values = {}
    for name in ("google-genai", "fastapi", "uvicorn", "httpx", "starlette", "pydantic"):
        try:
            values[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            values[name] = None
    return values


class Recorder:
    def __init__(self, folder: Path, settings: Settings, config: dict, *, mode="LIVE_SESSION"):
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=False)
        self.lock = threading.RLock()
        self.secrets = (settings.channel_secret, settings.channel_access_token,
                        settings.test_user_id, settings.gemini_key)
        self.data = {"mode": mode, "started_at_utc": datetime.now(timezone.utc).isoformat(),
                     "python": platform.python_version(), "platform": platform.system(),
                     "packages": versions(), "source_sha256": source_hashes(),
                     "config": config, "events": [], "event_count": 0,
                     "scope": "僅測試帳號及固定合成案例；記憶體佇列，沒有業務寫入。",
                     "operator": "not_authenticated_by_report",
                     "phone_review": "not_recorded", "published": False}
        self.write()

    def scrub(self, value):
        text = json.dumps(value, ensure_ascii=False)
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED]", text)
        return json.loads(text)

    def __call__(self, status: str, **fields):
        with self.lock:
            self.data["event_count"] += 1
            event = self.scrub({"status": status, "at_utc": datetime.now(timezone.utc).isoformat(), **fields})
            self.data["events"].append(event)
            self.data["events"] = self.data["events"][-100:]
            self.write()

    def write(self):
        with self.lock:
            data = self.scrub(self.data)
            data["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
            text = json.dumps(data, ensure_ascii=False, indent=2)
            tmp = self.folder / "verification.tmp"
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self.folder / "verification.json")
            def esc(value):
                return html.escape(json.dumps(value, ensure_ascii=False, indent=2))
            rows = "".join(
                f'<tr><td>{html.escape(e["status"])}</td><td>{html.escape(e.get("trace", "—"))}</td>'
                f'<td><pre>{esc({k: v for k, v in e.items() if k not in ("status", "trace", "at_utc")})}</pre></td></tr>'
                for e in data["events"])
            page = f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>LOCAL Day 4 執行紀錄</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1080px;margin:30px auto;padding:0 20px;line-height:1.7}}table{{border-collapse:collapse;width:100%}}td,th{{padding:9px;border-bottom:1px solid;text-align:left;vertical-align:top}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}small{{font-size:13px}}</style>
<small>LOCAL · DAY 04 · {html.escape(data['mode'])}</small>
<h1>LINE 收到了，不等於地方服務完成了。</h1>
<p>本頁為執行紀錄彙整，不是 LINE 手機截圖。LINE_REPLY_ACCEPTED 只表示回覆 API 回應 200；是否顯示在手機及內容是否適當，要另外由作者核對。</p>
<p>原始個人訊息、user ID、reply token 與金鑰不寫入本報告；送給 Gemini 的是固定合成案例。</p>
<table><tr><th>Python／系統</th><td>{data['python']}／{data['platform']}</td></tr>
<tr><th>模型設定</th><td><pre>{esc(data['config'])}</pre></td></tr>
<tr><th>實際套件</th><td><pre>{esc(data['packages'])}</pre></td></tr></table>
<h2>最近 100 筆事件（累計 {data['event_count']} 筆）</h2>
<table><tr><th>狀態</th><th>本機追蹤碼</th><th>紀錄</th></tr>{rows}</table>
<p>更新時間（UTC）：{html.escape(data['updated_at_utc'])}。單一行程、記憶體佇列與去重；重新啟動會清空，不能作為正式營運可靠性保證。</p></html>'''
            (self.folder / "REPORT.html").write_text(page, encoding="utf-8")
            (self.folder / "CHATGPT_HANDOFF.md").write_text(
                "# LOCAL Day 4 本機交接\n\n"
                f"模式：{data['mode']}\nPython：{data['python']}\n"
                "請讀同資料夾 verification.json 與 REPORT.html。\n"
                "本文只記錄這次行程；不要把測試替身當成 Google／LINE 的真實回應。\n"
                "手機畫面、作者判讀與發布狀態另行提供，不由程式代為核准。\n"
                "不公開 .env、權杖、使用者 ID 或原始收件資料。\n", encoding="utf-8")


def create_app(engine: Engine) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        engine.start()
        yield
        await asyncio.to_thread(engine.close)
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @application.get("/healthz")
    async def health():
        return {"status": "running", "scope": "local-test-only"}

    @application.post("/webhook")
    async def webhook(request: Request):
        signatures = request.headers.getlist("x-line-signature")
        if len(signatures) != 1:
            engine.record("SIGNATURE_REJECTED")
            return JSONResponse({}, status_code=401)
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) < 0 or int(length) > MAX_BODY_BYTES:
                    return JSONResponse({}, status_code=413)
            except ValueError:
                return JSONResponse({}, status_code=400)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                engine.record("BODY_TOO_LARGE")
                return JSONResponse({}, status_code=413)
            body.extend(chunk)
        status = await asyncio.to_thread(engine.receive, bytes(body), signatures[0])
        return JSONResponse({}, status_code=status)
    return application


def main():
    parser = argparse.ArgumentParser(description="LOCAL Day 4：限定測試帳號的 LINE × Gemini 入口")
    parser.add_argument("--live", action="store_true", help="同意啟動真實 API 模式；仍須手機發出固定指令")
    parser.add_argument("--line-env", type=Path, required=True)
    parser.add_argument("--gemini-env", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gemini-3.8-flash")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not args.live:
        parser.error("未提供 --live；不讀取金鑰，也不啟動服務。離線測試請執行 verify.py。")
    try:
        settings = load_settings(args.line_env, args.gemini_env, args.model)
        generate, config = make_gemini(settings)
        send = make_line_reply(settings)
        folder = args.output.resolve() / (datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6])
        recorder = Recorder(folder, settings, config)
    except Exception as exc:
        # 不顯示例外本文，以免第三方套件把設定值寫進錯誤訊息。
        print(f"啟動受阻：{type(exc).__name__}。請核對檔案、必要欄位與套件；不要列印金鑰。")
        return 2
    print(f"本機報告：{folder / 'REPORT.html'}")
    print("僅接受允許帳號的一對一 LOCAL ping／LOCAL 測試。每次啟動最多 3 次模型、8 次回覆。")
    print("程式不建立 HTTPS 通道、不修改 LINE 設定、不推送 GitHub、不部署。")
    import uvicorn
    engine = Engine(settings, generate, send, recorder)
    uvicorn.run(create_app(engine), host="127.0.0.1", port=args.port,
                access_log=False, log_level="warning", workers=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
