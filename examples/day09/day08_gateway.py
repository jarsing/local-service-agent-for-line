"""Day 9 到 Day 8 的窄介接層：沿用確認核心，另加服務端身分範圍與送出鍵。

Day 8 沒有公開唯讀 getter；本檔集中讀取其 _records，並使用原 _lock。
確認／到期／換版／取消的判斷仍呼叫原 decide()，不另寫一份規則。
此層是單行程、記憶體的教學服務；不把昨天匯出的 receipt JSON 當授權。
"""
from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
from threading import RLock
from typing import Callable, Iterator, Any
from dependencies import Identity, Operation, ConfirmationStore, operation_fingerprint

@dataclass(frozen=True)
class Actor:
    tenant_id: str
    user_id: str
    session_id: str

    def __post_init__(self) -> None:
        if any(type(x) is not str or not x.strip() for x in
               (self.tenant_id, self.user_id, self.session_id)):
            raise ValueError("Actor 必須包含服務端確認的 tenant、user 與 session。")

    @property
    def identity(self) -> Identity:
        return Identity(self.user_id, self.session_id)

class ConfirmationRejected(ValueError):
    def __init__(self, status: str):
        super().__init__(status)
        self.status = status

class Day08Gateway:
    """每個 tenant 使用獨立 Day 8 store；所有操作在同一服務鎖內完成。"""
    def __init__(self, clock: Callable[[], datetime] | None = None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock = RLock()
        self._stores: dict[str, Any] = {}
        self._issued: dict[tuple[str, str], dict[str, Any]] = {}
        self._drafts: dict[tuple[str, str, str, str], Any] = {}
        self.fixture = json.loads((Path(__file__).parent / "fixtures.json").read_text('utf-8'))
        self.catalog = deepcopy(self.fixture['snapshots']['v2'])

    def _store(self, tenant_id: str) -> ConfirmationStore:
        if tenant_id not in self._stores:
            self._stores[tenant_id] = ConfirmationStore()
        return self._stores[tenant_id]

    @staticmethod
    def _scope(actor: Actor, draft_id: str) -> tuple[str, str, str, str]:
        return actor.tenant_id, actor.user_id, actor.session_id, draft_id

    def prepare(self, actor: Actor, request_text: str, *, draft_id: str | None = None,
                ttl_seconds: int = 300, idempotency_key: str | None = None) -> dict[str, Any]:
        """可信應用端準備新確認；僅供測試／入口呼叫，沒有暴露給模型。"""
        with self.lock:
            ev = self.catalog['event']
            draft_id = draft_id or 'draft-' + secrets.token_hex(8)
            scope = self._scope(actor, draft_id)
            previous = self._drafts.get(scope)
            operation = Operation(
                draft_id=draft_id, revision=(previous.revision + 1 if previous else 1),
                event_id=ev['id'], catalog_version=self.catalog['catalog_version'],
                request_text=request_text,
                displayed_event={k: ev[k] for k in ('name','area','venue','date','time')})
            offer = self._store(actor.tenant_id).issue(
                owner=actor.identity, operation=operation,
                current_catalog_version=self.catalog['catalog_version'],
                data_status=self.catalog['data_status'], now=self.clock(), ttl_seconds=ttl_seconds)
            key = idempotency_key or 'send-' + secrets.token_urlsafe(18)
            self._drafts[scope] = operation
            self._issued[(actor.tenant_id, offer['confirmation_id'])] = {
                'actor': actor, 'draft_id': draft_id, 'key': key}
            return {**deepcopy(offer), 'idempotency_key': key}

    def _context(self, actor: Actor, confirmation_id: str) -> tuple[dict[str, Any], dict[str, Any], Operation]:
        binding = self._issued.get((actor.tenant_id, confirmation_id))
        if binding is None or binding['actor'] != actor:
            raise ConfirmationRejected('unconfirmed_operation')
        store = self._store(actor.tenant_id)
        with store._lock:
            record = deepcopy(store._records.get(confirmation_id))
        if record is None:
            raise ConfirmationRejected('unconfirmed_operation')
        op = self._drafts.get(self._scope(actor, binding['draft_id']))
        if op is None:
            raise ConfirmationRejected('unconfirmed_operation')
        event = self.catalog['event']
        if op.event_id != event['id']:
            raise ConfirmationRejected('content_changed')
        current = replace(op, catalog_version=self.catalog['catalog_version'],
            displayed_event={k: event[k] for k in ('name','area','venue','date','time')})
        return binding, record, current

    def record_user_decision(self, actor: Actor, confirmation_id: str,
                             *, approved: bool) -> dict[str, Any]:
        """由可信入口明確送入布林選擇；建立服務單時不呼叫本方法代人同意。"""
        with self.lock:
            _, _, op = self._context(actor, confirmation_id)
            return self._store(actor.tenant_id).decide(
                confirmation_id=confirmation_id, actor=actor.identity, current_operation=op,
                current_catalog_version=self.catalog['catalog_version'],
                data_status=self.catalog['data_status'], permitted=True,
                approved=approved, now=self.clock())

    @contextmanager
    def creation_guard(self, actor: Actor, confirmation_id: str, idempotency_key: str,
                       request_text: str, event_id: str) -> Iterator[Any]:
        """只接受已有確認，再重用 Day 8 decide 核對現行內容；鎖持續到 DB 提交。"""
        with self.lock:
            binding, record, op = self._context(actor, confirmation_id)
            if record['status'] != 'confirmation_recorded':
                raise ConfirmationRejected('unconfirmed_operation')
            if binding['key'] != idempotency_key:
                raise ConfirmationRejected('invalid_idempotency_key')
            if request_text != op.request_text or event_id != op.event_id:
                raise ConfirmationRejected('content_mismatch')
            result = self._store(actor.tenant_id).decide(
                confirmation_id=confirmation_id, actor=actor.identity, current_operation=op,
                current_catalog_version=self.catalog['catalog_version'],
                data_status=self.catalog['data_status'], permitted=True,
                approved=True, now=self.clock())
            if result['status'] != 'already_confirmed':
                raise ConfirmationRejected(result['status'])
            # 原確認收據仍為 execution_allowed=False；建單授權由 handoff 另行判定。
            yield deepcopy(op)

    def change_draft_text(self, actor: Actor, confirmation_id: str, request_text: str) -> None:
        """測試／未來編輯入口使用；刻意保留舊確認，交由核對抓出內容異動。"""
        with self.lock:
            binding, _, op = self._context(actor, confirmation_id)
            self._drafts[self._scope(actor, binding['draft_id'])] = replace(
                op, request_text=request_text, revision=op.revision+1)

    def switch_catalog(self, label: str) -> None:
        with self.lock:
            self.catalog = deepcopy(self.fixture['snapshots'][label])

    def record_status(self, actor: Actor, confirmation_id: str) -> str | None:
        with self.lock:
            store = self._stores.get(actor.tenant_id)
            if store is None:
                return None
            with store._lock:
                record = store._records.get(confirmation_id)
                return record['status'] if record and record['owner'] == actor.identity else None
