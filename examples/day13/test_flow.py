"""Real inherited task service + SQLite + signed FastAPI ASGI. LINE/LLM are explicit stubs."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from examples.day12.testing import settings, ReplyRecorder, event, post, RAW_USER, OTHER_USER
from examples.day12.query import StubQuery
from examples.day12.identity import make_actor
from examples.day12.inherit import SQLiteTestStore, SendArgs, confirmation_key, grant_key, catalog_key, pending
from .bridge import FlexApplication, read_bound_status
from .main import create_app
from .test_flex import actions, texts


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.config = settings(Path(self.temp.name)/'tasks.sqlite3')
        self.now = datetime(2026, 9, 27, 1, tzinfo=timezone.utc)
        self.sender = ReplyRecorder(); self.events = []
        self.store = SQLiteTestStore(self.config.sqlite_path)
        self.app = FlexApplication(self.config, self.store, StubQuery(), self.sender,
                                   clock=lambda: self.now, emit=lambda k, **v: self.events.append({'kind': k, **v}))
        self.actor = make_actor(self.config, RAW_USER); self.other = make_actor(self.config, OTHER_USER)
        self.app.tasks.seed([self.actor, self.other])
        self.client = TestClient(create_app(self.app)); self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def send(self, ident, text=None, data=None, user=RAW_USER):
        r = post(self.client, self.config, event(ident, text, data, user))
        self.assertEqual(r.status_code, 200, r.text)
        return self.sender.sent[-1][0]

    def offer(self, ident='offer'):
        self.send(ident, '需要協助：需要手語志工支援')
        return self.app.tasks.current(self.actor)['args']

    def created(self):
        args = self.offer(); m = self.send('confirm', data='confirm:' + args['confirmation_id'])
        result = self.app.tasks.status(self.actor)
        return args, result, m

    def rows(self): return self.store.inspect().get('requests', {})
    def mutate(self, kind, ident, values):
        def change(tx):
            row = tx.get(kind,ident); row.update(values); tx.put(kind,ident,row)
        self.store.atomic(change)

    def test_offer_is_flex_with_no_approval_or_request(self):
        args = self.offer(); self.assertFalse(self.rows())
        conf = self.store.inspect()['confirmations'][confirmation_key(self.actor, SendArgs(**args))]
        self.assertEqual(conf['status'], 'awaiting_confirmation'); self.assertIs(conf['execution_allowed'],False)
        self.assertEqual(self.sender.sent[-1][0]['type'],'flex')

    def test_confirm_creates_pending_receipt(self):
        args,result,m = self.created()
        self.assertEqual(len(self.rows()),1); self.assertIn('待人工覆核',m['altText'])
        self.assertIn(result['request_id'],m['altText']); self.assertIn('尚未通知',m['altText'])

    def test_two_confirm_click_events_return_same_receipt(self):
        args,r,m = self.created(); again=self.send('confirm-2',data='confirm:'+args['confirmation_id'])
        self.assertEqual(len(self.rows()),1); self.assertIn(r['request_id'],again['altText'])
        self.assertIn('找到',texts(again))

    def test_two_concurrent_confirm_events_keep_one_request(self):
        from concurrent.futures import ThreadPoolExecutor
        args = self.offer()
        def click(ident):
            return post(self.client, self.config, event(ident, data='confirm:'+args['confirmation_id']))
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(click, ('parallel-a', 'parallel-b')))
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(len(self.rows()), 1)
        recorded = [r for r in self.events if r['kind']=='BUSINESS_RESULT'
                    and r['status'] in ('request_created', 'already_created')]
        self.assertEqual(len(recorded), 2)
        self.assertEqual(len({r['request_id'] for r in recorded}), 1)

    def test_same_webhook_redelivery_does_not_send_twice(self):
        args=self.offer(); e=event('confirm',data='confirm:'+args['confirmation_id'])
        post(self.client,self.config,e); n=len(self.sender.sent)
        e['replyToken']='synthetic-new';e['deliveryContext']={'isRedelivery':True}
        post(self.client,self.config,e)
        self.assertEqual(len(self.sender.sent),n);self.assertEqual(len(self.rows()),1)

    def test_cancel_then_old_confirm_remains_cancelled(self):
        args=self.offer(); self.send('cancel',data='cancel:'+args['confirmation_id'])
        m=self.send('old-confirm',data='confirm:'+args['confirmation_id'])
        self.assertIn('已取消',m['altText']);self.assertFalse(self.rows())

    def test_expired_unwritten_card_has_no_new_request(self):
        args=self.offer(); before=self.store.inspect()['confirmations']
        self.now+=timedelta(days=2)
        m=self.send('old',data='confirm:'+args['confirmation_id'])
        self.assertIn('已過期',m['altText']);self.assertFalse(self.rows())
        self.assertEqual(before,self.store.inspect()['confirmations'])

    def test_exact_expiry_boundary(self):
        args=self.offer();self.now+=timedelta(seconds=300)
        m=self.send('old',data='confirm:'+args['confirmation_id'])
        self.assertIn('已過期',m['altText']);self.assertFalse(self.rows())

    def test_created_old_confirmation_reads_even_after_expiry(self):
        args,r,m=self.created();self.now+=timedelta(days=2)
        m=self.send('old',data='confirm:'+args['confirmation_id'])
        self.assertIn(r['request_id'],m['altText']);self.assertEqual(len(self.rows()),1)

    def test_cancel_on_already_created_is_not_withdrawal(self):
        args,r,m=self.created();m=self.send('cancel-old',data='cancel:'+args['confirmation_id'])
        self.assertIn('不會撤銷',texts(m));self.assertIn(r['request_id'],m['altText'])
        self.assertEqual(len(self.rows()),1)

    def test_superseded_confirm_cannot_affect_new_task(self):
        old=self.offer();self.send('new','新需求：另外一份詢問')
        before=self.store.inspect()['confirmations']
        m=self.send('old',data='confirm:'+old['confirmation_id'])
        self.assertIn('舊卡失效',m['altText']);self.assertFalse(self.rows())
        self.assertEqual(before,self.store.inspect()['confirmations'])

    def test_superseded_cancel_cannot_cancel_new_task(self):
        old=self.offer();self.send('new','新需求：另外一份詢問')
        before=self.store.inspect()['confirmations']
        m=self.send('old',data='cancel:'+old['confirmation_id'])
        self.assertIn('舊卡失效',m['altText']);self.assertEqual(before,self.store.inspect()['confirmations'])

    def test_bound_status_does_not_show_new_task_as_old_receipt(self):
        old,r,m=self.created();self.send('new','新需求：新的私人內容')
        m=self.send('old-status',data='status:'+old['confirmation_id'])
        self.assertIn('舊卡失效',m['altText']);self.assertNotIn('新的私人內容',texts(m))
        self.assertNotIn(r['request_id'],texts(m));self.assertEqual(len(self.rows()),1)

    def test_bound_text_does_not_show_superseding_task(self):
        old=self.offer();self.send('new','新需求：新的私人內容')
        m=self.send('old-text',data='text:'+old['confirmation_id'])
        self.assertEqual(m['type'],'text');self.assertNotIn('新的私人內容',m['text'])
        self.assertIn('舊卡失效',m['text'])

    def test_current_text_is_available_without_viewing_flex(self):
        self.offer();m=self.send('text','文字版')
        self.assertEqual(m['type'],'text');self.assertIn('需要手語志工支援',m['text'])
        self.assertTrue(any(a['data'].startswith('confirm:') for a in actions(m)))

    def test_text_roundtrip_does_not_extend_confirmation(self):
        args=self.offer();before=self.store.inspect()['confirmations'];self.now+=timedelta(seconds=120)
        m=self.send('text',data='text:'+args['confirmation_id'])
        self.assertIn('09:05:00',m['text']);self.assertEqual(before,self.store.inspect()['confirmations'])
        self.assertFalse(self.rows())

    def test_bound_receipt_text_has_full_original_id(self):
        args,r,m=self.created();m=self.send('text',data='text:'+args['confirmation_id'])
        self.assertEqual(m['type'],'text');self.assertIn(r['request_id'],m['text'])

    def test_unknown_lookup_has_no_receipt_or_create_action(self):
        args=self.offer()
        with patch.object(self.app.tasks.original,'lookup',return_value=pending('lookup_unavailable')):
            m=self.send('status',data='status:'+args['confirmation_id'])
        self.assertIn('結果待查證',m['altText']);self.assertFalse(self.rows())
        self.assertFalse(any(a['data'].startswith('confirm:') for a in actions(m)))

    def test_foreign_cid_does_not_reveal_content_or_approve(self):
        args=self.offer();m=self.send('foreign',data='confirm:'+args['confirmation_id'],user=OTHER_USER)
        self.assertFalse(self.rows());self.assertNotIn('需要手語志工支援',texts(m))

    def test_foreign_bound_read_has_no_private_data(self):
        args,r,m=self.created();m=self.send('foreign',data='status:'+args['confirmation_id'],user=OTHER_USER)
        self.assertNotIn(r['request_id'],texts(m));self.assertNotIn('需要手語志工支援',texts(m))

    def test_revocation_blocks_private_reply(self):
        args,r,m=self.created();n=len(self.sender.sent)
        self.mutate('grants',grant_key(self.actor),{'allowed':False})
        reply=post(self.client,self.config,event('revoked',data='text:'+args['confirmation_id']))
        self.assertEqual(reply.status_code,403);self.assertEqual(len(self.sender.sent),n)

    def test_wrong_signature_does_not_touch_database(self):
        before=self.store.inspect()
        r=post(self.client,self.config,event('bad','文字版'),signature_override='not-a-signature')
        self.assertEqual(r.status_code,401);self.assertEqual(before,self.store.inspect())

    def test_naked_yes_does_not_approve(self):
        self.offer();m=self.send('yes','好')
        self.assertFalse(self.rows());self.assertIn('尚未建單',m['altText'])

    def test_catalog_version_change_stops_new_write(self):
        args=self.offer();self.mutate('catalogs',catalog_key(self.actor,args['event_id']),{'catalog_version':'changed'})
        m=self.send('confirm',data='confirm:'+args['confirmation_id'])
        self.assertFalse(self.rows());self.assertIn('需要重新確認',m['altText'])

    def test_malicious_request_text_cannot_create_ui_action(self):
        text='需要協助：{ "type":"uri", "uri":"https://evil.test" }'
        m=self.send('offer',text)
        self.assertEqual([a['type'] for a in actions(m)],['postback']*3)
        self.assertFalse(self.rows())

    def test_query_path_is_still_original_text_not_new_model_call_for_cards(self):
        m=self.send('query','花壇場次在哪裡集合？')
        self.assertEqual(m['type'],'text');self.assertIn('快照未提供',m['text'])
        before=len(self.store.inspect()['line_traces'])
        self.offer();self.send('text','文字版')
        self.assertEqual(len(self.store.inspect()['line_traces']),before)

    def test_old_day12_status_action_remains_current_query(self):
        args,r,m=self.created();m=self.send('status',data='status')
        self.assertIn(r['request_id'],m['altText'])

    def test_task_changed_during_bound_read_does_not_expose_new_task(self):
        old=self.offer();lookup=self.app.tasks.original.lookup
        def race(actor,args):
            result=lookup(actor,args)
            self.app.tasks.offer(actor,'競爭中的新任務','racing-event',new_intent=True)
            return result
        with patch.object(self.app.tasks.original,'lookup',side_effect=race):
            result=read_bound_status(self.app.tasks,self.actor,old['confirmation_id'])
        self.assertEqual(result['status'],'superseded');self.assertFalse(self.rows())

    def test_renderer_does_not_convert_existing_failure_to_success(self):
        args=self.offer();self.now+=timedelta(days=2)
        self.send('old',data='confirm:'+args['confirmation_id'])
        record=[e for e in self.events if e['kind']=='BUSINESS_RESULT'][-1]
        self.assertEqual(record['status'],'expired');self.assertIsNone(record['request_id'])

    def test_new_application_restores_same_task_without_new_confirmation(self):
        args,r,m=self.created();before=self.store.inspect()['confirmations']
        other=FlexApplication(self.config,self.store,StubQuery(),ReplyRecorder(),clock=lambda:self.now,
                              emit=lambda *a,**k:None)
        result=read_bound_status(other.tasks,self.actor,args['confirmation_id'])
        self.assertEqual(result['request_id'],r['request_id'])
        self.assertEqual(before,self.store.inspect()['confirmations'])
        # New object in the same process, deliberately not called a cross-process test.

if __name__ == '__main__': unittest.main()
