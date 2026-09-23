"""真正 ADK 工具；可信控制器決定下一步，模型只提出指定操作的呼叫。"""
from __future__ import annotations
from typing import Any
from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
from google.genai import types
from policy import error_result
from records import SendArgs

INSTRUCTION = '''你是 LOCAL 地方服務助理，以自然繁體中文說明結果。
本次是教學流程：使用者訊息提供 expected_tool 與四個 send_args；它們由可信測試入口產生。
每回合只呼叫一次指定工具，四個參數逐字沿用。後端仍獨立查驗身分、權限與內容。
工具回 pending_verification 時，說明結果待查證；本回合先到這裡，下個步驟由應用端安排。
回 request_created 或 already_created 時引用回條中的完整 request_id，說明請求保存在本機。
其他狀態按工具回條說明需要處理的項目。沒有資料來源就維持未知。
目前沒有通知真人、沒有報名或付款流程；不要承諾專人稍後會回覆。
不要自造同意、換鍵、追加工具呼叫或根據模型記憶猜單號。
'''


class ToolGate:
    """每個模型回合至多一次工具呼叫，一個案例至多三次。"""
    def __init__(self):
        self.total = 0
        self.this_turn = 0

    def next_turn(self):
        self.this_turn = 0

    def take(self):
        if self.this_turn >= 1 or self.total >= 3:
            raise RuntimeError('TOOL_CALL_LIMIT')
        self.total += 1
        self.this_turn += 1


def make_tools(case, gate: ToolGate):
    def invoke(name: str, context: ToolContext | None, args: SendArgs) -> dict[str, Any]:
        gate.take()
        # ADK 2.9.1 Context.session 是公開屬性；身分不讀模型可改的 state。
        session = getattr(context, 'session', None)
        call_id = getattr(context, 'function_call_id', None)
        if (session is None or session.user_id != case.actor.user_id
                or session.id != case.actor.session_id):
            result = error_result('not_authorized')
        else:
            result = case.controller.execute(name, case.actor, args)
        case.trace.emit('TOOL_EXECUTED', name=name, id=call_id, args=args.tool_args(), result=result)
        return result

    def create_handoff_request(
        idempotency_key: str, confirmation_id: str, request_text: str, event_id: str,
        tool_context: ToolContext | None = None,
    ) -> dict[str, Any]:
        """送出已確認的地方服務詢問；逾時先回待查證，仍保留原送出鍵。

        Args:
            idempotency_key: 原送出鍵；同一操作所有步驟沿用。
            confirmation_id: 原確認識別碼；後端獨立核對。
            request_text: 已確認的完整詢問文字。
            event_id: 已確認的活動識別碼。
            tool_context: ADK 自動提供的工具環境。
        """
        return invoke('create_handoff_request', tool_context,
                      SendArgs(idempotency_key, confirmation_id, request_text, event_id))

    def reconcile_handoff_request(
        idempotency_key: str, confirmation_id: str, request_text: str, event_id: str,
        tool_context: ToolContext | None = None,
    ) -> dict[str, Any]:
        """用原鍵唯讀核對請求；查無紀錄或查詢受阻時回待查證。

        Args:
            idempotency_key: 與原送出相同的鍵。
            confirmation_id: 與原送出相同的確認識別碼。
            request_text: 原確認文字，完整保留空白與標點。
            event_id: 原活動識別碼。
            tool_context: ADK 自動提供的工具環境。
        """
        return invoke('reconcile_handoff_request', tool_context,
                      SendArgs(idempotency_key, confirmation_id, request_text, event_id))

    return [create_handoff_request, reconcile_handoff_request]


def build_agent(model, tools, before_model, after_model):
    return LlmAgent(name='local_day10_recovery', model=model, instruction=INSTRUCTION,
        tools=tools, before_model_callback=before_model, after_model_callback=after_model,
        generate_content_config=types.GenerateContentConfig(max_output_tokens=1024,
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)))
