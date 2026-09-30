"""簽章 ASGI＋原任務服務＋真正 SQLite；模型與 LINE Reply 是明示測試替身。"""
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from examples.day12.testing import settings, ReplyRecorder, event, post, RAW_USER, OTHER_USER
from examples.day12.identity import make_actor
from examples.day12.inherit import SQLiteTestStore, grant_key
from .main import MemoryApplication, create_app
from .engine import ScriptedInterpreter
from .test_support import Clock
from .memory import COLLECTION, owner_key

MAPPING={
 '今天想吃素，花壇有什麼店？':('search_local_places',{'area':'花壇鄉','dietary_type':'vegetarian'}),
 '長輩吃素，以後優先找蔬食，幫我記住':('propose_dietary_memory',{'dietary_type':'vegetarian'}),
 '花壇有推薦吃的嗎？':('search_local_places',{'area':'花壇鄉'}),
 '把我的偏好改成蛋奶素':('propose_dietary_memory',{'dietary_type':'ovo_lacto'}),
 '請忘掉之前的飲食設定':('request_memory_management',{'action':'forget'}),
 '這附近有推薦吃的嗎？':('search_local_places',{'area':'附近'}),
}
def action_data(messages,prefix):
    found=[]
    def walk(value):
        if isinstance(value,dict):
            if value.get('type')=='postback' and value.get('data','').startswith(prefix): found.append(value['data'])
            for v in value.values():walk(v)
        elif isinstance(value,list):
            for v in value:walk(v)
    walk(messages)
    if not found: raise AssertionError('missing action '+prefix)
    return found[0]

class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.config=settings(Path(self.tmp.name)/'state.sqlite3');self.clock=Clock()
        self.store=SQLiteTestStore(self.config.sqlite_path);self.sender=ReplyRecorder();self.logs=[];self.reports=[]
        self.interpreter=ScriptedInterpreter(MAPPING)
        self.app=MemoryApplication(self.config,self.store,self.interpreter,self.sender,clock=self.clock,
                                   emit=lambda k,**v:self.logs.append({'kind':k,**v}),observer=self.reports.append)
        self.actor=make_actor(self.config,RAW_USER);self.other=make_actor(self.config,OTHER_USER)
        self.app.tasks.seed([self.actor,self.other]);self.client=TestClient(create_app(self.app));self.client.__enter__()
        self.addCleanup(self.client.__exit__,None,None,None)
        self.seq=0
    def send(self,text=None,data=None,user=RAW_USER,eid=None):
        self.seq+=1;e=event(eid or 'day14-synthetic-'+str(self.seq),text=text,data=data,user=user)
        e['timestamp']=int(self.clock().timestamp()*1000)
        r=post(self.client,self.config,e);self.assertEqual(r.status_code,200,r.text)
        return self.sender.sent[-1]
    def approve(self):
        message=self.send('長輩吃素，以後優先找蔬食，幫我記住')
        data=action_data(message,'m14:approve:');self.send(data=data);return data
    def test_booking_three_actions_even_model_unavailable(self):
        class Fail:
            async def ask(self,*args): raise AssertionError('MODEL_SHOULD_NOT_BE_CALLED')
        self.app.interpreter=Fail();r=self.send('我要預約')
        for value in ('d14:events','d14:places','d14:enquiry'): self.assertEqual(action_data(r,value),value)
    def test_activity_button_reuses_catalog(self):
        result=self.send(data='d14:events');self.assertIn('集合時間與集合點',json.dumps(result,ensure_ascii=False))
    def test_places_button_selects_area(self):
        result=self.send(data='d14:places');self.assertEqual(action_data(result,'d14:area:花壇鄉'),'d14:area:花壇鄉')
    def test_area_button_returns_real_public_record(self):
        result=self.send(data='d14:area:花壇鄉');self.assertIn('和米素食',json.dumps(result,ensure_ascii=False))
    def test_enquiry_button_reaches_original_offer(self):
        result=self.send(data='d14:enquiry');self.assertIn('新需求：',json.dumps(result,ensure_ascii=False))
        result=self.send('新需求：需要手語志工支援');data=action_data(result,'confirm:')
        self.send(data=data);self.assertEqual(len(self.store.inspect().get('requests',{})),1)
    def test_single_turn_no_preference_saved(self):
        self.send('今天想吃素，花壇有什麼店？');self.assertEqual(self.app.memory.inspect(self.actor)['status'],'empty')
        self.assertNotIn(COLLECTION,self.store.inspect())
    def test_offer_is_not_profile(self):
        self.send('長輩吃素，以後優先找蔬食，幫我記住');self.assertNotIn(COLLECTION,self.store.inspect())
    def test_explicit_consent_then_reuse(self):
        self.approve();self.send('花壇有推薦吃的嗎？')
        self.assertEqual(self.reports[-1]['tool_events'][0]['effective_arguments']['dietary_type'],'vegetarian')
    def test_update_not_saved_until_click(self):
        self.approve();result=self.send('把我的偏好改成蛋奶素')
        self.assertEqual(self.app.memory.inspect(self.actor)['dietary_type'],'vegetarian')
        self.send(data=action_data(result,'m14:approve:'))
        self.assertEqual(self.app.memory.inspect(self.actor)['dietary_type'],'ovo_lacto')
    def test_forget_removes_runtime_personalization_values(self):
        token=self.approve();self.send('忘記我的飲食偏好')
        self.send(data=token);self.send('花壇有推薦吃的嗎？')
        self.assertIsNone(self.app.memory.inspect(self.actor)['dietary_type'])
        self.assertEqual(self.reports[-1]['tool_events'][0]['effective_arguments']['dietary_type'],'any')
        raw=json.dumps(self.store.inspect(),ensure_ascii=False)
        for value in ('vegetarian','ovo_lacto','長輩吃素','是否同意記住'): self.assertNotIn(value,raw)
        self.assertNotIn('line_traces',self.store.inspect())
        for row in self.store.inspect().get('line_events',{}).values(): self.assertIsNone(row['plan'])
    def test_second_user_cannot_approve_first(self):
        result=self.send('長輩吃素，以後優先找蔬食，幫我記住')
        self.send(data=action_data(result,'m14:approve:'),user=OTHER_USER)
        self.assertEqual(self.app.memory.inspect(self.other)['status'],'empty')
    def test_bare_yes_does_not_save_memory(self):
        self.send('長輩吃素，以後優先找蔬食，幫我記住');self.send('好')
        self.assertEqual(self.app.memory.inspect(self.actor)['status'],'empty')
    def test_double_click_same_card_new_events(self):
        token=self.approve();revision=self.app.memory.inspect(self.actor)['revision'];self.send(data=token)
        self.assertEqual(self.app.memory.inspect(self.actor)['revision'],revision)
    def test_same_event_no_second_reply(self):
        self.send('我要預約',eid='same');n=len(self.sender.sent);self.send('我要預約',eid='same')
        self.assertEqual(len(self.sender.sent),n)
    def test_expired_memory_card(self):
        result=self.send('長輩吃素，以後優先找蔬食，幫我記住');self.clock.now+=timedelta(seconds=301)
        self.send(data=action_data(result,'m14:approve:'));self.assertEqual(self.app.memory.inspect(self.actor)['status'],'empty')
    def test_unavailable_model_still_guides(self):
        class Fail:
            async def ask(self,*args): raise TimeoutError('private utterance must not be logged')
        self.app.interpreter=Fail();r=self.send('不明的非結構化需求')
        self.assertIn('查詢暫時',json.dumps(r,ensure_ascii=False))
        self.assertEqual(action_data(r,'status'),'status')
        retry=r[0]['contents']['footer']['contents'][0]['action']
        self.assertEqual(retry,{'type':'message','label':'稍後重新查詢','text':'重新輸入查詢條件'})
        self.assertNotIn('private utterance',json.dumps(self.logs))
    def test_model_fake_success_not_accepted(self):
        class Fake:
            async def ask(self,*args): return {'result':{'status':'memory_saved','approved':True}}
        self.app.interpreter=Fake();self.send('請幫忙')
        self.assertNotIn(COLLECTION,self.store.inspect())
    def test_revoke_during_model_call_suppresses_old_result(self):
        self.approve();memory=self.app.memory;actor=self.actor
        class Revoking:
            async def ask(self,text,actor,event_id,tools):
                tools.execute('search_local_places',{'area':'花壇鄉'})
                memory.forget(actor,'concurrent-forget')
                return {'mode':'SYNTHETIC_CONCURRENT_REVOKE'}
        self.app.interpreter=Revoking();r=self.send('花壇有推荐吃的嗎？')
        self.assertIn('偏好剛被修改',json.dumps(r,ensure_ascii=False));self.assertNotIn('和米素食',json.dumps(r,ensure_ascii=False))
    def test_nearby_does_not_invent_location(self):
        r=self.send('這附近有推薦吃的嗎？');self.assertIn('想找哪個鄉鎮',json.dumps(r,ensure_ascii=False))
    def test_natural_forget_proposal_no_delete_before_click(self):
        self.approve();r=self.send('請忘掉之前的飲食設定')
        self.assertEqual(self.app.memory.inspect(self.actor)['status'],'saved')
        self.send(data=action_data(r,'m14:approve:'));self.assertEqual(self.app.memory.inspect(self.actor)['status'],'empty')
    def test_invalid_signature_rejected(self):
        r=post(self.client,self.config,event('bad','我要預約'),signature_override='bad')
        self.assertEqual(r.status_code,401);self.assertEqual(self.sender.sent,[])
    def test_revoked_grant_blocks_inspect(self):
        self.approve();self.store.atomic(lambda tx:tx.put('grants',grant_key(self.actor),{'allowed':False}))
        e=event('blocked','我的偏好');e['timestamp']=int(self.clock().timestamp()*1000)
        before=len(self.sender.sent);r=post(self.client,self.config,e)
        self.assertEqual(r.status_code,403);self.assertEqual(len(self.sender.sent),before)
    def test_inspect_displays_current_preference(self):
        self.approve();self.send('我的偏好');self.assertIn('目前偏好',json.dumps(self.sender.sent[-1],ensure_ascii=False))
    def test_all_generated_actions_within_line_limits(self):
        self.approve();self.send('花壇有推薦吃的嗎？')
        def walk(value):
            if isinstance(value,dict):
                if value.get('type')=='flex':self.assertLessEqual(len(value['altText'].encode('utf-16-le'))//2,400)
                if value.get('type')=='postback':self.assertLessEqual(len(value['data']),300)
                for v in value.values():walk(v)
            elif isinstance(value,list):
                for v in value:walk(v)
        walk(self.sender.sent)

    def test_area_button_preserves_stricter_saved_preference(self):
        p=self.app.memory.propose(self.actor,'vegan','strict-proposal')
        self.app.memory.approve(self.actor,p['token'])
        r=self.send(data='d14:area:花壇鄉')
        self.assertEqual(self.reports[-1]['tool_events'][0]['effective_arguments']['dietary_type'],'vegan')
        self.assertIn('沒有符合',json.dumps(r,ensure_ascii=False))
    def test_explicit_any_does_not_rewrite_saved_preference(self):
        self.approve()
        self.app.interpreter=ScriptedInterpreter({'本次不限飲食，花壇有什麼店？':('search_local_places',{'area':'花壇鄉','dietary_type':'any'})})
        self.send('本次不限飲食，花壇有什麼店？')
        self.assertEqual(self.reports[-1]['tool_events'][0]['effective_arguments']['dietary_type'],'any')
        self.assertEqual(self.app.memory.inspect(self.actor)['dietary_type'],'vegetarian')


class LiveHarnessTests(unittest.TestCase):
    def test_development_harness_works_with_explicit_stub_and_sqlite(self):
        # This verifies the harness itself, NOT real Google ADK / Gemini.
        import sys, types
        from unittest.mock import patch
        from .live_check import run
        from .engine import TurnTools
        fake = types.ModuleType('examples.day14.adk_router')
        fake.INSTRUCTION = 'OFFLINE_HARNESS_NOT_GEMINI'
        class Stub:
            def __init__(self, model): pass
            async def ask(self, question, actor, name, tools):
                tool = 'propose_dietary_memory' if name == 'propose' else 'search_local_places'
                args = {'dietary_type':'vegetarian'} if name == 'propose' else {
                    'area':'花壇鄉', 'dietary_type':'vegetarian' if name == 'single' else ''}
                result = tools.execute(tool, args)
                return {'mode':'OFFLINE_HARNESS_STUB_NOT_GEMINI', 'model_calls':0,
                        'tool_events':tools.calls, 'result':result, 'session_id':'SYNTHETIC-STUB-'+name,
                        'trace_linkage':{'trace_linked':True,'scope':'SYNTHETIC_STUB_NOT_ADK'}}
        fake.AdkInterpreter = Stub
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(sys.modules, {'examples.day14.adk_router':fake}):
                result = asyncio.run(run('SYNTHETIC', Path(temp)/'development-harness'))
            self.assertTrue(result['passed'])
            self.assertEqual(len(result['cases']), 4)
            self.assertEqual(result['model_calls_observed'], 0)
            self.assertEqual(result['distinct_reported_session_count'],4)
            root=Path(temp)/'development-harness'
            self.assertTrue((root/'snapshots/02-propose-after-test-consent.sqlite3').is_file())
            self.assertEqual(json.loads((root/'snapshots/01-single-before.json').read_text()),[])
            forgotten=json.loads((root/'snapshots/04-after_forget-after-model.json').read_text())
            self.assertNotIn('vegetarian',json.dumps(forgotten))
