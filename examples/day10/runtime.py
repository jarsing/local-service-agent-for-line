"""真正 ADK Runner；每回合取得原文後才依可信狀態安排下一次查回。"""
from __future__ import annotations
import asyncio
import inspect
import json
import time
from pathlib import Path
from typing import Any
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from adk_bridge import ToolGate, make_tools, build_agent, INSTRUCTION
from demo import snapshot
from evidence import sha256
from proof import check_case, check_adk_trace, require
from records import sqlite_rows

USAGE_FIELDS = ('prompt_token_count','candidates_token_count','thoughts_token_count','total_token_count')


class ModelObserver:
    def __init__(self, trace):
        self.trace=trace; self.calls=0; self.turn_calls=0; self.responses=[]; self.runtime_error=False

    def before(self, callback_context, llm_request):
        if self.calls >= 9 or self.turn_calls >= 3:
            raise RuntimeError('MODEL_CALL_LIMIT')
        self.calls += 1; self.turn_calls += 1
        tools=getattr(getattr(llm_request,'config',None),'tools',None) or []
        self.trace.emit('MODEL_CALL', number=self.calls, tools=[
            t.model_dump(mode='json',exclude_none=True) for t in tools])

    def after(self, callback_context, llm_response):
        usage=getattr(llm_response,'usage_metadata',None)
        values={name:getattr(usage,name,None) for name in USAGE_FIELDS}
        self.responses.append(values)
        if getattr(llm_response,'error_code',None): self.runtime_error=True
        self.trace.emit('MODEL_RESPONSE', usage=values,
            model_version=getattr(llm_response,'model_version',None),
            finish_reason=str(getattr(llm_response,'finish_reason',None)))

    def observe(self, event):
        if getattr(event,'error_code',None): self.runtime_error=True
        for call in event.get_function_calls() or []:
            self.trace.emit('TOOL_REQUESTED',name=call.name,id=call.id,args=call.args)
        for response in event.get_function_responses() or []:
            self.trace.emit('TOOL_RESPONSE',name=response.name,id=response.id,response=response.response)
        text=''.join(p.text for p in getattr(getattr(event,'content',None),'parts',None) or []
                     if isinstance(getattr(p,'text',None),str) and not getattr(p,'thought',False))
        self.trace.emit('ADK_VISIBLE_EVENT',event_id=getattr(event,'id',None),
                        author=getattr(event,'author',None),text=text,is_final=bool(event.is_final_response()))
        return text if event.is_final_response() else ''


async def run_case(model: Any, case, directory: Path, *, mode: str) -> dict[str, Any]:
    observer=ModelObserver(case.trace); gate=ToolGate()
    agent=build_agent(model,make_tools(case,gate),observer.before,observer.after)
    sessions=InMemorySessionService()
    session=await sessions.create_session(app_name='local_day10',user_id=case.actor.user_id,
                                          session_id=case.actor.session_id)
    runner=Runner(app_name='local_day10',agent=agent,session_service=sessions)
    turns=[]; steps=[]; error=None; proof=None
    snapshot(case.db_path,directory/'step-00.sqlite3')
    try:
        while case.controller.next_tool:
            require(len(turns)<3,'RECOVERY_TURN_LIMIT')
            phase=case.controller.phase; expected_tool=case.controller.next_tool
            case.trace.turn=len(turns)+1; observer.turn_calls=0; gate.next_turn()
            start_index=len(case.trace.events)
            command={'expected_tool':expected_tool,'phase':phase,'send_args':case.args.tool_args(),
                     'purpose':'本回合以原參數呼叫一次指定工具，再依工具回覆說明。'}
            # 本訊息不含 fault 位置、資料列或被丟棄的後端回條。
            text=json.dumps(command,ensure_ascii=False)
            case.trace.emit('HARNESS_MESSAGE',source='trusted_application',command=command)
            parts=[]; started=time.perf_counter()
            async def consume():
                stream=runner.run_async(user_id=case.actor.user_id,session_id=session.id,
                    new_message=types.Content(role='user',parts=[types.Part(text=text)]),
                    run_config=RunConfig(max_llm_calls=3,streaming_mode=StreamingMode.NONE))
                try:
                    async for event in stream:
                        final=observer.observe(event)
                        if final: parts.append(final)
                finally:
                    await stream.aclose()
            await asyncio.wait_for(consume(),timeout=45)
            final_text='\n'.join(parts)
            turns.append({'phase':phase,'expected_tool':expected_tool,'final_text':final_text,
                          'duration_seconds':round(time.perf_counter()-started,3),
                          'model_calls':observer.turn_calls})
            this_turn=case.trace.events[start_index:]
            check_adk_trace(this_turn,case.args)
            executed=[e for e in this_turn if e['kind']=='TOOL_EXECUTED']
            require(len(executed)==1,'ONE_TOOL_PER_TURN')
            require(executed[0]['name']==expected_tool,'EXPECTED_PHASE_TOOL')
            result=executed[0]['result']
            require(case.controller.phase != phase,'CONTROLLER_DID_NOT_ADVANCE')
            require(bool(final_text.strip()),'MISSING_FINAL_TEXT')
            if result['status'] in ('request_created','already_created'):
                require(result['request_id'] in final_text,'RECEIPT_ID_NOT_IN_FINAL_TEXT')
            steps.append({'phase':phase,'result':result,'rows_after':len(sqlite_rows(case.db_path))})
            snapshot(case.db_path,directory/f'step-{len(steps):02d}.sqlite3')
        require(not observer.runtime_error,'MODEL_RUNTIME_ERROR')
        proof=check_case(case,[s['result'] for s in steps])
        check_adk_trace(case.trace.events,case.args)
    except Exception as exc:
        code=getattr(exc,'code',None)
        error={'type':type(exc).__name__,'http_code':code if type(code) is int else None}
        if type(exc).__name__=='EvidenceMismatch': error['check']=str(exc)
        # 不把 SDK 例外中可能含有金鑰的原始字串寫入公開檔。
    finally:
        try:
            close=getattr(runner,'close',None)
            if close:
                result=close()
                if inspect.isawaitable(result): await result
        except Exception as exc:
            case.trace.emit('CLEANUP_WARNING',error_type=type(exc).__name__)
    case.trace.save(directory/'events.jsonl')
    usage={name:sum(x[name] for x in observer.responses)
           if observer.responses and all(type(x[name]) is int for x in observer.responses) else None
           for name in USAGE_FIELDS}
    return {'name':case.name,'mode':mode,'technical_checks_passed':error is None,
            'send_args':case.args.tool_args(),'confirmation':case.confirmation,
            'confirmation_source':'test_harness_explicit_approval','steps':steps,'proof':proof,
            'model_turns':turns,'model_calls':observer.calls,'model_call_limit':9,
            'tool_calls':gate.total,'tool_call_limit':3,'usage':usage,'error':error,
            'final_rows':sqlite_rows(case.db_path),'database':directory.name+'/handoff.sqlite3',
            'files':{p.name:sha256(p) for p in sorted(directory.iterdir()) if p.is_file()},
            'semantic_review':'author_review_pending' if mode=='LIVE_GEMINI' else 'scripted_not_model_quality',
            'instruction':INSTRUCTION}
