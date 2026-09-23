"""固定預期＋真實 SQLite；刻意製造錯誤時仍由同一套斷言判斷。"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from evidence import Trace, no_network, write_json
from fault import Fault, FaultTransport
from policy import pending_verification
from proof import EvidenceMismatch, check_case, check_adk_trace
from records import ReceiptReader, SendArgs, sqlite_rows
from reconcile import RecoveryController
from scenarios import prepare_case
from upstream import Actor, REPO, check_dependencies


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='local-day10-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 9, 24, 1, 0, tzinfo=timezone.utc)

    def case(self, name='after_commit', **kwargs):
        return prepare_case(name, self.root/name, clock=lambda: self.now, **kwargs)

    def step(self, c):
        return c.controller.execute(c.controller.next_tool, c.actor, c.args)

    def test_day01_bytes_remain_original(self):
        raw = (REPO/'docs/day01/handoff-timeout-001.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
            '9a4768046189e6ba0d42637953b8d73e41566f7c573ea0a76b32079b1a762218')
        self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),
            '2279609fba99c4bdc4171c4ee6ff4bcda191a797')

    def test_independent_policy_matches_day01(self):
        spec = json.loads((REPO/'docs/day01/handoff-timeout-001.json').read_text())
        self.assertEqual(pending_verification(), spec['expected'])
        c = self.case()
        result = self.step(c)
        self.assertEqual({k:result[k] for k in spec['expected']}, spec['expected'])

    def test_upstream_code_is_exactly_locked(self):
        self.assertTrue(check_dependencies())

    def test_baseline_one_insert_no_lookup(self):
        c = self.case('baseline')
        result = c.controller.run_to_boundary()
        self.assertEqual([x['status'] for x in result], ['request_created'])
        check_case(c, result)

    def test_after_commit_first_response_unknown_but_one_row_exists(self):
        c = self.case()
        result = self.step(c)
        self.assertEqual(result['status'], 'pending_verification')
        self.assertIsNone(result['request_created'])
        self.assertFalse(result['claim_completed'])
        self.assertNotIn('request_id', result)
        self.assertEqual(len(sqlite_rows(c.db_path)), 1)

    def test_before_write_same_unknown_response_but_zero_rows(self):
        a = self.case('after_commit'); b = self.case('before_write')
        self.assertEqual(self.step(a), self.step(b))
        self.assertEqual(len(sqlite_rows(a.db_path)), 1)
        self.assertEqual(len(sqlite_rows(b.db_path)), 0)

    def test_after_commit_lookup_returns_original_id_without_second_create(self):
        c = self.case()
        a = self.step(c); original = sqlite_rows(c.db_path)[0]
        b = self.step(c)
        self.assertEqual(b['status'], 'already_created')
        self.assertEqual(b['request_id'], original['request_id'])
        self.assertEqual(c.transport.create_calls, 1)
        check_case(c, [a,b])

    def test_before_write_lookup_miss_then_same_key_retry_creates_once(self):
        c = self.case('before_write')
        a = self.step(c); b = self.step(c)
        self.assertEqual(b['observation'], 'not_found')
        self.assertEqual(sqlite_rows(c.db_path), [])
        last = self.step(c)
        self.assertEqual(last['status'], 'request_created')
        check_case(c, [a,b,last])

    def test_lookup_unavailable_keeps_unknown_despite_existing_row(self):
        c = self.case('lookup_unavailable')
        results = c.controller.run_to_boundary()
        self.assertEqual(results[-1]['observation'], 'lookup_unavailable')
        self.assertIsNone(c.controller.next_tool)
        check_case(c, results)

    def test_missing_lookup_is_read_only_including_file_hash(self):
        c = self.case('before_write'); self.step(c)
        before = c.db_path.read_bytes()
        r = c.transport.reader.lookup(c.actor, c.args)
        self.assertEqual(r['observation'], 'not_found')
        self.assertEqual(before, c.db_path.read_bytes())
        self.assertEqual(c.transport.create_calls, 1)

    def test_found_lookup_is_read_only_including_file_hash(self):
        c = self.case(); self.step(c)
        before = c.db_path.read_bytes()
        r = c.transport.reader.lookup(c.actor, c.args)
        self.assertEqual(r['status'], 'already_created')
        self.assertEqual(before, c.db_path.read_bytes())

    def test_bad_lookup_path_does_not_create_empty_database(self):
        c = self.case(); path = self.root/'missing.sqlite3'
        reader = ReceiptReader(path, lambda a: True)
        self.assertEqual(reader.lookup(c.actor,c.args)['observation'], 'lookup_unavailable')
        self.assertFalse(path.exists())

    def test_lookup_schema_error_is_not_silently_treated_as_not_found(self):
        path = self.root/'bad.sqlite3'
        with sqlite3.connect(path) as conn: conn.execute('CREATE TABLE unrelated (id INTEGER)')
        c = self.case()
        with self.assertRaises(sqlite3.OperationalError):
            ReceiptReader(path,lambda a: True).lookup(c.actor,c.args)

    def test_lookup_busy_is_unknown_not_permission_to_retry(self):
        c = self.case(); self.step(c)
        conn = sqlite3.connect(c.db_path, isolation_level=None)
        try:
            conn.execute('BEGIN EXCLUSIVE')
            result = self.step(c)
        finally:
            conn.rollback(); conn.close()
        self.assertEqual(result['observation'], 'lookup_unavailable')
        self.assertEqual(c.transport.create_calls, 1)
        self.assertIsNone(c.controller.next_tool)

    def test_current_permission_is_rechecked_for_lookup(self):
        permission = [True]
        c = self.case(permitted=lambda a: permission[0]); self.step(c)
        permission[0] = False
        self.assertEqual(self.step(c)['status'],'not_authorized')
        self.assertEqual(c.transport.create_calls, 1)

    def test_current_permission_is_rechecked_for_retry(self):
        permission = [True]
        c = self.case('before_write', permitted=lambda a: permission[0])
        self.step(c); self.step(c); permission[0] = False
        self.assertEqual(self.step(c)['status'], 'not_authorized')
        self.assertEqual(sqlite_rows(c.db_path), [])

    def test_permission_must_be_true_not_truthy_text(self):
        c = self.case()
        reader = ReceiptReader(c.db_path, lambda a: 'true')
        self.assertEqual(reader.lookup(c.actor,c.args)['status'], 'not_authorized')

    def test_unconfirmed_is_not_implicitly_approved(self):
        c = self.case('baseline', confirmed=False)
        self.assertEqual(self.step(c)['status'], 'unconfirmed_operation')
        self.assertEqual(sqlite_rows(c.db_path), [])
        self.assertNotEqual(c.gateway.record_status(c.actor,c.args.confirmation_id), 'confirmation_recorded')

    def test_receipt_after_confirmation_expiry_is_still_read_only(self):
        c = self.case(); self.step(c)
        original = sqlite_rows(c.db_path)[0]
        self.now += timedelta(seconds=301)
        self.assertEqual(self.step(c)['request_id'], original['request_id'])
        self.assertEqual(sqlite_rows(c.db_path), [original])

    def test_first_write_after_expiry_is_rejected(self):
        c = self.case('before_write'); self.step(c); self.step(c)
        self.now += timedelta(seconds=300)
        self.assertEqual(self.step(c)['status'], 'expired')
        self.assertEqual(sqlite_rows(c.db_path), [])

    def test_first_write_rechecks_catalog_version(self):
        c = self.case('before_write'); self.step(c); self.step(c)
        c.gateway.switch_catalog('v1')
        self.assertEqual(self.step(c)['status'], 'version_changed')
        self.assertEqual(sqlite_rows(c.db_path), [])

    def test_existing_receipt_does_not_replace_old_content_with_new_catalog(self):
        c = self.case(); self.step(c); original = sqlite_rows(c.db_path)[0]
        c.gateway.switch_catalog('v1')
        self.assertEqual(self.step(c)['request_id'], original['request_id'])
        self.assertEqual(sqlite_rows(c.db_path), [original])

    def test_first_write_rechecks_current_draft(self):
        c = self.case('before_write'); self.step(c); self.step(c)
        c.gateway.change_draft_text(c.actor,c.args.confirmation_id,'請問停車位置？')
        self.assertEqual(self.step(c)['status'], 'content_mismatch')
        self.assertEqual(sqlite_rows(c.db_path), [])

    def test_lookup_checks_session(self):
        c = self.case(); self.step(c)
        other = replace(c.actor, session_id='different')
        reader = ReceiptReader(c.db_path,lambda a: True)
        self.assertEqual(reader.lookup(other,c.args)['status'],'wrong_actor')

    def test_lookup_cannot_read_another_users_row(self):
        c = self.case(); self.step(c)
        reader = ReceiptReader(c.db_path,lambda a: True)
        result = reader.lookup(replace(c.actor,user_id='someone-else'),c.args)
        self.assertEqual(result['observation'], 'not_found')
        self.assertNotIn('request_id',result)

    def test_lookup_cannot_read_another_tenants_row(self):
        c = self.case(); self.step(c)
        result = ReceiptReader(c.db_path,lambda a: True).lookup(replace(c.actor,tenant_id='other'),c.args)
        self.assertEqual(result['observation'], 'not_found')
        self.assertNotIn('request_id',result)

    def test_same_key_changed_text_conflicts_at_read_only_lookup(self):
        c = self.case(); self.step(c)
        original = sqlite_rows(c.db_path)
        r = c.transport.reader.lookup(c.actor,replace(c.args,request_text='另一個問題'))
        self.assertEqual(r['status'],'idempotency_conflict')
        self.assertEqual(sqlite_rows(c.db_path),original)

    def test_changed_confirmation_does_not_read_original_receipt(self):
        c = self.case(); self.step(c)
        self.assertEqual(c.transport.reader.lookup(c.actor,replace(c.args,confirmation_id='other'))['status'],
                         'idempotency_conflict')

    def test_changed_event_does_not_read_original_receipt(self):
        c = self.case(); self.step(c)
        self.assertEqual(c.transport.reader.lookup(c.actor,replace(c.args,event_id='other'))['status'],
                         'idempotency_conflict')

    def test_whitespace_is_not_silently_normalized(self):
        c = self.case(); self.step(c)
        self.assertEqual(c.transport.reader.lookup(c.actor,replace(c.args,request_text=c.args.request_text+' '))['status'],
                         'idempotency_conflict')

    def test_sql_text_in_key_is_a_literal_not_query(self):
        c = self.case(); self.step(c)
        r = c.transport.reader.lookup(c.actor,replace(c.args,idempotency_key="' OR 1=1 --"))
        self.assertEqual(r['observation'],'not_found')

    def test_invalid_arguments_are_rejected_before_lookup(self):
        c = self.case()
        for changed in (replace(c.args,idempotency_key=''), replace(c.args,request_text='x'*2001)):
            self.assertEqual(c.transport.reader.lookup(c.actor,changed)['status'],'invalid_arguments')

    def test_controller_refuses_swapped_actor(self):
        c = self.case()
        r = c.controller.execute(c.controller.next_tool,replace(c.actor,session_id='other'),c.args)
        self.assertEqual(r['status'],'wrong_actor')
        self.assertEqual(c.transport.create_calls,0)

    def test_controller_refuses_model_generated_key(self):
        c = self.case()
        r = c.controller.execute(c.controller.next_tool,c.actor,replace(c.args,idempotency_key='new-key'))
        self.assertEqual(r['status'],'operation_binding_mismatch')
        self.assertEqual(c.transport.create_calls,0)

    def test_model_cannot_skip_lookup_and_retry_directly(self):
        c = self.case(); self.step(c)
        r = c.controller.execute('create_handoff_request',c.actor,c.args)
        self.assertEqual(r['status'],'sequence_rejected')
        self.assertEqual(c.transport.create_calls,1)

    def test_completed_controller_rejects_further_calls(self):
        c = self.case(); c.controller.run_to_boundary()
        r = c.controller.execute('create_handoff_request',c.actor,c.args)
        self.assertEqual(r['status'],'sequence_rejected')
        self.assertEqual(c.transport.create_calls,1)

    def test_retry_race_finds_original_row_instead_of_creating_another(self):
        c = self.case('before_write'); self.step(c); self.step(c)
        # SELECT 的空結果後，另一個送出者先完成相同操作。
        earlier = c.service.create(actor=c.actor,**c.args.tool_args())
        r = self.step(c)
        self.assertEqual(r['status'],'already_created')
        self.assertEqual(r['request_id'], earlier['request_id'])
        self.assertEqual(len(sqlite_rows(c.db_path)),1)

    def test_repeated_timeout_stops_after_one_retry(self):
        c = self.case('before_write'); c.transport.repeat_fault=True
        results = c.controller.run_to_boundary()
        self.assertEqual(len(results),3)
        self.assertEqual(results[-1]['status'],'pending_verification')
        self.assertEqual(c.transport.create_calls,2)
        self.assertIsNone(c.controller.next_tool)
        self.assertEqual(sqlite_rows(c.db_path),[])

    def test_day08_execution_allowed_remains_false(self):
        c = self.case(); c.controller.run_to_boundary()
        self.assertIs(c.confirmation['execution_allowed'], False)

    def test_fault_configuration_is_not_exposed_in_pending_receipt(self):
        c = self.case(); r = self.step(c)
        self.assertNotIn('after_commit',json.dumps(r))
        self.assertNotIn('request_id',r)
        self.assertTrue(any(e['kind']=='BACKEND_RETURNED' for e in c.trace.events))

    def test_programming_error_is_not_converted_to_success_or_not_found(self):
        c = self.case('baseline')
        with patch.object(c.service,'create',side_effect=ValueError('programming error')):
            with self.assertRaises(ValueError): self.step(c)

    def test_regression_mutated_lookup_key_is_caught_by_real_assertions(self):
        c = self.case()
        original = c.transport.lookup
        # 隔離注入「查回時亂換鍵」的退步，沒有改正式核心或另造同意。
        c.transport.lookup = lambda actor,args: original(actor,replace(args,idempotency_key='wrong-key'))
        results = c.controller.run_to_boundary()
        self.assertEqual(len(sqlite_rows(c.db_path)),1)
        with self.assertRaises(EvidenceMismatch): check_case(c,results)

    def test_proof_rejects_model_text_without_any_tool_events(self):
        c = self.case()
        with self.assertRaises(EvidenceMismatch):
            check_adk_trace([{'kind':'ADK_VISIBLE_EVENT','text':'成功，單號ABC'}],c.args)

    def test_events_are_defensive_copies(self):
        trace = Trace(); value={'a':1}; trace.emit('TEST',value=value); value['a']=2
        self.assertEqual(trace.events[0]['value'],{'a':1})

    def test_original_json_is_not_overwritten(self):
        path=self.root/'record.json'; write_json(path,{'value':1})
        with self.assertRaises(FileExistsError): write_json(path,{'value':2})
        self.assertEqual(json.loads(path.read_text()),{'value':1})

    def test_network_guard_blocks_connect_and_dns(self):
        import socket
        with no_network():
            with self.assertRaisesRegex(RuntimeError,'OFFLINE_NETWORK_BLOCKED'):
                socket.getaddrinfo('example.com',443)

    def test_no_human_acceptance_is_fabricated(self):
        c = self.case(); results=c.controller.run_to_boundary()
        self.assertTrue(all(r['human_claimed'] is False for r in results))
        self.assertEqual(results[-1]['delivery'],'local_sqlite_only')


if __name__ == '__main__':
    unittest.main(verbosity=2)
