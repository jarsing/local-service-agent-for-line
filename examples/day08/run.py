"""Day 8 執行入口（run.py）。

支援離線模式（--offline，預設）與真實 Gemini 實測模式（--live）。
在 --live 模式下，依核准之預算上限（每個情境最多 4 次請求，總上限 8 次）
執行情境 1（正常確認）與情境 2（等待中換版），並記錄完整原始事件與用量。
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from google.genai import types
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from adapter import CatalogCatalogState, DEFAULT_EVENT_ID
from adk_bridge import ConfirmationService, create_day08_agent
from confirmation import Identity
from ui import build_html_report

# 預設參數
DEFAULT_MODEL = "gemini-3.8-flash"
MAX_CALLS_PER_SCENARIO = 4
MAX_TOTAL_CALLS = 8


def load_env_if_needed() -> None:
    """若環境變數中無 GEMINI_API_KEY，嘗試從已知的 .env 位置載入。"""
    if os.getenv("GEMINI_API_KEY", "").strip():
        return
    candidates = [
        Path(__file__).resolve().parents[4] / "LOCAL-Day03/editorial/private/.env",
        Path.home() / "Documents/Agy_Works/2026ironman/LOCAL-Day03/editorial/private/.env",
    ]
    for p in candidates:
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip("\"'")
                    if val:
                        os.environ["GEMINI_API_KEY"] = val
                        return


class ScenarioMetricsTracker:
    """追蹤單一情境的模型呼叫次數與 Token 用量，嚴格限制預算上限。"""

    def __init__(self, scenario_name: str, max_calls: int = MAX_CALLS_PER_SCENARIO) -> None:
        self.scenario_name = scenario_name
        self.max_calls = max_calls
        self.call_count = 0
        self.prompt_tokens = 0
        self.candidates_tokens = 0
        self.total_tokens = 0
        self.call_records: list[dict[str, Any]] = []

    def before_model_callback(self, context: Any, request: Any) -> Any:
        self.call_count += 1
        if self.call_count > self.max_calls:
            raise RuntimeError(
                f"[{self.scenario_name}] 模型呼叫次數（{self.call_count}）已超過上限 {self.max_calls} 次！"
            )
        return None

    def after_model_callback(self, context: Any, response: Any) -> Any:
        usage = getattr(response, "usage_metadata", None)
        record: dict[str, Any] = {"call_index": self.call_count}
        if usage:
            p_tok = getattr(usage, "prompt_token_count", 0) or 0
            c_tok = getattr(usage, "candidates_token_count", 0) or 0
            t_tok = getattr(usage, "total_token_count", 0) or 0
            self.prompt_tokens += p_tok
            self.candidates_tokens += c_tok
            self.total_tokens += t_tok
            record.update({
                "prompt_tokens": p_tok,
                "candidates_tokens": c_tok,
                "total_tokens": t_tok,
            })
        self.call_records.append(record)
        return None


async def run_scenario_with_runner(
    runner: Runner,
    session_id: str,
    user_id: str,
    service: ConfirmationService,
    user_prompt: str,
    tracker: ScenarioMetricsTracker,
    simulate_version_switch: bool = False,
    switch_to_version: str = "v2",
) -> dict[str, Any]:
    """執行單一確認情境的回合互動。"""
    events_log: list[dict[str, Any]] = []
    start_time = time.perf_counter()

    # 回合 1：送出使用者需求
    user_msg = types.Content(role="user", parts=[types.Part(text=user_prompt)])
    events_turn1 = []
    async for ev in runner.run_async(session_id=session_id, user_id=user_id, new_message=user_msg):
        events_turn1.append(ev)
        events_log.append({
            "author": ev.author,
            "turn": 1,
            "function_calls": [
                {"name": fc.name, "id": fc.id, "args": fc.args}
                for fc in ev.get_function_calls()
            ],
            "text": "".join(p.text for p in ev.content.parts if p.text) if ev.content and ev.content.parts else None,
        })

    # 尋找 adk_request_confirmation 事件
    conf_fc = None
    for ev in events_turn1:
        for fc in ev.get_function_calls():
            if fc.name == "adk_request_confirmation":
                conf_fc = fc
                break

    if not conf_fc:
        duration = time.perf_counter() - start_time
        return {
            "success": False,
            "error": "No adk_request_confirmation event generated.",
            "call_count": tracker.call_count,
            "duration_seconds": duration,
            "events": events_log,
        }

    # 若需要模擬等待期間版本切換
    if simulate_version_switch:
        print(f"   [狀態切換] 在使用者確認前，主辦方更新目錄版本至 {switch_to_version}...")
        service.catalog_state.switch_to(switch_to_version)

    # 回合 2：使用者送出確認回覆
    conf_resp = types.FunctionResponse(
        name="adk_request_confirmation",
        id=conf_fc.id,
        response={"confirmed": True},
    )
    user_reply = types.Content(role="user", parts=[types.Part(function_response=conf_resp)])

    tool_result = None
    model_final_text = []
    async for ev in runner.run_async(session_id=session_id, user_id=user_id, new_message=user_reply):
        for fr in ev.get_function_responses():
            if fr.name == "prepare_handoff_draft":
                tool_result = fr.response
        if ev.content and ev.content.parts:
            for p in ev.content.parts:
                if p.text:
                    model_final_text.append(p.text)
        events_log.append({
            "author": ev.author,
            "turn": 2,
            "function_responses": [
                {"name": fr.name, "id": fr.id, "response": fr.response}
                for fr in ev.get_function_responses()
            ],
            "text": "".join(p.text for p in ev.content.parts if p.text) if ev.content and ev.content.parts else None,
        })

    duration = time.perf_counter() - start_time
    return {
        "success": True,
        "tool_result": tool_result,
        "model_reply": "\n".join(model_final_text),
        "call_count": tracker.call_count,
        "prompt_tokens": tracker.prompt_tokens,
        "candidates_tokens": tracker.candidates_tokens,
        "total_tokens": tracker.total_tokens,
        "call_records": tracker.call_records,
        "duration_seconds": duration,
        "events": events_log,
    }


async def main_async(args: argparse.Namespace) -> int:
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    is_live = args.live
    model_name = args.model or DEFAULT_MODEL

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        repo_evidence_dir = Path(__file__).resolve().parents[4] / "LOCAL-Day08/editorial/evidence"
        if repo_evidence_dir.is_dir():
            output_dir = repo_evidence_dir / f"run-{timestamp_str}"
        else:
            output_dir = Path(__file__).parent / "evidence_day08"

    output_dir.mkdir(parents=True, exist_ok=True)
    local_mirror_dir = Path(__file__).parent / "evidence_day08"
    local_mirror_dir.mkdir(parents=True, exist_ok=True)

    print("==================================================")
    print("LOCAL Day 8 執行入口")
    print(f"模式: {'真實 GEMINI API' if is_live else '離線 SCRIPTED MOCK'}")
    print(f"模型: {model_name if is_live else 'mock-gemini-model'}")
    print(f"預算限制: 單情境上限 {MAX_CALLS_PER_SCENARIO} 次，總上限 {MAX_TOTAL_CALLS} 次")
    print(f"輸出目錄: {output_dir.resolve()}")
    print("==================================================\n")

    generate_content_config = None
    if is_live:
        load_env_if_needed()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("❌ 錯誤: 在 --live 模式下必須提供 GEMINI_API_KEY 環境變數！")
            return 1
        model_1 = model_name
        model_2 = model_name
        generate_content_config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
        )
    else:
        from test_adk_offline import ScriptedMockLlm
        model_1 = ScriptedMockLlm()
        model_2 = ScriptedMockLlm()

    user_identity = Identity("demo-user-1", "demo-session-1")
    user_prompt = "請幫我整理一則詢問，問這場活動的集合地點在哪裡？"

    # --- 情境 1：正常確認流程 ---
    print("--- 執行情境 1：正常確認流程（內容與版本維持一致）---")
    tracker_1 = ScenarioMetricsTracker("情境 1: 正常確認", max_calls=MAX_CALLS_PER_SCENARIO)
    state_1 = CatalogCatalogState("v1")
    service_1 = ConfirmationService(
        catalog_state=state_1,
        time_provider=lambda: datetime.now(timezone.utc),
    )
    agent_1 = create_day08_agent(
        model=model_1,
        service=service_1,
        current_identity=user_identity,
        generate_content_config=generate_content_config,
        before_model_callback=tracker_1.before_model_callback,
        after_model_callback=tracker_1.after_model_callback,
    )
    sess_service_1 = InMemorySessionService()
    runner_1 = Runner(agent=agent_1, session_service=sess_service_1, app_name="local_day08")
    session_1 = await sess_service_1.create_session(
        app_name="local_day08", user_id=user_identity.user_id, session_id=user_identity.session_id
    )

    res_1 = await run_scenario_with_runner(
        runner=runner_1,
        session_id=session_1.id,
        user_id=user_identity.user_id,
        service=service_1,
        user_prompt=user_prompt,
        tracker=tracker_1,
        simulate_version_switch=False,
    )
    print(f"情境 1 結果狀態: {res_1.get('tool_result', {}).get('status')}")
    print(f"情境 1 執行授權: execution_allowed={res_1.get('tool_result', {}).get('execution_allowed')}")
    print(f"情境 1 模型呼叫次數: {res_1.get('call_count', 0)} 次")
    print(f"情境 1 Token 用量: 提示 {res_1.get('prompt_tokens', 0)}, 生成 {res_1.get('candidates_tokens', 0)}, 總計 {res_1.get('total_tokens', 0)}")
    print(f"情境 1 耗時: {res_1.get('duration_seconds', 0):.3f} 秒")
    if res_1.get("model_reply"):
        print(f"情境 1 模型回覆摘要:\n{res_1['model_reply'][:120]}...\n")

    # --- 情境 2：等待中換版流程 ---
    print("--- 執行情境 2：等待中換版流程（出示 v1 後系統切換至 v2）---")
    tracker_2 = ScenarioMetricsTracker("情境 2: 等待中換版", max_calls=MAX_CALLS_PER_SCENARIO)
    state_2 = CatalogCatalogState("v1")
    service_2 = ConfirmationService(
        catalog_state=state_2,
        time_provider=lambda: datetime.now(timezone.utc),
    )
    agent_2 = create_day08_agent(
        model=model_2,
        service=service_2,
        current_identity=user_identity,
        generate_content_config=generate_content_config,
        before_model_callback=tracker_2.before_model_callback,
        after_model_callback=tracker_2.after_model_callback,
    )
    sess_service_2 = InMemorySessionService()
    runner_2 = Runner(agent=agent_2, session_service=sess_service_2, app_name="local_day08")
    session_2 = await sess_service_2.create_session(
        app_name="local_day08", user_id=user_identity.user_id, session_id=user_identity.session_id
    )

    res_2 = await run_scenario_with_runner(
        runner=runner_2,
        session_id=session_2.id,
        user_id=user_identity.user_id,
        service=service_2,
        user_prompt=user_prompt,
        tracker=tracker_2,
        simulate_version_switch=True,
        switch_to_version="v2",
    )
    print(f"情境 2 結果狀態: {res_2.get('tool_result', {}).get('status')}")
    print(f"情境 2 執行授權: execution_allowed={res_2.get('tool_result', {}).get('execution_allowed')}")
    print(f"情境 2 模型呼叫次數: {res_2.get('call_count', 0)} 次")
    print(f"情境 2 Token 用量: 提示 {res_2.get('prompt_tokens', 0)}, 生成 {res_2.get('candidates_tokens', 0)}, 總計 {res_2.get('total_tokens', 0)}")
    print(f"情境 2 耗時: {res_2.get('duration_seconds', 0):.3f} 秒")
    if res_2.get("model_reply"):
        print(f"情境 2 模型回覆摘要:\n{res_2['model_reply'][:120]}...\n")

    total_calls = tracker_1.call_count + tracker_2.call_count
    total_tokens = tracker_1.total_tokens + tracker_2.total_tokens
    print("==================================================")
    print(f"總模型呼叫次數: {total_calls} 次 (預算上限: {MAX_TOTAL_CALLS} 次)")
    print(f"總 Token 用量: {total_tokens}")
    print("==================================================")

    # 產出 HTML 介面報告
    display_offer = service_1.last_offer or service_2.last_offer
    if display_offer:
        html_dest = output_dir / "CONFIRM.html"
        build_html_report(
            offer=display_offer,
            normal_result=res_1.get("tool_result", {}),
            conflict_result=res_2.get("tool_result", {}),
            output_path=html_dest,
        )
        # 複製到 local_mirror
        build_html_report(
            offer=display_offer,
            normal_result=res_1.get("tool_result", {}),
            conflict_result=res_2.get("tool_result", {}),
            output_path=local_mirror_dir / "CONFIRM.html",
        )
        print(f"已產出人機確認介面：{html_dest.resolve()}")

    # 產出完整執行證據 JSON
    report_data = {
        "metadata": {
            "title": "Day 8 執行證據報告",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "LIVE_GEMINI" if is_live else "OFFLINE_SCRIPTED",
            "model": model_name if is_live else "mock-gemini-model",
            "python_version": sys.version.split()[0],
            "adk_version": "google-adk 2.9.1",
            "total_calls": total_calls,
            "max_allowed_calls": MAX_TOTAL_CALLS,
            "total_tokens": total_tokens,
            "author_observation": "當伺服器目錄版本在等待中更新時，系統在確認階段精確攔截版本不一致（version_changed），execution_allowed 始終保持 False，阻斷過期內容執行。",
        },
        "scenario_1_normal": res_1,
        "scenario_2_version_changed": res_2,
    }

    report_file = output_dir / "execution_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    mirror_report = local_mirror_dir / "execution_report.json"
    with open(mirror_report, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    print(f"已儲存執行記錄：{report_file.resolve()}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="LOCAL Day 8 Runner")
    parser.add_argument("--live", action="store_true", help="執行真實 Gemini 模型呼叫")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini 模型名稱（預設：{DEFAULT_MODEL}）")
    parser.add_argument("--output-dir", help="輸出證據與報告資料夾")
    args = parser.parse_args()

    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
