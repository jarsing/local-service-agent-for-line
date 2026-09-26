"""LINE 事件去重不等於業務冪等；Reply API 結果不明時不盲目重送。"""
from datetime import timedelta
import json
import secrets
from .inherit import key, iso, utcnow, time_of, clone, authorized

class Busy(RuntimeError): pass

class EventLedger:
    def __init__(self, store, *, clock=utcnow): self.store,self.clock=store,clock

    @staticmethod
    def fingerprint(event):
        # replyToken 與 redelivery flag 可以改變；它們不代表另一項業務意圖。
        fields={k:event.get(k) for k in ('webhookEventId','type','timestamp','source','message','postback')}
        return key(json.dumps(fields,ensure_ascii=False,sort_keys=True,separators=(',',':')))

    def begin(self, actor, event):
        ident=key(actor.tenant_id,event['webhookEventId']); digest=self.fingerprint(event)
        token=secrets.token_hex(16);now=self.clock()
        def claim(tx):
            if not authorized(tx,actor): raise PermissionError('not_authorized')
            row=tx.get('line_events',ident)
            if row:
                if row['digest']!=digest: raise ValueError('EVENT_CONTENT_CONFLICT')
                if row['phase'] in ('sending','sent','reply_unknown'): return {'skip':True}
                if row['phase']=='processing' and time_of(row['until'])>now: raise Busy('EVENT_INFLIGHT')
                if row['attempts']>=2: return {'skip':True}
                row['attempts']+=1
            else:
                row={'digest':digest,'attempts':1,'plan':None}
            row.update(phase='processing',token=token,until=iso(now+timedelta(seconds=120)))
            tx.put('line_events',ident,row)
            return {'id':ident,'token':token,'plan':clone(row['plan'])}
        return self.store.atomic(claim)

    def save_plan(self, claim, plan):
        def change(tx):
            row=tx.get('line_events',claim['id'])
            if not row or row['token']!=claim['token']: raise Busy('STALE_EVENT_OWNER')
            row['plan']=clone(plan);tx.put('line_events',claim['id'],row)
        self.store.atomic(change)

    def transition(self, claim, phase, request_id=None):
        def change(tx):
            row=tx.get('line_events',claim['id'])
            if not row or row['token']!=claim['token']: raise Busy('STALE_EVENT_OWNER')
            row['phase']=phase;row['until']=iso(self.clock())
            if request_id: row['line_request_id']=request_id
            tx.put('line_events',claim['id'],row)
        self.store.atomic(change)

    def model_budget(self, actor, maximum):
        day=self.clock().date().isoformat();ident=key(actor.tenant_id,actor.user_id,day)
        def reserve(tx):
            if not authorized(tx,actor): raise PermissionError('not_authorized')
            row=tx.get('line_budget',ident) or {'day':day,'attempts':0}
            if row['attempts']>=maximum: return False
            row['attempts']+=1;tx.put('line_budget',ident,row);return True
        return self.store.atomic(reserve)

class LineReply:
    def __init__(self, token):
        if not token: raise ValueError('需要 LINE_CHANNEL_ACCESS_TOKEN。')
        self.token=token

    async def send(self, reply_token, messages):
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(8,connect=3)) as client:
            response=await client.post('https://api.line.me/v2/bot/message/reply',
                headers={'Authorization':'Bearer '+self.token},
                json={'replyToken':reply_token,'messages':messages})
        # 不記 reply token、Authorization 或包含個資的 response body。
        return {'accepted':response.status_code==200,
                'request_id':response.headers.get('x-line-request-id'),
                'http_status':response.status_code}
