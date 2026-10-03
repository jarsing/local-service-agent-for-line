"""Isolated tests of the additive SQLite example; never call LINE."""
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .inbox_contract import Inbox, FakeSender


class Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'test.sqlite'
        self.clock = [100.0]
        self.inbox = Inbox(self.path, lambda: self.clock[0])
        self.inbox.set_volunteer('a'); self.inbox.set_volunteer('b')
        self.inbox.register_confirmed('fixture-id', 'owner', 'meal', 'staff')

    def tearDown(self):
        self.tmp.cleanup()

    def test_repeated_projection_does_not_duplicate(self):
        self.inbox.register_confirmed('fixture-id','owner','meal','staff')
        self.assertEqual(len(self.inbox.list_for_volunteer('a')),1)

    def test_same_id_changed_owner_is_rejected(self):
        with self.assertRaises(ValueError):
            self.inbox.register_confirmed('fixture-id','someone-else','meal','staff')

    def test_api_acceptance_is_not_claim(self):
        self.inbox.dispatch('fixture-id',FakeSender())
        self.assertEqual(self.inbox.user_status('fixture-id','owner')['state'],'notification_accepted')

    def test_claim_version_survives_notification(self):
        version=json.loads(self.inbox.notification('fixture-id')['payload'])['claim_version']
        self.inbox.dispatch('fixture-id',FakeSender())
        self.assertTrue(self.inbox.claim('fixture-id','a',version))

    def test_two_database_connections_only_one_claim(self):
        barrier=threading.Barrier(2)
        def run(name):
            store=Inbox(self.path)
            barrier.wait(timeout=3)
            return store.claim('fixture-id',name,1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(run,['a','b']))
        self.assertEqual(sorted(outcomes),[False,True])

    def test_late_acceptance_does_not_overwrite_claim(self):
        self.inbox.claim('fixture-id','a',1)
        self.inbox.dispatch('fixture-id',FakeSender())
        self.assertEqual(self.inbox.user_status('fixture-id','owner')['state'],'human_claimed')

    def test_stale_card_is_rejected(self):
        self.inbox.claim('fixture-id','a',1)
        self.assertFalse(self.inbox.claim('fixture-id','b',1))

    def test_unknown_volunteer_is_rejected(self):
        with self.assertRaises(PermissionError):self.inbox.claim('fixture-id','x',1)

    def test_revoked_handler_cannot_resolve(self):
        self.inbox.claim('fixture-id','a',1)
        self.inbox.set_volunteer('a',False)
        with self.assertRaises(PermissionError):self.inbox.resolve('fixture-id','a')

    def test_other_owner_cannot_read(self):
        with self.assertRaises(PermissionError):self.inbox.user_status('fixture-id','other')

    def test_no_raw_query_or_volunteer_in_user_projection(self):
        self.inbox.claim('fixture-id','a',1)
        self.assertEqual(set(self.inbox.user_status('fixture-id','owner')),
                         {'request_id','state','updated_at'})
        self.assertNotIn('raw_query',self.inbox.notification('fixture-id')['payload'])

    def test_restart_preserves_key_and_state(self):
        key=self.inbox.notification('fixture-id')['retry_key']
        other=Inbox(self.path)
        self.assertEqual(other.notification('fixture-id')['retry_key'],key)
        self.assertEqual(other.user_status('fixture-id','owner')['state'],'request_created')

    def test_timeout_is_unknown_not_delivered(self):
        def fail(row):raise TimeoutError('synthetic')
        with self.assertRaises(TimeoutError):self.inbox.dispatch('fixture-id',fail)
        self.assertEqual(self.inbox.notification('fixture-id')['status'],'unknown')
        self.assertEqual(self.inbox.user_status('fixture-id','owner')['state'],'request_created')

    def test_retry_after_lost_ack_keeps_key(self):
        fake=FakeSender()
        def lost(row):fake(row);raise TimeoutError('synthetic_lost_ack')
        with self.assertRaises(TimeoutError):self.inbox.dispatch('fixture-id',lost)
        key=self.inbox.notification('fixture-id')['retry_key']
        self.inbox.dispatch('fixture-id',fake)
        self.assertEqual(len(fake.accepted),1)
        self.assertEqual(self.inbox.notification('fixture-id')['retry_key'],key)
        self.assertEqual(fake.attempts,2)

    def test_expired_retry_window_requires_reconciliation(self):
        def fail(row):raise TimeoutError()
        with self.assertRaises(TimeoutError):self.inbox.dispatch('fixture-id',fail)
        self.clock[0]+=86401
        with self.assertRaises(RuntimeError):self.inbox.dispatch('fixture-id',FakeSender())

    def test_accepted_local_record_skips_next_send(self):
        fake=FakeSender()
        one=self.inbox.dispatch('fixture-id',fake)
        self.assertEqual(self.inbox.dispatch('fixture-id',fake),one)
        self.assertEqual(fake.attempts,1)

    def test_resolution_is_only_handler_declaration(self):
        self.inbox.claim('fixture-id','a',1)
        self.assertFalse(self.inbox.resolve('fixture-id','b'))
        self.assertTrue(self.inbox.resolve('fixture-id','a'))
        self.assertFalse(self.inbox.resolve('fixture-id','a'))
        self.assertEqual(self.inbox.user_status('fixture-id','owner')['state'],'resolved')

    def test_boolean_version_is_not_an_integer_version(self):
        with self.assertRaises(ValueError):self.inbox.claim('fixture-id','a',True)

if __name__=='__main__':unittest.main()
