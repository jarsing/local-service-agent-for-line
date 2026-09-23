"""資料列查驗與參數；SQLite 查回不呼叫 create()。"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import sqlite3
from typing import Any, Callable
from upstream import Actor, HandoffRequest, payload_hash
from policy import error_result, pending_result


@dataclass(frozen=True)
class SendArgs:
    idempotency_key: str
    confirmation_id: str
    request_text: str
    event_id: str

    def valid(self) -> bool:
        return all(type(value) is str and bool(value.strip()) and len(value) <= limit
                   for value, limit in ((self.idempotency_key, 200), (self.confirmation_id, 200),
                                        (self.request_text, 2000), (self.event_id, 200)))

    def tool_args(self) -> dict[str, str]:
        return asdict(self)


class ReceiptReader:
    """查回時核對當前權限、本人、Session 與精確內容；全程 read-only。"""
    def __init__(self, db_path: Path, permission_resolver: Callable[[Actor], bool]):
        self.db_path = Path(db_path)
        self.permitted = permission_resolver

    def lookup(self, actor: Actor, args: SendArgs) -> dict[str, Any]:
        if not isinstance(actor, Actor):
            raise TypeError('actor 必須由可信入口提供。')
        if self.permitted(actor) is not True:
            return error_result('not_authorized')
        if not args.valid():
            return error_result('invalid_arguments')
        # mode=ro 防止路徑打錯時偷偷建立一個空資料庫。
        try:
            conn = sqlite3.connect(self.db_path.resolve().as_uri() + '?mode=ro',
                                   uri=True, timeout=0.2, isolation_level=None)
            try:
                conn.row_factory = sqlite3.Row
                conn.execute('PRAGMA query_only=ON')
                row = conn.execute(
                    'SELECT * FROM handoff_requests '
                    'WHERE tenant_id=? AND user_id=? AND idempotency_key=?',
                    (actor.tenant_id, actor.user_id, args.idempotency_key),
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            # 忙碌、磁碟 I/O 或檔案不可用，與「SELECT 成功但沒找到」分開。
            code = getattr(exc, 'sqlite_errorcode', -1)
            primary = code & 0xff if isinstance(code, int) else -1
            if primary in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED,
                           sqlite3.SQLITE_CANTOPEN, sqlite3.SQLITE_IOERR):
                return pending_result('lookup_unavailable')
            raise
        if row is None:
            return pending_result('not_found')
        if row['session_id'] != actor.session_id:
            return error_result('wrong_actor')
        if row['payload_hash'] != payload_hash(args.confirmation_id, args.request_text, args.event_id):
            return error_result('idempotency_conflict')
        request = HandoffRequest(**{name: row[name] for name in HandoffRequest.__dataclass_fields__})
        return {'status': 'already_created', 'request_id': request.request_id,
                'request': asdict(request), 'request_created': False,
                'human_claimed': False, 'delivery': 'local_sqlite_only',
                'observation': 'found'}


def sqlite_rows(path: Path) -> list[dict[str, Any]]:
    """僅供合成實驗、測試與離線報告；不暴露為 Agent 工具。"""
    conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(
            'SELECT * FROM handoff_requests ORDER BY request_id')]
    finally:
        conn.close()
