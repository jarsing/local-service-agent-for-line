"""具名離線測試支援；不是 LINE／Gemini 真實 API。"""
import json
from datetime import datetime,timezone
from .settings import Settings
from .identity import signature, make_actor

RAW_USER='U00000000000000000000000000000001'
OTHER_USER='U00000000000000000000000000000002'

class ReplyRecorder:
    def __init__(self, fail=False): self.sent=[];self.fail=fail
    async def send(self, token, messages):
        # 不保存 token，即使是合成資料也沿用安全習慣。
        self.sent.append(messages)
        if self.fail: raise TimeoutError('SYNTHETIC_REPLY_TIMEOUT')
        return {'accepted':True,'request_id':'synthetic-line-request-'+str(len(self.sent))}

def settings(db):
    return Settings(backend='sqlite-test',project='demo-local-day12',namespace='day11-d12-local',
        sqlite_path=str(db),destination='Ulocalbot',channel_secret='synthetic-channel-secret',
        channel_token='',actor_key='s'*32,allowed_users=(RAW_USER,OTHER_USER))

def event(ident, text=None, data=None, user=RAW_USER):
    result={'webhookEventId':ident,'timestamp':1790000000000,'mode':'active',
            'source':{'type':'user','userId':user},'replyToken':'synthetic-'+ident}
    if data is not None: result.update(type='postback',postback={'data':data})
    else: result.update(type='message',message={'id':'message-'+ident,'type':'text','text':text})
    return result

def post(client,config,*events,signature_override=None,destination=None):
    body=json.dumps({'destination':destination or config.destination,'events':list(events)},
                    ensure_ascii=False).encode()
    return client.post('/webhook',content=body,headers={'content-type':'application/json',
        'x-line-signature':signature(config.channel_secret,body) if signature_override is None else signature_override})
