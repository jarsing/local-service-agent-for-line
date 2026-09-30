"""可信結果轉換接點與離線替身；不推測缺少的目錄資料格式。"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from .outcomes import (
    CatalogChanged, FailureReason, QueryOutcome, QueryState,
    QueryUnavailable, ToolContractError, UpstreamHTTPError,
)


READ_TOOL_FIELDS = MappingProxyType({
    "search_local_events": ("date", "area", "keyword"),
    "search_local_places": ("area", "dietary_type", "keyword"),
    "show_local_help": ("reason",),
})
SEARCH_TOOLS = frozenset({"search_local_events", "search_local_places"})


class QueryPhase(str, Enum):
    COMPLETED = "completed"
    NEEDS_AREA = "needs_area"


@dataclass(frozen=True)
class TrustedQueryResult:
    """由伺服器端轉換器建立，不能直接用模型 JSON 建立。

    rows 是一筆一段文字的可信呈現資料，並非既有 places/events schema。
    COMPLETED + conditions_valid + 空 rows 才能支持「快照查無資料」。
    """

    tool_name: str
    phase: QueryPhase = QueryPhase.COMPLETED
    conditions_valid: bool = True
    rows: tuple[str, ...] = ()
    available_areas: tuple[str, ...] = ()
    memory_revision: int | None = None


QueryAdapter = Callable[[Mapping[str, Any]], TrustedQueryResult]


def _revision(value: object) -> int | None:
    if value is not None and (type(value) is not int or value < 0):
        raise ToolContractError("INVALID_MEMORY_REVISION")
    return value


def _checked_query(value: TrustedQueryResult) -> QueryOutcome:
    if value.tool_name not in SEARCH_TOOLS or not isinstance(value.phase, QueryPhase):
        raise ToolContractError("UNKNOWN_QUERY_KIND")
    if type(value.conditions_valid) is not bool:
        raise ToolContractError("QUERY_VALIDATION_REQUIRED")
    if not isinstance(value.rows, tuple) or any(
        not isinstance(row, str) or not row.strip() or len(row) > 3000
        for row in value.rows
    ):
        raise ToolContractError("INVALID_PRESENTATION_ROWS")
    if (
        len(value.rows) > 50 or sum(len(row) for row in value.rows) > 3500
        or len("\n\n".join(value.rows).encode("utf-16-le")) // 2 > 4500
    ):
        raise ToolContractError("PRESENTATION_BUDGET")
    if not isinstance(value.available_areas, tuple) or any(
        not isinstance(area, str) or not area.strip()
        or len(area.encode("utf-16-le")) // 2 > 20
        or any(char in area for char in "\r\n:")
        for area in value.available_areas
    ):
        raise ToolContractError("INVALID_AVAILABLE_AREAS")
    revision = _revision(value.memory_revision)
    if value.phase is QueryPhase.NEEDS_AREA:
        if value.tool_name != "search_local_places" or value.rows or value.conditions_valid:
            raise ToolContractError("INVALID_AREA_QUERY_PHASE")
        if not value.available_areas:
            raise ToolContractError("AREA_CHOICES_REQUIRED")
        return QueryOutcome(
            QueryState.NEEDS_AREA, "area_required", value.tool_name,
            available_areas=value.available_areas, memory_revision=revision,
        )
    if not value.conditions_valid:
        raise ToolContractError("QUERY_NOT_VALIDATED")
    state = QueryState.SUCCESS if value.rows else QueryState.NO_DATA
    return QueryOutcome(
        state, "query_completed" if value.rows else "empty_snapshot",
        value.tool_name, value.rows, value.available_areas, revision,
    )


def normalize_executed_result(
    raw: object,
    query_adapter: QueryAdapter | None = None,
    *,
    executed_tool_name: str | None = None,
) -> QueryOutcome:
    """只接收已執行工具的結果；呼叫數與工具身分由 QueryService 核對。

    原始店家／活動 dict 需由 host 依真實 schema 完整核對後轉換。
    缺少轉換器時直接拒絕，不能以 raw.get('places', []) 猜成空結果。
    """
    if executed_tool_name is not None and executed_tool_name not in READ_TOOL_FIELDS:
        raise ToolContractError("UNSUPPORTED_EXECUTED_TOOL")
    if isinstance(raw, TrustedQueryResult):
        if executed_tool_name is not None and raw.tool_name != executed_tool_name:
            raise ToolContractError("RESULT_TOOL_MISMATCH")
        return _checked_query(raw)
    if not isinstance(raw, Mapping):
        raise ToolContractError("RESULT_MAPPING_REQUIRED")
    if raw.get("status") == "help":
        if executed_tool_name not in (None, "show_local_help"):
            raise ToolContractError("RESULT_TOOL_MISMATCH")
        if set(raw) - {"status", "reason", "memory_revision"}:
            raise ToolContractError("UNKNOWN_HELP_FIELDS")
        reason = raw.get("reason", "")
        if reason not in ("", "unsupported"):
            raise ToolContractError("UNKNOWN_HELP_REASON")
        return QueryOutcome(
            QueryState.UNSUPPORTED if reason == "unsupported" else QueryState.HELP,
            "unsupported" if reason == "unsupported" else "general_help",
            "show_local_help", memory_revision=_revision(raw.get("memory_revision")),
        )
    if executed_tool_name == "show_local_help" or query_adapter is None:
        raise ToolContractError("TRUSTED_QUERY_ADAPTER_REQUIRED")
    adapted = query_adapter(raw)
    if not isinstance(adapted, TrustedQueryResult):
        raise ToolContractError("TRUSTED_QUERY_RESULT_REQUIRED")
    if executed_tool_name is not None and adapted.tool_name != executed_tool_name:
        raise ToolContractError("RESULT_TOOL_MISMATCH")
    # 轉換器不可意外丟掉或改寫原工具所附的偏好版本。
    if "memory_revision" in raw and _revision(raw["memory_revision"]) != adapted.memory_revision:
        raise ToolContractError("RESULT_REVISION_MISMATCH")
    return _checked_query(adapted)


def is_events_result(raw: object) -> bool:
    return (
        isinstance(raw, TrustedQueryResult) and raw.tool_name == "search_local_events"
    ) or (isinstance(raw, Mapping) and raw.get("status") == "events_result")


def classify_exception(exc: Exception) -> FailureReason:
    """僅辨識列明的類別或既有固定錯誤碼；未知 SDK 錯誤不猜屬性。"""
    if isinstance(exc, QueryUnavailable):
        return exc.reason
    if isinstance(exc, CatalogChanged):
        return FailureReason.CATALOG_CHANGED
    if isinstance(exc, ToolContractError):
        return FailureReason.TOOL_CONTRACT
    if isinstance(exc, ValueError) and exc.args == ("CATALOG_CHANGED",):
        return FailureReason.CATALOG_CHANGED
    if isinstance(exc, ValueError) and exc.args == ("NO_EXECUTED_TOOL",):
        return FailureReason.TOOL_CONTRACT
    if isinstance(exc, UpstreamHTTPError):
        if exc.status_code == 429:
            return FailureReason.RATE_LIMITED
        if exc.status_code in (408, 504):
            return FailureReason.UPSTREAM_TIMEOUT
        if exc.status_code in (500, 502, 503):
            return FailureReason.UPSTREAM_UNAVAILABLE
        return FailureReason.UNEXPECTED
    if isinstance(exc, TimeoutError):
        return FailureReason.UPSTREAM_TIMEOUT
    if isinstance(exc, ConnectionError):
        return FailureReason.NETWORK
    return FailureReason.UNEXPECTED


def classify_failure(exc: Exception) -> FailureReason:
    """供既有應用程式使用的純函式接點，與離線服務採相同原因表。"""
    return classify_exception(exc)


class ScriptedTools:
    """離線替身：只有三項唯讀工具；沒有服務單或偏好寫入方法。"""

    def __init__(self, results: Mapping[str, object] | None = None, *, revision: int = 0):
        self.results = dict(results or {})
        self.revision = _revision(revision)
        self.calls: list[dict[str, object]] = []
        self.last: object = None
        self._attempted = False

    def execute(self, name: str, args: dict[str, str]) -> object:
        if name not in READ_TOOL_FIELDS:
            raise PermissionError("TOOL_NOT_ALLOWED")
        if not isinstance(args, dict) or set(args) - set(READ_TOOL_FIELDS[name]):
            raise PermissionError("UNEXPECTED_ARGUMENTS")
        if any(not isinstance(value, str) or len(value) > 100 for value in args.values()):
            raise PermissionError("INVALID_ARGUMENT_VALUE")
        if name == "search_local_places" and args.get("dietary_type", "") not in (
            "", "any", "vegetarian", "vegan", "ovo_lacto",
        ):
            raise PermissionError("INVALID_DIETARY_VALUE")
        if self._attempted:
            raise ToolContractError("ONE_BUSINESS_TOOL_PER_TURN")
        self._attempted = True
        normalized = {key: args.get(key, "") for key in READ_TOOL_FIELDS[name]}
        if name in self.results:
            result = self.results[name]
        elif name == "show_local_help":
            result = {
                "status": "help", "reason": normalized["reason"],
                "memory_revision": self.revision,
            }
        else:
            raise ToolContractError("SCRIPTED_QUERY_RESULT_REQUIRED")
        if isinstance(result, Exception):
            raise result
        self.calls.append({"tool": name, "memory_revision": self.revision})
        self.last = result
        return result


@dataclass(frozen=True)
class ScriptedStep:
    tool_name: str | None = None
    arguments: Mapping[str, str] = field(default_factory=dict)
    failure: Exception | None = None
    delay_seconds: float = 0
    reported_text: str = ""


class ScriptedInterpreter:
    """測試程式指定工具，不代表 Gemini 的意圖判定成果。"""

    mode = "SCRIPTED_INTENT_NOT_GEMINI"

    def __init__(self, mapping: Mapping[str, ScriptedStep] | None = None):
        self.mapping = dict(mapping or {})
        self.ask_count = 0

    async def ask(self, text: str, actor: object, event_id: str, tools: Any) -> dict[str, object]:
        self.ask_count += 1
        step = self.mapping.get(text, ScriptedStep())
        if step.delay_seconds:
            await asyncio.sleep(step.delay_seconds)
        if step.failure is not None:
            raise step.failure
        if step.tool_name is not None:
            tools.execute(step.tool_name, dict(step.arguments))
        return {
            "mode": self.mode, "reported_text": step.reported_text,
            "model_api_calls": 0,
        }
