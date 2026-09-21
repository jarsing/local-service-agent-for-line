"""Day 8 核心離線測試；預期結果固定寫入案例，不依實際回傳反推。"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from confirmation import ConfirmationStore, Identity, Operation, operation_fingerprint

T = datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)
OWNER = Identity("demo-user-a", "demo-session-a")

def sample() -> Operation:
    return Operation("draft-demo-1", 1, "demo-event-a", "catalog-v1",
                     "請問這場活動的集合地點在哪裡？",
                     {"name": "教學走讀", "time": "07:30~11:00"})

class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.store = ConfirmationStore()
        self.operation = sample()
        self.offer = self.issue()
    def issue(self, **kw):
        args = dict(owner=OWNER, operation=self.operation,
                    current_catalog_version="catalog-v1", data_status="adopted", now=T)
        args.update(kw)
        return self.store.issue(**args)
    def decide(self, **kw):
        args = dict(confirmation_id=self.offer["confirmation_id"], actor=OWNER,
                    current_operation=self.operation, current_catalog_version="catalog-v1",
                    data_status="adopted", permitted=True, approved=True,
                    now=T+timedelta(seconds=1))
        args.update(kw)
        return self.store.decide(**args)
    def test_confirmation_records_content_not_execution(self):
        r = self.decide()
        self.assertEqual(r["status"], "confirmation_recorded")
        self.assertFalse(r["execution_allowed"])
    def test_repeat_returns_same_receipt(self):
        a=self.decide(); b=self.decide()
        self.assertEqual(b["status"], "already_confirmed")
        self.assertEqual(a["receipt"], b["receipt"])
    def test_changed_catalog_invalidates_old_confirmation(self):
        self.assertEqual(self.decide(current_catalog_version="catalog-v2")["status"], "version_changed")
    def test_changed_text_requires_new_confirmation(self):
        d=replace(self.operation, request_text="請問停車位置？")
        self.assertEqual(self.decide(current_operation=d)["status"], "content_changed")
    def test_changed_displayed_time_is_content_change(self):
        d=replace(self.operation, displayed_event={"name":"教學走讀", "time":"08:00~11:00"})
        self.assertEqual(self.decide(current_operation=d)["status"], "content_changed")
    def test_draft_revision_is_part_of_fingerprint(self):
        self.assertEqual(self.decide(current_operation=replace(self.operation, revision=2))["status"], "content_changed")
    def test_event_identity_is_part_of_fingerprint(self):
        self.assertEqual(self.decide(current_operation=replace(self.operation, event_id="other"))["status"], "content_changed")
    def test_other_user_cannot_confirm_or_cancel(self):
        actor=Identity("demo-user-b",OWNER.session_id)
        self.assertEqual(self.decide(actor=actor)["status"], "wrong_actor")
        self.assertEqual(self.decide(actor=actor,approved=False)["status"], "wrong_actor")
        self.assertEqual(self.decide()["status"], "confirmation_recorded")
    def test_other_session_is_rejected(self):
        self.assertEqual(self.decide(actor=Identity(OWNER.user_id,"other"))["status"], "wrong_actor")
    def test_expiry_at_exact_boundary(self):
        self.assertEqual(self.decide(now=T+timedelta(seconds=300))["status"], "expired")
    def test_before_expiry(self):
        self.assertEqual(self.decide(now=T+timedelta(seconds=299))["status"], "confirmation_recorded")
    def test_revoked_permission_is_rechecked(self):
        self.assertEqual(self.decide(permitted=False)["status"], "not_authorized")
    def test_pending_source_cannot_be_confirmed(self):
        self.assertEqual(self.decide(data_status="pending_review")["status"], "data_pending")
    def test_pending_source_cannot_issue_offer(self):
        with self.assertRaises(ValueError): self.issue(data_status="pending_review")
    def test_cancelled_offer_stays_cancelled(self):
        self.assertEqual(self.decide(approved=False)["status"], "cancelled")
        self.assertEqual(self.decide()["status"], "cancelled")
    def test_reissued_offer_supersedes_previous(self):
        self.issue()
        self.assertEqual(self.decide()["status"], "superseded")
    def test_unknown_confirmation(self):
        self.assertEqual(self.decide(confirmation_id="missing")["status"], "not_found")
    def test_string_true_is_not_approval(self):
        with self.assertRaises(ValueError): self.decide(approved="true")
    def test_timezone_is_required(self):
        with self.assertRaises(ValueError): self.decide(now=datetime(2026,9,22))
    def test_time_before_issue(self):
        self.assertEqual(self.decide(now=T-timedelta(seconds=1))["status"], "clock_error")
    def test_issue_snapshot_is_not_mutable_from_return_value(self):
        self.offer["operation"]["displayed_event"]["time"]="23:00"
        self.assertEqual(self.decide()["status"], "confirmation_recorded")
    def test_changed_source_object_is_detected(self):
        self.operation.displayed_event["time"]="23:00"
        self.assertEqual(self.decide()["status"], "content_changed")
    def test_fingerprint_ignores_object_key_order_only(self):
        d=replace(self.operation, displayed_event={"time":"07:30~11:00","name":"教學走讀"})
        self.assertEqual(operation_fingerprint(d),operation_fingerprint(self.operation))
    def test_confirmed_receipt_does_not_survive_version_change_as_authorization(self):
        self.decide()
        r=self.decide(current_catalog_version="catalog-v2")
        self.assertEqual(r["status"],"version_changed")
        self.assertFalse(r["execution_allowed"])
    def test_wrong_action_is_not_issued(self):
        with self.assertRaises(ValueError): self.issue(operation=replace(self.operation,action="pay"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
