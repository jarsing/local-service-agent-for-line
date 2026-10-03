"""SQLite inbox teaching extension. No LINE client and no production integration.

Identifiers are passed by a trusted application adapter, never by an unauthenticated
HTTP caller. This database is an isolated projection, NOT the existing requests DB.
Channel acceptance, human claim and human-recorded resolution are separate facts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

SCHEMA = """
CREATE TABLE IF NOT EXISTS volunteers(id TEXT PRIMARY KEY, enabled INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS inbox(
 request_id TEXT PRIMARY KEY, owner_ref TEXT NOT NULL, category TEXT NOT NULL,
 fingerprint TEXT NOT NULL, state TEXT NOT NULL, claim_version INTEGER NOT NULL,
 claimed_by TEXT, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox(
 request_id TEXT PRIMARY KEY REFERENCES inbox(request_id), recipient_ref TEXT NOT NULL,
 retry_key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL,
 first_attempt REAL, attempts INTEGER NOT NULL DEFAULT 0, provider_id TEXT
);
"""


class Inbox:
    def __init__(self, path: str | Path, clock: Callable[[], float] = time.time):
        self.path, self.clock = str(path), clock
        with self.connection() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def set_volunteer(self, volunteer: str, enabled: bool = True):
        # Administrative adapter only; not a public endpoint.
        if not volunteer or type(enabled) is not bool:
            raise ValueError("INVALID_VOLUNTEER")
        with self.transaction() as db:
            db.execute("INSERT INTO volunteers VALUES(?,?) ON CONFLICT(id) "
                       "DO UPDATE SET enabled=excluded.enabled", (volunteer, int(enabled)))

    @staticmethod
    def authorize(db, volunteer):
        if not db.execute("SELECT 1 FROM volunteers WHERE id=? AND enabled=1",
                          (volunteer,)).fetchone():
            raise PermissionError("UNAUTHORIZED_VOLUNTEER")

    def register_confirmed(self, request_id: str, owner_ref: str, category: str,
                           recipient_ref: str) -> dict:
        """Mirror an ALREADY confirmed source record. Caller must verify ownership.

        No raw query or telephone is stored or sent by this minimal projection.
        `claim_version` changes on ownership transitions, not delivery bookkeeping.
        """
        if any(not isinstance(v, str) or not v or len(v) > 120
               for v in (request_id, owner_ref, category, recipient_ref)):
            raise ValueError("INVALID_CONFIRMED_REQUEST")
        canonical = json.dumps([owner_ref, category, recipient_ref], ensure_ascii=False)
        fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        with self.transaction() as db:
            old = db.execute("SELECT * FROM inbox WHERE request_id=?", (request_id,)).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise ValueError("SAME_ID_DIFFERENT_CONTENT")
                return dict(old)
            db.execute("INSERT INTO inbox VALUES(?,?,?,?,?,1,NULL,?)",
                       (request_id, owner_ref, category, fingerprint,
                        "request_created", self.clock()))
            payload = {"request_id": request_id, "category": category,
                       "claim_version": 1, "label": "我來處理"}
            db.execute("INSERT INTO outbox VALUES(?,?,?,?,?,NULL,0,NULL)",
                       (request_id, recipient_ref, str(uuid.uuid4()),
                        json.dumps(payload, ensure_ascii=False, sort_keys=True), "pending"))
        return self.user_status(request_id, owner_ref)

    def claim(self, request_id: str, volunteer: str, expected_version: int) -> bool:
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("INVALID_VERSION")
        with self.transaction() as db:
            self.authorize(db, volunteer)
            changed = db.execute(
                "UPDATE inbox SET state='human_claimed', claimed_by=?, "
                "claim_version=claim_version+1, updated_at=? "
                "WHERE request_id=? AND claim_version=? AND claimed_by IS NULL "
                "AND state IN ('request_created','notification_accepted')",
                (volunteer, self.clock(), request_id, expected_version),
            ).rowcount
            return changed == 1

    def resolve(self, request_id: str, volunteer: str) -> bool:
        # This records the handler's declaration; it does not prove a phone call.
        with self.transaction() as db:
            self.authorize(db, volunteer)
            return db.execute("UPDATE inbox SET state='resolved', "
                              "claim_version=claim_version+1, updated_at=? "
                              "WHERE request_id=? AND claimed_by=? AND state='human_claimed'",
                              (self.clock(), request_id, volunteer)).rowcount == 1

    def user_status(self, request_id: str, owner_ref: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT request_id,state,updated_at FROM inbox "
                             "WHERE request_id=? AND owner_ref=?", (request_id, owner_ref)).fetchone()
            if row is None:
                raise PermissionError("REQUEST_NOT_VISIBLE")
            return dict(row)

    def list_for_volunteer(self, volunteer: str) -> list[dict]:
        with self.transaction() as db:
            self.authorize(db, volunteer)
            return [dict(r) for r in db.execute(
                "SELECT request_id,category,state,claim_version FROM inbox WHERE state!='resolved'")]

    def notification(self, request_id: str) -> dict:
        # Internal dispatcher query, never an unauthenticated client response.
        with self.connection() as db:
            row = db.execute("SELECT * FROM outbox WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise ValueError("NOTIFICATION_NOT_FOUND")
            return dict(row)

    def dispatch(self, request_id: str, sender: Callable[[dict], str]) -> str:
        """`sender` must honor persisted retry_key and return channel acceptance ID.

        No claim of exactly-once network delivery. Repeated attempts are allowed
        with the same key within 24h; expiry requires reconciliation, not a new key.
        Local tests use FakeSender. No real network sender is included.
        """
        with self.transaction() as db:
            row = db.execute("SELECT * FROM outbox WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise ValueError("NOTIFICATION_NOT_FOUND")
            row = dict(row)
            if row['status'] == 'accepted':
                return row['provider_id']
            now = self.clock()
            first = row['first_attempt']
            if first is not None and now - first >= 24 * 3600:
                raise RuntimeError("RETRY_WINDOW_EXPIRED_RECONCILE")
            db.execute("UPDATE outbox SET first_attempt=COALESCE(first_attempt,?), "
                       "attempts=attempts+1,status='attempting' WHERE request_id=?", (now, request_id))
        # External side effect must not occur in a transaction callback.
        try:
            provider_id = sender(row)
            if not isinstance(provider_id, str) or not provider_id:
                raise ValueError("CHANNEL_ACCEPTANCE_REQUIRED")
        except Exception:
            with self.transaction() as db:
                db.execute("UPDATE outbox SET status='unknown' WHERE request_id=? "
                           "AND status!='accepted'", (request_id,))
            raise
        with self.transaction() as db:
            db.execute("UPDATE outbox SET status='accepted',provider_id=? WHERE request_id=?",
                       (provider_id, request_id))
            db.execute("UPDATE inbox SET state='notification_accepted',updated_at=? "
                       "WHERE request_id=? AND state='request_created'", (self.clock(), request_id))
        return provider_id


class FakeSender:
    """Offline stand-in: records provider acceptance, NOT LINE delivery."""
    def __init__(self):
        self.accepted = {}
        self.attempts = 0

    def __call__(self, row: dict) -> str:
        self.attempts += 1
        key = row['retry_key']
        signature = (row['recipient_ref'], row['payload'])
        if key in self.accepted:
            receipt, original = self.accepted[key]
            if original != signature:
                raise ValueError("RETRY_CONTENT_CHANGED")
            return receipt
        receipt = 'synthetic-acceptance-' + uuid.uuid4().hex
        self.accepted[key] = (receipt, signature)
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    inbox = Inbox(args.out / 'inbox.sqlite')
    inbox.set_volunteer('synthetic-amy'); inbox.set_volunteer('synthetic-bob')
    rid = 'synthetic-request-' + uuid.uuid4().hex
    inbox.register_confirmed(rid, 'synthetic-owner', 'meal_inquiry', 'synthetic-inbox')
    card_version = inbox.notification(rid)
    sender = FakeSender()
    receipt = inbox.dispatch(rid, sender)
    version = json.loads(card_version['payload'])['claim_version']
    first = inbox.claim(rid, 'synthetic-amy', version)
    second = inbox.claim(rid, 'synthetic-bob', version)
    report = {'mode': 'SQLITE_OFFLINE_FAKE_SENDER', 'network_calls': 0,
              'request_id': rid, 'fake_acceptance_id': receipt,
              'claims': [first, second], 'status': inbox.user_status(rid, 'synthetic-owner'),
              'external_integration': 'NOT_EXECUTED', 'real_human': 'NOT_OBSERVED'}
    (args.out/'REPORT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
