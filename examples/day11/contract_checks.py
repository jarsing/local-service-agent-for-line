"""共用的業務契約；由 SQLite 測試 adapter 或真正模擬器套用同一組檢查。"""
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
import json
from domain import (SendArgs,key,operation_id,confirmation_key,grant_key,catalog_key,draft_key,
                    session_key,ContractError,pending)
from fixtures import ACTOR,sample_operation,seed_authority
from service import HandoffService
from jobs import RecoveryWorker
from upstream import Actor,ConfirmationStore,Operation,operation_fingerprint
from store import StoreUnavailable


class ContractChecks:
    def init_contract(self):
        self.actor=ACTOR;self.op=sample_operation()
        self.now=datetime(2026,9,25,0,0,tzinfo=timezone.utc)
        self.clock=lambda:self.now
        seed_authority(self.store,self.actor,self.op)
        self.service=HandoffService(self.store,clock=self.clock)
        self.args=self.service.prepare(self.actor,self.op,approved=True)
        self.oid=operation_id(self.actor,self.args)
        self.cid=confirmation_key(self.actor,self.args)
        self.worker=RecoveryWorker(self.service,clock=self.clock)

    def alter(self,kind,ident,changes):
        def fn(tx):
            value=tx.get(kind,ident);value.update(changes);tx.put(kind,ident,value)
        self.store.atomic(fn)
    def requests(self):return self.store.inspect().get('requests',{})
    def state(self):return self.store.inspect()['jobs'][self.oid]
    def write(self,args=None,actor=None):return self.service.create(actor or self.actor,args or self.args)

    def test_normal_create_and_repeat_same_receipt(self):
        a=self.write();b=self.write()
        self.assertEqual((a['status'],b['status']),('request_created','already_created'))
        self.assertEqual(a['request_id'],b['request_id']);self.assertEqual(len(self.requests()),1)
        self.assertIs(b['request_created'],False)
    def test_lookup_is_read_only_and_has_original_content(self):
        a=self.write();before=self.store.inspect()
        b=self.service.lookup(self.actor,self.args)
        self.assertEqual(a['request_id'],b['request_id']);self.assertEqual(before,self.store.inspect())
        self.assertEqual(b['request']['request_text'],self.op.request_text)
    def test_lookup_miss_is_unknown_not_failure(self):
        b=self.service.lookup(self.actor,self.args)
        self.assertEqual(b['observation'],'not_found');self.assertIsNone(b['request_created'])
        self.assertNotIn('request_id',b);self.assertEqual(len(self.requests()),0)
    def test_current_permission_rechecked_for_create(self):
        self.alter('grants',grant_key(self.actor),{'allowed':False})
        self.assertEqual(self.write()['status'],'not_authorized');self.assertEqual(len(self.requests()),0)
    def test_current_permission_rechecked_for_receipt(self):
        self.write();self.alter('grants',grant_key(self.actor),{'allowed':False})
        b=self.service.lookup(self.actor,self.args)
        self.assertEqual(b['status'],'not_authorized');self.assertNotIn('request_id',b)
    def test_session_not_an_identity_bypass(self):
        other=replace(self.actor,session_id='other-session')
        self.assertEqual(self.write(actor=other)['status'],'wrong_actor')
        self.assertEqual(self.service.lookup(other,self.args)['status'],'wrong_actor')
    def test_other_user_not_authorized(self):
        other=replace(self.actor,user_id='other-user')
        self.assertEqual(self.service.lookup(other,self.args)['status'],'not_authorized')
    def test_other_tenant_not_authorized(self):
        other=replace(self.actor,tenant_id='other-tenant')
        self.assertEqual(self.write(actor=other)['status'],'not_authorized')
    def test_same_key_changed_text_is_conflict(self):
        self.write();changed=replace(self.args,request_text='請問附近停車場？')
        self.assertEqual(self.write(args=changed)['status'],'idempotency_conflict')
        self.assertEqual(self.service.lookup(self.actor,changed)['status'],'idempotency_conflict')
        self.assertEqual(len(self.requests()),1)
    def test_same_key_changed_event_is_conflict(self):
        self.assertEqual(self.write(args=replace(self.args,event_id='another'))['status'],'idempotency_conflict')
    def test_same_key_changed_confirmation_is_conflict(self):
        self.assertEqual(self.write(args=replace(self.args,confirmation_id='another'))['status'],'idempotency_conflict')
    def test_same_confirmation_new_key_not_a_new_intent(self):
        self.write()
        b=self.write(args=replace(self.args,idempotency_key='a-new-key'))
        self.assertEqual(b['status'],'confirmation_already_used');self.assertEqual(len(self.requests()),1)
    def test_unconfirmed_snapshot_cannot_write(self):
        self.alter('confirmations',self.cid,{'status':'awaiting_confirmation','receipt':None})
        self.assertEqual(self.write()['status'],'unconfirmed_operation')
        self.assertEqual(len(self.requests()),0)
    def test_prepare_without_approval_stays_unconfirmed(self):
        args=self.service.prepare(self.actor,replace(self.op,draft_id='unconfirmed-draft'),approved=False)
        self.assertEqual(self.service.create(self.actor,args)['status'],'unconfirmed_operation')
    def test_expired_first_write_is_rejected(self):
        self.now+=timedelta(seconds=300)
        self.assertEqual(self.write()['status'],'expired');self.assertEqual(len(self.requests()),0)
    def test_expired_existing_receipt_can_be_read(self):
        a=self.write();self.now+=timedelta(seconds=301)
        before=self.store.inspect()
        self.assertEqual(self.service.lookup(self.actor,self.args)['request_id'],a['request_id'])
        self.assertEqual(self.write()['status'],'already_created');self.assertEqual(before,self.store.inspect())
    def test_version_change_blocks_first_write(self):
        self.alter('catalogs',catalog_key(self.actor,self.args.event_id),{'catalog_version':'v2'})
        self.assertEqual(self.write()['status'],'version_changed')
    def test_unadopted_catalog_blocks_first_write(self):
        self.alter('catalogs',catalog_key(self.actor,self.args.event_id),{'data_status':'pending'})
        self.assertEqual(self.write()['status'],'data_pending')
    def test_changed_displayed_event_blocks_first_write(self):
        self.alter('catalogs',catalog_key(self.actor,self.args.event_id),{'displayed_event':{'venue':'new'}})
        self.assertEqual(self.write()['status'],'content_changed')
    def test_changed_draft_blocks_first_write(self):
        self.alter('drafts',draft_key(self.actor,self.op.draft_id),{'request_text':'不同內容'})
        self.assertEqual(self.write()['status'],'content_changed')
    def test_clock_rollback_is_rejected(self):
        self.now-=timedelta(seconds=1)
        self.assertEqual(self.write()['status'],'clock_error')
    def test_execution_false_never_upgraded_by_worker(self):
        self.worker.run(self.actor,self.args)
        self.assertIs(self.store.inspect()['confirmations'][self.cid]['execution_allowed'],False)
    def test_tampered_execution_allowed_not_a_pass(self):
        self.alter('confirmations',self.cid,{'execution_allowed':True})
        self.assertEqual(self.write()['status'],'invalid_confirmation_record')
    def test_tampered_confirmation_owner_is_rejected(self):
        self.alter('confirmations',self.cid,{'owner':asdict(replace(self.actor,user_id='other'))})
        self.assertEqual(self.write()['status'],'invalid_confirmation_record')
    def test_tampered_confirmation_fingerprint_is_rejected(self):
        self.alter('confirmations',self.cid,{'fingerprint':'0'*64})
        self.assertEqual(self.write()['status'],'invalid_confirmation_record')
    def test_tampered_receipt_is_rejected(self):
        c=self.store.inspect()['confirmations'][self.cid]
        c['receipt']['confirmation_id']='new'
        self.alter('confirmations',self.cid,{'receipt':c['receipt']})
        self.assertEqual(self.write()['status'],'invalid_confirmation_record')
    def test_damaged_request_is_not_silently_reported_found(self):
        self.write();self.alter('requests',self.oid,{'payload_hash':'broken'})
        with self.assertRaises(ContractError):self.service.lookup(self.actor,self.args)
    def test_new_explicit_intent_can_create_same_text(self):
        self.write();args=self.service.prepare(self.actor,replace(self.op,draft_id='new-draft'),approved=True)
        self.assertEqual(self.service.create(self.actor,args)['status'],'request_created')
        self.assertEqual(len(self.requests()),2)
    def test_binding_cannot_be_silently_overwritten(self):
        before=self.store.inspect()
        with self.assertRaises(ContractError):
            self.service.prepare(self.actor,self.op,approved=True,idempotency_key=self.args.idempotency_key)
        self.assertEqual(before,self.store.inspect())
    def test_restore_is_task_link_not_full_adk_history(self):
        before=self.store.inspect();link=self.service.restore_session(self.actor)
        self.assertEqual(link['args'],self.args.values());self.assertEqual(link['scope'],'task_reference_only')
        self.assertNotIn('events',link);self.assertEqual(before,self.store.inspect())
    def test_restore_wrong_session_does_not_invent_a_new_approval(self):
        b=self.service.restore_session(replace(self.actor,session_id='new-session'))
        self.assertEqual(b['status'],'session_not_found')
        self.assertEqual(len(self.store.inspect()['confirmations']),1)
    def test_restore_rechecks_current_grant(self):
        self.alter('grants',grant_key(self.actor),{'allowed':False})
        self.assertEqual(self.service.restore_session(self.actor)['status'],'not_authorized')
    def test_after_commit_lookup_does_not_write_again(self):
        a=self.worker.step(self.actor,self.args,fault='after_commit')
        self.assertIsNone(a['request_created']);self.assertNotIn('request_id',a)
        saved=next(iter(self.requests().values()))
        b=self.worker.run(self.actor,self.args)[-1]
        self.assertEqual(b['request_id'],saved['request_id']);self.assertEqual(self.state()['writes'],1)
    def test_before_write_lookup_then_same_key_once(self):
        self.worker.step(self.actor,self.args,fault='before_write')
        self.assertEqual(len(self.requests()),0)
        result=self.worker.run(self.actor,self.args)
        self.assertEqual([r['status'] for r in result],['pending_verification','request_created'])
        self.assertEqual(self.state()['writes'],2);self.assertEqual(len(self.requests()),1)
    def test_lookup_outage_does_not_trigger_write(self):
        self.worker.step(self.actor,self.args,fault='after_commit')
        result=self.worker.run(self.actor,self.args,lookup_unavailable=True)[-1]
        self.assertEqual(result['observation'],'lookup_unavailable')
        self.assertEqual(self.state()['phase'],'paused');self.assertEqual(self.state()['writes'],1)
    def test_worker_lease_held_prevents_second_worker(self):
        c=self.worker.claim(self.actor,self.args)
        self.assertIn('token',c)
        self.assertEqual(self.worker.step(self.actor,self.args)['observation'],'worker_busy')
        self.assertEqual(self.state()['writes'],1)
    def test_expired_lease_new_worker_starts_with_lookup(self):
        self.worker.claim(self.actor,self.args);self.now+=timedelta(seconds=31)
        second=RecoveryWorker(self.service,clock=self.clock)
        self.assertEqual(second.claim(self.actor,self.args)['phase'],'lookup')
    def test_stale_worker_cannot_finish_newer_claim(self):
        a=self.worker.claim(self.actor,self.args);self.now+=timedelta(seconds=31)
        b=self.worker.claim(self.actor,self.args)
        before=self.state()
        self.assertFalse(self.worker.finish(self.actor,self.args,a,pending('submit_timeout')))
        self.assertEqual(before,self.state());self.assertNotEqual(a['token'],b['token'])
    def test_lookup_race_with_other_writer_keeps_one_receipt(self):
        self.worker.step(self.actor,self.args,fault='before_write')
        missed=self.worker.step(self.actor,self.args)
        self.assertEqual(missed['observation'],'not_found')
        earlier=self.write()
        replay=self.worker.step(self.actor,self.args)
        self.assertEqual(replay['request_id'],earlier['request_id']);self.assertEqual(len(self.requests()),1)
    def test_permission_revoked_before_retry(self):
        self.worker.step(self.actor,self.args,fault='before_write');self.worker.step(self.actor,self.args)
        self.alter('grants',grant_key(self.actor),{'allowed':False})
        self.assertEqual(self.worker.step(self.actor,self.args)['status'],'not_authorized')
        self.assertEqual(len(self.requests()),0)
    def test_confirmation_expires_before_retry(self):
        self.worker.step(self.actor,self.args,fault='before_write');self.worker.step(self.actor,self.args)
        self.now+=timedelta(seconds=300)
        self.assertEqual(self.worker.step(self.actor,self.args)['status'],'expired')
    def test_retry_budget_persists_across_worker_objects(self):
        self.worker.step(self.actor,self.args,fault='before_write');self.worker.step(self.actor,self.args)
        self.worker.step(self.actor,self.args,fault='before_write')
        second=RecoveryWorker(self.service,clock=self.clock)
        self.assertEqual(second.step(self.actor,self.args)['observation'],'recovery_paused')
        self.assertEqual(self.state()['writes'],2);self.assertEqual(len(self.requests()),0)
    def test_wrong_phase_tool_does_not_spend_budget(self):
        b=self.worker.step(self.actor,self.args,expected_tool='reconcile_handoff_request')
        self.assertEqual(b['status'],'sequence_rejected');self.assertEqual(self.state()['writes'],0)
    def test_wrong_key_does_not_create_new_operation(self):
        changed=replace(self.args,idempotency_key='scripted-wrong-key')
        b=self.worker.step(self.actor,changed)
        self.assertEqual(b['status'],'unconfirmed_operation');self.assertEqual(len(self.requests()),0)
    def test_done_job_revalidates_receipt_instead_of_cached_success(self):
        first=self.worker.step(self.actor,self.args)
        replay=self.worker.step(self.actor,self.args)
        self.assertEqual(replay['status'],'already_created');self.assertEqual(replay['request_id'],first['request_id'])
    def test_parallel_same_key_has_one_business_receipt(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.write(),range(4)))
        self.assertEqual(len(self.requests()),1)
        successes=[r for r in results if r['status'] in ('request_created','already_created')]
        self.assertTrue(successes);self.assertEqual(sum(r['request_created'] for r in successes),1)
        self.assertEqual(len({r['request_id'] for r in successes}),1)
        # 正式 Firestore 遇暫時受阻允許保留未知，不能把它謊稱成功。
        self.assertTrue(all(r['status'] in ('request_created','already_created','pending_verification') for r in results))
    def test_transaction_rollback_preserves_original_document(self):
        before=self.store.inspect()
        def fail(tx):
            job=tx.get('jobs',self.oid);job['writes']=999;tx.put('jobs',self.oid,job)
            raise RuntimeError('INJECTED_BEFORE_COMMIT')
        with self.assertRaises(RuntimeError):self.store.atomic(fail)
        self.assertEqual(before,self.store.inspect())
    def test_read_only_transaction_cannot_put(self):
        with self.assertRaises(ContractError):
            self.store.atomic(lambda tx:tx.put('requests',self.oid,{}),read_only=True)
    def test_read_after_write_is_rejected_and_rolled_back(self):
        before=self.store.inspect()
        def invalid(tx):
            tx.put('jobs',self.oid,{});tx.get('bindings',self.oid)
        with self.assertRaises(ContractError):self.store.atomic(invalid)
        self.assertEqual(before,self.store.inspect())
    def test_invalid_argument_does_not_enter_storage(self):
        bad=replace(self.args,idempotency_key='')
        self.assertEqual(self.write(args=bad)['status'],'invalid_arguments')
    def test_whitespace_in_payload_is_not_silently_removed(self):
        b=self.write(args=replace(self.args,request_text=self.args.request_text+' '))
        self.assertEqual(b['status'],'idempotency_conflict')
    def test_original_day01_unknown_contract(self):
        from upstream import REPO
        expected=json.loads((REPO/'docs/day01/handoff-timeout-001.json').read_text('utf-8'))
        # 原規格四欄；實作獨立產生，不讀 expected 當回覆。
        value=pending('submit_timeout')
        policy=expected.get('expected',expected.get('expected_policy',{}))
        self.assertTrue(policy)
        for k,v in policy.items():self.assertEqual(value[k],v)

    def test_empty_original_key_is_not_silently_generated(self):
        before=self.store.inspect()
        with self.assertRaises(ValueError):
            self.service.prepare(self.actor,self.op,approved=True,idempotency_key='')
        self.assertEqual(before,self.store.inspect())
    def test_invalid_lookup_arguments_leave_storage_unchanged(self):
        before=self.store.inspect()
        result=self.service.lookup(self.actor,replace(self.args,idempotency_key=''))
        self.assertEqual(result['status'],'invalid_arguments')
        self.assertEqual(before,self.store.inspect())
    def test_request_keeps_actual_service_destination_not_event_id(self):
        result=self.write();row=result['request']
        self.assertEqual(row['service_id'],self.op.destination)
        self.assertEqual(row['event_id'],self.op.event_id)
        self.assertNotEqual(row['service_id'],row['event_id'])
    def test_corrupt_request_body_cannot_be_returned_as_original(self):
        self.write();self.alter('requests',self.oid,{'request_text':'另一份問題'})
        with self.assertRaises(ContractError):self.service.lookup(self.actor,self.args)
    def test_corrupt_request_state_is_not_human_acceptance(self):
        self.write();self.alter('requests',self.oid,{'human_claimed':True})
        with self.assertRaises(ContractError):self.service.lookup(self.actor,self.args)
