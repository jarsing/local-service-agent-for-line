"""真正 ADK＋腳本模型；缺 SDK 是未執行／錯誤，不是假通過。"""
import tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from fixtures import ACTOR,sample_operation,seed_authority
from service import HandoffService
from store import SQLiteTestStore
from jobs import RecoveryWorker
from adk_bridge import Gate,make_tools,run_recovery


class AdkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=SQLiteTestStore(Path(self.tmp.name)/'store.sqlite3')
        self.now=datetime(2026,9,25,tzinfo=timezone.utc);clock=lambda:self.now
        seed_authority(self.store);self.service=HandoffService(self.store,clock=clock)
        self.args=self.service.prepare(ACTOR,sample_operation(),approved=True)
        self.worker=RecoveryWorker(self.service,clock=clock)
    async def test_runner_creates_and_fresh_session_reads(self):
        created=await run_recovery(self.service,ACTOR,self.args,self.worker)
        replay=await run_recovery(self.service,ACTOR,self.args,self.worker)
        self.assertEqual(replay['results'][-1]['status'],'already_created')
        self.assertEqual(created['results'][-1]['request_id'],replay['results'][-1]['request_id'])
    async def test_runner_recovers_after_committed_unknown(self):
        self.worker.step(ACTOR,self.args,fault='after_commit')
        result=await run_recovery(self.service,ACTOR,self.args,self.worker)
        self.assertEqual(result['results'][-1]['status'],'already_created');self.assertEqual(result['tool_calls'],1)
    async def test_runner_read_miss_then_same_key(self):
        self.worker.step(ACTOR,self.args,fault='before_write')
        result=await run_recovery(self.service,ACTOR,self.args,self.worker)
        self.assertEqual([v['status'] for v in result['results']],['pending_verification','request_created'])
        self.assertEqual(result['tool_calls'],2)
    async def test_runner_lookup_unavailable_preserves_unknown(self):
        self.worker.step(ACTOR,self.args,fault='after_commit')
        result=await run_recovery(self.service,ACTOR,self.args,self.worker,lookup_unavailable=True)
        self.assertEqual(result['results'][-1]['observation'],'lookup_unavailable')
    async def test_actual_schema_has_only_four_business_arguments(self):
        result=await run_recovery(self.service,ACTOR,self.args,self.worker)
        decls=[]
        for event in result['events']:
            if event['kind']=='MODEL_CALL':
                for tool in event['tools']:decls.extend(tool.get('function_declarations',[]))
        self.assertTrue(decls)
        for d in decls:
            schema=d.get('parameters') or d.get('parameters_json_schema')
            self.assertEqual(set(schema['properties']),{'idempotency_key','confirmation_id','request_text','event_id'})
    async def test_scripted_changed_key_is_detected(self):
        with self.assertRaisesRegex(AssertionError,'ARGUMENT'):await run_recovery(self.service,ACTOR,self.args,self.worker,behavior='changed_key')
        self.assertFalse(self.store.inspect().get('requests'))
    async def test_scripted_wrong_tool_is_detected(self):
        with self.assertRaisesRegex(AssertionError,'NAME'):await run_recovery(self.service,ACTOR,self.args,self.worker,behavior='wrong_tool')
        self.assertFalse(self.store.inspect().get('requests'))
    async def test_text_only_model_is_not_completion(self):
        with self.assertRaisesRegex(AssertionError,'ONE_TOOL'):await run_recovery(self.service,ACTOR,self.args,self.worker,behavior='no_tool')
        self.assertFalse(self.store.inspect().get('requests'))
    async def test_missing_tool_context_rejected(self):
        gate=Gate();gate.reset('create_handoff_request')
        tool=make_tools(self.service,ACTOR,self.args,self.worker,gate,lambda *a,**k:None)[0]
        self.assertEqual(tool(**self.args.values())['status'],'not_authorized')
    async def test_wrong_session_context_rejected(self):
        gate=Gate();gate.reset('create_handoff_request')
        tool=make_tools(self.service,ACTOR,self.args,self.worker,gate,lambda *a,**k:None)[0]
        context=SimpleNamespace(session=SimpleNamespace(user_id=ACTOR.user_id,id='wrong'),function_call_id='x')
        self.assertEqual(tool(**self.args.values(),tool_context=context)['status'],'not_authorized')
    async def test_tool_gate_one_call_per_turn(self):
        gate=Gate();gate.reset('create_handoff_request');gate.take()
        with self.assertRaises(RuntimeError):gate.take()
    async def test_emitted_command_contains_no_answer(self):
        result=await run_recovery(self.service,ACTOR,self.args,self.worker)
        for e in result['events']:
            if e['kind']=='HARNESS_MESSAGE':self.assertEqual(set(e['command']),{'expected_tool','send_args'})
        self.assertEqual(result['restored_scope'],'task_reference_only')
    async def test_cross_process_adk_after_commit(self):
        from demo import run_demo
        folder,report=run_demo(Path(self.tmp.name)/'cross',selected=['after_commit'],adk=True)
        self.assertTrue(report['success'],report)
        self.assertNotEqual(*report['cases'][0]['pids'])

if __name__=='__main__':unittest.main()
