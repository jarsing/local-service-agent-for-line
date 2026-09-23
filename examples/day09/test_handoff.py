"""固定預期的離線回歸；實際讀寫暫存 SQLite，不呼叫模型。"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest
from day08_gateway import Actor, Day08Gateway
from handoff import HandoffService
from demo import tool_args, run_core_demo

class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'db.sqlite3'
        self.now=datetime(2026,9,23,1,0,tzinfo=timezone.utc)
        self.clock=lambda:self.now
        self.actor=Actor('tenant-A','user-A','session-A')
        self.gateway=Day08Gateway(self.clock)
        self.allow=True
        self.service=HandoffService(self.path,self.gateway,lambda a:self.allow,self.clock)
        self.offer=self.gateway.prepare(self.actor,'請問集合地點？')
        self.args=tool_args(self.offer)
        self.receipt=self.gateway.record_user_decision(self.actor,self.offer['confirmation_id'],approved=True)

    def call(self, **kw):
        return self.service.create(actor=kw.pop('actor',self.actor),**{**self.args,**kw})

    def test_first_creation_persists_pending_human_request(self):
        r=self.call()
        self.assertEqual(r['status'],'request_created')
        self.assertEqual(r['request']['status'],'pending_human_review')
        self.assertFalse(r['human_claimed'])
        self.assertEqual(self.service.count(),1)
        self.assertEqual(self.service.inspect_rows()[0]['request_id'],r['request_id'])

    def test_replay_returns_same_request_without_insert(self):
        a=self.call();b=self.call()
        self.assertEqual(b['status'],'already_created')
        self.assertEqual(a['request'],b['request'])
        self.assertEqual(self.service.count(),1)

    def test_same_key_changed_text_conflicts_and_preserves_row(self):
        a=self.call();before=self.service.inspect_rows()
        b=self.call(request_text='請問停車位置？')
        self.assertEqual(b['status'],'idempotency_conflict')
        self.assertEqual(before,self.service.inspect_rows())

    def test_same_key_changed_event_conflicts(self):
        self.call()
        self.assertEqual(self.call(event_id='other-event')['status'],'idempotency_conflict')

    def test_same_key_changed_confirmation_conflicts(self):
        self.call()
        self.assertEqual(self.call(confirmation_id='another-id')['status'],'idempotency_conflict')

    def test_unconfirmed_is_not_implicitly_approved(self):
        offer=self.gateway.prepare(self.actor,'尚未同意的問題')
        r=self.service.create(actor=self.actor,**tool_args(offer))
        self.assertEqual(r['status'],'unconfirmed_operation')
        self.assertEqual(self.service.count(),0)
        self.assertEqual(self.gateway.record_status(self.actor,offer['confirmation_id']),'awaiting_confirmation')

    def test_missing_confirmation_rejected(self):
        self.assertEqual(self.call(confirmation_id='')['status'],'unconfirmed_operation')
        self.assertEqual(self.service.count(),0)

    def test_unknown_confirmation_rejected(self):
        self.assertEqual(self.call(confirmation_id='invented')['status'],'unconfirmed_operation')

    def test_receipt_does_not_grant_execution(self):
        self.assertFalse(self.receipt['execution_allowed'])
        self.assertEqual(self.call()['status'],'request_created')
        self.assertFalse(self.receipt['execution_allowed'])

    def test_permission_rechecked_for_creation(self):
        self.allow=False
        self.assertEqual(self.call()['status'],'not_authorized')
        self.assertEqual(self.service.count(),0)

    def test_permission_rechecked_for_receipt_lookup(self):
        self.call();self.allow=False
        r=self.call()
        self.assertEqual(r['status'],'not_authorized')
        self.assertNotIn('request_id',r)

    def test_exact_expiry_blocks_first_insert(self):
        self.now+=timedelta(seconds=300)
        self.assertEqual(self.call()['status'],'expired')
        self.assertEqual(self.service.count(),0)

    def test_one_second_before_expiry_allows_insert(self):
        self.now+=timedelta(seconds=299)
        self.assertEqual(self.call()['status'],'request_created')

    def test_committed_replay_after_expiry_is_read_only(self):
        a=self.call();self.now+=timedelta(seconds=301)
        b=self.call()
        self.assertEqual(b['status'],'already_created')
        self.assertEqual(a['request_id'],b['request_id'])
        self.assertEqual(self.service.count(),1)

    def test_catalog_change_before_creation_requires_confirmation(self):
        self.gateway.switch_catalog('v1')
        self.assertEqual(self.call()['status'],'version_changed')
        self.assertEqual(self.service.count(),0)

    def test_committed_receipt_survives_later_catalog_change(self):
        a=self.call();self.gateway.switch_catalog('v1');b=self.call()
        self.assertEqual(b['status'],'already_created')
        self.assertEqual(a['request'],b['request'])

    def test_model_cannot_change_confirmed_text(self):
        self.assertEqual(self.call(request_text='改成取消活動')['status'],'content_mismatch')
        self.assertEqual(self.service.count(),0)

    def test_current_server_draft_change_is_detected(self):
        self.gateway.change_draft_text(self.actor,self.offer['confirmation_id'],'請問停車位置？')
        self.assertEqual(self.call(request_text='請問停車位置？')['status'],'content_changed')
        self.assertEqual(self.service.count(),0)

    def test_forged_key_cannot_start_another_submission(self):
        self.assertEqual(self.call(idempotency_key='made-up-key')['status'],'invalid_idempotency_key')
        self.assertEqual(self.service.count(),0)

    def test_new_key_after_creation_still_creates_no_second_row(self):
        self.call()
        r=self.call(idempotency_key='second-key')
        self.assertEqual(r['status'],'invalid_idempotency_key')
        self.assertEqual(self.service.count(),1)

    def test_wrong_user_cannot_create_or_read_receipt(self):
        self.call()
        other=Actor(self.actor.tenant_id,'other',self.actor.session_id)
        r=self.call(actor=other)
        self.assertEqual(r['status'],'unconfirmed_operation')
        self.assertNotIn('request_id',r)
        self.assertEqual(self.service.count(),1)

    def test_wrong_session_cannot_read_existing_receipt(self):
        self.call()
        other=Actor(self.actor.tenant_id,self.actor.user_id,'other-session')
        self.assertEqual(self.call(actor=other)['status'],'wrong_actor')

    def test_tenants_can_have_same_key_without_cross_talk(self):
        a=self.call()
        other=Actor('tenant-B',self.actor.user_id,self.actor.session_id)
        offer=self.gateway.prepare(other,'B的問題',idempotency_key=self.args['idempotency_key'])
        self.gateway.record_user_decision(other,offer['confirmation_id'],approved=True)
        b=self.service.create(actor=other,**tool_args(offer))
        self.assertEqual(b['status'],'request_created')
        self.assertNotEqual(a['request_id'],b['request_id'])
        self.assertEqual(self.service.count(),2)

    def test_users_can_have_same_key_without_cross_talk(self):
        self.call()
        other=Actor(self.actor.tenant_id,'user-B',self.actor.session_id)
        offer=self.gateway.prepare(other,'B的問題',idempotency_key=self.args['idempotency_key'])
        self.gateway.record_user_decision(other,offer['confirmation_id'],approved=True)
        b=self.service.create(actor=other,**tool_args(offer))
        self.assertEqual(b['status'],'request_created')
        self.assertEqual(self.service.count(),2)

    def test_cancelled_confirmation_cannot_create(self):
        offer=self.gateway.prepare(self.actor,'取消的問題')
        self.gateway.record_user_decision(self.actor,offer['confirmation_id'],approved=False)
        r=self.service.create(actor=self.actor,**tool_args(offer))
        self.assertEqual(r['status'],'unconfirmed_operation')

    def test_snapshot_of_content_is_stored_in_database(self):
        self.call()
        row=self.service.inspect_rows()[0]
        self.assertIn('請問集合地點',row['operation_json'])
        self.assertEqual(row['operation_fingerprint'],self.receipt['receipt']['operation_fingerprint'])

    def test_service_reopen_can_read_existing_receipt_without_gateway_state(self):
        a=self.call()
        reopened=HandoffService(self.path,Day08Gateway(self.clock),lambda a:True,self.clock)
        b=reopened.create(actor=self.actor,**self.args)
        self.assertEqual(b['status'],'already_created')
        self.assertEqual(a['request_id'],b['request_id'])
        self.assertEqual(reopened.count(),1)

    def test_reopen_does_not_reconstruct_unexecuted_confirmation(self):
        reopened=HandoffService(self.path,Day08Gateway(self.clock),lambda a:True,self.clock)
        self.assertEqual(reopened.create(actor=self.actor,**self.args)['status'],'unconfirmed_operation')

    def test_concurrent_same_key_commits_one_request(self):
        barrier=Barrier(6)
        def submit(_):
            barrier.wait(timeout=5)
            return self.call()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(submit,range(6)))
        self.assertEqual(sum(r['status']=='request_created' for r in results),1)
        self.assertEqual(sum(r['status']=='already_created' for r in results),5)
        self.assertEqual(len({r['request_id'] for r in results}),1)
        self.assertEqual(self.service.count(),1)

    def test_sql_quoted_text_is_literal_data(self):
        text="集合在哪？'); DROP TABLE handoff_requests; --"
        offer=self.gateway.prepare(self.actor,text)
        self.gateway.record_user_decision(self.actor,offer['confirmation_id'],approved=True)
        r=self.service.create(actor=self.actor,**tool_args(offer))
        self.assertEqual(r['request']['request_text'],text)
        self.assertEqual(self.service.count(),1)

    def test_database_unique_constraint_rejects_duplicate_key(self):
        self.call()
        with self.service.connection() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO handoff_requests SELECT 'other-request',tenant_id,user_id,session_id,idempotency_key,confirmation_id,request_text,event_id,payload_hash,operation_fingerprint,catalog_version,operation_json,status,created_at FROM handoff_requests")
        self.assertEqual(self.service.count(),1)

    def test_demo_returns_expected_contrast_from_real_databases(self):
        out=Path(self.temp.name)/'demo';out.mkdir()
        result=run_core_demo(out,'assistant_check')
        self.assertTrue(result['success'])
        self.assertEqual((result['naive_count'],result['final_count']),(2,1))


    def test_permission_must_be_explicit_boolean_true(self):
        other_service = HandoffService(self.path, self.gateway, lambda a: "true", self.clock)
        result = other_service.create(actor=self.actor, **self.args)
        self.assertEqual(result["status"], "not_authorized")
        self.assertEqual(other_service.count(), 0)

    def test_invalid_arguments_leave_no_rows(self):
        for patch in ({"request_text": ""}, {"request_text": "x" * 2001},
                      {"event_id": None}, {"idempotency_key": False}):
            with self.subTest(patch=patch):
                self.assertEqual(self.call(**patch)["status"], "invalid_arguments")
        self.assertEqual(self.service.count(), 0)

    def test_newer_draft_does_not_reuse_old_confirmed_content(self):
        draft_id = self.offer["operation"]["draft_id"]
        newer = self.gateway.prepare(self.actor, "請問停車位置？", draft_id=draft_id)
        self.gateway.record_user_decision(self.actor, newer["confirmation_id"], approved=True)
        self.assertEqual(self.call(request_text="請問停車位置？")["status"], "content_changed")
        self.assertEqual(self.service.count(), 0)

    def test_new_confirmed_intent_with_same_words_can_create_a_new_request(self):
        first = self.call()
        new_offer = self.gateway.prepare(self.actor, self.args["request_text"])
        self.gateway.record_user_decision(self.actor, new_offer["confirmation_id"], approved=True)
        second = self.service.create(actor=self.actor, **tool_args(new_offer))
        self.assertEqual(second["status"], "request_created")
        self.assertNotEqual(first["request_id"], second["request_id"])
        self.assertEqual(self.service.count(), 2)

    def test_new_connection_reads_exact_committed_request(self):
        first = self.call()
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            stored = dict(conn.execute("SELECT * FROM handoff_requests").fetchone())
        for field, value in first["request"].items():
            self.assertEqual(stored[field], value)

    def test_pending_catalog_blocks_new_creation(self):
        with self.gateway.lock:
            self.gateway.catalog["data_status"] = "pending_review"
        self.assertEqual(self.call()["status"], "data_pending")
        self.assertEqual(self.service.count(), 0)

if __name__=='__main__':
    unittest.main(verbosity=2)
