"""真正 ADK Runner＋腳本模型。缺 SDK 會非零退出，不能列略過後算綠燈。"""
import unittest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from .adk_query import AdkQuery
from .catalog_view import CatalogView
from .identity import make_actor
from .testing import settings,RAW_USER

class ScriptedSearch(BaseLlm):
    model:str='local-day12-scripted'
    no_tool:bool=False
    async def generate_content_async(self,llm_request,stream=False):
        seen=any(getattr(p,'function_response',None) is not None
                 for c in llm_request.contents for p in c.parts or [])
        if seen or self.no_tool:
            yield LlmResponse(content=types.Content(role='model',parts=[types.Part(text='腳本回覆，不是真實 Gemini。')]))
        else:
            yield LlmResponse(content=types.Content(role='model',parts=[types.Part(function_call=
                types.FunctionCall(name='search_local_events',args={'date':'','area':'花壇','keyword':''},id='d12-search-1'))]))

class AdkTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_runner_tool_trace(self):
        actor=make_actor(settings('unused.sqlite3'),RAW_USER)
        report=await AdkQuery('scripted',model_override=ScriptedSearch()).ask('花壇集合？',actor,'evt1',CatalogView())
        self.assertEqual(report['mode'],'ADK_SCRIPTED');self.assertEqual(report['tool_calls'],1)
        self.assertEqual(report['result']['events'][0]['meeting_point'],None)
        self.assertEqual(report['input'],'花壇集合？')
    async def test_text_only_is_not_tool_evidence(self):
        actor=make_actor(settings('unused.sqlite3'),RAW_USER)
        with self.assertRaisesRegex(RuntimeError,'UNVERIFIED_TOOL_TRACE'):
            await AdkQuery('scripted',model_override=ScriptedSearch(no_tool=True)).ask('花壇集合？',actor,'evt2',CatalogView())
    def test_gemini_retry_parameter_constructs(self):
        # 不發網路；核對當前安裝版本真的接受這個設定。
        from google.adk.models.google_llm import Gemini
        m=Gemini(model='gemini-test-configuration-only',retry_options=types.HttpRetryOptions(attempts=1))
        self.assertEqual(m.retry_options.attempts,1)
