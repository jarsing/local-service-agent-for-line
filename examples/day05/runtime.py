"""同一個 ADK Runner 執行有工具與無工具兩組，保存可見事件。"""
from __future__ import annotations

import asyncio
import inspect
import time
from catalog import make_search_tool, load_catalog, normalize_query, TOOL_NAME

DEFAULT_MODEL = "gemini-3.8-flash"
MAX_LLM_CALLS = 3
MAX_OUTPUT_TOKENS = 2048
HTTP_TIMEOUT_MS = 10_000
TURN_TIMEOUT_SECONDS = 28
INSTRUCTION = """你是 LOCAL 地方活動小幫手，使用親切簡短的繁體中文與臺灣用語。
這次使用教學用活動目錄；根據可取得的資料回答。若有搜尋工具，回答活動資訊前先查詢。
依使用者的日期、地區、活動名稱選擇參數，保持搜尋條件的原意。
有資料時先回答時間與地點，結尾列出 source；accessibility 為 null 或列在
unknown_fields 時，說明哪一項還需詢問主辦單位。false 則說明資料中已知的動線限制。
not_found 表示這份目錄查無符合條件的活動。資料不足時，指出缺少什麼及可詢問誰。
一般回覆使用二至四句、約 180 字，純文字即可；提供下一步建議，不代做報名或通知。
"""


def val(value):
    return getattr(value, "value", value) if value is not None else None


def error_info(exc: Exception) -> dict:
    code = getattr(exc, "code", None)
    return {"type": type(exc).__name__, "http_code": code if type(code) is int else None}


def trace_matches(events: list[dict], expected_ids: list[str], expected_query: dict | None = None) -> bool:
    """核對實際查詢、ADK 回傳與預期資料；語意由作者另讀原文。"""
    requests = [x for x in events if x["kind"] == "TOOL_REQUESTED" and x.get("name") == TOOL_NAME]
    results = [x for x in events if x["kind"] == "TOOL_RESPONSE" and x.get("name") == TOOL_NAME]
    executions = [x for x in events if x["kind"] == "TOOL_EXECUTED"]
    for execution in executions:
        result = execution["result"]
        if result.get("status") not in ("ok", "not_found"):
            continue
        ids = sorted(x["id"] for x in result.get("events", []))
        if ids != sorted(expected_ids):
            continue
        if not expected_ids and expected_query is not None:
            try:
                if normalize_query(execution["args"]) != normalize_query(expected_query):
                    continue
            except (ValueError, TypeError):
                continue
        requested = False
        for request in requests:
            try:
                requested |= normalize_query(request["args"]) == normalize_query(execution["args"])
            except (ValueError, TypeError):
                continue
        returned = any(x.get("response") == result for x in results)
        if requested and returned:
            return True
    return False


class Trace:
    def __init__(self, record, max_calls: int):
        self.record = record
        self.max_calls = max_calls
        self.events = []
        self.responses = []
        self.model_calls = 0
        self.final_text = ""
        self.finish_reason = None
        self.runtime_error = False
        self.event_count = 0
        self.tools_schema = None

    def emit(self, kind: str, **fields):
        self.events.append({"kind": kind, **fields})
        self.record(kind, **fields)

    def before_model(self, callback_context, llm_request):
        if self.model_calls >= self.max_calls:
            raise RuntimeError("MODEL_CALL_LIMIT")
        self.model_calls += 1
        # 保存當次 ADK 送給模型的函式宣告，不呼叫私有 schema 產生介面。
        if self.tools_schema is None:
            tools = getattr(getattr(llm_request, "config", None), "tools", None) or []
            self.tools_schema = [t.model_dump(mode="json", exclude_none=True) if hasattr(t, "model_dump") else dict(t) for t in tools]
            self.emit("TOOL_SCHEMA", tools=self.tools_schema)
        self.emit("MODEL_CALL", number=self.model_calls)

    def after_model(self, callback_context, llm_response):
        usage = getattr(llm_response, "usage_metadata", None)
        item = {"model_version": getattr(llm_response, "model_version", None),
                "finish_reason": val(getattr(llm_response, "finish_reason", None)),
                "usage": {name: getattr(usage, name, None) for name in
                          ("prompt_token_count", "candidates_token_count", "thoughts_token_count", "total_token_count")}}
        self.responses.append(item)
        if getattr(llm_response, "error_code", None):
            self.runtime_error = True
        self.emit("MODEL_RESPONSE", **item)

    def before_tool(self, tool, args, tool_context):
        try:
            if tool.name != TOOL_NAME:
                raise ValueError("工具名稱不符")
            normalize_query(args)
        except (ValueError, TypeError):
            result = {"status": "error", "code": "INVALID_ARGUMENTS", "events": [], "unknown_fields": []}
            self.emit("TOOL_REJECTED", reason="name_or_arguments")
            return result
        return None

    def observe(self, event):
        self.event_count += 1
        if self.event_count > 32:
            raise RuntimeError("EVENT_LIMIT")
        if getattr(event, "error_code", None):
            self.runtime_error = True
        calls = event.get_function_calls() or []
        responses = event.get_function_responses() or []
        for call in calls:
            self.emit("TOOL_REQUESTED", name=call.name, args=dict(call.args or {}), id=getattr(call, "id", None))
        for response in responses:
            self.emit("TOOL_RESPONSE", name=response.name, response=dict(response.response or {}), id=getattr(response, "id", None))
        if event.is_final_response() and not getattr(event, "partial", False) and not calls and not responses:
            parts = getattr(getattr(event, "content", None), "parts", None) or []
            text = "".join(p.text for p in parts if isinstance(getattr(p, "text", None), str) and not getattr(p, "thought", False))
            if text:
                self.final_text = text
                self.finish_reason = val(getattr(event, "finish_reason", None))
                self.emit("FINAL_TEXT", text=text, finish_reason=self.finish_reason)


def build_agent(llm, trace: Trace, tool, *, with_tool: bool):
    from google.adk.agents import LlmAgent
    from google.genai import types
    instruction = INSTRUCTION if with_tool else INSTRUCTION + "\n目前環境沒有搜尋工具，請直接以純文字回答，不要嘗試呼叫任何函式。"
    return LlmAgent(
        name="local_event_assistant", model=llm, instruction=instruction,
        tools=[tool] if with_tool else [],
        generate_content_config=types.GenerateContentConfig(
            max_output_tokens=MAX_OUTPUT_TOKENS,
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)),
        before_model_callback=trace.before_model, after_model_callback=trace.after_model,
        before_tool_callback=trace.before_tool,
    )


async def run_turn(case: dict, *, with_tool: bool, record=lambda *a, **k: None,
                   key: str | None = None, model: str = DEFAULT_MODEL, test_model=None) -> dict:
    limit = MAX_LLM_CALLS if with_tool else 1
    trace = Trace(record, limit)
    tool = make_search_tool(load_catalog(), trace.emit)
    started = time.perf_counter()
    runner = client = None
    error = None
    try:
        from google.adk.models.google_llm import Gemini
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.adk.agents.run_config import RunConfig, StreamingMode
        from google import genai
        from google.genai import types
        if test_model is None:
            if not key:
                raise ValueError("GEMINI_API_KEY_REQUIRED")
            client = genai.Client(api_key=key, vertexai=False,
                http_options=types.HttpOptions(api_version="v1beta",
                    base_url="https://generativelanguage.googleapis.com", timeout=HTTP_TIMEOUT_MS,
                    retry_options=types.HttpRetryOptions(attempts=1)))
            llm = Gemini(model=model, client=client, use_interactions_api=False)
        else:
            llm = test_model
        agent = build_agent(llm, trace, tool, with_tool=with_tool)
        sessions = InMemorySessionService()
        session = await sessions.create_session(app_name="local_day05", user_id="demo_reader")
        runner = Runner(app_name="local_day05", agent=agent, session_service=sessions)

        async def consume():
            stream = runner.run_async(user_id="demo_reader", session_id=session.id,
                new_message=types.Content(role="user", parts=[types.Part.from_text(text=case["question"])]),
                run_config=RunConfig(max_llm_calls=limit, streaming_mode=StreamingMode.NONE))
            try:
                async for event in stream:
                    trace.observe(event)
            finally:
                await stream.aclose()
        await asyncio.wait_for(consume(), timeout=TURN_TIMEOUT_SECONDS)
    except Exception as exc:
        error = error_info(exc)
        trace.emit("TURN_ERROR", **error)
    finally:
        if runner is not None:
            try:
                closing = runner.close()
                if inspect.isawaitable(closing):
                    await closing
            except Exception:
                pass
        if client is not None:
            try:
                await client.aio.aclose()
                client.close()
            except Exception:
                pass
    matched = trace_matches(trace.events, case["expected_ids"], case["query"]) if with_tool else None
    if error or trace.runtime_error:
        status = "ERROR"
    elif not trace.final_text or trace.finish_reason != "STOP":
        status = "RESPONSE_INCOMPLETE"
    elif with_tool and not matched:
        status = "TRACE_MISMATCH"
    else:
        status = "RECORDED"
    return {"case_id": case["id"], "question": case["question"],
            "condition": "with_tool" if with_tool else "without_tool",
            "mode": "OFFLINE_SCRIPTED_MODEL" if test_model is not None else "LIVE_GEMINI",
            "status": status, "requested_model": model, "thinking_level": "LOW",
            "session_service": "InMemorySessionService", "instruction": INSTRUCTION,
            "model_calls": trace.model_calls, "tool_calls": sum(e["kind"] == "TOOL_EXECUTED" for e in trace.events),
            "duration_seconds": round(time.perf_counter() - started, 3), "final_text": trace.final_text,
            "finish_reason": trace.finish_reason, "trace_matches_expected": matched,
            "model_responses": trace.responses, "events": trace.events,
            "error": error, "semantic_review": "author_review_pending"}
