"""將 Day 9 建單服務接成 ADK 工具；身分與 tenant 由可信入口提供。"""
from __future__ import annotations
from typing import Any, Callable
from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
from google.genai import types
from day08_gateway import Actor
from handoff import HandoffService

TOOL_NAME = 'create_handoff_request'
INSTRUCTION = '''你是 LOCAL 地方服務助理，使用自然的繁體中文與臺灣用語。
目前只有 create_handoff_request 工具。本次任務是把已確認的詢問建立為服務請求。
使用者訊息會附上由測試入口提供的送出參數；請照原值呼叫工具，保持同一組
idempotency_key、confirmation_id、request_text、event_id。這些值仍由後端核對。
每一回合都要實際呼叫一次工具；再次詢問送出結果時仍用原鍵。
工具回 request_created 時，簡短告知請求編號及等待真人受理。
工具回 already_created 時，回覆原單號並說明這次沒有新增第二筆。
其他狀態請依工具結果說明需要重新確認或處理的項目。
單號與狀態以工具結果為準；不可宣稱主辦已讀、真人已受理或報名成功。
'''

class ToolBudget:
    def __init__(self):
        self.total = 0
        self.this_turn = 0
    def next_turn(self):
        self.this_turn = 0
    def take(self):
        if self.total >= 2 or self.this_turn >= 1:
            raise RuntimeError('TOOL_CALL_LIMIT')
        self.total += 1
        self.this_turn += 1


def actor_resolver(expected: Actor) -> Callable[[ToolContext], Actor]:
    """本機 Runner 已確定身分；對照 ADK Session，tenant 來自服務設定。

    session 讀取集中在此處；沿用 Day 8 的 _invocation_context 相容接點，
    需以本機已安裝 ADK 的離線整合測試核對。不是讀取模型可寫的 state。
    """
    def resolve(context: ToolContext) -> Actor:
        inv = getattr(context, '_invocation_context', None)
        session = getattr(inv, 'session', None)
        if (session is None or getattr(session, 'user_id', None) != expected.user_id
                or getattr(session, 'id', None) != expected.session_id):
            raise PermissionError('ADK_SESSION_IDENTITY_MISMATCH')
        return expected
    return resolve


def make_handoff_tool(service: HandoffService, resolve_actor: Callable[[ToolContext], Actor],
                      budget: ToolBudget, emit: Callable[..., None]):
    def create_handoff_request(
        idempotency_key: str,
        confirmation_id: str,
        request_text: str,
        event_id: str,
        tool_context: ToolContext | None = None,
    ) -> dict[str, Any]:
        """建立人工服務請求；先核對已確認內容，以冪等鍵避免重複建立。

        Args:
            idempotency_key: 由應用端提供的送出鍵，同一操作重送沿用原值。
            confirmation_id: 本次已完成內容確認的識別碼，後端會查驗原紀錄。
            request_text: 使用者已確認的完整詢問文字，重送時保持原樣。
            event_id: 已確認的活動識別碼。
            tool_context: ADK 自動提供的工具環境，不由模型填寫。
        """
        budget.take()
        try:
            actor = resolve_actor(tool_context)
        except PermissionError:
            result = {'status':'not_authorized','request_created':False,'human_claimed':False}
        else:
            result = service.create(actor=actor,idempotency_key=idempotency_key,
                confirmation_id=confirmation_id,request_text=request_text,event_id=event_id)
        emit('TOOL_EXECUTED', args={'idempotency_key':idempotency_key,
            'confirmation_id':confirmation_id,'request_text':request_text,'event_id':event_id},
            result=result,rows_after=service.count())
        return result
    return create_handoff_request


def build_agent(model: Any, tool: Callable, before_model: Callable, after_model: Callable):
    return LlmAgent(name='local_day09_handoff',model=model,instruction=INSTRUCTION,
        tools=[tool],before_model_callback=before_model,after_model_callback=after_model,
        generate_content_config=types.GenerateContentConfig(max_output_tokens=1024,
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)))
