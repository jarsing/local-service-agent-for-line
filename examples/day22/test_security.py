"""Day 22 本機契約驗證；不呼叫 Google、LINE 或雲端 IAM。"""
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .circuit_breaker import Paused, SecurityStore, demo_policy


class FakeSender:
    def __init__(self, lose_first=False):
        self.receipts = {}
        self.calls = 0
        self.lose_first = lose_first

    def __call__(self, ticket):
        self.calls += 1
        key = ticket['retry_key']
        if key in self.receipts:
            receipt, payload = self.receipts[key]
            if payload != ticket['payload']:
                raise ValueError('RETRY_CONTENT_CHANGED')
        else:
            receipt = 'synthetic-accepted-' + str(len(self.receipts) + 1)
            self.receipts[key] = (receipt, ticket['payload'])
        if self.lose_first:
            self.lose_first = False
            raise TimeoutError('SYNTHETIC_ACK_LOST')
        return self.receipts[key][0]


class SecurityContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state.sqlite'
        self.now = 1000.0
        self.policy = demo_policy()
        self.store = SecurityStore(self.path, self.policy, clock=lambda: self.now)

    def serving(self):
        return self.store.set_mode('sample-operator', 'SERVING', 'demo')

    def pause(self):
        return self.store.set_mode('sample-operator', 'PAUSED', 'incident')

    def create(self, key='same-confirmation'):
        self.serving()
        return self.store.confirm('sample-user', key, 'service_inquiry',
                                  self.store.admit('sample-user'))

    def test_defaults_to_paused(self):
        with self.assertRaises(Paused):
            self.store.admit('sample-user')

    def test_only_operator_can_change_control(self):
        for subject in ('sample-user', 'sample-model', 'sample-deployer', 'sample-volunteer', 'unknown'):
            with self.subTest(subject=subject), self.assertRaises(PermissionError):
                self.store.set_mode(subject, 'SERVING', 'demo')

    def test_invalid_mode_and_reason_rejected(self):
        with self.assertRaises(ValueError):
            self.store.set_mode('sample-operator', 'anything', 'demo')
        with self.assertRaises(ValueError):
            self.store.set_mode('sample-operator', 'SERVING', 'raw private text')

    def test_pause_preserves_committed_rows_and_pending_outbox(self):
        self.create()
        before = (self.store.request_snapshot(), self.store.outbox_snapshot())
        self.pause()
        self.assertEqual(before, (self.store.request_snapshot(), self.store.outbox_snapshot()))

    def test_paused_new_confirmation_is_rejected(self):
        epoch = self.serving()
        self.pause()
        with self.assertRaises(Paused):
            self.store.confirm('sample-user', 'new', 'service_inquiry', epoch)
        self.assertEqual(self.store.request_snapshot(), [])
        self.assertEqual(self.store.outbox_snapshot(), [])

    def test_authorized_read_still_works_while_paused(self):
        row = self.create()
        self.pause()
        self.assertEqual(self.store.read('sample-user', row['request_id']), row)
        self.assertEqual(self.store.read('sample-volunteer', row['request_id']), row)

    def test_read_never_bypasses_owner_or_role(self):
        row = self.create()
        self.pause()
        for subject in ('sample-other', 'sample-operator', 'sample-deployer', 'sample-model', 'unknown'):
            with self.subTest(subject=subject), self.assertRaises(PermissionError):
                self.store.read(subject, row['request_id'])

    def test_same_key_replay_while_paused_returns_original(self):
        row = self.create()
        before = (self.store.request_snapshot(), self.store.outbox_snapshot())
        self.pause()
        replay = self.store.confirm('sample-user', 'same-confirmation', 'service_inquiry', 0)
        self.assertEqual(replay, row)
        self.assertEqual(before, (self.store.request_snapshot(), self.store.outbox_snapshot()))

    def test_same_key_different_contents_rejected_even_paused(self):
        self.create()
        self.pause()
        with self.assertRaises(ValueError):
            self.store.confirm('sample-user', 'same-confirmation', 'meal_inquiry', 0)

    def test_same_key_is_scoped_by_owner(self):
        row = self.create()
        other = self.store.confirm('sample-other', 'same-confirmation', 'service_inquiry',
                                   self.store.admit('sample-other'))
        self.assertNotEqual(row['request_id'], other['request_id'])

    def test_claim_and_resolve_are_blocked_while_paused(self):
        row = self.create()
        self.pause()
        with self.assertRaises(Paused):
            self.store.claim('sample-volunteer', row['request_id'], 1)
        self.serving()
        self.assertTrue(self.store.claim('sample-volunteer', row['request_id'], 1))
        before = self.store.request_snapshot()
        self.pause()
        with self.assertRaises(Paused):
            self.store.resolve('sample-volunteer', row['request_id'])
        self.assertEqual(before, self.store.request_snapshot())

    def test_reopen_database_does_not_reset_paused_state(self):
        row = self.create()
        self.pause()
        reopened = SecurityStore(self.path, self.policy)
        with self.assertRaises(Paused):
            reopened.admit('sample-user')
        self.assertEqual(reopened.read('sample-user', row['request_id']), row)

    def test_resume_itself_does_not_replay_anything(self):
        self.create()
        self.pause()
        before = (self.store.request_snapshot(), self.store.outbox_snapshot())
        self.serving()
        self.assertEqual(before, (self.store.request_snapshot(), self.store.outbox_snapshot()))

    def test_old_epoch_is_invalid_even_after_resume(self):
        old_epoch = self.serving()
        self.pause()
        self.serving()
        with self.assertRaisesRegex(Paused, 'CONTROL_EPOCH_CHANGED'):
            self.store.confirm('sample-user', 'late-model-result', 'service_inquiry', old_epoch)
        self.assertEqual(self.store.request_snapshot(), [])

    def test_noop_mode_write_does_not_bump_epoch(self):
        epoch = self.serving()
        self.assertEqual(self.serving(), epoch)

    def test_missing_control_state_fails_closed(self):
        self.serving()
        with self.store.transaction() as db:
            db.execute('DELETE FROM control')
        with self.assertRaises(Paused):
            self.store.admit('sample-user')

    def test_invalid_values_are_rejected(self):
        epoch = self.serving()
        for key, cat, ep in [('', 'service_inquiry', epoch), ('x', 'delete_all', epoch),
                              ('x', 'service_inquiry', True)]:
            with self.subTest(key=key, cat=cat, ep=ep), self.assertRaises(ValueError):
                self.store.confirm('sample-user', key, cat, ep)

    def test_request_and_outbox_rollback_together(self):
        epoch = self.serving()
        with self.store.connection() as db:
            db.execute("CREATE TRIGGER reject_outbox BEFORE INSERT ON outbox "
                       "BEGIN SELECT RAISE(ABORT,'INJECTED_OUTBOX_ERROR'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.confirm('sample-user', 'fails', 'service_inquiry', epoch)
        self.assertEqual(self.store.request_snapshot(), [])

    def test_concurrent_connections_create_one_request(self):
        epoch = self.serving()
        other = SecurityStore(self.path, self.policy)
        barrier = threading.Barrier(2)
        def confirm(store):
            barrier.wait(timeout=3)
            return store.confirm('sample-user', 'same', 'service_inquiry', epoch)['request_id']
        with ThreadPoolExecutor(2) as pool:
            a, b = pool.map(confirm, (self.store, other))
        self.assertEqual(a, b)
        self.assertEqual(len(self.store.request_snapshot()), 1)
        self.assertEqual(len(self.store.outbox_snapshot()), 1)

    def test_two_volunteers_claim_one_version(self):
        row = self.create()
        other = SecurityStore(self.path, self.policy)
        barrier = threading.Barrier(2)
        def claim(args):
            store, subject = args
            barrier.wait(timeout=3)
            return store.claim(subject, row['request_id'], 1)
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(claim, ((self.store, 'sample-volunteer'),
                                           (other, 'sample-second-volunteer'))))
        self.assertEqual(sorted(results), [False, True])

    def test_paused_dispatch_never_calls_sender(self):
        row = self.create()
        self.pause()
        sender = FakeSender()
        with self.assertRaises(Paused):
            self.store.dispatch('sample-worker', row['request_id'], sender)
        self.assertEqual(sender.calls, 0)

    def test_notification_acceptance_does_not_change_claim_version(self):
        row = self.create()
        before = self.store.request_snapshot()
        self.store.dispatch('sample-worker', row['request_id'], FakeSender())
        self.assertEqual(before, self.store.request_snapshot())

    def test_late_acceptance_after_pause_preserves_business_rows(self):
        row = self.create()
        before = self.store.request_snapshot()
        sender = FakeSender()
        def in_flight(ticket):
            self.pause()
            return sender(ticket)
        self.store.dispatch('sample-worker', row['request_id'], in_flight)
        self.assertEqual(before, self.store.request_snapshot())
        self.assertEqual(self.store.outbox_snapshot()[0]['status'], 'accepted')

    def test_accepted_notification_is_not_sent_again_after_resume(self):
        row = self.create()
        sender = FakeSender()
        first = self.store.dispatch('sample-worker', row['request_id'], sender)
        self.pause()
        self.serving()
        second = self.store.dispatch('sample-worker', row['request_id'], sender)
        self.assertEqual(first, second)
        self.assertEqual(sender.calls, 1)

    def test_uncertain_acceptance_uses_original_retry_key(self):
        row = self.create()
        sender = FakeSender(lose_first=True)
        with self.assertRaises(TimeoutError):
            self.store.dispatch('sample-worker', row['request_id'], sender)
        key = self.store.outbox_snapshot()[0]['retry_key']
        self.pause()
        self.serving()
        self.store.dispatch('sample-worker', row['request_id'], sender)
        self.assertEqual(key, self.store.outbox_snapshot()[0]['retry_key'])
        self.assertEqual(len(sender.receipts), 1)
        self.assertEqual(sender.calls, 2)

    def test_resume_does_not_extend_retry_window(self):
        row = self.create()
        sender = FakeSender(lose_first=True)
        with self.assertRaises(TimeoutError):
            self.store.dispatch('sample-worker', row['request_id'], sender)
        self.pause()
        self.now += 86400
        self.serving()
        with self.assertRaisesRegex(RuntimeError, 'RETRY_WINDOW_EXPIRED'):
            self.store.dispatch('sample-worker', row['request_id'], sender)
        self.assertEqual(sender.calls, 1)

    def test_only_claimant_can_resolve(self):
        row = self.create()
        self.store.claim('sample-volunteer', row['request_id'], 1)
        self.assertFalse(self.store.resolve('sample-second-volunteer', row['request_id']))
        self.assertTrue(self.store.resolve('sample-volunteer', row['request_id']))

    def test_notification_payload_has_only_required_fields(self):
        self.create()
        payload = json.loads(self.store.outbox_snapshot()[0]['payload'])
        self.assertEqual(set(payload), {'request_id', 'category', 'claim_version', 'label'})


if __name__ == '__main__':
    unittest.main()
