"""Google 與 LINE 的最小介接；來源固定，不接受模型指定遠端網址。"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import time

from core import Settings

HERE = Path(__file__).resolve().parent
GEMINI_TIMEOUT_MS = 15_000
LINE_TIMEOUT_SECONDS = 8


def read_env(path: Path, allowed: set[str]) -> dict[str, str]:
    """只讀指定檔案與欄位；不執行 shell，不自行展開變數。"""
    result = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition("=")
        if sep and name.strip() in allowed:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            result[name.strip()] = value
    return result


def load_settings(line_env: Path, gemini_env: Path, model: str) -> Settings:
    local = read_env(line_env, {"LINE_CHANNEL_SECRET", "LINE_CHANNEL_ACCESS_TOKEN", "LINE_TEST_USER_ID"})
    gemini = read_env(gemini_env, {"GEMINI_API_KEY"})
    for name, values in (("LINE_CHANNEL_SECRET", local), ("LINE_CHANNEL_ACCESS_TOKEN", local),
                         ("LINE_TEST_USER_ID", local), ("GEMINI_API_KEY", gemini)):
        value = values.get(name, "")
        if not value or "YOUR_" in value or any(c.isspace() for c in value):
            raise ValueError(f"缺少或無法使用：{name}（不顯示欄位內容）。")
    if not re.fullmatch(r"U[0-9a-fA-F]{32}", local["LINE_TEST_USER_ID"]):
        raise ValueError("LINE_TEST_USER_ID 須為該 Provider 下的使用者 ID，不是 @官方帳號。")
    if not re.fullmatch(r"gemini-[a-z0-9.-]+", model):
        raise ValueError("模型識別格式不符。")
    return Settings(local["LINE_CHANNEL_SECRET"], local["LINE_CHANNEL_ACCESS_TOKEN"],
                    local["LINE_TEST_USER_ID"], gemini["GEMINI_API_KEY"], model)


def load_day03():
    path = HERE.parent / "day03" / "run.py"
    spec = importlib.util.spec_from_file_location("local_day03_reuse", path)
    if not spec or not spec.loader:
        raise RuntimeError("找不到既有 examples/day03/run.py。")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_gemini(settings: Settings):
    # 沿用作者 Day 3 已實測的 SDK 介面，不執行 Day 3 main、不回改舊檔。
    from google import genai
    from google.genai import types
    prior = load_day03()
    prompt = prior.build_prompt(prior.load_case())
    system = prior.SYSTEM + (
        "\n這次文字會出現在 LINE 一對一的合成案例演練。"
        "請用兩到三句親切的繁體中文，不使用 Markdown 標記。"
        "不可暗示已有人接手，不說『請稍候專人確認』；"
        "不可把內部操作識別碼說成使用者已取得的單號。"
        "你只說明合成狀態，沒有執行任何後續動作。"
    )
    def generate():
        client = genai.Client(api_key=settings.gemini_key, vertexai=False,
                             http_options=types.HttpOptions(
                                 api_version="v1beta", base_url="https://generativelanguage.googleapis.com",
                                 timeout=GEMINI_TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1)))
        started = time.perf_counter()
        try:
            raw = client.models.generate_content(
                model=settings.model, contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system, max_output_tokens=2048,
                    thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
            selected = prior.selected_response(raw.model_dump(mode="json", exclude_none=True))
            return {"text": selected["text"], "finish_reason": selected["finish_reason"],
                    "model_version": selected["model_version"], "usage": selected["usage"],
                    "blocked": selected["prompt_block_reason"],
                    "unexpected_non_text": selected["unexpected_non_text_part"],
                    "duration_seconds": round(time.perf_counter() - started, 3)}
        finally:
            try:
                client.close()
            except Exception:
                pass
    return generate, {"system_instruction": system, "prompt": prompt,
                      "requested_model": settings.model, "thinking_level": "LOW",
                      "max_output_tokens": 2048, "http_timeout_ms": GEMINI_TIMEOUT_MS,
                      "sdk_total_attempts": 1, "tools": "not_provided"}


def make_line_reply(settings: Settings, transport=None):
    import httpx
    def reply(reply_token: str, text: str):
        with httpx.Client(timeout=LINE_TIMEOUT_SECONDS, follow_redirects=False,
                          trust_env=False, transport=transport) as client:
            response = client.post(
                "https://api.line.me/v2/bot/message/reply",
                headers={"Authorization": "Bearer " + settings.channel_access_token},
                json={"replyToken": reply_token, "messages": [{"type": "text", "text": text}]})
            # 不保存 token、標頭、回覆本文或訊息識別；200 不是已讀證據。
            return {"http_code": response.status_code}
    return reply
