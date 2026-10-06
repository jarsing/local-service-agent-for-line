"""本機 SQLite 人工停止開關；不是 Cloud Run、LINE 或 IAM 的整合實作。

本資料庫獨立於 Day 19。主體來自可信驗證接點，policy 來自可信設定，
不可直接採用 HTTP body 的 subject、role 或 confirmed 欄位作為授權。
confirm() 的呼叫前提：既有確認接點已驗證本次使用者與操作內容的綁定。
外部 sender 僅有測試替身。通知許可取得後可能在停止期間回傳接受紀錄；
晚到回條只更新 outbox，不改服務單。此程式不保證網路 exactly-once。
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
from typing import Callable, Iterator, Mapping

SCHEMA = """
CREATE TABLE IF NOT EXISTS control(
 id INTEGER PRIMARY KEY CHECK(id=1), mode TEXT NOT NULL
 CHECK(mode IN ('SERVING','PAUSED')), epoch INTEGER NOT NULL);
INSERT OR IGNORE INTO control VALUES(1,'PAUSED',0);
CREATE TABLE IF NOT EXISTS requests(
 request_id TEXT PRIMARY KEY, owner TEXT NOT NULL, operation_key TEXT NOT NULL,
 fingerprint TEXT NOT NULL, category TEXT NOT NULL, state TEXT NOT NULL,
 claim_version INTEGER NOT NULL, claimed_by TEXT,
 UNIQUE(owner,operation_key));
CREATE TABLE IF NOT EXISTS outbox(
 request_id TEXT PRIMARY KEY REFERENCES requests(request_id),
 retry_key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL,
 status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 first_attempt REAL, provider_id TEXT);
CREATE TABLE IF NOT EXISTS control_audit(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, mode TEXT NOT NULL,
 epoch INTEGER NOT NULL, operator TEXT NOT NULL, reason TEXT NOT NULL);
"""


class Paused(RuntimeError):
    """服務暫停或控制版本已變更。"""


class SecurityStore:
    def __init__(self, path: str | Path, policy: Mapping[str, str],
                 clock: Callable[[], float] = time.time):
        self.path, self.policy, self.clock = str(path), dict(policy), clock
        with self.connection() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def require(self, subject: str, role: str) -> None:
        if not isinstance(subject, str) or self.policy.get(subject) != role:
            raise PermissionError('ROLE_DENIED')

    @staticmethod
    def gate(db: sqlite3.Connection, expected_epoch: int | None = None) -> int:
        row = db.execute('SELECT mode,epoch FROM control WHERE id=1').fetchone()
        if row is None or row['mode'] != 'SERVING':
            raise Paused('SERVICE_PAUSED')
        if expected_epoch is not None and (
                type(expected_epoch) is not int or row['epoch'] != expected_epoch):
            raise Paused('CONTROL_EPOCH_CHANGED')
        return row['epoch']

    def set_mode(self, subject: str, mode: str, reason: str) -> int:
        self.require(subject, 'operator')
        if mode not in ('PAUSED', 'SERVING'):
            raise ValueError('INVALID_MODE')
        if reason not in ('maintenance', 'incident', 'recovered', 'demo'):
            raise ValueError('INVALID_REASON_CODE')
        with self.transaction() as db:
            row = db.execute('SELECT mode,epoch FROM control WHERE id=1').fetchone()
            if row is None:
                raise Paused('CONTROL_STATE_MISSING')
            if row['mode'] == mode:
                return row['epoch']
            epoch = row['epoch'] + 1
            db.execute('UPDATE control SET mode=?,epoch=? WHERE id=1', (mode, epoch))
            db.execute('INSERT INTO control_audit(mode,epoch,operator,reason) '
                       'VALUES(?,?,?,?)', (mode, epoch, subject, reason))
        return epoch

    def admit(self, subject: str) -> int:
        """模型呼叫前取控制版本；不是授權憑證，也不是確認回條。"""
        self.require(subject, 'user')
        with self.connection() as db:
            return self.gate(db)

    def confirm(self, subject: str, operation_key: str, category: str,
                expected_epoch: int) -> dict:
        """可信確認接點呼叫；相同操作查回優先於停止檢查。"""
        self.require(subject, 'user')
        if not isinstance(operation_key, str) or not 1 <= len(operation_key) <= 120:
            raise ValueError('INVALID_OPERATION_KEY')
        if category not in ('service_inquiry', 'meal_inquiry'):
            raise ValueError('INVALID_CATEGORY')
        if type(expected_epoch) is not int or expected_epoch < 0:
            raise ValueError('INVALID_EPOCH')
        fingerprint = hashlib.sha256(category.encode()).hexdigest()
        with self.transaction() as db:
            old = db.execute('SELECT * FROM requests WHERE owner=? AND operation_key=?',
                             (subject, operation_key)).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise ValueError('SAME_KEY_DIFFERENT_CONTENT')
                return dict(old)
            self.gate(db, expected_epoch)
            rid = str(uuid.uuid4())
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,1,NULL)',
                       (rid, subject, operation_key, fingerprint, category, 'request_created'))
            payload = json.dumps({'request_id': rid, 'category': category,
                                  'claim_version': 1, 'label': '我來處理'},
                                 ensure_ascii=False, sort_keys=True)
            db.execute('INSERT INTO outbox VALUES(?,?,?,?,0,NULL,NULL)',
                       (rid, str(uuid.uuid4()), payload, 'pending'))
            return dict(db.execute('SELECT * FROM requests WHERE request_id=?',
                                   (rid,)).fetchone())

    def read(self, subject: str, request_id: str) -> dict:
        """停止期間仍需授權：使用者僅讀自己的單，志工讀授權收件匣。"""
        role = self.policy.get(subject)
        if role not in ('user', 'volunteer'):
            raise PermissionError('READ_DENIED')
        with self.connection() as db:
            row = db.execute('SELECT * FROM requests WHERE request_id=?',
                             (request_id,)).fetchone()
            if row is None or (role == 'user' and row['owner'] != subject):
                raise PermissionError('REQUEST_NOT_VISIBLE')
            return dict(row)

    def claim(self, subject: str, request_id: str, version: int) -> bool:
        self.require(subject, 'volunteer')
        if type(version) is not int or version < 1:
            raise ValueError('INVALID_CLAIM_VERSION')
        with self.transaction() as db:
            self.gate(db)
            changed = db.execute(
                "UPDATE requests SET state='human_claimed',claimed_by=?, "
                "claim_version=claim_version+1 WHERE request_id=? "
                "AND claim_version=? AND claimed_by IS NULL AND state='request_created'",
                (subject, request_id, version)).rowcount
        return changed == 1

    def resolve(self, subject: str, request_id: str) -> bool:
        self.require(subject, 'volunteer')
        with self.transaction() as db:
            self.gate(db)
            changed = db.execute(
                "UPDATE requests SET state='resolved',claim_version=claim_version+1 "
                "WHERE request_id=? AND state='human_claimed' AND claimed_by=?",
                (request_id, subject)).rowcount
        return changed == 1

    def dispatch(self, subject: str, request_id: str,
                 sender: Callable[[dict], str]) -> str:
        self.require(subject, 'dispatcher')
        with self.transaction() as db:
            row = db.execute('SELECT * FROM outbox WHERE request_id=?',
                             (request_id,)).fetchone()
            if row is None:
                raise ValueError('OUTBOX_NOT_FOUND')
            if row['status'] == 'accepted':
                return row['provider_id']
            self.gate(db)
            first = row['first_attempt']
            if first is not None and self.clock() - first >= 86400:
                raise RuntimeError('RETRY_WINDOW_EXPIRED_RECONCILE')
            db.execute("UPDATE outbox SET status='attempting',attempts=attempts+1, "
                       'first_attempt=COALESCE(first_attempt,?) WHERE request_id=?',
                       (self.clock(), request_id))
            ticket = dict(row)
        # 派送許可以上面的提交為界；已取許可的在途工作不能假裝被撤回。
        try:
            receipt = sender(ticket)
            if not isinstance(receipt, str) or not receipt:
                raise ValueError('ACCEPTANCE_ID_REQUIRED')
        except Exception:
            with self.transaction() as db:
                db.execute("UPDATE outbox SET status='unknown' WHERE request_id=? "
                           "AND status!='accepted'", (request_id,))
            raise
        with self.transaction() as db:
            old = db.execute('SELECT provider_id FROM outbox WHERE request_id=?',
                             (request_id,)).fetchone()
            if old['provider_id'] is not None and old['provider_id'] != receipt:
                raise ValueError('ACCEPTANCE_ID_CONFLICT')
            db.execute("UPDATE outbox SET status='accepted',provider_id=? WHERE request_id=?",
                       (receipt, request_id))
            # 通知回條不更新 requests，也不修改 claim_version。
        return receipt

    def request_snapshot(self) -> list[dict]:
        """僅供本機稽核；不是公開的查詢路由。"""
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM requests ORDER BY request_id')]

    def outbox_snapshot(self) -> list[dict]:
        """僅供本機稽核；可能包含內部通知資訊。"""
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM outbox ORDER BY request_id')]


def demo_policy() -> dict[str, str]:
    """合成身分；不是 LINE 帳號、Cloud IAM 或外部驗證結果。"""
    return {'sample-user': 'user', 'sample-other': 'user',
            'sample-volunteer': 'volunteer', 'sample-second-volunteer': 'volunteer',
            'sample-operator': 'operator', 'sample-worker': 'dispatcher',
            'sample-model': 'model', 'sample-deployer': 'deployer'}


def demo(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    store = SecurityStore(out / 'security.sqlite', demo_policy())
    store.set_mode('sample-operator', 'SERVING', 'demo')
    epoch = store.admit('sample-user')
    old = store.confirm('sample-user', 'sample-confirmation-1', 'service_inquiry', epoch)
    before = store.request_snapshot()
    store.set_mode('sample-operator', 'PAUSED', 'incident')
    blocked = False
    try:
        store.confirm('sample-user', 'sample-confirmation-2', 'service_inquiry', epoch)
    except Paused:
        blocked = True
    unchanged = store.request_snapshot() == before
    same = store.confirm('sample-user', 'sample-confirmation-1', 'service_inquiry', epoch)
    restart = SecurityStore(out / 'security.sqlite', demo_policy())
    still_paused = False
    try:
        restart.admit('sample-user')
    except Paused:
        still_paused = True
    restart.set_mode('sample-operator', 'SERVING', 'recovered')
    stale_blocked = False
    try:
        restart.confirm('sample-user', 'sample-confirmation-3', 'service_inquiry', epoch)
    except Paused:
        stale_blocked = True
    same_after = restart.confirm('sample-user', 'sample-confirmation-1', 'service_inquiry', epoch)
    report = {'mode': 'SQLITE_OFFLINE_STOP_GATE', 'external_calls': 0,
              'new_request_blocked': blocked, 'committed_rows_unchanged': unchanged,
              'same_request_id': same['request_id'] == old['request_id'] == same_after['request_id'],
              'paused_after_reopen': still_paused, 'stale_epoch_blocked': stale_blocked,
              'request_count': len(restart.request_snapshot()),
              'request_id': old['request_id'],
              'cloud_iam': 'NOT_EXECUTED', 'line_human_handoff': 'NOT_EXECUTED'}
    (out / 'REPORT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if not all(report[k] for k in ('new_request_blocked', 'committed_rows_unchanged',
                                   'same_request_id', 'paused_after_reopen', 'stale_epoch_blocked')):
        raise AssertionError('DEMO_CONTRACT_FAILED')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(demo(args.out), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
