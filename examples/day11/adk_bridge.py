"""新的 ADK Session 接上已保存的任務參照；不宣稱恢復全部聊天歷史。"""
from __future__ import annotations
import asyncio,inspect,json,time
from typing import Any
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.run_config import RunConfig,StreamingMode
from google.adk.tools import ToolContext
from google.genai import types
from domain import SendArgs,operation_id,pending,rejected
from service import authorized,check_binding
from store import StoreUnavailable
from scripted_model import ScriptedTaskModel

INSTRUCTION="""以繁體中文說明 LOCAL 請求狀態。這次是固定腳本模型接線驗證。
可信應用端提供 expected_tool 與 send_args，逐字沿用四參數，只呼叫指定工具一次。
工具回待查證就說待查證，回單號就引用該單號。請求保存與真人受理分開。
不猜測不存在的同意、原對話內容或資料庫結果。"""


class Gate:
    def __init__(self):self.total=0;self.this_turn=0;self.expected_tool=None;self.receipt_only=False
    def reset(self,tool,receipt_only=False):
        self.this_turn=0;self.expected_tool=tool;self.receipt_only=receipt_only
    def take(self):
        if self.this_turn>=1 or self.total>=3:raise RuntimeError('TOOL_CALL_LIMIT')
        self.this_turn+=1;self.total+=1


def plan_next(service,actor,args):
    def read(tx):
        ok=authorized(tx,actor);binding=tx.get('bindings',operation_id(actor,args))
        job=tx.get('jobs',operation_id(actor,args))
        if not ok:return {'result':rejected('not_authorized')}
        issue=check_binding(binding,actor,args)
        if issue:return {'result':rejected(issue)}
        if not job:raise RuntimeError('工作紀錄不存在。')
        if job['phase']=='done':return {'tool':'reconcile_handoff_request','receipt_only':True}
        if job['phase']=='paused':return {'result':pending('recovery_paused')}
        return {'tool':'reconcile_handoff_request' if job['phase']=='lookup' else 'create_handoff_request','receipt_only':False}
    try:return service.store.atomic(read,read_only=True)
    except StoreUnavailable:return {'result':pending('lookup_unavailable')}


def make_tools(service,actor,bound_args,worker,gate,emit,*,lookup_unavailable=False):
    def invoke(name,context,args):
        gate.take()
        session=getattr(context,'session',None);call_id=getattr(context,'function_call_id',None)
        if session is None or session.user_id!=actor.user_id or session.id!=actor.session_id:
            value=rejected('not_authorized')
        elif args!=bound_args:value=rejected('operation_binding_mismatch')
        elif name!=gate.expected_tool:value=rejected('sequence_rejected')
        elif gate.receipt_only:value=service.lookup(actor,args)
        else:value=worker.step(actor,args,expected_tool=name,lookup_unavailable=lookup_unavailable)
        emit('TOOL_EXECUTED',name=name,id=call_id,args=args.values(),result=value)
        return value

    def create_handoff_request(idempotency_key:str,confirmation_id:str,request_text:str,event_id:str,
                               tool_context:ToolContext|None=None)->dict[str,Any]:
        """依已確認的原參數送出一次；權限、期限與順序由後端檢查。"""
        return invoke('create_handoff_request',tool_context,SendArgs(idempotency_key,confirmation_id,request_text,event_id))

    def reconcile_handoff_request(idempotency_key:str,confirmation_id:str,request_text:str,event_id:str,
                                  tool_context:ToolContext|None=None)->dict[str,Any]:
        """以原鍵讀回已保存的請求；查詢路徑不建立請求。"""
        return invoke('reconcile_handoff_request',tool_context,SendArgs(idempotency_key,confirmation_id,request_text,event_id))
    return [create_handoff_request,reconcile_handoff_request]


def check_turn(events,args,expected):
    requested=[e for e in events if e['kind']=='TOOL_REQUESTED']
    executed=[e for e in events if e['kind']=='TOOL_EXECUTED']
    responses=[e for e in events if e['kind']=='TOOL_RESPONSE']
    if not len(requested)==len(executed)==len(responses)==1:raise AssertionError('ONE_TOOL_REQUEST_EXECUTION_RESPONSE')
    a,b,c=requested[0],executed[0],responses[0]
    if not a['id'] or not a['id']==b['id']==c['id']:raise AssertionError('TOOL_CALL_ID_MISMATCH')
    if not a['name']==b['name']==c['name']==expected:raise AssertionError('TOOL_NAME_MISMATCH')
    if not a['args']==b['args']==args.values():raise AssertionError('TOOL_ARGUMENT_MISMATCH')
    if b['result']!=c['response']:raise AssertionError('TOOL_RECEIPT_MISMATCH')
    return b['result']


async def run_recovery(service,actor,args,worker,*,emit=lambda *a,**k:None,lookup_unavailable=False,behavior='normal'):
    events=[];turns=[];results=[];calls=0;turn_calls=0
    def record(kind,**values):
        item={'kind':kind,**values};events.append(item);emit(kind,**values)
    def before(callback_context,llm_request):
        nonlocal calls,turn_calls
        if calls>=9 or turn_calls>=3:raise RuntimeError('MODEL_CALL_LIMIT')
        calls+=1;turn_calls+=1
        tools=getattr(getattr(llm_request,'config',None),'tools',None) or []
        record('MODEL_CALL',number=calls,tools=[t.model_dump(mode='json',exclude_none=True) for t in tools])
    gate=Gate();tools=make_tools(service,actor,args,worker,gate,record,lookup_unavailable=lookup_unavailable)
    model=ScriptedTaskModel(behavior=behavior)
    agent=LlmAgent(name='local_day11_resume',model=model,instruction=INSTRUCTION,tools=tools,before_model_callback=before)
    sessions=InMemorySessionService()
    # 新 ADK Session 沒有載入 Day 10 聊天 events，只放本次已授權的任務參照。
    session=await sessions.create_session(app_name='local_day11',user_id=actor.user_id,session_id=actor.session_id,
        state={'active_operation':operation_id(actor,args)})
    runner=Runner(app_name='local_day11',agent=agent,session_service=sessions)
    try:
        for turn in range(1,4):
            plan=plan_next(service,actor,args)
            if 'result' in plan:results.append(plan['result']);break
            expected=plan['tool'];gate.reset(expected,plan['receipt_only']);turn_calls=0;start=len(events)
            command={'expected_tool':expected,'send_args':args.values()}
            record('HARNESS_MESSAGE',source='trusted_application',command=command)
            final=[]
            async def consume():
                stream=runner.run_async(user_id=actor.user_id,session_id=session.id,
                    new_message=types.Content(role='user',parts=[types.Part(text=json.dumps(command,ensure_ascii=False))]),
                    run_config=RunConfig(max_llm_calls=3,streaming_mode=StreamingMode.NONE))
                try:
                    async for event in stream:
                        if getattr(event,'error_code',None):raise RuntimeError('ADK_EVENT_ERROR')
                        for call in event.get_function_calls() or []:
                            record('TOOL_REQUESTED',name=call.name,id=call.id,args=call.args)
                        for response in event.get_function_responses() or []:
                            record('TOOL_RESPONSE',name=response.name,id=response.id,response=response.response)
                        text=''.join(p.text for p in getattr(getattr(event,'content',None),'parts',None) or []
                            if isinstance(getattr(p,'text',None),str) and not getattr(p,'thought',False))
                        record('ADK_VISIBLE_EVENT',text=text,is_final=bool(event.is_final_response()))
                        if event.is_final_response() and text:final.append(text)
                finally:await stream.aclose()
            started=time.perf_counter();await asyncio.wait_for(consume(),timeout=45)
            result=check_turn(events[start:],args,expected)
            text='\n'.join(final)
            if not text.strip():raise AssertionError('MISSING_FINAL_TEXT')
            if result['status'] in ('already_created','request_created'):
                verified=service.lookup(actor,args)
                if verified.get('request_id')!=result['request_id']:raise AssertionError('DATABASE_RECEIPT_MISMATCH')
                if result['request_id'] not in text:raise AssertionError('RECEIPT_ID_NOT_IN_FINAL_TEXT')
            results.append(result);turns.append({'turn':turn,'tool':expected,'final_text':text,
                'duration_seconds':round(time.perf_counter()-started,3),'model_calls':turn_calls})
            if result['status']!='pending_verification' or result.get('observation') not in ('not_found','submit_timeout'):
                break
    finally:
        close=getattr(runner,'close',None)
        if close:
            r=close()
            if inspect.isawaitable(r):await r
    report={'mode':'OFFLINE_ADK_SCRIPTED','results':results,'model_turns':turns,'tool_calls':gate.total,
        'model_calls':calls,'events':events,'restored_scope':'task_reference_only','semantic_review':'scripted_not_gemini'}
    record('ADK_RUN_FINISHED',model_calls=calls,tool_calls=gate.total,results=results)
    return report
