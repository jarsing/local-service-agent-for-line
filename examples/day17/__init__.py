"""可離線重現的查詢結果分流；外部服務以明確接點注入。"""

from .outcomes import FailureReason, QueryOutcome, QueryState

__all__ = ["FailureReason", "QueryOutcome", "QueryState"]
