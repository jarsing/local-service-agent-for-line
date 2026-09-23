"""兩回合受控 ADK 實驗：Gemini/替身使用同一組參數呼叫建單工具兩次。"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import inspect
import json
import time
from typing import Any
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from adk_bridge import make_handoff_tool, actor_resolver, build_agent, ToolBudget, INSTRUCTION, TOOL_NAME
from day08_gateway import Actor
from handoff import HandoffService
from provenance import environment, source_snapshot

class Trace:
    def __init__(self):
        self.events: list[dict[str,Any]] = []
        self.responses: list[dict[str,Any]] = []
        self.model_calls = 0
        self.turn_calls = 0
        self.turn = 0
        self.runtime_error = False
    def emit(self,kind,**values):
        self.events.append({'kind':kind,'turn':self.turn,**values})
    def before_model(self,callback_context,llm_request):
        if self.model_calls >= 6 or self.turn_calls >= 3:
            raise RuntimeError('MODEL_CALL_LIMIT')
        self.model_calls += 1
        self.turn_calls += 1
        tools=getattr(getattr(llm_request,'config',None),'tools',None) or []
        self.emit('MODEL_CALL',number=self.model_calls,
            tools=[t.model_dump(mode='json',exclude_none=True) for t in tools])
    def after_model(self,callback_context,llm_response):
        usage=getattr(llm_response,'usage_metadata',None)
        raw={name:getattr(usage,name,None) for name in
             ('prompt_token_count','candidates_token_count','thoughts_token_count','total_token_count')}
        self.responses.append(raw)
        if getattr(llm_response,'error_code',None):
            self.runtime_error=True
        self.emit('MODEL_RESPONSE',usage=raw,model_version=getattr(llm_response,'model_version',None),
                  finish_reason=str(getattr(llm_response,'finish_reason',None)))
    def observe(self,event):
        if len(self.events)>160:
            raise RuntimeError('EVENT_LIMIT')
        if getattr(event,'error_code',None):
            self.runtime_error=True
        for fc in event.get_function_calls() or []:
            self.emit('TOOL_REQUESTED',name=fc.name,id=fc.id,args=fc.args)
        for fr in event.get_function_responses() or []:
            self.emit('TOOL_RESPONSE',name=fr.name,id=fr.id,response=fr.response)
        visible_text=''.join(
            part.text for part in getattr(getattr(event,'content',None),'parts',None) or []
            if isinstance(getattr(part,'text',None),str) and not getattr(part,'thought',False))
        self.emit('ADK_VISIBLE_EVENT',event_id=getattr(event,'id',None),
                  author=getattr(event,'author',None),text=visible_text,
                  is_final=bool(event.is_final_response()))

async def run_two_turns(model: Any, service: HandoffService, actor: Actor,
                        send_args: dict[str,str], *, mode: str, origin: str) -> dict[str,Any]:
    trace=Trace();budget=ToolBudget();sources=source_snapshot()
    tool=make_handoff_tool(service,actor_resolver(actor),budget,trace.emit)
    agent=build_agent(model,tool,trace.before_model,trace.after_model)
    sessions=InMemorySessionService()
    session=await sessions.create_session(app_name='local_day09',user_id=actor.user_id,session_id=actor.session_id)
    runner=Runner(app_name='local_day09',agent=agent,session_service=sessions)
    turns=[];results=[];error=None
    try:
        for turn,(label,prompt) in enumerate([
            ('第一次送出','請建立這份已確認內容的服務請求。'),
            ('同一組參數重送','我想再次核對送出結果，請使用完全相同的參數再呼叫一次工具。')],1):
            trace.turn=turn;trace.turn_calls=0;budget.next_turn()
            count_before=len(trace.events)
            text=prompt+'\n送出參數（測試入口提供，仍須後端核對）：'+json.dumps(send_args,ensure_ascii=False)
            final_text=[];started=time.perf_counter()
            async def consume():
                stream=runner.run_async(user_id=actor.user_id,session_id=session.id,
                    new_message=types.Content(role='user',parts=[types.Part(text=text)]),
                    run_config=RunConfig(max_llm_calls=3,streaming_mode=StreamingMode.NONE))
                try:
                    async for event in stream:
                        trace.observe(event)
                        if event.is_final_response():
                            for part in getattr(getattr(event,'content',None),'parts',None) or []:
                                if isinstance(getattr(part,'text',None),str) and not getattr(part,'thought',False):
                                    final_text.append(part.text)
                finally:
                    await stream.aclose()
            await asyncio.wait_for(consume(),timeout=45)
            produced=[x for x in trace.events[count_before:] if x['kind']=='TOOL_EXECUTED']
            for x in produced:
                results.append({'label':label,'result':x['result'],'rows_after':x['rows_after']})
            turns.append({'label':label,'final_text':'\n'.join(final_text),
                          'duration_seconds':round(time.perf_counter()-started,3),'model_calls':trace.turn_calls})
    except Exception as exc:
        error={'type':type(exc).__name__,'http_code':getattr(exc,'code',None)}
        # 不將可能含金鑰或私人路徑的完整例外字串輸出至報告。
        if type(error['http_code']) is not int:
            error['http_code']=None
    finally:
        try:
            close=getattr(runner,'close',None)
            if close:
                closing=close()
                if inspect.isawaitable(closing):
                    await closing
        except Exception as exc:
            trace.emit('CLEANUP_WARNING',error_type=type(exc).__name__)
    actual=[x['result'].get('status') for x in results]
    ids=[x['result'].get('request_id') for x in results]
    executed=[x for x in trace.events if x['kind']=='TOOL_EXECUTED']
    returned=[x for x in trace.events if x['kind']=='TOOL_RESPONSE' and x.get('name')==TOOL_NAME]
    requested=[x for x in trace.events if x['kind']=='TOOL_REQUESTED' and x.get('name')==TOOL_NAME]
    exact_args=(len(executed)==2 and len(requested)==2
                and all(x['args']==send_args for x in executed+requested))
    matched=len(returned)==2 and all(a['result']==b['response'] for a,b in zip(executed,returned))
    event_ids_match=(len(requested)==2 and len(returned)==2
                     and all(a.get('id') and a.get('id')==b.get('id')
                             for a,b in zip(requested,returned)))
    textual=len(turns)==2 and len(ids)==2 and all(ids[i] and ids[i] in turns[i]['final_text'] for i in range(2))
    success=(error is None and not trace.runtime_error and actual==['request_created','already_created']
             and len(set(ids))==1 and service.count()==1 and exact_args and matched and event_ids_match and textual
             and source_snapshot()==sources)
    usage={name:sum(x[name] for x in trace.responses) if trace.responses and all(type(x[name]) is int for x in trace.responses) else None
           for name in ('prompt_token_count','candidates_token_count','thoughts_token_count','total_token_count')}
    return {'mode':mode,'origin':origin,'timestamp':datetime.now(timezone.utc).isoformat(),
        'success':success,'environment':environment(),'results':results,'model_turns':turns,
        'model_calls':trace.model_calls,'max_model_calls':6,'max_tool_calls':2,
        'usage':usage,'final_count':service.count(),'database_rows':service.inspect_rows(),
        'trace_checks':{'exact_args':exact_args,'tool_result_returned':matched,'function_call_ids_match':event_ids_match,'id_in_text':textual},
        'events':trace.events,'source_files':sources,'instruction':INSTRUCTION,
        'error':error,'semantic_review':'author_review_pending' if mode=='LIVE_GEMINI' else 'scripted_not_model_quality'}
