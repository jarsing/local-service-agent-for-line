"""LOCAL Day 3：一次文字模型呼叫；不提供業務工具、不寫入服務資料。

離線檢查不需要 SDK 或金鑰。只有 --live 才會嘗試呼叫 Gemini。
報告不認證操作者，也不自動判定回答品質或文章已發布。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import re
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = "gemini-3.8-flash"
MAX_OUTPUT_TOKENS = 2048
HTTP_TIMEOUT_MS = 60_000
API_VERSION = "v1beta"
SYSTEM = (
    "你是 LOCAL 地方服務的文字說明助手。使用繁體中文與臺灣慣用語。"
    "只依提供的合成紀錄回答；分清已知、未知與建議的下一步。"
    "你沒有工具、資料庫或外部系統存取權限。"
    "不能宣稱自己已核對、送出、重新送出、通知或完成任何業務操作。"
    "不要揭露內部推理；只提供給使用者看的簡短說明。"
)


def load_case() -> dict:
    data = json.loads((HERE / "case.json").read_text(encoding="utf-8"))
    if data.get("kind") != "synthetic_model_input":
        raise ValueError("資料必須明確標示為合成輸入。")
    return data


def build_prompt(case: dict) -> str:
    return (
        "以下是合成地方服務案例，不是真實使用者資料：\n"
        + json.dumps(case, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n請直接回覆使用者，說明目前能確認什麼、不能確認什麼，以及下一步應如何核對。"
        + "使用繁體中文與臺灣慣用語，控制在約 180 字內。"
        + "建議下一步不等於你已執行下一步。"
    )


def load_key(env_file: Path | None, environ=None) -> str:
    """優先取 GEMINI_API_KEY；不讀取或記錄其他環境變數值。"""
    env = os.environ if environ is None else environ
    key = env.get("GEMINI_API_KEY", "").strip()
    if not key and env_file:
        # 這裡只支援一行 GEMINI_API_KEY=...，不執行 shell 或變數展開。
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            name, sep, value = line.partition("=")
            if sep and name.strip() == "GEMINI_API_KEY":
                key = value.strip()
                if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
                    key = key[1:-1]
                break
    if not key or "YOUR_" in key or "在這裡" in key or any(c.isspace() for c in key):
        raise ValueError("尚未設定有效格式的 GEMINI_API_KEY；未送出請求。")
    return key


def safe_text(value, key: str = "") -> str:
    text = str(value)
    if key:
        text = text.replace(key, "[REDACTED]")
    return re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED]", text)


def enum_text(value):
    return getattr(value, "value", value) if value is not None else None


def selected_response(raw: dict) -> dict:
    """只保留第一個候選的可見文字與必要資料，不保存 thought/signature。"""
    candidates = raw.get("candidates") or []
    first = candidates[0] if candidates else {}
    parts = (first.get("content") or {}).get("parts") or []
    texts = [p["text"] for p in parts if isinstance(p.get("text"), str) and not p.get("thought")]
    non_text = any(
        any(k not in {"text", "thought", "thought_signature", "thoughtSignature"} and v is not None
            for k, v in p.items())
        for p in parts
    )
    finish = enum_text(first.get("finish_reason"))
    usage = raw.get("usage_metadata") or {}
    names = ("prompt_token_count", "candidates_token_count", "thoughts_token_count",
             "cached_content_token_count", "total_token_count")
    return {
        "text": "".join(texts).strip(),
        "finish_reason": finish,
        "model_version": raw.get("model_version"),
        "response_id": raw.get("response_id"),
        "candidate_count": len(candidates),
        "unexpected_non_text_part": non_text,
        "usage": {name: usage.get(name) for name in names},
        "prompt_block_reason": enum_text((raw.get("prompt_feedback") or {}).get("block_reason")),
    }


def response_status(response: dict) -> str:
    if (response.get("text") and response.get("finish_reason") == "STOP"
            and not response.get("unexpected_non_text_part")
            and not response.get("prompt_block_reason")):
        return "API_TEXT_RECEIVED"
    return "API_RESPONSE_NEEDS_REVIEW"


def hint_for_code(code) -> str:
    return {
        400: "核對模型、參數及 SDK；不要刪除驗證條件來掩蓋錯誤。",
        401: "核對 API 金鑰與所屬專案；不要把金鑰貼進聊天。",
        403: "核對金鑰限制、服務權限、地區與帳號條件。",
        404: "在 AI Studio 核對這個模型能否使用；不要自動換模型重試。",
        429: "核對配額及帳務；停止連續重試。",
        503: "服務暫時不可用；保留失敗紀錄，稍後由作者決定是否再試一次。",
    }.get(code, "保留狀態與錯誤類型；核對環境、網路或官方文件，不要偽造成功結果。")


def source_hashes() -> dict:
    names = ["run.py", "test_run.py", "case.json", "requirements.txt"]
    return {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
            for name in names if (HERE / name).is_file()}


def package_versions() -> dict:
    result = {}
    for name in ("google-genai", "httpx", "pydantic"):
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = None
    return result


def write_report(record: dict, directory: Path) -> None:
    """此頁只呈現紀錄；不把回答文字的存在當成語意驗收。"""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "verification.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    response = record.get("response") or {}
    rows = [
        ("本次狀態", record["status"]),
        ("資料來源", record["origin"]),
        ("Python / 系統", f'{record["python"]} / {record["platform"]}'),
        ("google-genai", record["packages"].get("google-genai")),
        ("要求模型", record["requested_model"]),
        ("服務回傳模型版本", response.get("model_version")),
        ("結束原因", response.get("finish_reason")),
        ("本機觀察耗時（秒）", record.get("duration_seconds")),
        ("輸入 / 回覆 / 思考 / 總 token", " / ".join(
            str((response.get("usage") or {}).get(k)) for k in
            ("prompt_token_count", "candidates_token_count", "thoughts_token_count", "total_token_count"))),
        ("業務資料庫操作", "無；本程式只寫入本機實驗報告"),
        ("回答內容審閱", "待作者核對；不由程式自動評為正確"),
    ]
    def show(v):
        return "未提供／未知" if v is None else str(v)
    table = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(show(v))}</td></tr>" for k, v in rows)
    answer = response.get("text") or "本次沒有可展示的模型文字；不要補造。"
    error = record.get("error")
    page = f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>LOCAL Day 3 實驗報告</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1000px;margin:30px auto;padding:0 22px;line-height:1.65}}h1{{font-size:28px}}table{{border-collapse:collapse;width:100%}}th,td{{padding:8px;border-bottom:1px solid;text-align:left}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;border:1px solid;padding:16px}}.note{{border-left:4px solid;padding:10px 16px}}</style>
<small>LOCAL · DAY 03 · {html.escape(record['origin'])}</small>
<h1>模型有回答，不代表服務已完成。</h1>
<p class="note">Gemini 單回合文字實驗。只送出合成資料；沒有 LINE、ADK 工具或業務資料庫操作。這是執行紀錄的 HTML 彙整，不是完整 Agent 的可靠性證明。</p>
<table>{table}</table><h2>本次模型實際文字</h2><pre>{html.escape(answer)}</pre>
<p>人工核對：是否保留未知？是否未宣稱已核對／已安排？是否只把後續核對當作建議？</p>
{('<h2>阻擋／錯誤</h2><pre>' + html.escape(json.dumps(error, ensure_ascii=False, indent=2)) + '</pre>') if error else ''}
<h2>本次實際輸入</h2><pre>{html.escape(record['prompt'])}</pre>
<p><small>時間（UTC）：{html.escape(record['generated_at_utc'])}。版本、參數、用量、雜湊與未測事項見 verification.json。模型文字未自動判定為正確；操作者與發布狀態由作者另外記錄。</small></p></html>'''
    (directory / "REPORT.html").write_text(page, encoding="utf-8")
    handoff = (
        "# LOCAL Day 3｜本次執行交接\n\n"
        + f"狀態：{record['status']}\n來源：{record['origin']}\n"
        + f"Python：{record['python']}；系統：{record['platform']}\n"
        + f"要求模型：{record['requested_model']}\nSDK：{record['packages'].get('google-genai')}\n\n"
        + "本次沒有執行業務工具、LINE 或雲端部署。回答品質尚待人工核對。\n\n"
        + "## 請讀 verification.json 與 REPORT.html\n"
        + "請依真實輸出更新文章的結果區；不要把 API_TEXT_RECEIVED 寫成服務完成。\n"
        + "作者姓名／審閱時間、文章 URL、公開 commit 與平台日次：未由程式核對。\n"
    )
    (directory / "CHATGPT_HANDOFF.md").write_text(handoff, encoding="utf-8")
    (directory / "response.txt").write_text(response.get("text") or "", encoding="utf-8")
    pins = record.get("packages") or {}
    if pins.get("google-genai"):
        (directory / "sdk-version.txt").write_text(
            f"google-genai=={pins['google-genai']}\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="LOCAL Day 3：受控的單次 Gemini 文字實驗")
    parser.add_argument("--live", action="store_true", help="明確允許本次真實 API 呼叫，可能產生費用")
    parser.add_argument("--env-file", type=Path, help="Repo 外的私人 .env；禁止貼金鑰到參數")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, required=True, help="建議設為 Repo 外 editorial/evidence/day03")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"gemini-[a-z0-9.-]+", args.model):
        parser.error("模型識別格式不符；請使用官方模型頁或 AI Studio 的完整識別。")
    case = load_case()
    stamp = datetime.now(timezone.utc)
    folder = args.output.resolve() / (stamp.strftime("run-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6])
    record = {
        "generated_at_utc": stamp.isoformat(), "origin": "LOCAL_SCRIPT_EXECUTION",
        "operator": "not_authenticated_by_script", "status": "NOT_RUN",
        "scope": "Synthetic input sent to Gemini Developer API only when --live is supplied; no business tools.",
        "python": platform.python_version(), "platform": platform.system(),
        "packages": package_versions(), "requested_model": args.model,
        "api_family": "Gemini Developer API / GenerateContent", "api_version": API_VERSION,
        "system_instruction": SYSTEM, "prompt": build_prompt(case),
        "config": {"max_output_tokens": MAX_OUTPUT_TOKENS, "thinking_level": "LOW",
                   "temperature": "not_set", "tools": "not_provided", "http_timeout_ms": HTTP_TIMEOUT_MS,
                   "sdk_total_attempts": 1, "automatic_function_calling": "disabled"},
        "generation_invocations": 0, "response": None, "error": None,
        "source_sha256": source_hashes(), "content_review": "not_recorded", "published": False,
    }
    record["prompt_sha256"] = hashlib.sha256(record["prompt"].encode()).hexdigest()
    key = ""
    client = None
    started = None
    try:
        if not args.live:
            record["status"] = "BLOCKED_NO_LIVE_CONSENT"
            record["error"] = {"hint": "未提供 --live；沒有讀金鑰，也沒有送出模型請求。"}
        else:
            # 本例固定 Developer API；拒絕沿用另一個後端的全域設定。
            if any(os.environ.get(k, "").lower() in {"true", "1"} for k in
                   ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_ENTERPRISE")):
                raise ValueError("偵測到其他 Google 模型後端設定；請使用獨立環境執行本例。")
            key = load_key(args.env_file)
            from google import genai
            from google.genai import types
            options = types.HttpOptions(
                api_version=API_VERSION,
                base_url="https://generativelanguage.googleapis.com",
                timeout=HTTP_TIMEOUT_MS,
                retry_options=types.HttpRetryOptions(attempts=1),
            )
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )
            client = genai.Client(api_key=key, http_options=options)
            record["generation_invocations"] = 1
            started = time.perf_counter()
            result = client.models.generate_content(model=args.model, contents=record["prompt"], config=config)
            record["duration_seconds"] = round(time.perf_counter() - started, 3)
            selected = selected_response(result.model_dump(mode="json", exclude_none=True))
            # 固定合成輸入仍做防禦性遮蔽，不寫入原始 HTTP header 或錯誤本文。
            record["response"] = json.loads(safe_text(json.dumps(selected, ensure_ascii=False), key))
            record["status"] = response_status(record["response"])
    except Exception as exc:
        if started is not None:
            record["duration_seconds"] = round(time.perf_counter() - started, 3)
        code = getattr(exc, "code", None)
        code = code if isinstance(code, int) else None
        record["status"] = "API_ERROR" if record["generation_invocations"] else "BLOCKED_SETUP"
        # 不記 str(exc)，避免金鑰、路徑或請求內容進入分享資料。
        record["error"] = {"type": type(exc).__name__, "http_code": code, "hint": hint_for_code(code)}
        if isinstance(exc, (ImportError, ModuleNotFoundError)):
            record["error"]["hint"] = "此 Python 環境尚未安裝可用的 google-genai；先安裝 requirements.txt。"
        elif isinstance(exc, (ValueError, FileNotFoundError)) and not record["generation_invocations"]:
            record["error"]["hint"] = "核對私人 .env 路徑、金鑰格式、SDK 設定與是否誤用其他後端；未送出模型請求。"
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                record["client_close_warning"] = True
    record = json.loads(safe_text(json.dumps(record, ensure_ascii=False), key))
    write_report(record, folder)
    print(f"狀態：{record['status']}")
    print(f"報告資料夾：{folder}")
    print("模型文字是否正確，請開 REPORT.html 人工核對；此程式沒有發布文章或 GitHub。")
    return 0 if record["status"] == "API_TEXT_RECEIVED" else 2


if __name__ == "__main__":
    sys.exit(main())
