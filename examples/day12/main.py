"""LINE → 受控工作 → Reply。所有必要工作在回 200 前完成，沒有記憶體背景佇列。"""
import asyncio
from contextlib import asynccontextmanager
import json
import os
import secrets
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .settings import Settings
from .identity import verify_signature, make_actor
from .inherit import SQLiteTestStore, StoreUnavailable, SendArgs, key, operation_id, authorized
from .catalog_view import CatalogView
from .tasks import LineTasks
from .delivery import EventLedger, LineReply, Busy
from .messages import text_message, offer_message, render_result

STATUS_TEXT={'查詢原單','剛才那單有成功嗎？','我剛才送出的單進度如何？'}

class Application:
    def __init__(self, settings, store, query, sender, *, emit=None, clock=None):
        self.settings=settings.validate();self.store=store;self.query=query;self.sender=sender
        self.catalog=CatalogView();kwargs={} if clock is None else {'clock':clock}
        self.tasks=LineTasks(store,self.catalog,**kwargs);self.ledger=EventLedger(store,**kwargs)
        self.boot_id=secrets.token_hex(16)
        self.revision=os.environ.get('K_REVISION','local-process')
        self.emit=emit or (lambda kind,**data:print(json.dumps({'kind':kind,**data},ensure_ascii=False),flush=True))
        self.emit('PROCESS_STARTED',boot_id=self.boot_id,revision=self.revision,pid=os.getpid(),
                  source_commit=os.environ.get('LOCAL_SOURCE_COMMIT','unrecorded'),backend=store.mode)

    async def route(self, actor, event):
        value=event.get('postback',{}).get('data','') if event['type']=='postback' else ''
        message=event.get('message',{});text=message.get('text','') if message.get('type')=='text' else ''
        if value=='status' or text in STATUS_TEXT:
            result=await run_in_threadpool(self.tasks.status,actor)
            return {'messages':[render_result(result)],'result':result}
        if value.startswith(('confirm:','cancel:')):
            kind,cid=value.split(':',1)
            if not 1<=len(cid)<=100: raise ValueError('INVALID_CONFIRMATION_ID')
            result=await run_in_threadpool(self.tasks.decide,actor,cid,kind=='confirm')
            return {'messages':[render_result(result)],'result':result}
        if value:
            return {'messages':[text_message('這個操作目前不支援，請查詢原單。')],'result':{'status':'unsupported_postback'}}
        if text in ('好','確認','確認送出'):
            result=await run_in_threadpool(self.tasks.status,actor)
            if result['status']=='awaiting_confirmation':
                current=await run_in_threadpool(self.tasks.status,actor)
                return {'messages':[render_result(current)],'result':current}
            return {'messages':[text_message('請使用這份內容下方的「確認送出」按鈕，或查詢原單。')],
                    'result':{'status':'explicit_confirmation_required'}}
        if text.startswith(('需要協助：','需要協助:','新需求：','新需求:')) or text=='需要手語志工支援':
            new=text.startswith('新需求')
            body=text[5:] if text.startswith(('需要協助：','需要協助:')) else text[4:] if new else text
            result=await run_in_threadpool(self.tasks.offer,actor,body,event['webhookEventId'],new_intent=new)
            if result['status'] in ('offer_created','offer_existing'):
                current=await run_in_threadpool(self.tasks.status,actor)
                return {'messages':[render_result(current)],'result':current}
            if result['status']=='active_task_exists':
                current=await run_in_threadpool(self.tasks.status,actor)
                return {'messages':[render_result(current),text_message('這段對話已有任務。另一件事請用「新需求：」開頭。')],
                        'result':current}
            return {'messages':[render_result(result)],'result':result}
        if not text or len(text)>1200:
            return {'messages':[text_message('本示範只收 1200 字以內文字；可先問「花壇場次在哪裡集合？」。')],
                    'result':{'status':'unsupported_message'}}
        if not await run_in_threadpool(self.tasks.catalog_is_current,actor):
            return {'messages':[text_message('採用資料已更新，請等候示範版本同步後再查詢。')],
                    'result':{'status':'catalog_not_current'}}
        allowed=await run_in_threadpool(self.ledger.model_budget,actor,self.settings.model_daily_limit)
        if not allowed:
            return {'messages':[text_message('今天的教學模型查詢額度已用完；查詢原單與確認仍可操作。')],
                    'result':{'status':'model_budget_exhausted'}}
        try:
            report=await self.query.ask(text,actor,event['webhookEventId'],self.catalog)
        except Exception as exc:
            # 只記型別，不把含金鑰或原問句的例外丟進公開 log。
            self.emit('QUERY_UNAVAILABLE',error_type=type(exc).__name__)
            partial=getattr(exc,'report',None)
            if isinstance(partial,dict):
                await self.save_query_report(actor,event['webhookEventId'],partial)
            return {'messages':[text_message('這次查詢暫時沒有取得可核對的工具結果。原單查詢仍可使用。')],
                    'result':{'status':'query_unavailable'}}
        self.emit('QUERY_RESULT',boot_id=self.boot_id,revision=self.revision,mode=report['mode'],
                  model_calls=report['model_calls'],tool_calls=report['tool_calls'],
                  query=report['result'].get('query'),catalog_version=report['result'].get('catalog_version'))
        # 完整 trace 只留在授權的測試回報／受限的證據 sink；不預設公開私人自然語言。
        await self.save_query_report(actor,event['webhookEventId'],report)
        if not await run_in_threadpool(self.tasks.catalog_is_current,actor):
            return {'messages':[text_message('查詢期間採用資料已更新，請稍後重新查詢。')],
                    'result':{'status':'catalog_changed_during_query'}}
        return {'messages':[text_message(self.catalog.format_result(report['result']))],
                'result':{'status':'query_result','mode':report['mode'],'query':report['result'].get('query')}}

    async def save_query_report(self, actor, event_id, report):
        trace_id=key(actor.tenant_id,event_id)
        def save_trace(tx):
            existing=tx.get('line_traces',trace_id)
            if existing is None:
                tx.create('line_traces',trace_id,{'report':report,'boot_id':self.boot_id,
                    'revision':self.revision,'data_scope':'private_allowlisted_demo',
                    'event_key':trace_id})
        await run_in_threadpool(self.store.atomic,save_trace)

    async def process(self, event):
        actor=make_actor(self.settings,event['source']['userId'])
        claim=await run_in_threadpool(self.ledger.begin,actor,event)
        if claim.get('skip'): return
        try:
            plan=claim['plan'] or await self.route(actor,event)
            if claim['plan'] is None: await run_in_threadpool(self.ledger.save_plan,claim,plan)
        except Exception:
            await run_in_threadpool(self.ledger.transition,claim,'retryable')
            raise
        result=plan['result'];record={
            'event_key':key(actor.tenant_id,event['webhookEventId']), 'boot_id':self.boot_id,
            'revision':self.revision,'status':result['status'], 'request_id':result.get('request_id'),
            'operation_id':result.get('request',{}).get('operation_id') or
                (operation_id(actor,SendArgs(**result['args'])) if result.get('args') else None),
            'confirmation_id':result.get('request',{}).get('args',{}).get('confirmation_id')}
        self.emit('BUSINESS_RESULT',**record)
        # 在可能造成 LINE 副作用前先保存 sending；不對同事件盲目發第二次 Reply。
        await run_in_threadpool(self.ledger.transition,claim,'sending')
        try: reply=await self.sender.send(event['replyToken'],plan['messages'])
        except Exception as exc:
            reply={'accepted':False,'error_type':type(exc).__name__}
        phase='sent' if reply.get('accepted') else 'reply_unknown'
        await run_in_threadpool(self.ledger.transition,claim,phase,reply.get('request_id'))
        self.emit('LINE_REPLY_RESULT',event_key=record['event_key'],boot_id=self.boot_id,revision=self.revision,
                  api_accepted=bool(reply.get('accepted')),line_request_id=reply.get('request_id'))


def open_store(settings):
    if settings.backend=='sqlite-test': return SQLiteTestStore(settings.sqlite_path)
    from .inherit import DAY11
    from firestore_store import FirestoreStore
    return FirestoreStore(settings.project,settings.namespace,cloud=settings.backend=='cloud',
                          approve_cloud=settings.approve_external)

def build_runtime():
    s=Settings.from_env();store=open_store(s)
    if s.model_mode=='gemini':
        if os.environ.get('GOOGLE_GENAI_USE_VERTEXAI','false').lower() not in ('false','0',''):
            raise ValueError('本篇採 Developer API，請清除其他模型路徑設定。')
        if not os.environ.get('GOOGLE_API_KEY') and not os.environ.get('GEMINI_API_KEY'):
            raise ValueError('本篇採 Gemini Developer API，需明示私人 key。')
        from .adk_query import AdkQuery
        query=AdkQuery(s.model_id)
    else:
        from .query import StubQuery
        query=StubQuery()
    return Application(s,store,query,LineReply(s.channel_token))

def create_app(runtime=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.runtime=runtime or build_runtime()
        yield
        close=getattr(app.state.runtime.store,'close',None)
        if close: close()
    app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    @app.get('/healthz')
    async def healthz():
        # 只判斷 HTTP 行程是否能回應，不查 Firestore／Gemini／LINE。
        return {'status':'ok'}
    @app.post('/webhook')
    async def webhook(request:Request):
        engine=request.app.state.runtime
        chunks=[];length=0
        async for chunk in request.stream():
            length+=len(chunk)
            if length>65536: return JSONResponse({'error':'body_too_large'},status_code=413)
            chunks.append(chunk)
        body=b''.join(chunks)
        if not verify_signature(engine.settings.channel_secret,body,request.headers.get('x-line-signature','')):
            return JSONResponse({'error':'invalid_signature'},status_code=401)
        try:
            payload=json.loads(body)
            if not isinstance(payload,dict) or payload.get('destination')!=engine.settings.destination:
                return JSONResponse({'error':'wrong_destination'},status_code=403)
            events=payload.get('events')
            if not isinstance(events,list) or len(events)>10: raise ValueError('INVALID_EVENTS')
            for event in events:
                if not isinstance(event,dict): raise ValueError('INVALID_EVENT')
                source=event.get('source') or {}
                if source.get('type')!='user' or source.get('userId') not in engine.settings.allowed_users:
                    continue
                if event.get('type') not in ('message','postback'): continue
                if event.get('mode','active')!='active': continue
                if not isinstance(event.get('webhookEventId'),str) or not event['webhookEventId']:
                    raise ValueError('MISSING_EVENT_ID')
                if not isinstance(event.get('replyToken'),str) or not event['replyToken']: continue
                await engine.process(event)
        except PermissionError:
            # 已驗簽但被撤權：不回覆私人資料，也不重新授權。
            return JSONResponse({'error':'not_authorized'},status_code=403)
        except (Busy,StoreUnavailable):
            return JSONResponse({'error':'temporarily_unavailable'},status_code=503)
        except (ValueError,TypeError,KeyError):
            return JSONResponse({'error':'invalid_event'},status_code=400)
        except Exception as exc:
            engine.emit('WEBHOOK_FAILURE',error_type=type(exc).__name__)
            return JSONResponse({'error':'processing_error'},status_code=503)
        return {'ok':True}
    return app

app=create_app()
