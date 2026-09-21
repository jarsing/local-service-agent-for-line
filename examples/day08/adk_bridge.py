"""Day 8 ADK 工具確認介接層。

連接 Google ADK 的 ToolContext.request_confirmation 與 LOCAL 的 ConfirmationStore。
支援離線 Scripted/Mock 模型驗證與真實 Gemini 模型呼叫。
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Callable

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import ToolContext
from google.genai import types

from adapter import CatalogCatalogState, DEFAULT_EVENT_ID
from confirmation import ConfirmationStore, Identity, Operation

logger = logging.getLogger(__name__)


class ConfirmationService:
    """應用層服務：整合狀態、確認 Store 與身分。"""

    def __init__(
        self,
        catalog_state: CatalogCatalogState | None = None,
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.catalog_state = catalog_state or CatalogCatalogState("v1")
        self.store = ConfirmationStore()
        self.time_provider = time_provider or (lambda: datetime.now(timezone.utc))
        self._current_operations: dict[Any, Operation] = {}
        self.last_offer: dict[str, Any] | None = None

    def get_or_create_operation(
        self,
        draft_id: str,
        event_id: str,
        request_text: str,
        owner: Identity | None = None,
    ) -> Operation:
        event = self.catalog_state.get_event(event_id)
        displayed = {
            "name": event["name"],
            "area": event["area"],
            "venue": event["venue"],
            "date": event["date"],
            "time": event["time"],
        }
        op = Operation(
            draft_id=draft_id,
            revision=1,
            event_id=event_id,
            catalog_version=self.catalog_state.catalog_version,
            request_text=request_text,
            displayed_event=displayed,
        )
        if owner:
            self._current_operations[(owner.user_id, owner.session_id, draft_id)] = op
        self._current_operations[draft_id] = op
        return op

    def issue_offer(
        self,
        owner: Identity,
        operation: Operation,
        ttl_seconds: int = 300,
    ) -> dict[str, Any]:
        now = self.time_provider()
        offer = self.store.issue(
            owner=owner,
            operation=operation,
            current_catalog_version=self.catalog_state.catalog_version,
            data_status=self.catalog_state.data_status,
            now=now,
            ttl_seconds=ttl_seconds,
        )
        self.last_offer = offer
        return offer

    def validate_and_record(
        self,
        confirmation_id: str,
        actor: Identity,
        draft_id: str,
        approved: bool,
    ) -> dict[str, Any]:
        now = self.time_provider()
        # 取得伺服器端保存之確認紀錄
        record = self.store._records.get(confirmation_id)
        if not record:
            return {
                "status": "not_found",
                "confirmation_id": confirmation_id,
                "execution_allowed": False,
            }

        # 取得最新伺服器版本下的活動資料
        event_id = record["snapshot"]["event_id"]
        try:
            current_event = self.catalog_state.get_event(event_id)
            current_displayed = {
                "name": current_event["name"],
                "area": current_event["area"],
                "venue": current_event["venue"],
                "date": current_event["date"],
                "time": current_event["time"],
            }
        except KeyError:
            current_displayed = record["snapshot"]["displayed_event"]

        # M04: 核對時讀取現行草稿內容，以 (actor.user_id, actor.session_id, draft_id) 優先
        active_op = self._current_operations.get((actor.user_id, actor.session_id, draft_id))
        if active_op is None:
            active_op = self._current_operations.get(draft_id)

        if active_op is not None:
            current_request_text = active_op.request_text
            current_revision = active_op.revision
        else:
            current_request_text = record["snapshot"]["request_text"]
            current_revision = record["snapshot"]["revision"]

        current_op = Operation(
            draft_id=draft_id,
            revision=current_revision,
            event_id=event_id,
            catalog_version=self.catalog_state.catalog_version,
            request_text=current_request_text,
            displayed_event=current_displayed,
        )

        return self.store.decide(
            confirmation_id=confirmation_id,
            actor=actor,
            current_operation=current_op,
            current_catalog_version=self.catalog_state.catalog_version,
            data_status=self.catalog_state.data_status,
            permitted=True,
            approved=approved,
            now=now,
        )


def make_prepare_handoff_draft_tool(
    service: ConfirmationService,
    get_current_identity: Callable[[ToolContext], Identity],
) -> Callable[..., dict[str, Any]]:
    """建立帶有 ToolContext 確認機制的 ADK 工具。"""

    def prepare_handoff_draft(
        draft_id: str = "draft-001",
        request_text: str = "請問這場活動的集合地點在哪裡？",
        tool_context: ToolContext | None = None,
        event_id: str = DEFAULT_EVENT_ID,
    ) -> dict[str, Any]:
        """準備人工服務詢問草稿，並向使用者請求明確確認。

        Args:
            draft_id: 草稿唯一編號，例如 'draft-001'。
            request_text: 整理後的詢問文字，例如 '請問這場活動的集合地點在哪裡？'。
            tool_context: ADK 工具執行環境，用於呼叫確認與取得回覆。
            event_id: 目標活動 ID，預設為花壇場次 'evt-60d76a55472c503faa4c'。
        """
        identity = get_current_identity(tool_context)
        confirmation = tool_context.tool_confirmation

        if confirmation is None:
            # 階段一：建立草稿與待確認單（offer），向使用者出示確認請求
            operation = service.get_or_create_operation(
                draft_id=draft_id,
                event_id=event_id,
                request_text=request_text,
                owner=identity,
            )
            offer = service.issue_offer(owner=identity, operation=operation)
            ev = operation.displayed_event

            hint = (
                f"【請確認這份詢問內容】\n"
                f"活動：{ev.get('name')}（{ev.get('area')}・{ev.get('venue')}）\n"
                f"日期：{ev.get('date')}\n"
                f"活動時段：{ev.get('time')}\n"
                f"詢問內容：{request_text}\n"
                f"接收對象：LOCAL 教學服務窗口"
            )

            tool_context.request_confirmation(
                hint=hint,
                payload={
                    "confirmation_id": offer["confirmation_id"],
                    "draft_id": draft_id,
                    "event_id": event_id,
                    "operation_fingerprint": offer["operation_fingerprint"],
                },
            )
            return {
                "status": "awaiting_confirmation",
                "confirmation_id": offer["confirmation_id"],
                "summary": hint,
            }

        # 階段二：使用者已按下按鈕回覆，重新核對伺服器最新狀態
        # M03: 依已安裝 ADK 的實際事件，保留原工具／確認事件與 confirmation_id 的可靠對應
        confirmation_id = None
        if confirmation.payload and isinstance(confirmation.payload, dict):
            confirmation_id = confirmation.payload.get("confirmation_id")

        # 若 payload 未附帶，從 session 事件中尋找綁定此 tool call 的原 adk_request_confirmation 事件
        if not confirmation_id and tool_context:
            fc_id = getattr(tool_context, "function_call_id", None)
            inv_ctx = getattr(tool_context, "_invocation_context", None)
            session = getattr(inv_ctx, "session", None) if inv_ctx else None
            if fc_id and session and getattr(session, "events", None):
                for ev in session.events:
                    for fc in ev.get_function_calls():
                        if fc.name == "adk_request_confirmation":
                            orig = fc.args.get("originalFunctionCall", {}) if fc.args else {}
                            if orig.get("id") == fc_id:
                                tc = fc.args.get("toolConfirmation", {})
                                p = tc.get("payload", {}) if isinstance(tc, dict) else {}
                                if isinstance(p, dict):
                                    confirmation_id = p.get("confirmation_id")
                                break
                    if confirmation_id:
                        break

        # 若仍無 confirmation_id，明確拒絕，絕不回退至 store._latest
        if not confirmation_id:
            return {
                "status": "not_found",
                "error": "Cannot find valid confirmation_id bound to original tool confirmation event.",
                "execution_allowed": False,
            }

        decision = service.validate_and_record(
            confirmation_id=confirmation_id,
            actor=identity,
            draft_id=draft_id,
            approved=bool(confirmation.confirmed),
        )
        return decision

    return prepare_handoff_draft


def create_day08_agent(
    model: str | BaseLlm,
    service: ConfirmationService,
    current_identity: Identity,
    agent_name: str = "local_day08_agent",
    generate_content_config: types.GenerateContentConfig | None = None,
    before_model_callback: Any | None = None,
    after_model_callback: Any | None = None,
) -> LlmAgent:
    """建立 Day 8 的 ADK LlmAgent。"""
    tool = make_prepare_handoff_draft_tool(
        service=service,
        get_current_identity=lambda ctx: current_identity,
    )
    instruction = (
        "你是 LOCAL 本機服務小幫手。當使用者想詢問活動詳情（例如集合地點、停車位）時，"
        "請呼叫 prepare_handoff_draft 工具準備草稿，向使用者出示確認內容。\n"
        "若呼叫工具，draft_id 可用 'draft-001'，request_text 為整理後的詢問內容，event_id 預設為 'evt-60d76a55472c503faa4c'。\n"
        "當工具確認結果回傳時：\n"
        "- 若 status 為 confirmation_recorded，告訴使用者已成功確認內容，將在下一階段建立服務單。\n"
        "- 若 status 為 version_changed，告訴使用者活動資訊已更新，出示新時段並請使用者確認新版。\n"
        "- 若 status 為 cancelled，告知使用者已取消。\n"
        "切勿替使用者做決定，亦勿捏造已向主辦方送出或報名成功。"
    )
    kwargs: dict[str, Any] = {
        "name": agent_name,
        "model": model,
        "instruction": instruction,
        "tools": [tool],
    }
    if generate_content_config is not None:
        kwargs["generate_content_config"] = generate_content_config
    if before_model_callback is not None:
        kwargs["before_model_callback"] = before_model_callback
    if after_model_callback is not None:
        kwargs["after_model_callback"] = after_model_callback
    return LlmAgent(**kwargs)
