"""離線 BaseLlm 替身：依入口腳本提出工具呼叫；絕不是 Gemini 品質證據。"""
from __future__ import annotations
import json
from typing import AsyncGenerator, Any
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import PrivateAttr
from policy import client_text


class ScriptedRecoveryModel(BaseLlm):
    model: str = 'local-day10-scripted'
    behavior: str = 'normal'
    _calls: int = PrivateAttr(default=0)

    async def generate_content_async(self, llm_request, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        self._calls += 1
        # 最後一則 user 文字是可信測試入口 JSON；尋找其後是否已有工具回覆。
        command = None
        reply: dict[str, Any] | None = None
        for content in reversed(llm_request.contents):
            for part in getattr(content,'parts',None) or []:
                response = getattr(part,'function_response',None)
                if response is not None and reply is None:
                    reply = response.response
                text = getattr(part,'text',None)
                if text:
                    try:
                        value = json.loads(text)
                    except (TypeError,ValueError):
                        continue
                    if isinstance(value,dict) and 'expected_tool' in value:
                        command=value
                        break
            if command is not None:
                break
        if command is None:
            raise RuntimeError('SCRIPT_COMMAND_MISSING')
        if reply is not None:
            yield LlmResponse(content=types.Content(role='model',parts=[types.Part(text=client_text(reply))]))
            return
        if self.behavior == 'no_tool':
            yield LlmResponse(content=types.Content(role='model',parts=[types.Part(text='已完成，單號 fabricated。')]))
            return
        args = dict(command['send_args'])
        name = command['expected_tool']
        if self.behavior == 'changed_key':
            args['idempotency_key'] = 'wrong-key-from-script'
        if self.behavior == 'wrong_tool':
            name = 'reconcile_handoff_request' if name == 'create_handoff_request' else 'create_handoff_request'
        yield LlmResponse(content=types.Content(role='model',parts=[types.Part(
            function_call=types.FunctionCall(name=name,args=args,id=f'call-day10-{self._calls}'))]))
