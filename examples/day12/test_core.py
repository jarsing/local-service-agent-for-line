import asyncio
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from .main import Application,create_app
from .query import StubQuery
from .identity import signature,verify_signature,make_actor
from .inherit import SQLiteTestStore,SendArgs,grant_key,catalog_key,confirmation_key,key,StoreUnavailable
from .delivery import Busy
from .testing import settings,ReplyRecorder,event,post,RAW_USER,OTHER_USER

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.config=settings(Path(self.temp.name)/'tasks.sqlite3')
        self.now=datetime(2026,9,26,tzinfo=timezone.utc)
        self.sender=ReplyRecorder();self.events=[];self.store=SQLiteTestStore(self.config.sqlite_path)
        self.engine=Application(self.config,self.store,StubQuery(),self.sender,clock=lambda:self.now,
                                emit=lambda k,**v:self.events.append({'kind':k,**v}))
        self.actor=make_actor(self.config,RAW_USER);self.other=make_actor(self.config,OTHER_USER)
        self.engine.tasks.seed([self.actor,self.other])
        self.client=TestClient(create_app(self.engine));self.client.__enter__()
        self.addCleanup(self.client.__exit__,None,None,None)
    def send(self,ident,text=None,data=None,user=RAW_USER):
        r=post(self.client,self.config,event(ident,text,data,user));self.assertEqual(r.status_code,200,r.text);return r
    def draft(self,ident='offer',text='集合地點在哪裡？'):
        self.send(ident,'需要協助：'+text)
        return self.engine.tasks.current(self.actor)['args']
    def create(self):
        args=self.draft();self.send('confirm',data='confirm:'+args['confirmation_id'])
        return args,self.engine.tasks.status(self.actor)
    def count(self):return len(self.store.inspect().get('requests',{}))
    def mutate(self,kind,ident,change):
        def write(tx):
            row=tx.get(kind,ident);change(row);tx.put(kind,ident,row)
        self.store.atomic(write)

    def test_unfavorable_model_output_is_saved_as_failed_trace(self):
        from .query import QueryFailure
        class FailedQuery:
            async def ask(self,*args):
                raise QueryFailure('NO_TOOL',{'mode':'STUB_FAILURE_NOT_GEMINI',
                    'status':'failed','model_text':'刻意設計的假完成','events':[]})
        self.engine.query=FailedQuery()
        self.send('failed-query','花壇集合？')
        self.assertIn('暫時沒有取得',self.sender.sent[-1][0]['text'])
        trace=next(iter(self.store.inspect()['line_traces'].values()))
        self.assertEqual(trace['report']['status'],'failed')
        self.assertIn('假完成',trace['report']['model_text'])

    def test_signature_checks_exact_raw_bytes(self):
        raw='{"x":"花壇"}'.encode();signed=signature('s',raw)
        self.assertTrue(verify_signature('s',raw,signed));self.assertFalse(verify_signature('s',raw+b' ',signed))
        self.assertFalse(verify_signature('s',raw,'非簽章'))
    def test_wrong_signature_never_reads_or_writes(self):
        before=self.store.inspect();r=post(self.client,self.config,event('x','問'),signature_override='bad')
        self.assertEqual(r.status_code,401);self.assertEqual(before,self.store.inspect())
    def test_empty_webhook_verification(self):self.assertEqual(post(self.client,self.config).status_code,200)
    def test_wrong_destination_rejected(self):
        self.assertEqual(post(self.client,self.config,event('x','問'),destination='another').status_code,403)
    def test_non_allowlisted_user_ignored(self):
        self.send('x','問',user='not-allowed');self.assertFalse(self.sender.sent)
    def test_group_source_ignored(self):
        e=event('x','問');e['source']['type']='group'
        self.assertEqual(post(self.client,self.config,e).status_code,200);self.assertFalse(self.sender.sent)
    def test_health_does_not_touch_storage(self):
        with patch.object(self.store,'atomic',side_effect=RuntimeError('down')):
            self.assertEqual(self.client.get('/healthz').json(),{'status':'ok'})
    def test_health_has_no_boot_or_secret(self):self.assertEqual(set(self.client.get('/healthz').json()),{'status'})
    def test_body_limit(self):
        r=self.client.post('/webhook',content=b'x'*65537);self.assertEqual(r.status_code,413)
    def test_query_returns_snapshot_unknown_not_fake_meeting_point(self):
        self.send('q','花壇場次在哪裡集合？');text=self.sender.sent[-1][0]['text']
        self.assertIn('活動地點：大嶺巷步道',text);self.assertIn('集合時間與集合點：這份快照未提供',text)
        self.assertIn('2026-09-19',text);self.assertIn('教學快照',text);self.assertEqual(self.count(),0)
    def test_core_stub_trace_does_not_claim_gemini(self):
        self.send('q','花壇集合？');trace=next(iter(self.store.inspect()['line_traces'].values()))
        self.assertEqual(trace['report']['mode'],'STUB_NOT_GEMINI')
    def test_offer_does_not_approve(self):
        args=self.draft();c=self.store.inspect()['confirmations'][confirmation_key(self.actor,SendArgs(**args))]
        self.assertEqual(c['status'],'awaiting_confirmation');self.assertIs(c['execution_allowed'],False)
        self.assertIsNone(c['receipt']);self.assertEqual(self.count(),0)
    def test_naked_yes_does_not_approve(self):
        self.draft();self.send('yes','好');self.assertEqual(self.count(),0)
        self.assertIn('quickReply',self.sender.sent[-1][0])
    def test_postback_creates_one_request(self):
        args,result=self.create();self.assertEqual(result['status'],'already_created');self.assertEqual(self.count(),1)
        c=self.store.inspect()['confirmations'][confirmation_key(self.actor,SendArgs(**args))]
        self.assertIs(c['execution_allowed'],False);self.assertEqual(c['decision_source'],'verified_line_postback')
    def test_two_confirm_events_same_key_one_request(self):
        args,result=self.create();self.send('confirm-again',data='confirm:'+args['confirmation_id'])
        self.assertEqual(self.count(),1);self.assertIn(result['request_id'],self.sender.sent[-1][0]['text'])
    def test_reply_has_no_volunteer_promise_or_booking(self):
        self.create();text=self.sender.sent[-1][0]['text']
        self.assertIn('尚未通知',text);self.assertNotIn('活動前與您聯繫',text);self.assertNotIn('預約成功',text)
    def test_foreign_confirmation_cannot_write(self):
        args=self.draft();self.send('foreign',data='confirm:'+args['confirmation_id'],user=OTHER_USER)
        self.assertEqual(self.count(),0)
    def test_expired_confirmation_not_renewed(self):
        args=self.draft();cid=confirmation_key(self.actor,SendArgs(**args));before=self.store.inspect()['confirmations'][cid]
        self.now+=timedelta(seconds=301);self.send('c',data='confirm:'+args['confirmation_id'])
        self.assertEqual(self.count(),0);self.assertIn('過期',self.sender.sent[-1][0]['text'])
        self.assertEqual(before['expires_at'],self.store.inspect()['confirmations'][cid]['expires_at'])
    def test_expired_status_does_not_offer_new_five_minutes(self):
        self.draft();self.now+=timedelta(seconds=301);self.send('s','查詢原單')
        self.assertIn('過期',self.sender.sent[-1][0]['text']);self.assertNotIn('quickReply',self.sender.sent[-1][0])
    def test_existing_receipt_after_expiry_can_be_read(self):
        args,result=self.create();self.now+=timedelta(hours=1);self.send('s','查詢原單')
        self.assertIn(result['request_id'],self.sender.sent[-1][0]['text']);self.assertEqual(self.count(),1)
    def test_version_change_stops_first_write(self):
        args=self.draft();self.mutate('catalogs',catalog_key(self.actor,args['event_id']),lambda r:r.update(catalog_version='new'))
        self.send('c',data='confirm:'+args['confirmation_id']);self.assertEqual(self.count(),0)
    def test_permission_revoked_before_confirmation(self):
        args=self.draft();self.mutate('grants',grant_key(self.actor),lambda r:r.update(allowed=False))
        r=post(self.client,self.config,event('c',data='confirm:'+args['confirmation_id']))
        self.assertEqual(r.status_code,403);self.assertEqual(self.count(),0)
    def test_permission_revoked_after_create_no_cached_private_reply(self):
        self.create();n=len(self.sender.sent);self.mutate('grants',grant_key(self.actor),lambda r:r.update(allowed=False))
        r=post(self.client,self.config,event('s','查詢原單'));self.assertEqual(r.status_code,403)
        self.assertEqual(n,len(self.sender.sent))
    def test_seed_does_not_regrant_revoked_user(self):
        self.mutate('grants',grant_key(self.actor),lambda r:r.update(allowed=False))
        self.engine.tasks.seed([self.actor]);self.assertFalse(self.store.inspect()['grants'][grant_key(self.actor)]['allowed'])
    def test_cancel_cannot_turn_into_approval(self):
        args=self.draft();self.send('cancel',data='cancel:'+args['confirmation_id'])
        self.send('confirm',data='confirm:'+args['confirmation_id']);self.assertEqual(self.count(),0)
    def test_old_card_superseded_after_explicit_new_intent(self):
        args=self.draft();self.send('offer2','新需求：另一項詢問')
        self.send('old',data='confirm:'+args['confirmation_id']);self.assertEqual(self.count(),0)
        self.assertIn('較早',self.sender.sent[-1][0]['text'])
    def test_identical_text_without_new_intent_returns_current(self):
        args=self.draft();self.send('offer2','需要協助：集合地點在哪裡？')
        self.assertEqual(self.engine.tasks.current(self.actor)['args'],args)
    def test_explicit_new_intent_gets_different_key(self):
        args=self.draft();self.send('offer2','新需求：集合地點在哪裡？')
        self.assertNotEqual(args['idempotency_key'],self.engine.tasks.current(self.actor)['args']['idempotency_key'])
    def test_redelivery_same_event_is_not_second_model_call(self):
        e=event('q','花壇集合？');post(self.client,self.config,e);n=len(self.sender.sent)
        e['replyToken']='changed';e['deliveryContext']={'isRedelivery':True};post(self.client,self.config,e)
        self.assertEqual(n,len(self.sender.sent));self.assertEqual(len(self.store.inspect()['line_traces']),1)
    def test_same_event_changed_payload_rejected(self):
        self.send('q','花壇');r=post(self.client,self.config,event('q','another'))
        self.assertEqual(r.status_code,400)
    def test_event_inflight_gets_503(self):
        e=event('q','花壇');self.engine.ledger.begin(self.actor,e)
        self.assertEqual(post(self.client,self.config,e).status_code,503)
    def test_reply_failure_does_not_recreate_business(self):
        args=self.draft();self.sender.fail=True;e=event('c',data='confirm:'+args['confirmation_id'])
        post(self.client,self.config,e);self.assertEqual(self.count(),1);n=len(self.sender.sent)
        post(self.client,self.config,e);self.assertEqual(n,len(self.sender.sent));self.assertEqual(self.count(),1)
        self.sender.fail=False;self.send('new-status','查詢原單');self.assertIn('找到',self.sender.sent[-1][0]['text'])
    def test_missing_receipt_status_does_not_create(self):
        self.draft();self.send('s','查詢原單');self.assertEqual(self.count(),0)
    def test_new_runtime_finds_same_request_without_memory_copy(self):
        args,result=self.create()
        fresh_sender=ReplyRecorder();fresh=Application(self.config,SQLiteTestStore(self.config.sqlite_path),StubQuery(),fresh_sender,emit=lambda *a,**k:None)
        with TestClient(create_app(fresh)) as c: self.assertEqual(post(c,self.config,event('s','查詢原單')).status_code,200)
        self.assertNotEqual(fresh.boot_id,self.engine.boot_id)
        self.assertIn(result['request_id'],fresh_sender.sent[-1][0]['text'])
    def test_actor_does_not_depend_on_revision(self):
        with patch.dict(os.environ,{'K_REVISION':'different'}):
            self.assertEqual(self.actor,make_actor(self.config,RAW_USER))
    def test_hmac_rotation_not_misreported_as_original_user(self):
        other_key=replace(self.config,actor_key='x'*32)
        self.assertNotEqual(self.actor,make_actor(other_key,RAW_USER))
    def test_safety_cloud_rejects_stub(self):
        with patch.dict(os.environ,{'K_SERVICE':'cloud'}):
            with self.assertRaises(ValueError):self.config.validate()
    def test_cloud_requires_approval(self):
        with self.assertRaises(ValueError):replace(self.config,backend='cloud').validate()
    def test_daily_budget_is_shared_across_runtime_objects(self):
        for i in range(10): self.send('q'+str(i),'花壇')
        self.send('blocked','花壇');self.assertIn('額度已用完',self.sender.sent[-1][0]['text'])
        self.send('s','查詢原單');self.assertNotIn('額度已用完',self.sender.sent[-1][0]['text'])
    def test_adopted_catalog_changed_query_not_silently_old(self):
        self.mutate('catalogs',catalog_key(self.actor,self.engine.catalog.event['id']),lambda r:r.update(catalog_version='changed'))
        self.send('q','花壇');self.assertIn('資料已更新',self.sender.sent[-1][0]['text'])
        self.assertNotIn('line_budget',self.store.inspect())
    def test_no_raw_user_or_reply_token_in_logs_or_documents(self):
        self.create();serialized=json.dumps([self.events,self.store.inspect()],ensure_ascii=False)
        self.assertNotIn(RAW_USER,serialized);self.assertNotIn('synthetic-confirm',serialized)
        self.assertNotIn(self.config.channel_secret,serialized)
    def test_same_offer_recovery_after_register_before_plan(self):
        first=self.engine.tasks.offer(self.actor,'保留原詢問','original-event')
        second=self.engine.tasks.offer(self.actor,'保留原詢問','original-event')
        self.assertEqual(first['args'],second['args']);self.assertEqual(len(self.store.inspect()['confirmations']),1)
    def test_offer_same_event_different_text_is_conflict(self):
        self.engine.tasks.offer(self.actor,'A','original-event')
        self.assertEqual(self.engine.tasks.offer(self.actor,'B','original-event')['status'],'idempotency_conflict')
    def test_original_text_colons_preserved(self):
        args=self.draft(text='時間：08:00 是否集合？');self.assertEqual(args['request_text'],'時間：08:00 是否集合？')

if __name__=='__main__':unittest.main()
