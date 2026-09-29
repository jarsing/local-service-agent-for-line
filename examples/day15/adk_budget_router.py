"""Day 15 ADK adapter based on the supplied Day 14 router.

Fresh ADK Session + explicitly composed short context; original tool controls
are retained. Gemini/ADK execution is a separate validation layer.
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

from examples.day14.model_contract import session_state
from .policy import INSTRUCTION
from .session_budget import MODEL_ID, BudgetSessionManager
from .context_store import ContextJournal, project_result
from .token_counter import countable_envelope
import hashlib
from starlette.concurrency import run_in_threadpool
POLICY_VERSION = "day15-budget-v1"
def instruction_sha256():
    return hashlib.sha256(INSTRUCTION.encode()).hexdigest()
from examples.day14.trace_contract import verify_triplet


class BudgetAdkInterpreter:
    mode='ADK_GEMINI_DAY15'
    def __init__(self, model_id, *, counter, model_override=None, strategy="budget"):
        if model_id != MODEL_ID:
            raise ValueError("FIXED_SERIES_MODEL_REQUIRED")
        if strategy not in ("budget", "full_comparison"):
            raise ValueError("UNSUPPORTED_CONTEXT_STRATEGY")
        self.model_id, self.override = model_id, model_override
        self.counter, self.strategy = counter, strategy
        self.manager = BudgetSessionManager(
            max_turns=2 if strategy == "budget" else 20,
            limit=8192 if counter.unit == "tokens" else 30000,
            unit=counter.unit,
        )

    async def ask(self,question,actor,event_id,tools):
        sid='day15-'+secrets.token_hex(12)
        journal = ContextJournal(tools.memory)
        snapshot = await run_in_threadpool(journal.read, actor)
        if snapshot.preference_revision != tools.snapshot['revision']:
            raise PermissionError('CONTEXT_AND_PREFERENCE_MISMATCH')
        budget_report = None
        counter = self.counter.fork() if hasattr(self.counter, "fork") else self.counter
        state=session_state(tools.snapshot, tools.places)
        model_inputs=[]
        records=[];requests=[];responses=[];usage=[];model_texts=[];calls=0
        async def before(callback_context, llm_request):
            nonlocal calls, budget_report
            if calls >= 1:
                raise RuntimeError("ONE_MODEL_CALL_PER_TURN")
            await run_in_threadpool(journal.assert_current, actor, snapshot)
            config = llm_request.config.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
            envelope = countable_envelope(self.model_id, config)
            prepared = await self.manager.prepare(
                snapshot.window, question, envelope, counter
            )
            if self.strategy == "full_comparison" and prepared.removed_turns:
                raise RuntimeError("FULL_COMPARISON_EXCEEDED_LIMIT")
            await run_in_threadpool(journal.assert_current, actor, snapshot)
            llm_request.contents = [
                types.Content.model_validate(c) for c in prepared.request["contents"]
            ]
            budget_report = {
                "unit": prepared.unit, "input_units": prepared.measured_units,
                "measurements": list(prepared.measurements),
                "removed_turns": prepared.removed_turns,
                "kept_turns": len(prepared.window.turns),
                "summary": prepared.window.summary.__dict__,
                "input_limit": self.manager.limit, "output_limit": 512,
                "count_api": list(getattr(counter, "records", [])),
            }
            calls += 1
            model_inputs.append({
                "model": llm_request.model,
                "contents": prepared.request["contents"],
                "config": config,
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
        agent=LlmAgent(name='local_day15',include_contents='none',model=self.override or Gemini(model=self.model_id,
                       retry_options=types.HttpRetryOptions(attempts=1)),instruction=INSTRUCTION,
                       tools=[search_local_places,search_local_events,propose_dietary_memory,show_local_help,request_memory_management],
                       before_model_callback=before,
                       generate_content_config=types.GenerateContentConfig(temperature=0,max_output_tokens=512,
                           thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)))
        sessions=InMemorySessionService()
        await sessions.create_session(app_name='local_day15',user_id=actor.user_id,session_id=sid,state=state)
        runner=Runner(app_name='local_day15',agent=agent,session_service=sessions)
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
            # Save only a safe public projection; not raw text, diet, result or token.
            # Memory proposals/management are intentionally not context material.
            if tools.last.get("status") not in (
                "memory_proposal_requested", "memory_management_requested"
            ):
                await run_in_threadpool(
                    journal.append, actor, snapshot, event_id, project_result(tools.last)
                )
            return {'mode':'ADK_SCRIPTED' if self.override else self.mode,'result':tools.last,'budget':budget_report,
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
                        'usage':usage,'model_texts':model_texts,'budget':budget_report,'error_type':type(exc).__name__,
                        'duration_seconds':round(time.perf_counter()-start,3)}
            raise
        finally:
            # No memory-bank import, history replay, persistent conversation or summary.
            await sessions.delete_session(app_name='local_day15',user_id=actor.user_id,session_id=sid)
            close=getattr(runner,'close',None)
            if close:
                value=close()
                if inspect.isawaitable(value): await value
