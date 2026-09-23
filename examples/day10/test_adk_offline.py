"""真正 ADK＋固定腳本模型；相依套件缺少應整組失敗，不當成略過通過。"""
from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from google.adk.tools import ToolContext
from adk_bridge import ToolGate, make_tools
from records import sqlite_rows
from runtime import run_case
from scenarios import prepare_case
from scripted_model import ScriptedRecoveryModel


class AdkRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='local-day10-adk-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    async def run_model(self,name='after_commit',behavior='normal'):
        self.case=prepare_case(name,self.root/name)
        return await run_case(ScriptedRecoveryModel(behavior=behavior),self.case,self.root/name,mode='OFFLINE_ADK')

    async def test_actual_runner_recovers_committed_receipt(self):
        report=await self.run_model()
        self.assertTrue(report['technical_checks_passed'],report['error'])
        self.assertEqual([s['result']['status'] for s in report['steps']],['pending_verification','already_created'])
        self.assertEqual(report['tool_calls'],2)
        self.assertEqual(report['final_rows'][0]['request_id'],report['steps'][-1]['result']['request_id'])

    async def test_actual_runner_read_miss_then_same_key_retry(self):
        report=await self.run_model('before_write')
        self.assertTrue(report['technical_checks_passed'],report['error'])
        self.assertEqual([s['rows_after'] for s in report['steps']],[0,0,1])
        self.assertEqual(report['tool_calls'],3)

    async def test_actual_runner_lookup_unavailable_keeps_unknown(self):
        report=await self.run_model('lookup_unavailable')
        self.assertTrue(report['technical_checks_passed'],report['error'])
        self.assertEqual(report['steps'][-1]['result']['status'],'pending_verification')
        self.assertEqual(report['tool_calls'],2)
        self.assertEqual(len(report['final_rows']),1)

    async def test_actual_runner_baseline_creates_once(self):
        report=await self.run_model('baseline')
        self.assertTrue(report['technical_checks_passed'],report['error'])
        self.assertEqual(report['tool_calls'],1)

    async def test_no_tool_natural_language_is_not_evidence(self):
        report=await self.run_model(behavior='no_tool')
        self.assertFalse(report['technical_checks_passed'])
        self.assertEqual(report['tool_calls'],0)
        self.assertEqual(sqlite_rows(self.case.db_path),[])

    async def test_model_changed_key_is_rejected_before_write(self):
        report=await self.run_model('baseline',behavior='changed_key')
        self.assertFalse(report['technical_checks_passed'])
        self.assertEqual(sqlite_rows(self.case.db_path),[])
        events=[e for e in self.case.trace.events if e['kind']=='TOOL_EXECUTED']
        self.assertEqual(events[0]['result']['status'],'operation_binding_mismatch')

    async def test_model_cannot_choose_wrong_phase_tool(self):
        report=await self.run_model('baseline',behavior='wrong_tool')
        self.assertFalse(report['technical_checks_passed'])
        self.assertEqual(sqlite_rows(self.case.db_path),[])

    async def test_actual_schema_has_only_four_business_arguments(self):
        report=await self.run_model('baseline')
        self.assertTrue(report['technical_checks_passed'],report['error'])
        declarations=[]
        for event in self.case.trace.events:
            if event['kind']=='MODEL_CALL':
                for tool in event['tools']:
                    declarations.extend(tool.get('function_declarations',[]))
        self.assertTrue(declarations)
        self.assertEqual({d['name'] for d in declarations},
            {'create_handoff_request','reconcile_handoff_request'})
        for declaration in declarations:
            schema=declaration.get('parameters') or declaration.get('parameters_json_schema') or {}
            self.assertEqual(set(schema.get('properties',{})),
                {'idempotency_key','confirmation_id','request_text','event_id'})

    async def test_missing_context_cannot_create(self):
        case=prepare_case('baseline',self.root/'baseline')
        result=make_tools(case,ToolGate())[0](**case.args.tool_args())
        self.assertEqual(result['status'],'not_authorized')
        self.assertEqual(sqlite_rows(case.db_path),[])

    async def test_wrong_session_cannot_create(self):
        case=prepare_case('baseline',self.root/'baseline')
        context=SimpleNamespace(session=SimpleNamespace(user_id=case.actor.user_id,id='wrong-session'),function_call_id='test')
        result=make_tools(case,ToolGate())[0](**case.args.tool_args(),tool_context=context)
        self.assertEqual(result['status'],'not_authorized')
        self.assertEqual(sqlite_rows(case.db_path),[])

    async def test_unknown_application_status_precedes_lookup_call(self):
        report=await self.run_model()
        self.assertTrue(report['technical_checks_passed'],report['error'])
        events=self.case.trace.events
        pending=next(e['sequence'] for e in events if e['kind']=='CLIENT_STATUS' and e['result']['status']=='pending_verification')
        lookup=next(e['sequence'] for e in events if e['kind']=='TOOL_REQUESTED' and e['name']=='reconcile_handoff_request')
        self.assertLess(pending,lookup)
        for event in events:
            if event['kind']=='HARNESS_MESSAGE':
                self.assertNotIn('fault',event['command'])
                self.assertNotIn('database_rows',event['command'])

    async def test_tool_gate_rejects_second_call_in_same_turn(self):
        gate=ToolGate(); gate.take()
        with self.assertRaisesRegex(RuntimeError,'TOOL_CALL_LIMIT'): gate.take()


if __name__=='__main__':
    unittest.main(verbosity=2)
