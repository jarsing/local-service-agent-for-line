"""單回合查詢服務；不建立 Webhook，也不代替原有確認、查單或偏好路由。"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
import inspect
import math
import time
from typing import Any

from .adapters import (
    QueryAdapter, READ_TOOL_FIELDS, classify_exception, is_events_result,
    normalize_executed_result,
)
from . import messages as msg
from .outcomes import (
    CatalogChanged, FailureReason, PreferenceChanged, QueryOutcome,
    QueryState, QueryUnavailable, ToolContractError, unavailable,
)


HELP_TEXT = frozenset({
    "我要預約", "預約", "幫我預約", "我想預約", "功能", "你好", "開始", "使用說明",
})
RETRY_TEXT = msg.RETRY_TEXT


async def _invoke(function: Callable[..., Any], *args: object) -> Any:
    """保留同步資料存取的背景執行，也容納既有非同步接點。"""
    if inspect.iscoroutinefunction(function):
        return await function(*args)
    result = await asyncio.to_thread(function, *args)
    return await result if inspect.isawaitable(result) else result


class QueryService:
    def __init__(
        self, interpreter: Any, tools_factory: Callable[[object], Any], *,
        catalog_is_current: Callable[[object], Any] | None = None,
        assert_revision: Callable[[object, int], Any] | None = None,
        query_adapter: QueryAdapter | None = None,
        emit: Callable[..., Any] | None = None,
        timeout_seconds: float = 18,
        legacy_route: Callable[[object, Mapping[str, Any]], Any] | None = None,
        preference_changed_exceptions: tuple[type[Exception], ...] = (PreferenceChanged,),
    ):
        if isinstance(timeout_seconds, bool) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("POSITIVE_TIMEOUT_REQUIRED")
        if not preference_changed_exceptions or any(
            not isinstance(kind, type) or not issubclass(kind, Exception)
            or kind in (Exception, BaseException, PermissionError)
            for kind in preference_changed_exceptions
        ):
            raise ValueError("SPECIFIC_PREFERENCE_EXCEPTION_REQUIRED")
        self.interpreter = interpreter
        self.tools_factory = tools_factory
        self.catalog_is_current = catalog_is_current
        self.assert_revision = assert_revision
        self.query_adapter = query_adapter
        self.emit = emit
        self.timeout_seconds = timeout_seconds
        self.legacy_route = legacy_route
        self.preference_changed_exceptions = preference_changed_exceptions

    @staticmethod
    def _plan(messages: list[dict[str, object]], result: dict[str, object], revision: int | None = None) -> dict[str, object]:
        return {"messages": messages, "result": result, "memory_revision": revision}

    def query_failure(self, reason: FailureReason | str, *, elapsed: float, exc: Exception | None = None) -> dict[str, object]:
        outcome = unavailable(reason)
        if self.emit is not None:
            # 不收原文、使用者識別、偏好值、工具引數或任意例外全文。
            fields: dict[str, object] = {"reason": outcome.reason, "elapsed_ms": round(elapsed * 1000, 3)}
            if exc is not None:
                fields["error_type"] = type(exc).__name__
            self.emit("DAY14_QUERY_UNAVAILABLE", **fields)
        return self._plan(msg.present_query_outcome(outcome), outcome.as_result())

    async def present_query_outcome(self, actor: object, outcome: QueryOutcome) -> dict[str, object]:
        if outcome.memory_revision is not None:
            if self.assert_revision is None:
                raise ToolContractError("MEMORY_REVISION_CHECK_REQUIRED")
            await _invoke(self.assert_revision, actor, outcome.memory_revision)
        return self._plan(
            msg.present_query_outcome(outcome), outcome.as_result(), outcome.memory_revision,
        )

    async def _ask_once(self, text: str, actor: object, event_id: str, tools: Any) -> None:
        try:
            # 工具／模型介面本身拋出的逾時，先與外層等待期限分開。
            await self.interpreter.ask(text, actor, event_id, tools)
        except TimeoutError as exc:
            raise QueryUnavailable(FailureReason.UPSTREAM_TIMEOUT) from exc

    async def route_query(self, actor: object, event: Mapping[str, Any]) -> dict[str, object]:
        started = time.monotonic()
        try:
            text = event.get("message", {}).get("text", "")
            event_id = event.get("webhookEventId")
            if not isinstance(text, str) or not text.strip() or len(text) > 1200 or not isinstance(event_id, str) or not event_id:
                raise ToolContractError("VALID_TEXT_EVENT_REQUIRED")
            tools = await _invoke(self.tools_factory, actor)
            try:
                await asyncio.wait_for(
                    self._ask_once(text, actor, event_id, tools),
                    timeout=self.timeout_seconds,
                )
            except TimeoutError as exc:
                raise QueryUnavailable(FailureReason.MODEL_TIMEOUT) from exc
            if tools.last is None or len(tools.calls) != 1:
                raise ToolContractError("NO_EXECUTED_TOOL")
            call = tools.calls[0]
            if not isinstance(call, Mapping) or call.get("tool") not in READ_TOOL_FIELDS:
                raise ToolContractError("INVALID_EXECUTED_TOOL")
            raw = tools.last
            if call["tool"] == "search_local_events" or is_events_result(raw):
                if self.catalog_is_current is None:
                    raise ToolContractError("CATALOG_CURRENT_CHECK_REQUIRED")
                if await _invoke(self.catalog_is_current, actor) is not True:
                    raise CatalogChanged()
            outcome = normalize_executed_result(raw, self.query_adapter, executed_tool_name=call["tool"])
            return await self.present_query_outcome(actor, outcome)
        except self.preference_changed_exceptions:
            outcome = QueryOutcome(QueryState.PREFERENCE_CHANGED, "preference_changed")
            return self._plan(msg.present_query_outcome(outcome), outcome.as_result())
        except PermissionError:
            raise
        except Exception as exc:
            return self.query_failure(classify_exception(exc), elapsed=time.monotonic() - started, exc=exc)

    async def route(self, actor: object, event: Mapping[str, Any]) -> dict[str, object]:
        """固定入口可避開模型；既有業務路由由 host 注入並維持其授權。"""
        text = event.get("message", {}).get("text", "")
        data = event.get("postback", {}).get("data", "") if event.get("type") == "postback" else ""
        if not isinstance(text, str) or not isinstance(data, str):
            return self._plan([msg.help_card()], {"status": "unsupported_message", "reason": "text_required"})
        if text in HELP_TEXT or data == "d14:help":
            return self._plan([msg.help_card()], {"status": "help", "reason": "fixed_help"})
        if text == RETRY_TEXT:
            return self._plan([msg.retry_guide()], {"status": "retry_prompt", "reason": "new_query_required"})
        if data:
            if self.legacy_route is not None:
                return await _invoke(self.legacy_route, actor, event)
            return self._plan(
                [msg.text("此離線入口只呈現查詢分流。按鈕需由原服務路由接手處理。")],
                {"status": "legacy_route_required", "reason": "host_route_required"},
            )
        return await self.route_query(actor, event)
