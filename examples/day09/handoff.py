"""Day 9：SQLite 受控建單；同鍵同內容取得同一回條，同鍵異內容明確拒絕。"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
from typing import Any, Callable, Iterator
from day08_gateway import Actor, Day08Gateway, ConfirmationRejected
from dependencies import operation_fingerprint

@dataclass(frozen=True)
class HandoffRequest:
    request_id: str
    idempotency_key: str
    user_id: str
    tenant_id: str
    session_id: str
    request_text: str
    event_id: str
    confirmation_id: str
    catalog_version: str
    operation_fingerprint: str
    status: str
    created_at: str

SCHEMA = """
CREATE TABLE IF NOT EXISTS handoff_requests (
 request_id TEXT PRIMARY KEY,
 tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, session_id TEXT NOT NULL,
 idempotency_key TEXT NOT NULL, confirmation_id TEXT NOT NULL,
 request_text TEXT NOT NULL, event_id TEXT NOT NULL,
 payload_hash TEXT NOT NULL, operation_fingerprint TEXT NOT NULL,
 catalog_version TEXT NOT NULL, operation_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status = 'pending_human_review'),
 created_at TEXT NOT NULL,
 UNIQUE(tenant_id, user_id, idempotency_key),
 UNIQUE(tenant_id, user_id, confirmation_id)
);
"""

def payload_hash(confirmation_id: str, request_text: str, event_id: str) -> str:
    """固定編碼，只比較本次送出的原始值；不移除會改變問題的空白或標點。"""
    data = json.dumps({'confirmation_id': confirmation_id, 'request_text': request_text,
        'event_id': event_id, 'action':'create_handoff_request',
        'destination':'local_demo_service_desk'}, ensure_ascii=False, sort_keys=True,
        separators=(',',':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()

class HandoffService:
    """此服務只寫本機 DB。permission_resolver 由可信應用端提供，不列入工具參數。"""
    def __init__(self, db_path: Path | str, confirmations: Day08Gateway,
                 permission_resolver: Callable[[Actor], bool],
                 clock: Callable[[], datetime] | None = None):
        self.db_path = Path(db_path)
        if str(db_path) == ':memory:':
            raise ValueError('本例需可查回的 SQLite 檔案，請提供檔案路徑。')
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.confirmations = confirmations
        self.permitted = permission_resolver
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _error(status: str) -> dict[str, Any]:
        return {'status':status, 'request_created':False, 'human_claimed':False}

    @staticmethod
    def _result(row: sqlite3.Row, status: str) -> dict[str, Any]:
        request = HandoffRequest(**{name:row[name] for name in HandoffRequest.__dataclass_fields__})
        return {'status':status, 'request_id':request.request_id, 'request':asdict(request),
                'request_created':status == 'request_created', 'human_claimed':False,
                'delivery':'local_sqlite_only'}

    def create(self, *, actor: Actor, idempotency_key: str, confirmation_id: str,
               request_text: str, event_id: str) -> dict[str, Any]:
        if not isinstance(actor, Actor):
            raise TypeError('actor 必須來自可信入口。')
        if any(type(s) is not str or not s.strip() or len(s) > limit for s,limit in
               ((idempotency_key,200),(confirmation_id,200),(request_text,2000),(event_id,200))):
            return self._error('unconfirmed_operation' if not confirmation_id else 'invalid_arguments')
        digest = payload_hash(confirmation_id, request_text, event_id)
        with self.connection() as conn:
            try:
                # BEGIN IMMEDIATE 先取得寫入交易；查重與新增在同一筆交易完成。
                conn.execute('BEGIN IMMEDIATE')
                if self.permitted(actor) is not True:
                    conn.rollback()
                    return self._error('not_authorized')
                row = conn.execute(
                    'SELECT * FROM handoff_requests WHERE tenant_id=? AND user_id=? AND idempotency_key=?',
                    (actor.tenant_id, actor.user_id, idempotency_key)).fetchone()
                if row is not None:
                    if row['session_id'] != actor.session_id:
                        conn.rollback()
                        return self._error('wrong_actor')
                    if row['payload_hash'] != digest:
                        conn.rollback()
                        return self._error('idempotency_conflict')
                    # 已建立的重送是讀取既有結果；確認到期不會再新增一筆。
                    conn.commit()
                    return self._result(row, 'already_created')

                with self.confirmations.creation_guard(actor, confirmation_id, idempotency_key,
                                                       request_text, event_id) as operation:
                    # 二道唯一約束：同一確認即使換一個鍵，也只能對應一筆請求。
                    used = conn.execute(
                        'SELECT request_id FROM handoff_requests WHERE tenant_id=? AND user_id=? AND confirmation_id=?',
                        (actor.tenant_id, actor.user_id, confirmation_id)).fetchone()
                    if used is not None:
                        conn.rollback()
                        return self._error('confirmation_already_used')
                    now = self.clock()
                    if now.tzinfo is None or now.utcoffset() is None:
                        raise ValueError('建單時間必須含時區。')
                    request_id = 'req-' + now.strftime('%Y%m%d') + '-' + secrets.token_hex(8)
                    conn.execute("""INSERT INTO handoff_requests
                        (request_id,tenant_id,user_id,session_id,idempotency_key,confirmation_id,
                         request_text,event_id,payload_hash,operation_fingerprint,catalog_version,
                         operation_json,status,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (request_id,actor.tenant_id,actor.user_id,actor.session_id,idempotency_key,
                         confirmation_id,operation.request_text,operation.event_id,digest,
                         operation_fingerprint(operation), operation.catalog_version,
                         json.dumps(asdict(operation),ensure_ascii=False,sort_keys=True),
                         'pending_human_review',now.isoformat()))
                    row = conn.execute('SELECT * FROM handoff_requests WHERE request_id=?',
                                       (request_id,)).fetchone()
                    conn.commit()
                    if row is None:
                        raise RuntimeError('已提交後找不到剛建立的資料列。')
                    return self._result(row, 'request_created')
            except ConfirmationRejected as exc:
                if conn.in_transaction:
                    conn.rollback()
                return self._error(exc.status)
            except sqlite3.OperationalError as exc:
                if conn.in_transaction:
                    conn.rollback()
                # 資料庫忙碌是可核對的失敗，不把任何 SQLite 錯誤寫成成功。
                if getattr(exc, 'sqlite_errorcode', None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    return self._error('storage_busy')
                raise
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise

    def inspect_rows(self) -> list[dict[str, Any]]:
        """僅供本機測試與報告；不是對外工具，勿將多使用者內容交給模型。"""
        with self.connection() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM handoff_requests ORDER BY created_at,request_id')]

    def count(self) -> int:
        with self.connection() as conn:
            return conn.execute('SELECT COUNT(*) FROM handoff_requests').fetchone()[0]
