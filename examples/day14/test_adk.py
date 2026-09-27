"""需真正 ADK 的離線整合。缺 SDK 即載入失敗，不 skip、不列為通過。"""
from pathlib import Path
import tempfile
import unittest
import json
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field
from examples.day12.inherit import Actor, SQLiteTestStore, grant_key
from .memory import PreferenceMemory
from .engine import TurnTools
from .adk_router import AdkInterpreter

class ScriptedModel(BaseLlm):
    model:str='day14-scripted-not-gemini'
    tool:str='search_local_places'
    parameters:dict=Field(default_factory=lambda:{'area':'花壇鄉','dietary_type':'','keyword':''})
    no_tool:bool=False
    async def generate_content_async(self,llm_request,stream=False):
        if any(getattr(p,'function_response',None) for c in llm_request.contents for p in c.parts or []):
            raise AssertionError('NO_SECOND_CALL_WITH_TOOL_RESULTS')
        if self.no_tool:
            yield LlmResponse(content=types.Content(role='model',parts=[types.Part(text='I saved it (not true).')]))
        else:
            yield LlmResponse(content=types.Content(role='model',parts=[types.Part(function_call=
                types.FunctionCall(name=self.tool,args=self.parameters,id='SYNTHETIC-D14-CALL'))]))

class AdkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=SQLiteTestStore(Path(self.tmp.name)/'s.sqlite3');self.actor=Actor('synthetic-t','synthetic-u','A')
        self.store.atomic(lambda tx:tx.put('grants',grant_key(self.actor),{'allowed':True,'actor':{'tenant_id':self.actor.tenant_id,'user_id':self.actor.user_id}}))
        self.memory=PreferenceMemory(self.store,'SYNTHETIC_'+('a'*32))
    async def ask(self,model=None):
        return await AdkInterpreter('test-only',model_override=model or ScriptedModel()).ask('合成問題',self.actor,'synthetic-event',TurnTools(self.memory,self.actor))
    async def test_real_runner_executes_places(self):
        r=await self.ask();self.assertEqual(r['mode'],'ADK_SCRIPTED');self.assertEqual(r['model_calls'],1)
        self.assertEqual(r['result']['places'][0]['name'],'和米素食')
    async def test_two_real_sessions_apply_same_preference(self):
        p=self.memory.propose(self.actor,'vegetarian','x');self.memory.approve(self.actor,p['token'])
        a=await self.ask();b=await self.ask()
        self.assertNotEqual(a['session_id'],b['session_id']);self.assertEqual(b['result']['query']['dietary_type'],'vegetarian')
    async def test_proposal_does_not_write(self):
        r=await self.ask(ScriptedModel(tool='propose_dietary_memory',parameters={'dietary_type':'vegetarian'}))
        self.assertEqual(r['result']['status'],'memory_proposal_requested');self.assertEqual(self.memory.inspect(self.actor)['status'],'empty')
    async def test_text_without_tool_is_rejected(self):
        with self.assertRaises(RuntimeError): await self.ask(ScriptedModel(no_tool=True))
    async def test_forget_before_new_session_clears_effective_query(self):
        p=self.memory.propose(self.actor,'vegan','x');self.memory.approve(self.actor,p['token'])
        self.memory.forget(self.actor,'f');r=await self.ask()
        self.assertEqual(r['result']['query']['dietary_type'],'any')
    async def test_all_trace_ids_match(self):
        r=await self.ask();self.assertEqual(len(r['adk_events']),3)
        self.assertEqual(len({e['id'] for e in r['adk_events']}),1)

    async def test_real_adk_expands_public_state_context(self):
        r=await self.ask()
        serialized=json.dumps(r['model_inputs'],ensure_ascii=False)
        self.assertIn('available_areas',serialized)
        self.assertIn('花壇鄉',serialized)
        self.assertNotIn('{day14_catalog_context}',serialized)
    async def test_same_question_keeps_saved_value_out_of_model_input(self):
        p=self.memory.propose(self.actor,'vegan','first');self.memory.approve(self.actor,p['token'])
        a=await self.ask()
        p=self.memory.propose(self.actor,'ovo_lacto','second');self.memory.approve(self.actor,p['token'])
        b=await self.ask()
        self.assertEqual(a['model_inputs'],b['model_inputs'])
        self.assertEqual(a['tool_events'][0]['effective_arguments']['dietary_type'],'vegan')
        self.assertEqual(b['tool_events'][0]['effective_arguments']['dietary_type'],'ovo_lacto')
    async def test_context_is_not_model_supplied_argument(self):
        r=await self.ask()
        for e in r['adk_events']:
            if e['kind'] in ('TOOL_REQUESTED','TOOL_EXECUTED'):
                self.assertNotIn('tool_context',e['args'])
                self.assertNotIn('approved',e['args'])
        self.assertTrue(r['trace_linkage']['trace_linked'])
