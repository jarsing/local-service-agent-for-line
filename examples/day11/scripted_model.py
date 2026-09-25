"""固定腳本模型。只用於真正 ADK 的接線驗證，不能代表 Gemini 品質。"""
import json
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import PrivateAttr


def result_text(result):
    if result['status'] in ('request_created','already_created'):
        return f"原詢問的請求編號是 {result['request_id']}。這是已保存的請求，尚未通知真人。"
    if result['status']=='pending_verification':return '這次結果仍待查證，保留原操作識別。'
    return '這次狀態是 '+result['status']+'，請先處理確認或權限。'


class ScriptedTaskModel(BaseLlm):
    model:str='local-day11-scripted'
    behavior:str='normal'
    _calls:int=PrivateAttr(default=0)
    async def generate_content_async(self,llm_request,stream=False):
        self._calls+=1;command=None;reply=None
        for content in reversed(llm_request.contents):
            for part in content.parts or []:
                response=getattr(part,'function_response',None)
                if response is not None and reply is None:reply=response.response
                text=getattr(part,'text',None)
                if not text:continue
                try:value=json.loads(text)
                except (ValueError,TypeError):continue
                if isinstance(value,dict) and 'expected_tool' in value:command=value;break
            if command is not None:break
        if command is None:raise RuntimeError('SCRIPT_COMMAND_MISSING')
        if reply is not None:
            yield LlmResponse(content=types.Content(role='model',parts=[types.Part(text=result_text(reply))]));return
        if self.behavior=='no_tool':
            yield LlmResponse(content=types.Content(role='model',parts=[types.Part(text='已完成（刻意設計的反例）。')]));return
        args=dict(command['send_args']);name=command['expected_tool']
        if self.behavior=='changed_key':args['idempotency_key']='wrong-key-from-script'
        if self.behavior=='wrong_tool':
            name='reconcile_handoff_request' if name=='create_handoff_request' else 'create_handoff_request'
        yield LlmResponse(content=types.Content(role='model',parts=[types.Part(function_call=
            types.FunctionCall(name=name,args=args,id=f'call-day11-{self._calls}'))]))
