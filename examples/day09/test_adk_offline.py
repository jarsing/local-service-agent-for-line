"""真實 ADK Runner 搭配模型替身；請用已安裝 ADK 的 Python 執行。"""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from adk_bridge import make_handoff_tool, actor_resolver, ToolBudget
from day08_gateway import Actor, Day08Gateway
from handoff import HandoffService
from demo import QUESTION, tool_args
from runtime import run_two_turns
from scripted_model import ScriptedHandoffModel

class AdkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.actor=Actor('local-demo','demo-user','sdk-session')
        self.gateway=Day08Gateway()
        self.service=HandoffService(Path(self.temp.name)/'db.sqlite3',self.gateway,lambda a:a==self.actor)
        self.offer=self.gateway.prepare(self.actor,QUESTION)
        self.gateway.record_user_decision(self.actor,self.offer['confirmation_id'],approved=True)
        self.args=tool_args(self.offer)
    async def run_model(self,requests):
        model=ScriptedHandoffModel(model='day09-test',requests=requests)
        return await run_two_turns(model,self.service,self.actor,self.args,mode='OFFLINE_ADK',origin='reader_local')

    async def test_two_runner_turns_create_and_replay_same_request(self):
        report=await self.run_model([self.args,self.args])
        self.assertTrue(report['success'],report)
        self.assertEqual(report['model_calls'],4)
        self.assertEqual(report['final_count'],1)
        self.assertEqual([r['result']['status'] for r in report['results']],['request_created','already_created'])
        self.assertTrue(report['trace_checks']['tool_result_returned'])

    async def test_model_changed_text_reaches_conflict_guard(self):
        changed={**self.args,'request_text':'請問停車位置？'}
        report=await self.run_model([self.args,changed])
        self.assertFalse(report['success'])
        self.assertEqual(report['results'][1]['result']['status'],'idempotency_conflict')
        self.assertEqual(report['final_count'],1)

    async def test_model_without_confirmation_creates_no_row(self):
        bad={**self.args,'confirmation_id':'invented'}
        report=await self.run_model([bad,bad])
        self.assertFalse(report['success'])
        self.assertEqual(report['final_count'],0)
        self.assertEqual(report['results'][0]['result']['status'],'unconfirmed_operation')

    async def test_tool_schema_does_not_expose_actor_or_context(self):
        report=await self.run_model([self.args,self.args])
        captured=[x['tools'] for x in report['events'] if x['kind']=='MODEL_CALL']
        self.assertTrue(captured)
        declarations=[]
        for group in captured:
            for tool in group:
                declarations.extend(tool.get('function_declarations',[]))
        self.assertTrue(declarations,'需保存 ADK 實際送給模型的函式宣告')
        for d in declarations:
            parameters=d.get('parameters') or d.get('parameters_json_schema') or {}
            props=parameters.get('properties',{})
            self.assertTrue({'idempotency_key','confirmation_id','request_text','event_id'} <= set(props))
            self.assertFalse({'tenant_id','user_id','permitted','tool_context'} & set(props))

    async def test_missing_context_is_not_authorized(self):
        events=[]
        tool=make_handoff_tool(self.service,actor_resolver(self.actor),ToolBudget(),lambda *a,**k:events.append(k))
        result=tool(**self.args,tool_context=None)
        self.assertEqual(result['status'],'not_authorized')
        self.assertEqual(self.service.count(),0)

    async def test_model_invented_key_cannot_duplicate_submission(self):
        report=await self.run_model([{**self.args,'idempotency_key':'invented-key'},self.args])
        self.assertFalse(report['success'])
        self.assertEqual(report['results'][0]['result']['status'],'invalid_idempotency_key')
        self.assertEqual(self.service.count(),1)

    async def test_plain_model_text_is_not_tool_completion(self):
        class NoToolModel(BaseLlm):
            async def generate_content_async(self,req,stream=False):
                yield LlmResponse(content=types.Content(role='model',parts=[types.Part(text='我想這樣就完成了。')]))
        report=await run_two_turns(NoToolModel(model='no-tool-test'),self.service,self.actor,self.args,
                                  mode='OFFLINE_ADK',origin='reader_local')
        self.assertFalse(report['success'])
        self.assertEqual(report['results'],[])
        self.assertEqual(self.service.count(),0)

if __name__=='__main__':
    unittest.main(verbosity=2)
