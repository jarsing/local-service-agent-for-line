"""有限結果型別與安全錯誤原因；不把例外全文送進訊息或日誌。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QueryState(str, Enum):
    NO_DATA = "no_data"
    UNAVAILABLE = "query_unavailable"
    UNSUPPORTED = "unsupported"
    SUCCESS = "success"
    NEEDS_AREA = "needs_area"
    HELP = "help"
    PREFERENCE_CHANGED = "preference_changed"


class FailureReason(str, Enum):
    MODEL_TIMEOUT = "model_timeout"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    NETWORK = "network"
    STORE_UNAVAILABLE = "store_unavailable"
    CATALOG_CHANGED = "catalog_changed"
    TOOL_CONTRACT = "tool_contract"
    UNEXPECTED = "unexpected"


TEMPORARY_REASONS = frozenset({
    FailureReason.MODEL_TIMEOUT,
    FailureReason.UPSTREAM_TIMEOUT,
    FailureReason.RATE_LIMITED,
    FailureReason.UPSTREAM_UNAVAILABLE,
    FailureReason.NETWORK,
    FailureReason.STORE_UNAVAILABLE,
})


class ToolContractError(ValueError):
    """查詢未完成既定工具契約；不能據此推定需求不支援。"""


class CatalogChanged(RuntimeError):
    """活動目錄版本不符；等資料同步後才可採用查詢結果。"""


class PreferenceChanged(RuntimeError):
    """離線接點的偏好異動例外；正式服務需接入原有例外類別。"""


class QueryUnavailable(RuntimeError):
    def __init__(self, reason: FailureReason | str):
        self.reason = FailureReason(reason)
        if self.reason not in TEMPORARY_REASONS:
            raise ValueError("TEMPORARY_REASON_REQUIRED")
        super().__init__(self.reason.value)


class UpstreamHTTPError(RuntimeError):
    """由已核對 SDK 類別的接入層轉換；不猜任意例外的屬性。"""

    def __init__(self, status_code: int):
        if type(status_code) is not int or not 100 <= status_code <= 599:
            raise ValueError("HTTP_STATUS_REQUIRED")
        self.status_code = status_code
        super().__init__("UPSTREAM_HTTP_ERROR")


@dataclass(frozen=True)
class QueryOutcome:
    state: QueryState
    reason: str
    tool_name: str | None = None
    rows: tuple[str, ...] = ()
    available_areas: tuple[str, ...] = ()
    memory_revision: int | None = None

    def as_result(self) -> dict[str, object]:
        result: dict[str, object] = {
            "status": self.state.value,
            "reason": self.reason,
        }
        if self.tool_name is not None:
            result["tool"] = self.tool_name
        if self.state in (QueryState.SUCCESS, QueryState.NO_DATA):
            result["item_count"] = len(self.rows)
        return result


def unavailable(reason: FailureReason | str) -> QueryOutcome:
    return QueryOutcome(QueryState.UNAVAILABLE, FailureReason(reason).value)
