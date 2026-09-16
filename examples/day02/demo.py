"""LOCAL Day 2: a LOCAL synthetic transport-failure experiment, not a Gemini run.

Standard library only. The SQLite write is real; timeouts are deliberately
injected. No network, LINE, Google API, production authorization or cloud SDK.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from collections.abc import Iterator
from enum import Enum
from pathlib import Path
import hashlib
import json
import sqlite3
import tempfile
import uuid

# This file lives at <repo>/examples/day02/demo.py.
SPEC_PATH = Path(__file__).resolve().parents[2] / "docs/day01/handoff-timeout-001.json"
from typing import Any


class IdempotencyConflict(ValueError):
    """An existing operation key cannot be reused with changed content."""


class Fault(str, Enum):
    NONE = "none"
    BEFORE_WRITE = "before_write"
    AFTER_COMMIT = "after_commit"


@dataclass(frozen=True)
class Request:
    # The caller identity is a TRUSTED SYNTHETIC fixture, not model-supplied auth.
    tenant_id: str
    user_id: str
    idempotency_key: str
    service_id: str
    request_text: str

    def validate(self) -> None:
        for name, value in vars(self).items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")

    def payload_hash(self) -> str:
        payload = json.dumps(
            {"service_id": self.service_id, "request_text": self.request_text},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: Path):
        self.path = path
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    service_id TEXT NOT NULL,
                    request_text TEXT NOT NULL,
                    request_id TEXT NOT NULL UNIQUE,
                    human_state TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, user_id, idempotency_key)
                )
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def create(self, request: Request) -> dict[str, Any]:
        request.validate()
        digest = request.payload_hash()
        # The uniqueness check and insert happen in one database transaction.
        # No external side effects may be performed inside a retried transaction.
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO requests (tenant_id, user_id, idempotency_key, payload_hash,
                                      service_id, request_text, request_id, human_state)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (tenant_id, user_id, idempotency_key) DO NOTHING
            """, (
                request.tenant_id, request.user_id, request.idempotency_key,
                digest, request.service_id, request.request_text,
                f"req-{uuid.uuid4().hex}", "awaiting_acceptance",
            ))
            row = conn.execute("""
                SELECT * FROM requests
                WHERE tenant_id=? AND user_id=? AND idempotency_key=?
            """, (request.tenant_id, request.user_id, request.idempotency_key)).fetchone()
            if row is None:
                raise RuntimeError("Invariant violated: insert did not create a row")
            if row["payload_hash"] != digest:
                raise IdempotencyConflict("The operation key is bound to different content")
            receipt = dict(row)
        # Returning after leaving the context ensures that commit has completed.
        return receipt

    def lookup(self, request: Request) -> dict[str, Any] | None:
        request.validate()
        with self.connect() as conn:
            row = conn.execute("""
                SELECT * FROM requests
                WHERE tenant_id=? AND user_id=? AND idempotency_key=?
            """, (request.tenant_id, request.user_id, request.idempotency_key)).fetchone()
        if row is not None and row["payload_hash"] != request.payload_hash():
            raise IdempotencyConflict("Cannot reconcile changed content under the same key")
        return dict(row) if row is not None else None

    def count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0])


def pending_verification() -> dict[str, Any]:
    # This implements Day 1's expected policy. Do not load the answer from the
    # fixture here: implementation and expectation must remain independent.
    return {
        "reply_state": "pending_verification",
        "claim_completed": False,
        "next_step": "reconcile_by_idempotency_key",
        "retry_policy": "reuse_same_idempotency_key",
    }


def verified_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    # This receipt proves request creation, NOT staff acceptance/service completion.
    return {
        "reply_state": "request_created",
        "request_id": receipt["request_id"],
        "human_state": receipt["human_state"],
        "next_step": "await_human_receipt",
    }


def submit(
    store: Store, request: Request, *, confirmed: bool, fault: Fault = Fault.NONE
) -> dict[str, Any]:
    request.validate()
    # Day 2 uses a boolean fixture only. This is NOT production authorization.
    # A later lesson must bind verified identity, action content and expiry.
    if confirmed is not True:
        return {"reply_state": "needs_confirmation", "claim_completed": False}
    if not isinstance(fault, Fault):
        raise ValueError("fault must be a Fault enum value")
    try:
        if fault is Fault.BEFORE_WRITE:
            raise TimeoutError("SYNTHETIC: request lost before write")
        receipt = store.create(request)
        if fault is Fault.AFTER_COMMIT:
            raise TimeoutError("SYNTHETIC: reply lost after committed write")
        return verified_receipt(receipt)
    except TimeoutError:
        # The caller cannot distinguish the two injected failures by timeout alone.
        return pending_verification()


def reconcile(
    store: Store, request: Request, *, lookup_unavailable: bool = False
) -> dict[str, Any]:
    if lookup_unavailable:
        return pending_verification()
    receipt = store.lookup(request)
    if receipt is None:
        # Absence in this lookup is not a universal proof that a remote operation
        # can never finish. Remain pending; no blind new operation key is issued.
        return pending_verification()
    return verified_receipt(receipt)


def demo_request(**changes: str) -> Request:
    values = {
        "tenant_id": "synthetic-town-a", "user_id": "synthetic-user-a",
        "idempotency_key": "demo-request-001", "service_id": "walk-001",
        "request_text": "請協助確認走讀活動的無障礙需求。",
    }
    values.update(changes)
    return Request(**values)


def main() -> None:
    fixture_path = SPEC_PATH
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="local-day02-") as temp:
        store = Store(Path(temp) / "local.db")
        request = demo_request(idempotency_key=fixture["given"]["idempotency_key"])
        after_timeout = submit(
            store, request, confirmed=fixture["given"]["user_confirmed"],
            fault=Fault.AFTER_COMMIT,
        )
        if after_timeout != fixture["expected"]:
            raise AssertionError("Day 1 acceptance specification not satisfied")
        # A fresh Store reopens the same file, rather than depending on memory.
        reopened = Store(store.path)
        checked = reconcile(reopened, request)
        retried = submit(reopened, request, confirmed=True)
        for label, data in [
            ("after_timeout", after_timeout),
            ("after_reconciliation", {
                "reply_state": checked["reply_state"],
                "human_state": checked["human_state"],
            }),
            ("after_same_key_retry", {
                "same_request_id": checked["request_id"] == retried["request_id"],
                "stored_request_count": reopened.count(),
            }),
        ]:
            print(label + ": " + json.dumps(data, ensure_ascii=False, sort_keys=True))
        print("NOTE: synthetic transport + real local SQLite; no Gemini/LINE/cloud call.")


if __name__ == "__main__":
    main()
