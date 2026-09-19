"""載入真正的 ADK，使用腳本化模型驗證工具迴圈；全程封鎖網路連線。"""
from __future__ import annotations
import asyncio
from unittest.mock import patch
from catalog import load_cases, TOOL_NAME
from runtime import run_turn


def scripted(case, *, with_tool=True, skip_tool=False):
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types
    from pydantic import PrivateAttr
    class ScriptedModel(BaseLlm):
        model: str = "offline-scripted-model"
        _step: int = PrivateAttr(default=0)
        async def generate_content_async(self,llm_request,stream=False):
            self._step+=1
            if self._step==1 and with_tool and not skip_tool:
                yield LlmResponse(content=types.Content(role="model",parts=[types.Part(function_call=types.FunctionCall(
                    name=TOOL_NAME,args=case['query'],id='test-call-1'))]),finish_reason=types.FinishReason.STOP)
                return
            responses=[p.function_response for c in llm_request.contents for p in (c.parts or []) if p.function_response is not None]
            if with_tool and not skip_tool and not responses:
                raise AssertionError("ADK 未將工具結果送回模型替身。")
            yield LlmResponse(content=types.Content(role="model",parts=[types.Part.from_text(text="【離線模型替身】這段文字用來檢查 ADK 介面。")]),finish_reason=types.FinishReason.STOP)
    return ScriptedModel()


def check():
    results=[]
    with patch('socket.socket.connect',side_effect=RuntimeError('OFFLINE_NETWORK_BLOCKED')):
        for case in load_cases():
            for enabled in (False,True):
                result=asyncio.run(run_turn(case,with_tool=enabled,test_model=scripted(case,with_tool=enabled),model="OFFLINE_SCRIPTED_MODEL"))
                results.append(result)
        case=load_cases()[0]
        missing=asyncio.run(run_turn(case,with_tool=True,test_model=scripted(case,skip_tool=True),model="OFFLINE_SCRIPTED_MODEL"))
    schemas=[e for r in results for e in r['events'] if e['kind']=='TOOL_SCHEMA' and e.get('tools')]
    checks={'eight_turns_recorded':all(r['status']=='RECORDED' for r in results),
            'actual_function_executed':all(r['tool_calls']==1 for r in results if r['condition']=='with_tool'),
            'tool_schema_observed':bool(schemas),
            'unsupported_lookup_claim_detected':missing['status']=='TRACE_MISMATCH'}
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'turns':results+[missing],
            'google_live_calls':0,'line_live_calls':0}
