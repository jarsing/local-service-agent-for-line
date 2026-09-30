"""Day 14 接回原 LINE Webhook。新偏好流程不保存回覆計畫／模型歷史／偏好快取。"""
from __future__ import annotations
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import time
from starlette.concurrency import run_in_threadpool
from examples.day13.bridge import FlexApplication
from examples.day12.main import create_app as original_create_app, open_store, STATUS_TEXT
from examples.day12.settings import Settings
from examples.day12.identity import make_actor
from examples.day12.delivery import EventLedger, LineReply
from examples.day12.inherit import utcnow, StoreUnavailable
from .memory import PreferenceMemory, PreferenceChanged, BadToken
from .engine import TurnTools, ScriptedInterpreter
from .places import PlacesCatalog
from . import messages as msg
from examples.day17 import messages as recovery_msg
from examples.day17.legacy_adapter import legacy_result_plan, legacy_failure_plan
from examples.day17.outcomes import CatalogChanged, ToolContractError

HELP_TEXT={'我要預約','預約','幫我預約','我想預約','功能','你好','開始','使用說明'}
INSPECT_TEXT={'我的偏好','查看飲食偏好','我記住了什麼'}
FORGET_TEXT={'忘記我的飲食偏好','刪除我的飲食偏好','撤回我的飲食偏好'}

class PrivateLedger(EventLedger):
    """Keep transport idempotency metadata, not raw queries, preference values or reply plans."""
    def __init__(self,store,secret,*,clock=utcnow):
        super().__init__(store,clock=clock);self.secret=secret.encode()
    def fingerprint(self,event):
        fields={k:event.get(k) for k in ('webhookEventId','type','timestamp','source','message','postback')}
        raw=json.dumps(fields,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
        return hmac.new(self.secret,raw,hashlib.sha256).hexdigest()
    def save_plan(self,claim,plan):
        raise RuntimeError('DAY14_DOES_NOT_PERSIST_REPLY_PLANS')

class MemoryApplication(FlexApplication):
    def __init__(self,settings,store,interpreter,sender,*,emit=None,clock=None,observer=None):
        # Parent receives a query object only for legacy types; free text is handled below.
        super().__init__(settings,store,interpreter,sender,emit=emit,clock=clock)
        self.clock=clock or utcnow
        self.memory=PreferenceMemory(store,settings.actor_key,clock=self.clock)
        self.ledger=PrivateLedger(store,settings.actor_key,clock=self.clock)
        self.interpreter=interpreter;self.places=PlacesCatalog()
        # Explicit observer is for synthetic tests / approved live audit, never enabled by default.
        self.observer=observer

    async def save_query_report(self,actor,event_id,report):
        # Day 12 trace storage is intentionally not used for the Day 14 memory path.
        return None

    def tools(self,actor):
        return TurnTools(self.memory,actor,places=self.places,events=self.catalog,clock=self.clock)

    @staticmethod
    def _plan(messages,result,revision=None):
        return {'messages':messages,'result':result,'memory_revision':revision}

    def _issued_at(self,event):
        timestamp=event.get('timestamp')
        if type(timestamp) not in (int,float): raise ValueError('EVENT_TIMESTAMP_REQUIRED')
        value=datetime.fromtimestamp(timestamp/1000,timezone.utc)
        if value.timestamp()>self.clock().timestamp()+60: raise ValueError('EVENT_FROM_FUTURE')
        return value

    async def _finalize(self,actor,event,result):
        rev=result.get('memory_revision')
        if rev is not None: await run_in_threadpool(self.memory.assert_revision,actor,rev)
        recovery=legacy_result_plan(self,result,place_formatter=msg.format_places)
        if recovery is not None: return recovery
        state=result['status']
        if state=='memory_proposal_requested':
            p=await run_in_threadpool(self.memory.propose,actor,result['dietary_type'],event['webhookEventId'],issued_at=self._issued_at(event))
            return self._plan([msg.consent_card(p)],{'status':p['status']},p['revision'])
        if state=='memory_management_requested':
            op=result['action']
            if op=='inspect':
                current=await run_in_threadpool(self.memory.inspect,actor)
                return self._plan([msg.memory_card(current)],{'status':'memory_inspected'},current['revision'])
            if op=='forget':
                p=await run_in_threadpool(self.memory.propose,actor,'',event['webhookEventId'],operation='forget',issued_at=self._issued_at(event))
                return self._plan([msg.consent_card(p)],{'status':p['status']},p['revision'])
            if result['dietary_type']:
                return await self._finalize(actor,event,{'status':'memory_proposal_requested','dietary_type':result['dietary_type'],'memory_revision':rev})
            return self._plan([msg.text('請告訴我未來想改用哪種飲食條件，例如「把我的偏好改成蛋奶素」。我會先請你確認。')],{'status':'memory_update_prompt'})
        if state=='events_result':
            return self._plan([msg.text(self.catalog.format_result(result['catalog_result']))],{'status':'events_result'},rev)
        if result.get('tool')=='search_local_places':
            return self._plan(msg.format_places(result),{'status':'places_'+state},rev)
        return self._plan([msg.help_card()],{'status':'help'})

    async def route(self,actor,event):
        data=event.get('postback',{}).get('data','') if event['type']=='postback' else ''
        text=event.get('message',{}).get('text','')
        eid=event['webhookEventId']
        # Authoritative controls work without Gemini. A natural-language guess never writes memory.
        if data.startswith(('m14:approve:','m14:cancel:')):
            verb,token=data[4:].split(':',1)
            try:
                fn=self.memory.approve if verb=='approve' else self.memory.cancel
                result=await run_in_threadpool(fn,actor,token)
            except (BadToken,ValueError):
                return self._plan([msg.text('這張記憶卡無法核對，沒有變更偏好。請輸入「我的偏好」。')],{'status':'invalid_memory_card'})
            return self._plan([msg.memory_card(result)],{'status':result['status']},result['revision'])
        if data=='m14:inspect' or text in INSPECT_TEXT:
            result=await run_in_threadpool(self.memory.inspect,actor)
            return self._plan([msg.memory_card(result)],{'status':'memory_inspected'},result['revision'])
        if data=='m14:forget' or text in FORGET_TEXT:
            result=await run_in_threadpool(self.memory.forget,actor,eid)
            return self._plan([msg.memory_card(result)],{'status':result['status']},result['revision'])
        if data=='m14:update':
            return self._plan([msg.text('請輸入「把我的偏好改成蛋奶素」等明確條件。按同意前仍使用原偏好。')],{'status':'memory_update_prompt'})
        if event['type']=='message' and text==recovery_msg.RETRY_TEXT:
            return self._plan([recovery_msg.retry_guide()],{'status':'retry_prompt'})
        if data=='d14:help' or text in HELP_TEXT:
            return self._plan([msg.help_card()],{'status':'help'})
        if data=='d14:places':
            return self._plan([msg.area_card(sorted({p['area'] for p in self.places.data['places']}))],{'status':'choose_area'})
        if data=='d14:enquiry':
            return self._plan([msg.text('請輸入「新需求：」加上希望窗口協助的事情。這會沿用花壇歷史教學詢問，先請你確認，並非預約或已通知窗口。')],{'status':'enquiry_guide'})
        if data=='d14:events' or data.startswith('d14:area:'):
            started=time.monotonic()
            try:
                tools=await run_in_threadpool(self.tools,actor)
                if data=='d14:events':
                    if not await run_in_threadpool(self.tasks.catalog_is_current,actor):
                        raise CatalogChanged()
                    result=await run_in_threadpool(tools.execute,'search_local_events',{'date':'','area':'花壇','keyword':''})
                else:
                    area=data[len('d14:area:'):]
                    if area not in {p['area'] for p in self.places.data['places']}: raise ValueError('UNSUPPORTED_AREA_BUTTON')
                    result=await run_in_threadpool(tools.execute,'search_local_places',{'area':area,'dietary_type':'' if tools.snapshot['dietary_type'] else 'vegetarian','keyword':''})
                if self.observer: self.observer({'mode':'DETERMINISTIC_BUTTON','tool_events':tools.calls})
                return await self._finalize(actor,event,result)
            except PreferenceChanged:
                return self._plan([msg.text('偏好剛被修改或忘記，這次結果先不套用。請再查一次。')],{'status':'preference_changed'})
            except PermissionError: raise
            except Exception as exc:
                return legacy_failure_plan(self,exc,started=started)
        # Reuse original typed confirmation/cancel/status/enquiry exactly. No new booking tool.
        if (data in ('status','text') or data.startswith(('confirm:','cancel:','status:','text:')) or
            text in STATUS_TEXT or text in ('文字版','目前任務文字版','好','確認','確認送出','需要手語志工支援') or
            text.startswith(('需要協助：','需要協助:','新需求：','新需求:'))):
            return await super().route(actor,event)
        if data or not isinstance(text,str) or not text.strip() or len(text)>1200:
            return self._plan([msg.help_card()],{'status':'unsupported_message'})
        if not await run_in_threadpool(self.ledger.model_budget,actor,self.settings.model_daily_limit):
            return self._plan([msg.text('今天的模型理解額度已用完。仍可用按鈕查資料、查看或忘記偏好。'),msg.help_card()],{'status':'model_budget_exhausted'})
        started=time.monotonic();query_phase='initialization'
        try:
            tools=await run_in_threadpool(self.tools,actor)
            query_phase='model'
            report=await self.interpreter.ask(text,actor,eid,tools)
            query_phase='result'
            # Trust the executed server tool result, not an interpreter's returned text/dict.
            if tools.last is None or len(tools.calls)!=1: raise ToolContractError('NO_EXECUTED_TOOL')
            if tools.last.get('status')=='events_result' and not await run_in_threadpool(self.tasks.catalog_is_current,actor):
                raise CatalogChanged()
            if self.observer: self.observer(report)
            return await self._finalize(actor,event,tools.last)
        except PreferenceChanged:
            return self._plan([msg.text('偏好剛被修改或忘記，這次結果先不套用。請再查一次。')],{'status':'preference_changed'})
        except PermissionError: raise
        except Exception as exc:
            return legacy_failure_plan(self,exc,started=started,model_stage=query_phase=='model')

    async def process(self,event):
        actor=make_actor(self.settings,event['source']['userId'])
        claim=await run_in_threadpool(self.ledger.begin,actor,event)
        if claim.get('skip'): return
        sending=False
        try:
            plan=await self.route(actor,event)
            # Do not persist this plan: preference cards / personalized results must not replay after forget.
            await run_in_threadpool(self.ledger.transition,claim,'sending')
            sending=True
            try:
                current=await run_in_threadpool(self.memory.inspect,actor)
                if plan.get('memory_revision') is not None and current['revision']!=plan['memory_revision']:
                    plan=self._plan([msg.text('偏好已變更，請重新查詢。')],{'status':'preference_changed'})
            except PermissionError:
                await run_in_threadpool(self.ledger.transition,claim,'reply_unknown');raise
            try: reply=await self.sender.send(event['replyToken'],plan['messages'])
            except Exception: reply={'accepted':False}
            await run_in_threadpool(self.ledger.transition,claim,'sent' if reply.get('accepted') else 'reply_unknown',reply.get('request_id'))
            self.emit('DAY14_TURN_FINISHED',status=plan['result']['status'],api_accepted=bool(reply.get('accepted')),
                      revision=self.revision,boot_id=self.boot_id)
        except PermissionError: raise
        except Exception:
            # Before sending, a retry re-evaluates the current memory. Never replay an old personalized plan.
            if not sending: await run_in_threadpool(self.ledger.transition,claim,'retryable')
            raise


def build_runtime():
    s=Settings.from_env()
    if s.model_mode=='gemini':
        if os.getenv('GOOGLE_GENAI_USE_VERTEXAI','false').lower() not in ('','0','false'):
            raise ValueError('DAY14_USES_EXISTING_DEVELOPER_API_ROUTE')
        if not (os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')): raise ValueError('EXPLICIT_GEMINI_KEY_REQUIRED')
        from .adk_router import AdkInterpreter
        interpreter=AdkInterpreter(s.model_id)
    else: interpreter=ScriptedInterpreter()
    return MemoryApplication(s,open_store(s),interpreter,LineReply(s.channel_token))

def create_app(runtime=None):
    app=original_create_app(runtime)
    @asynccontextmanager
    async def lifespan(app):
        engine=runtime or build_runtime();app.state.runtime=engine
        try: yield
        finally:
            close=getattr(engine.store,'close',None)
            if close: close()
    app.router.lifespan_context=lifespan
    return app

app=create_app()
