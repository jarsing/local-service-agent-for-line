"""應用端同意記憶；共用 Day 11 文件交易，不假稱 ADK MemoryService。
待同意內容只在有期限的簽章卡片，尚未寫入偏好庫。忘記後只留無偏好值的版本墓碑。
"""
from __future__ import annotations
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
from examples.day12.inherit import key, authorized, utcnow
from .places import diet

COLLECTION='consented_preferences'
PURPOSE='未來在 LOCAL 找店家時套用飲食條件'
class PreferenceChanged(RuntimeError): pass
class BadToken(ValueError): pass

def owner_key(actor):
    # Session is intentionally absent: same authorized LINE account, fresh Session.
    return key('day14-diet',actor.tenant_id,actor.user_id)

def _b64(raw): return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')
def _unb64(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',value): raise BadToken('INVALID_TOKEN_ENCODING')
    return base64.urlsafe_b64decode(value+'='*((-len(value))%4))

class PreferenceMemory:
    def __init__(self,store,secret:str,*,clock=utcnow):
        if not isinstance(secret,str) or len(secret)<32: raise ValueError('STABLE_SIGNING_KEY_REQUIRED')
        self.store,self.secret,self.clock=store,secret.encode(),clock

    def _row(self,tx,actor):
        if not authorized(tx,actor): raise PermissionError('not_authorized')
        row=tx.get(COLLECTION,owner_key(actor)) or {'schema':1,'revision':0}
        if (row.get('schema')!=1 or type(row.get('revision')) is not int or row['revision']<0):
            raise ValueError('MEMORY_SCHEMA')
        if 'dietary_type' in row: diet(row['dietary_type'],allow_any=False)
        return row

    def inspect(self,actor):
        def read(tx):
            row=self._row(tx,actor)
            return {'revision':row['revision'],'dietary_type':row.get('dietary_type'),
                    'status':'saved' if row.get('dietary_type') else 'empty','purpose':PURPOSE,
                    'consented_at':row.get('consented_at')}
        return self.store.atomic(read,read_only=True)

    def assert_revision(self,actor,revision):
        current=self.inspect(actor)
        if current['revision']!=revision: raise PreferenceChanged('PREFERENCE_CHANGED')
        return current

    def _signature(self,actor,body):
        return _b64(hmac.new(self.secret,(owner_key(actor)+'\0'+body).encode(),hashlib.sha256).digest())

    def propose(self,actor,value:str,event_id:str,*,operation='save',issued_at:datetime|None=None):
        if operation not in ('save','forget'): raise ValueError('INVALID_MEMORY_OPERATION')
        value=diet(value,allow_any=False) if operation=='save' else ''
        current=self.inspect(actor)
        issued_at=issued_at or self.clock()
        if issued_at.tzinfo is None: raise ValueError('AWARE_TIME_REQUIRED')
        # No raw utterance or relationship profile. Nonce is keyed and bound to the event.
        nonce=hmac.new(self.secret,(owner_key(actor)+'\0'+event_id+'\0'+operation+'\0'+value).encode(),hashlib.sha256).hexdigest()[:20]
        payload={'v':1,'r':current['revision'],'d':value,'e':int(issued_at.timestamp())+300,'n':nonce,'o':operation}
        body=_b64(json.dumps(payload,sort_keys=True,separators=(',',':')).encode())
        token=body+'.'+self._signature(actor,body)
        if len('m14:approve:'+token)>300: raise ValueError('POSTBACK_BUDGET')
        return {'status':'awaiting_memory_consent','dietary_type':value or None,'operation':operation,
                'token':token,'revision':current['revision'],'expires_at':datetime.fromtimestamp(payload['e'],timezone.utc).isoformat(),
                'purpose':PURPOSE}

    def _decode(self,actor,token):
        if not isinstance(token,str) or len(token)>285 or token.count('.')!=1: raise BadToken('INVALID_TOKEN')
        body,sig=token.split('.')
        if not hmac.compare_digest(sig,self._signature(actor,body)): raise BadToken('TOKEN_OWNER_OR_SIGNATURE')
        try:p=json.loads(_unb64(body))
        except Exception as exc: raise BadToken('INVALID_TOKEN_BODY') from exc
        if (not isinstance(p,dict) or set(p)!={'v','r','d','e','n','o'} or p['v']!=1 or
            type(p['r']) is not int or p['r']<0 or type(p['e']) is not int or
            not isinstance(p['n'],str) or not re.fullmatch('[a-f0-9]{20}',p['n']) or
            p['o'] not in ('save','forget')): raise BadToken('TOKEN_SCHEMA')
        if p['o']=='save': diet(p['d'],allow_any=False)
        elif p['d']!='': raise BadToken('TOKEN_SCHEMA')
        return p

    def approve(self,actor,token):
        """Only trusted, signed LINE postback routes call this. Never exposed as an LLM tool."""
        p=self._decode(actor,token);now=self.clock()
        def change(tx):
            row=self._row(tx,actor)
            if row.get('last_nonce')==p['n'] and row['revision']==p['r']+1:
                return {'status':'already_applied','revision':row['revision'],'dietary_type':row.get('dietary_type')}
            if row['revision']!=p['r']: return {'status':'stale_memory_card','revision':row['revision']}
            if now.timestamp()>=p['e']: return {'status':'expired_memory_card','revision':row['revision']}
            new={'schema':1,'revision':row['revision']+1,'last_nonce':p['n']}
            if p['o']=='save':
                new.update(dietary_type=p['d'],consented_at=now.isoformat())
            tx.put(COLLECTION,owner_key(actor),new)
            return {'status':'memory_saved' if p['o']=='save' else 'memory_forgotten',
                    'revision':new['revision'],'dietary_type':new.get('dietary_type')}
        return self.store.atomic(change)

    def cancel(self,actor,token):
        p=self._decode(actor,token)
        def change(tx):
            row=self._row(tx,actor)
            if row['revision']!=p['r']: return {'status':'stale_memory_card','revision':row['revision']}
            # Generation invalidation preserves an older approved preference, if any.
            new={k:v for k,v in row.items() if k!='last_nonce'}
            new['revision']+=1
            tx.put(COLLECTION,owner_key(actor),new)
            return {'status':'memory_proposal_cancelled','revision':new['revision']}
        return self.store.atomic(change)

    def forget(self,actor,event_id):
        """An explicit current user command; strip values and invalidate every old consent card."""
        nonce=hmac.new(self.secret,('forget\0'+owner_key(actor)+'\0'+event_id).encode(),hashlib.sha256).hexdigest()[:20]
        def change(tx):
            row=self._row(tx,actor)
            if row.get('last_nonce')==nonce and 'dietary_type' not in row:
                return {'status':'memory_forgotten','revision':row['revision']}
            new={'schema':1,'revision':row['revision']+1,'last_nonce':nonce}
            tx.put(COLLECTION,owner_key(actor),new)
            return {'status':'memory_forgotten','revision':new['revision']}
        return self.store.atomic(change)
