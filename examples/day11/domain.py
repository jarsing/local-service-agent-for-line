"""操作識別、序列化與回條。摘要是相等性比較，不是簽章或權限。"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from upstream import Actor, payload_hash


def clone(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def key(*values: str) -> str:
    raw = json.dumps(list(values),ensure_ascii=False,separators=(',',':'),allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def utcnow():
    return datetime.now(timezone.utc)


def iso(value: datetime):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('時間必須含時區。')
    return value.astimezone(timezone.utc).isoformat()


def time_of(value: str):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('已保存時間必須含時區。')
    return parsed


@dataclass(frozen=True)
class SendArgs:
    idempotency_key: str
    confirmation_id: str
    request_text: str
    event_id: str

    def valid(self):
        return all(type(v) is str and bool(v.strip()) and len(v)<=n for v,n in (
            (self.idempotency_key,200),(self.confirmation_id,200),
            (self.request_text,2000),(self.event_id,200)))

    def values(self):
        return asdict(self)

    def digest(self):
        return payload_hash(self.confirmation_id,self.request_text,self.event_id)


def operation_id(actor: Actor, args: SendArgs):
    return key(actor.tenant_id,actor.user_id,args.idempotency_key)


def confirmation_key(actor: Actor, args: SendArgs):
    return key(actor.tenant_id,actor.user_id,args.confirmation_id)


def session_key(actor: Actor):
    return key(actor.tenant_id,actor.user_id,actor.session_id)


def grant_key(actor: Actor):
    return key(actor.tenant_id,actor.user_id)


def catalog_key(actor: Actor, event_id: str):
    return key(actor.tenant_id,event_id)


def draft_key(actor: Actor, draft_id: str):
    return key(actor.tenant_id,actor.user_id,actor.session_id,draft_id)


def pending(observation: str):
    return {'status':'pending_verification','reply_state':'pending_verification',
            'claim_completed':False,'next_step':'reconcile_by_idempotency_key',
            'retry_policy':'reuse_same_idempotency_key','observation':observation,
            'request_created':None,'human_claimed':False}


def rejected(status: str):
    # False 指本次沒有新增，不是推定歷史請求不存在。
    return {'status':status,'request_created':False,'claim_completed':False,
            'human_claimed':False}


def receipt_result(row, created: bool, mode: str):
    return {'status':'request_created' if created else 'already_created',
            'request_id':row['request_id'],'request':clone(row),
            'request_created':created,'human_claimed':False,'delivery':mode,
            'observation':'created' if created else 'found'}


class ContractError(RuntimeError):
    pass
