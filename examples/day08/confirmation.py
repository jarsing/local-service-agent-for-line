"""Day 8：把同意綁定到使用者、操作內容、資料版本與期限。

這是單一 Python 行程的教學核心。呼叫端必須提供已驗證的身分、
伺服器保存的草稿及目前採用版本；模型／表單不能自行指定這些可信值。
本模組只記錄內容確認，不建立人工服務請求，也不授予執行權限。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import secrets
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class Identity:
    user_id: str
    session_id: str


@dataclass(frozen=True)
class Operation:
    draft_id: str
    revision: int
    event_id: str
    catalog_version: str
    request_text: str
    displayed_event: dict[str, Any]
    # 此處代表下一篇預定建立的人工服務請求，不是本篇已執行的工具。
    action: str = "create_handoff_request"
    destination: str = "local_demo_service_desk"


def operation_fingerprint(operation: Operation) -> str:
    """依本例確定的 JSON 編碼規則比較內容；摘要不是數位簽章。"""
    data = json.dumps(asdict(operation), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _require_time(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("時間必須包含時區。")


class ConfirmationStore:
    """記憶體確認紀錄；Lock 僅保護本行程，不是跨服務交易。"""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._latest: dict[tuple[str, str, str], str] = {}
        self._lock = Lock()

    def issue(self, *, owner: Identity, operation: Operation,
              current_catalog_version: str, data_status: str,
              now: datetime, ttl_seconds: int = 300) -> dict[str, Any]:
        _require_time(now)
        if not owner.user_id.strip() or not owner.session_id.strip():
            raise ValueError("需要由呼叫端提供使用者及 Session。")
        if (not operation.draft_id.strip() or not operation.event_id.strip()
                or not operation.catalog_version.strip()
                or not operation.request_text.strip()):
            raise ValueError("操作識別、活動、版本與詢問內容不得空白。")
        if type(operation.revision) is not int or operation.revision < 1:
            raise ValueError("草稿修訂版須為正整數。")
        if (operation.action != "create_handoff_request"
                or operation.destination != "local_demo_service_desk"):
            raise ValueError("本篇只準備一種人工服務請求的內容確認。")
        if type(ttl_seconds) is not int or ttl_seconds <= 0:
            raise ValueError("確認期限必須為正整數秒。")
        if (data_status != "adopted"
                or current_catalog_version != operation.catalog_version):
            raise ValueError("先取得目前已採用的活動資料，再建立確認。")
        snapshot = json.loads(json.dumps(asdict(operation), ensure_ascii=False,
                                         allow_nan=False))
        fingerprint = operation_fingerprint(operation)
        with self._lock:
            scope = (owner.user_id, owner.session_id, operation.draft_id)
            previous = self._latest.get(scope)
            if previous and self._records[previous]["status"] == "awaiting_confirmation":
                self._records[previous]["status"] = "superseded"
            confirmation_id = secrets.token_urlsafe(24)
            record = {
                "owner": owner, "fingerprint": fingerprint, "snapshot": snapshot,
                "status": "awaiting_confirmation", "created_at": now,
                "expires_at": now + timedelta(seconds=ttl_seconds), "receipt": None,
            }
            self._records[confirmation_id] = record
            self._latest[scope] = confirmation_id
            return {
                "confirmation_id": confirmation_id,
                "status": record["status"],
                "operation": json.loads(json.dumps(snapshot, ensure_ascii=False)),
                "operation_fingerprint": fingerprint,
                "expires_at": record["expires_at"].isoformat(),
            }

    def decide(self, *, confirmation_id: str, actor: Identity,
               current_operation: Operation, current_catalog_version: str,
               data_status: str, permitted: bool, approved: bool,
               now: datetime) -> dict[str, Any]:
        """先核對最新伺服器狀態；重複確認只回傳既有確認收據。

        approved 必須是介面／可信呼叫端傳入的布林選擇，不是模型猜出的值。
        current_operation、permitted、actor 均由應用程式取得。
        """
        _require_time(now)
        if type(approved) is not bool or type(permitted) is not bool:
            raise ValueError("同意與授權狀態必須是布林值。")
        with self._lock:
            record = self._records.get(confirmation_id)
            def result(status: str) -> dict[str, Any]:
                return {"status": status, "confirmation_id": confirmation_id,
                        "execution_allowed": False}
            if record is None:
                return result("not_found")
            if actor != record["owner"]:
                return result("wrong_actor")
            if record["status"] not in ("awaiting_confirmation", "confirmation_recorded"):
                return result(record["status"])
            # 取消的是尚待確認的內容；不把取消已確認紀錄當成撤回已發出的服務。
            if not approved:
                if record["status"] == "confirmation_recorded":
                    return result("already_confirmed")
                record["status"] = "cancelled"
                return result("cancelled")
            if not permitted:
                return result("not_authorized")
            if now < record["created_at"]:
                return result("clock_error")
            if now >= record["expires_at"]:
                record["status"] = "expired"
                return result("expired")
            if data_status != "adopted":
                return result("data_pending")
            if current_catalog_version != record["snapshot"]["catalog_version"]:
                record["status"] = "version_changed"
                return result("version_changed")
            if operation_fingerprint(current_operation) != record["fingerprint"]:
                record["status"] = "content_changed"
                return result("content_changed")
            if record["status"] == "confirmation_recorded":
                return {**result("already_confirmed"), "receipt": dict(record["receipt"])}
            record["status"] = "confirmation_recorded"
            record["receipt"] = {
                "confirmation_id": confirmation_id,
                "operation_fingerprint": record["fingerprint"],
                "catalog_version": current_catalog_version,
                "recorded_at": now.isoformat(),
            }
            return {**result("confirmation_recorded"), "receipt": dict(record["receipt"])}
