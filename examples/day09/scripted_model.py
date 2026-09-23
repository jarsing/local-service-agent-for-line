"""固定腳本替身；只測 ADK 介接，不能當 Gemini 品質實測。"""
from __future__ import annotations
from typing import Any, AsyncGenerator
from pydantic import PrivateAttr
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

class ScriptedHandoffModel(BaseLlm):
    requests: list[dict[str,Any]]
    _step: int = PrivateAttr(default=0)

    async def generate_content_async(self,req: LlmRequest,stream: bool=False) -> AsyncGenerator[LlmResponse,None]:
        step=self._step;self._step+=1
        if step%2==0:
            args=self.requests[min(step//2,len(self.requests)-1)]
            part=types.Part(function_call=types.FunctionCall(name='create_handoff_request',args=args,id=f'call-{step}'))
        else:
            result={}
            for content in reversed(req.contents or []):
                for p in content.parts or []:
                    fr=getattr(p,'function_response',None)
                    if fr and fr.name=='create_handoff_request':
                        result=fr.response
                        break
                if result: break
            status=result.get('status')
            if status in ('request_created','already_created'):
                text=f"請求單號 {result['request_id']}，目前等待真人受理。"
                if status=='already_created': text+='這次取得同一筆請求。'
            else:
                text=f"本次工具結果為 {status}，請核對確認內容。"
            part=types.Part(text=text)
        yield LlmResponse(content=types.Content(role='model',parts=[part]))
