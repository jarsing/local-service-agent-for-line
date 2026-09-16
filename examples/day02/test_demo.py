from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from demo import (
    Fault, IdempotencyConflict, Store, demo_request, SPEC_PATH,
    pending_verification, reconcile, submit,
)


class Day02Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="local-test-")
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "test.db")
        self.request = demo_request()

    def test_original_day01_fixture_unchanged(self):
        raw = SPEC_PATH.read_bytes()
        # Git's blob identifier from the publicly read original file.
        blob = b"blob " + str(len(raw)).encode() + b"\0" + raw
        self.assertEqual(hashlib.sha1(blob).hexdigest(), "2279609fba99c4bdc4171c4ee6ff4bcda191a797")

    def test_day01_expected_policy(self):
        path = SPEC_PATH
        fixture = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            submit(self.store, self.request, confirmed=True, fault=Fault.AFTER_COMMIT),
            fixture["expected"],
        )

    def test_timeout_after_commit_really_did_write(self):
        result = submit(self.store, self.request, confirmed=True, fault=Fault.AFTER_COMMIT)
        self.assertFalse(result["claim_completed"])
        self.assertEqual(self.store.count(), 1)

    def test_timeout_before_write_looks_identical_but_did_not_write(self):
        result = submit(self.store, self.request, confirmed=True, fault=Fault.BEFORE_WRITE)
        self.assertEqual(result, pending_verification())
        self.assertEqual(self.store.count(), 0)

    def test_unconfirmed_request_does_not_write(self):
        result = submit(self.store, self.request, confirmed=False)
        self.assertEqual(result["reply_state"], "needs_confirmation")
        self.assertEqual(self.store.count(), 0)

    def test_string_true_is_not_confirmation(self):
        result = submit(self.store, self.request, confirmed="true")  # type: ignore[arg-type]
        self.assertEqual(result["reply_state"], "needs_confirmation")
        self.assertEqual(self.store.count(), 0)

    def test_same_key_retry_returns_same_receipt(self):
        first = submit(self.store, self.request, confirmed=True)
        second = submit(self.store, self.request, confirmed=True)
        self.assertEqual(first, second)
        self.assertEqual(self.store.count(), 1)

    def test_changed_payload_under_same_key_rejected(self):
        submit(self.store, self.request, confirmed=True)
        changed = demo_request(request_text="不同的請求內容")
        with self.assertRaises(IdempotencyConflict):
            submit(self.store, changed, confirmed=True)
        self.assertEqual(self.store.count(), 1)

    def test_reconcile_survives_reopening_database(self):
        submit(self.store, self.request, confirmed=True, fault=Fault.AFTER_COMMIT)
        reopened = Store(self.store.path)
        result = reconcile(reopened, self.request)
        self.assertEqual(result["reply_state"], "request_created")
        self.assertEqual(result["human_state"], "awaiting_acceptance")

    def test_missing_receipt_stays_pending(self):
        self.assertEqual(reconcile(self.store, self.request), pending_verification())

    def test_unavailable_lookup_stays_pending_even_if_row_exists(self):
        submit(self.store, self.request, confirmed=True)
        self.assertEqual(
            reconcile(self.store, self.request, lookup_unavailable=True),
            pending_verification(),
        )

    def test_other_user_cannot_lookup_fixture_users_receipt(self):
        submit(self.store, self.request, confirmed=True)
        self.assertEqual(
            reconcile(self.store, demo_request(user_id="synthetic-user-b")),
            pending_verification(),
        )

    def test_other_tenant_cannot_lookup_fixture_tenants_receipt(self):
        submit(self.store, self.request, confirmed=True)
        self.assertEqual(
            reconcile(self.store, demo_request(tenant_id="synthetic-town-b")),
            pending_verification(),
        )

    def test_empty_key_rejected(self):
        with self.assertRaises(ValueError):
            submit(self.store, demo_request(idempotency_key=""), confirmed=True)
        self.assertEqual(self.store.count(), 0)

    def test_concurrent_same_key_creates_one_row(self):
        def worker(_: int):
            return submit(Store(self.store.path), self.request, confirmed=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(worker, range(8)))
        self.assertEqual(len({r["request_id"] for r in receipts}), 1)
        self.assertEqual(self.store.count(), 1)

    def test_changed_payload_cannot_reconcile_existing_receipt(self):
        submit(self.store, self.request, confirmed=True)
        with self.assertRaises(IdempotencyConflict):
            reconcile(self.store, demo_request(service_id="different-service"))


    def test_request_content_is_really_persisted(self):
        submit(self.store, self.request, confirmed=True)
        row = Store(self.store.path).lookup(self.request)
        self.assertIsNotNone(row)
        self.assertEqual(row["service_id"], self.request.service_id)
        self.assertEqual(row["request_text"], self.request.request_text)

    def test_user_facing_receipt_excludes_request_text(self):
        receipt = submit(self.store, self.request, confirmed=True)
        self.assertNotIn("request_text", receipt)
        self.assertNotIn("user_id", receipt)
        self.assertNotIn("payload_hash", receipt)

    def test_invalid_fault_is_rejected_before_write(self):
        with self.assertRaises(ValueError):
            submit(self.store, self.request, confirmed=True, fault="after_commit")
        self.assertEqual(self.store.count(), 0)

    def test_non_string_field_is_rejected(self):
        with self.assertRaises(ValueError):
            submit(self.store, demo_request(service_id=123), confirmed=True)
        self.assertEqual(self.store.count(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
