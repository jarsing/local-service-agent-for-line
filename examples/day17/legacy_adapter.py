"""接回 2fe7736 的真實目錄與原路由；不建立另一組記憶／同意流程。

schema 依 examples/day14/places.py、day05/catalog.py、day12/catalog_view.py。
此轉換器只接受伺服器已執行的工具結果，不接受模型自稱完成的 JSON。
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
import importlib
import time
from typing import Any

from .adapters import (
    QueryPhase, TrustedQueryResult, classify_exception, normalize_executed_result,
)
from . import messages
from .outcomes import (
    FailureReason, QueryOutcome, QueryState, ToolContractError,
    UpstreamHTTPError, unavailable,
)


_DIETS = frozenset({"any", "vegetarian", "vegan", "ovo_lacto", "lacto", "allium", "friendly"})
_NEARBY = frozenset({"附近", "這附近", "集合點附近", "花壇集合點附近", "彰化"})
_PLACES_REQUIRED = frozenset({
    "tool", "query", "catalog_version", "catalog_sha256", "selection", "campaign",
    "available_areas", "unknown_fields", "sources", "status", "places", "total", "message",
})
_EVENTS_REQUIRED = frozenset({"status", "query", "catalog_version", "events", "unknown_fields"})


def _mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ToolContractError(code)
    return value


def _revision(raw: Mapping[str, Any]) -> int | None:
    value = raw.get("memory_revision")
    if value is not None and (type(value) is not int or value < 0):
        raise ToolContractError("INVALID_MEMORY_REVISION")
    return value


def _query(value: object, fields: frozenset[str]) -> Mapping[str, str]:
    query = _mapping(value, "QUERY_MAPPING_REQUIRED")
    if set(query) != fields or any(
        not isinstance(item, str) or len(item) > 80 for item in query.values()
    ):
        raise ToolContractError("INVALID_QUERY_FIELDS")
    return query


def _strings(value: object, code: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ToolContractError(code)
    return tuple(value)


def _places(raw: Mapping[str, Any]) -> TrustedQueryResult:
    if not _PLACES_REQUIRED <= set(raw):
        raise ToolContractError("INCOMPLETE_PLACES_RESULT")
    query = _query(raw["query"], frozenset({"area", "dietary_type", "keyword"}))
    if query["dietary_type"] not in _DIETS:
        raise ToolContractError("INVALID_DIETARY_TYPE")
    if any(any(ord(char) < 32 for char in query[key]) for key in ("area", "keyword")):
        raise ToolContractError("INVALID_QUERY_CHARACTERS")
    if not isinstance(raw["catalog_version"], str) or not raw["catalog_version"]:
        raise ToolContractError("CATALOG_VERSION_REQUIRED")
    digest = raw["catalog_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ToolContractError("CATALOG_DIGEST_REQUIRED")
    _mapping(raw["campaign"], "CAMPAIGN_REQUIRED")
    _mapping(raw["sources"], "SOURCES_REQUIRED")
    _strings(raw["unknown_fields"], "UNKNOWN_FIELDS_REQUIRED")
    areas = _strings(raw["available_areas"], "AREAS_REQUIRED")
    rows, total, status = raw["places"], raw["total"], raw["status"]
    if not isinstance(rows, list) or type(total) is not int or total < 0:
        raise ToolContractError("INVALID_PLACES_ROWS")
    if not isinstance(raw["message"], str):
        raise ToolContractError("CATALOG_MESSAGE_REQUIRED")
    if status == "needs_area":
        if query["area"] not in _NEARBY or rows or total != 0:
            raise ToolContractError("INCONSISTENT_NEEDS_AREA")
        return TrustedQueryResult(
            "search_local_places", QueryPhase.NEEDS_AREA, False,
            available_areas=areas, memory_revision=_revision(raw),
        )
    if query["area"] in _NEARBY or status not in ("ok", "not_found"):
        raise ToolContractError("INVALID_PLACES_STATUS")
    if status == "not_found" and (rows or total != 0):
        raise ToolContractError("INCONSISTENT_EMPTY_PLACES")
    if status == "ok" and (total == 0 or len(rows) != min(total, 5)):
        raise ToolContractError("INCONSISTENT_PLACES_TOTAL")
    names = []
    for row in rows:
        row = _mapping(row, "PLACE_MAPPING_REQUIRED")
        if any(not isinstance(row.get(key), str) or not row[key] for key in ("place_id", "name", "area")):
            raise ToolContractError("PLACE_IDENTITY_REQUIRED")
        names.append(row["name"])
    return TrustedQueryResult(
        "search_local_places", rows=tuple(names), available_areas=areas,
        memory_revision=_revision(raw),
    )


def _events(raw: Mapping[str, Any]) -> TrustedQueryResult:
    if "catalog_result" not in raw:
        raise ToolContractError("CATALOG_RESULT_REQUIRED")
    result = _mapping(raw["catalog_result"], "EVENT_RESULT_MAPPING_REQUIRED")
    # Day 5 的 error 有空 events，但它不代表查詢成功且資料為空。
    if result.get("status") == "error":
        raise ToolContractError("EVENT_QUERY_REJECTED")
    if not _EVENTS_REQUIRED <= set(result):
        raise ToolContractError("INCOMPLETE_EVENTS_RESULT")
    query = _query(result["query"], frozenset({"date", "area", "keyword"}))
    if not any(query.values()):
        raise ToolContractError("EVENT_CONDITION_REQUIRED")
    if query["date"]:
        try:
            valid_date = date.fromisoformat(query["date"]).isoformat() == query["date"]
        except ValueError:
            valid_date = False
        if not valid_date:
            raise ToolContractError("INVALID_EVENT_DATE")
    if not isinstance(result["catalog_version"], str) or not result["catalog_version"]:
        raise ToolContractError("CATALOG_VERSION_REQUIRED")
    _strings(result["unknown_fields"], "UNKNOWN_FIELDS_REQUIRED")
    status, rows = result["status"], result["events"]
    if status not in ("ok", "not_found") or not isinstance(rows, list):
        raise ToolContractError("INVALID_EVENTS_STATUS")
    if (status == "ok") != bool(rows):
        raise ToolContractError("INCONSISTENT_EVENTS_STATUS")
    names = []
    for row in rows:
        row = _mapping(row, "EVENT_MAPPING_REQUIRED")
        if any(not isinstance(row.get(key), str) or not row[key] for key in ("id", "name", "date", "area")):
            raise ToolContractError("EVENT_IDENTITY_REQUIRED")
        names.append(row["name"])
    return TrustedQueryResult(
        "search_local_events", rows=tuple(names), memory_revision=_revision(raw),
    )


def legacy_query_adapter(raw: Mapping[str, Any]) -> TrustedQueryResult:
    """把既有完整回傳轉為核心契約；名稱文字只供分類，成功結果仍由原 renderer 呈現。"""
    raw = _mapping(raw, "RESULT_MAPPING_REQUIRED")
    if raw.get("tool") == "search_local_places":
        return _places(raw)
    if raw.get("status") == "events_result":
        return _events(raw)
    raise ToolContractError("UNKNOWN_LEGACY_QUERY")


def legacy_outcome(raw: Mapping[str, Any]) -> QueryOutcome | None:
    """None 表示沿用原記憶提案／管理流程，不能把寫入流程交給唯讀示範器。"""
    raw = _mapping(raw, "RESULT_MAPPING_REQUIRED")
    if raw.get("status") in ("memory_proposal_requested", "memory_management_requested"):
        return None
    if raw.get("status") == "help":
        tool = "show_local_help"
    elif raw.get("tool") == "search_local_places":
        tool = "search_local_places"
    elif raw.get("status") == "events_result":
        tool = "search_local_events"
    else:
        raise ToolContractError("UNKNOWN_LEGACY_RESULT")
    return normalize_executed_result(raw, legacy_query_adapter, executed_tool_name=tool)


def legacy_result_plan(
    app: Any, result: Mapping[str, Any], *, place_formatter=None,
) -> dict[str, Any] | None:
    """在原 _finalize 已核對偏好版本之後呼叫；保留來源完整的成功與區域追問 renderer。"""
    outcome = legacy_outcome(result)
    if outcome is None or outcome.state in (QueryState.SUCCESS, QueryState.NEEDS_AREA):
        return None
    rendered = messages.present_query_outcome(outcome)
    if outcome.state is QueryState.NO_DATA:
        if outcome.tool_name == "search_local_places":
            if place_formatter is None:
                raise ToolContractError("ORIGINAL_PLACES_FORMATTER_REQUIRED")
            rendered = place_formatter(result)[:1] + rendered
        else:
            rendered = [messages.text(app.catalog.format_result(result["catalog_result"]))] + rendered
    return app._plan(rendered, outcome.as_result(), outcome.memory_revision)


def _optional_module(name: str):
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def classify_legacy_exception(exc: Exception, *, model_stage: bool = False) -> FailureReason:
    """先確認真正 SDK 類別，再讀其正式狀態欄位；不依任意例外的 code 猜測。"""
    if isinstance(exc, PermissionError):
        raise exc
    legacy = _optional_module("examples.day12.inherit")
    if legacy is not None and isinstance(exc, legacy.StoreUnavailable):
        return FailureReason.STORE_UNAVAILABLE
    genai = _optional_module("google.genai.errors")
    if genai is not None and isinstance(exc, genai.APIError):
        code = exc.code
        if isinstance(code, int) and not isinstance(code, bool) and 100 <= code <= 599:
            return classify_exception(UpstreamHTTPError(int(code)))
        return FailureReason.UNEXPECTED
    httpx = _optional_module("httpx")
    if httpx is not None:
        if isinstance(exc, httpx.TimeoutException):
            return FailureReason.UPSTREAM_TIMEOUT
        if isinstance(exc, (httpx.NetworkError, httpx.RemoteProtocolError)):
            return FailureReason.NETWORK
    cloud = _optional_module("google.api_core.exceptions")
    if cloud is not None:
        if isinstance(exc, cloud.TooManyRequests):
            return FailureReason.RATE_LIMITED
        if isinstance(exc, cloud.DeadlineExceeded):
            return FailureReason.UPSTREAM_TIMEOUT
        if isinstance(exc, cloud.ServiceUnavailable):
            return FailureReason.UPSTREAM_UNAVAILABLE
    if isinstance(exc, TimeoutError) and model_stage:
        return FailureReason.MODEL_TIMEOUT
    return classify_exception(exc)


def legacy_failure_plan(
    app: Any, exc: Exception, *, started: float | None = None, model_stage: bool = False,
) -> dict[str, Any]:
    reason = classify_legacy_exception(exc, model_stage=model_stage)
    fields: dict[str, Any] = {"reason": reason.value, "error_type": type(exc).__name__}
    if started is not None:
        fields["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
    app.emit("DAY14_QUERY_UNAVAILABLE", **fields)
    outcome = unavailable(reason)
    return app._plan(messages.present_query_outcome(outcome), outcome.as_result())
