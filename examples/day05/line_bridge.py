"""重用 Day 4 的 Webhook，將固定測試指令接到活動搜尋 Agent。"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import importlib
import logging
from pathlib import Path
import sys
from catalog import load_cases
from runtime import run_turn, DEFAULT_MODEL
from reporting import Report

HERE = Path(__file__).resolve().parent
DAY04_FILES = {
    "core.py": "aa72352008ec2c94047805027bcc79ad56e60d5f",
    "app.py": "a91646b7958e5617268c895e10e375d50a59c9f2",
    "adapters.py": "918fc5dae98dbfa5b34851afa3bc6f5d15b5aed1",
}
FALLBACK_TEXT = "這次活動查詢暫時遇到問題，請稍後再試。"


def load_day04():
    parent = HERE.parent / "day04"
    for name, expected in DAY04_FILES.items():
        raw = (parent / name).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if actual != expected:
            raise ValueError("DAY04_SOURCE_CHANGED")
    # Day 4 使用同資料夾匯入，先確認沒有其他專案占用相同模組名稱。
    for name in ("core", "app", "adapters"):
        loaded = sys.modules.get(name)
        if loaded is not None and Path(loaded.__file__).resolve().parent != parent.resolve():
            raise ValueError("DAY04_MODULE_NAME_CONFLICT")
    if str(parent) not in sys.path:
        sys.path.insert(0, str(parent))
    return tuple(importlib.import_module(n) for n in ("core", "app", "adapters"))



class BridgeGenerator:
    def __init__(self, report, key, model=DEFAULT_MODEL):
        self.report, self.key, self.model = report, key, model
        self.calls = 0

    def __call__(self):
        if self.calls >= 1:
            raise RuntimeError("本次服務已使用一個 Agent 回合。")
        self.calls += 1
        case = next(x for x in load_cases() if x["id"] == "accessibility")
        turn = asyncio.run(run_turn(case, with_tool=True, key=self.key,
                                   model=self.model, record=self.report))
        self.report.add_turn(turn)
        if turn["status"] != "RECORDED":
            raise RuntimeError("請先查看查詢報告。")
        return {"text":turn["final_text"], "finish_reason":turn["finish_reason"],
                "blocked":None, "unexpected_non_text":False}


def make_reply(send, core):
    def reply(token, text):
        # 固定文案在 Day 5 介接層轉換；模型原文保留。
        if text == core.PING_TEXT:
            text = "LOCAL 已連線，接著輸入「LOCAL 測試」，看看活動查詢。"
        elif text == core.FALLBACK:
            text = FALLBACK_TEXT
        elif text.startswith(core.PREFIX):
            text = "【LOCAL 範例活動】\n" + text[len(core.PREFIX):]
        return send(token, text)
    return reply


def main(argv=None):
    parser = argparse.ArgumentParser(description="LOCAL Day 5｜LINE 展示")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--line-env", type=Path, required=True)
    parser.add_argument("--gemini-env", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("output/day05-line"))
    parser.add_argument("--origin", default="operator_not_recorded")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not args.live:
        parser.error("核准 LINE 測試後加 --live。")
    core, app, adapters = load_day04()
    settings = adapters.load_settings(args.line_env, args.gemini_env, args.model)
    report = Report(args.output, "LIVE_LINE_ADK", origin=args.origin,
        secrets=(settings.channel_secret,settings.channel_access_token,settings.test_user_id,settings.gemini_key))
    generator = BridgeGenerator(report, settings.gemini_key, args.model)
    def record(kind, **fields):
        aliases={"MODEL_STARTED":"ADK_TURN_STARTED","MODEL_TEXT_RECEIVED":"ADK_TEXT_FOR_LINE"}
        report(aliases.get(kind,kind), **fields)
    engine = core.Engine(settings, generator, make_reply(adapters.make_line_reply(settings),core),record)
    logging.getLogger("google").setLevel(logging.CRITICAL)
    print(f"手機先傳 LOCAL ping，再傳一次 LOCAL 測試。報告：{report.folder / 'REPORT.html'}")
    import uvicorn
    uvicorn.run(app.create_app(engine),host="127.0.0.1",port=args.port,workers=1,access_log=False,log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
