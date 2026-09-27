"""真正 ADK + Gemini 路線。每個回合全新 Session；工具後直接由固定模板回覆。
沒有把語料映射表冒充 NLU，也沒有把模型文字當成工具執行證據。
"""
import asyncio
import inspect
import secrets
import time
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import ToolContext
from google.genai import types

from .model_contract import INSTRUCTION, POLICY_VERSION, session_state, instruction_sha256
from .trace_contract import verify_triplet


class AdkInterpreter:
    mode='ADK_GEMINI'
    def __init__(self,model_id,*,model_override=None):
        if not model_id: raise ValueError('EXPLICIT_MODEL_REQUIRED')
        self.model_id,self.override=model_id,model_override

    async def ask(self,question,actor,event_id,tools):
        sid='day14-'+secrets.token_hex(12)
        state=session_state(tools.snapshot, tools.places)
        model_inputs=[]
        records=[];requests=[];responses=[];usage=[];model_texts=[];calls=0
        def before(callback_context,llm_request):
            nonlocal calls
            # The callback rejects another request before allowing it to be sent.
            if calls>=1: raise RuntimeError('ONE_MODEL_CALL_PER_TURN')
            tools.memory.assert_revision(actor, tools.snapshot['revision'])
            calls+=1
            # Kept only in this ephemeral result; default production routing never persists it.
            model_inputs.append({
                'model': llm_request.model,
                'contents': [c.model_dump(mode='json', exclude_none=True) for c in llm_request.contents],
                'config': llm_request.config.model_dump(mode='json', exclude_none=True),
            })
        def invoke(name,args,context):
            session=getattr(context,'session',None)
            if not session or session.user_id!=actor.user_id or session.id!=sid:
                raise PermissionError('TOOL_SESSION_MISMATCH')
            if context.state.get('day14_preference_revision') != tools.snapshot['revision']:
                raise PermissionError('TOOL_CONTEXT_REVISION_MISMATCH')
            result=tools.execute(name,args)
            context.actions.skip_summarization=True
            records.append({'kind':'TOOL_EXECUTED','id':context.function_call_id,'name':name,
                            'args':args,'result':result})
            return result
        def search_local_places(tool_context:ToolContext,area:str='',dietary_type:str='',keyword:str='')->dict:
            """依鄉鎮、明示飲食類型及店名查公開店家；未提供飲食類型留空，由後端取用已同意偏好。"""
            return invoke('search_local_places',dict(area=area,dietary_type=dietary_type,keyword=keyword),tool_context)
        def search_local_events(tool_context:ToolContext,date:str='',area:str='',keyword:str='')->dict:
            """查活動日期、區域與名稱。資料是已標示的歷史快照，不能據此預約。"""
            return invoke('search_local_events',dict(date=date,area=area,keyword=keyword),tool_context)
        def propose_dietary_memory(dietary_type:str,tool_context:ToolContext,area:str='',keyword:str='')->dict:
            """明確要記住或更正未來飲食偏好時提議一項 enum；不會保存，必須等人按同意。"""
            return invoke('propose_dietary_memory',dict(dietary_type=dietary_type,area=area,keyword=keyword),tool_context)
        def show_local_help(tool_context:ToolContext,reason:str='')->dict:
            """未支援預約或需求不明，提供查活動、查蔬食、留下詢問三個入口。"""
            return invoke('show_local_help',dict(reason=reason),tool_context)
        def request_memory_management(action:str,tool_context:ToolContext,dietary_type:str='')->dict:
            """action 為 inspect/update/forget；update 應提供素別。只有提案，沒有直接保存或刪除權。"""
            return invoke('request_memory_management',dict(action=action,dietary_type=dietary_type),tool_context)
        agent=LlmAgent(name='local_day14',model=self.override or Gemini(model=self.model_id,
                       retry_options=types.HttpRetryOptions(attempts=1)),instruction=INSTRUCTION,
                       tools=[search_local_places,search_local_events,propose_dietary_memory,show_local_help,request_memory_management],
                       before_model_callback=before,
                       generate_content_config=types.GenerateContentConfig(temperature=0,max_output_tokens=512,
                           thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)))
        sessions=InMemorySessionService()
        await sessions.create_session(app_name='local_day14',user_id=actor.user_id,session_id=sid,state=state)
        runner=Runner(app_name='local_day14',agent=agent,session_service=sessions)
        start=time.perf_counter()
        async def consume():
            stream=runner.run_async(user_id=actor.user_id,session_id=sid,
                new_message=types.Content(role='user',parts=[types.Part(text=question)]),
                run_config=RunConfig(max_llm_calls=2,streaming_mode=StreamingMode.NONE))
            try:
                async for e in stream:
                    if getattr(e,'error_code',None): raise RuntimeError('ADK_EVENT_ERROR')
                    for c in e.get_function_calls() or []: requests.append({'kind':'TOOL_REQUESTED','id':c.id,'name':c.name,'args':c.args})
                    for r in e.get_function_responses() or []: responses.append({'kind':'TOOL_RESPONSE','id':r.id,'name':r.name,'result':r.response})
                    for part in getattr(getattr(e,'content',None),'parts',[]) or []:
                        if getattr(part,'text',None) and not getattr(part,'thought',False): model_texts.append(part.text)
                    u=getattr(e,'usage_metadata',None)
                    if u: usage.append(u.model_dump(mode='json',exclude_none=True))
            finally: await stream.aclose()
        try:
            await asyncio.wait_for(consume(),timeout=18)
            linkage=verify_triplet(requests,records,responses)
            tools.memory.assert_revision(actor,tools.snapshot['revision'])
            return {'mode':'ADK_SCRIPTED' if self.override else self.mode,'result':tools.last,
                    'model_calls':calls,'tool_calls':len(records),'trace_linkage':linkage,
                    'policy_version':POLICY_VERSION,'instruction_sha256':instruction_sha256(),
                    'session_context':state,'model_inputs':model_inputs,'tool_events':tools.calls,
                    'adk_events':requests+records+responses,'session_id':sid,'usage':usage,
                    'model_texts':model_texts,'duration_seconds':round(time.perf_counter()-start,3)}
        except Exception as exc:
            # Only a caller explicitly enabled for a synthetic audit persists this report.
            exc.report={'mode':'ADK_SCRIPTED' if self.override else self.mode,'session_id':sid,
                        'model_calls':calls,'tool_events':tools.calls,'adk_events':requests+records+responses,
                        'policy_version':POLICY_VERSION,'session_context':state,'model_inputs':model_inputs,
                        'usage':usage,'model_texts':model_texts,'error_type':type(exc).__name__,
                        'duration_seconds':round(time.perf_counter()-start,3)}
            raise
        finally:
            # No memory-bank import, history replay, persistent conversation or summary.
            await sessions.delete_session(app_name='local_day14',user_id=actor.user_id,session_id=sid)
            close=getattr(runner,'close',None)
            if close:
                value=close()
                if inspect.isawaitable(value): await value
