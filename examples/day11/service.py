"""Firestore／測試 adapter 共用業務規則；不雙寫 Day 9 SQLite。"""
from __future__ import annotations
from dataclasses import asdict
from datetime import timedelta
import secrets
from domain import (SendArgs,clone,key,operation_id,confirmation_key,session_key,grant_key,
                    catalog_key,draft_key,iso,utcnow,pending,rejected,receipt_result,ContractError)
from upstream import Actor,Operation,ConfirmationStore,operation_fingerprint
from confirmation_gate import validate_first_write
from store import StoreUnavailable


def authorized(tx, actor):
    grant=tx.get('grants',grant_key(actor))
    return bool(grant and grant.get('allowed') is True and grant.get('actor')==
                {'tenant_id':actor.tenant_id,'user_id':actor.user_id})


def check_binding(binding, actor, args):
    if binding is None:return 'unconfirmed_operation'
    if binding['actor']!=asdict(actor):return 'wrong_actor'
    if binding['args']!=args.values() or binding['payload_hash']!=args.digest():
        return 'idempotency_conflict'
    return None


class HandoffService:
    def __init__(self, store, *, clock=utcnow):
        self.store=store;self.clock=clock

    def prepare(self, actor: Actor, operation: Operation, *, ttl_seconds=300, approved=False,
                idempotency_key=None):
        """可信入口的明確使用者決定；不是模型工具，不接受任意匯入收據。"""
        if type(approved) is not bool:raise ValueError('approved 須為布林值。')
        if not isinstance(actor,Actor) or not isinstance(operation,Operation):raise TypeError('可信型別不符。')
        now=self.clock()
        # 真正使用原 Day 8 issue／decide，保存原內容與回條；重啟時不再次同意。
        original=ConfirmationStore()
        offer=original.issue(owner=actor.identity,operation=operation,
            current_catalog_version=operation.catalog_version,data_status='adopted',
            now=now,ttl_seconds=ttl_seconds)
        decision=(original.decide(confirmation_id=offer['confirmation_id'],actor=actor.identity,
            current_operation=operation,current_catalog_version=operation.catalog_version,
            data_status='adopted',permitted=True,approved=True,now=now) if approved else
            {'status':'awaiting_confirmation','execution_allowed':False,'receipt':None})
        args=SendArgs(idempotency_key if idempotency_key is not None else 'send-'+secrets.token_urlsafe(18),
                      offer['confirmation_id'],operation.request_text,operation.event_id)
        if not args.valid():raise ValueError('工具參數不合法。')
        oid=operation_id(actor,args);cid=confirmation_key(actor,args)
        sid=session_key(actor);dk=draft_key(actor,operation.draft_id)
        binding={'schema':1,'operation_id':oid,'actor':asdict(actor),'args':args.values(),
                 'payload_hash':args.digest(),'draft_key':dk,'created_at':iso(now)}
        confirmation={'schema':1,'operation_id':oid,'owner':asdict(actor),
            'status':decision['status'],'fingerprint':offer['operation_fingerprint'],
            'snapshot':asdict(operation),'created_at':iso(now),'expires_at':offer['expires_at'],
            'execution_allowed':False,'receipt':decision.get('receipt'),
            'decision_source':'trusted_entry_explicit_approval' if approved else 'awaiting_user'}
        def register(tx):
            # 註冊當下還是要查現在權限和目前採用資料，不拿 prepare 自稱代替。
            ok=authorized(tx,actor)
            existing=tx.get('bindings',oid);existing_c=tx.get('confirmations',cid)
            catalog=tx.get('catalogs',catalog_key(actor,operation.event_id))
            tx.get('drafts',dk);tx.get('sessions',sid)
            if not ok:raise PermissionError('not_authorized')
            if existing or existing_c:raise ContractError('既有操作識別不可重建或覆寫。')
            if not catalog or catalog.get('data_status')!='adopted' or (
                catalog.get('catalog_version')!=operation.catalog_version or
                catalog.get('displayed_event')!=operation.displayed_event):
                raise ContractError('prepare 需要目前採用資料。')
            tx.create('bindings',oid,binding);tx.create('confirmations',cid,confirmation)
            tx.create('jobs',oid,{'schema':1,'operation_id':oid,'phase':'submit',
                'writes':0,'lookups':0,'lease_token':None,'lease_until':None,
                'last_result':None,'updated_at':iso(now)})
            tx.put('drafts',dk,asdict(operation))
            tx.put('sessions',sid,{'schema':1,'actor':asdict(actor),'active_operation':oid,
                'updated_at':iso(now),'scope':'task_reference_only'})
        self.store.atomic(register)
        return args

    def lookup(self, actor: Actor, args: SendArgs):
        if not isinstance(actor,Actor) or not isinstance(args,SendArgs):
            raise TypeError('需要可信 Actor 與 SendArgs。')
        if not args.valid():return rejected('invalid_arguments')
        oid=operation_id(actor,args)
        def read(tx):
            ok=authorized(tx,actor)
            binding=tx.get('bindings',oid);row=tx.get('requests',oid)
            if not ok:return rejected('not_authorized')
            problem=check_binding(binding,actor,args)
            if problem:return rejected(problem)
            if row is None:return pending('not_found')
            self._check_row(row,binding)
            return receipt_result(row,False,self.store.mode)
        try:return self.store.atomic(read,read_only=True)
        except StoreUnavailable:return pending('lookup_unavailable')

    @staticmethod
    def _check_row(row,binding):
        if (row['operation_id']!=binding['operation_id'] or row['payload_hash']!=binding['payload_hash']
            or row['actor']!=binding['actor'] or row['args']!=binding['args']
            or row['request_text']!=binding['args']['request_text']
            or row['event_id']!=binding['args']['event_id']
            or row.get('status')!='pending_human_review' or row.get('human_claimed') is not False
            or row.get('service_id')!='local_demo_service_desk'
            or not isinstance(row.get('request_id'), str) or not row['request_id']):
            raise ContractError('已保存回條不符合原操作。')

    def create(self, actor: Actor, args: SendArgs):
        if not isinstance(actor,Actor) or not isinstance(args,SendArgs):
            raise TypeError('需要可信 Actor 與 SendArgs。')
        if not args.valid():return rejected('invalid_arguments')
        oid=operation_id(actor,args);cid=confirmation_key(actor,args)
        # 隨機單號只產生一次，不在會重跑的交易回呼內。
        candidate='req-'+self.clock().strftime('%Y%m%d')+'-'+secrets.token_hex(8)
        def write(tx):
            ok=authorized(tx,actor)
            binding=tx.get('bindings',oid);row=tx.get('requests',oid)
            confirmation=tx.get('confirmations',cid)
            catalog=tx.get('catalogs',catalog_key(actor,args.event_id))
            draft=tx.get('drafts',binding['draft_key']) if binding else None
            if not ok:return rejected('not_authorized')
            if binding is None and confirmation and confirmation.get('operation_id')!=oid:
                return rejected('confirmation_already_used')
            problem=check_binding(binding,actor,args)
            if problem:return rejected(problem)
            if row is not None:
                self._check_row(row,binding)
                return receipt_result(row,False,self.store.mode)
            now=self.clock()
            problem=validate_first_write(confirmation,binding,draft,catalog,now)
            if problem:return rejected(problem)
            row={'schema':1,'request_id':candidate,'operation_id':oid,'actor':asdict(actor),
                 'args':args.values(),'payload_hash':args.digest(),
                 'operation_fingerprint':confirmation['fingerprint'],
                 'catalog_version':confirmation['snapshot']['catalog_version'],
                 'request_text':args.request_text,'event_id':args.event_id,
                 'service_id':confirmation['snapshot']['destination'],
                 'status':'pending_human_review','human_claimed':False,'created_at':iso(now)}
            tx.create('requests',oid,row)
            return receipt_result(row,True,self.store.mode)
        try:return self.store.atomic(write)
        except StoreUnavailable:return pending('write_outcome_unknown')

    def restore_session(self, actor: Actor):
        """只讀取可信業務 Session 參照；不是完整 ADK 聊天紀錄。"""
        def read(tx):
            ok=authorized(tx,actor);link=tx.get('sessions',session_key(actor))
            if not ok:return rejected('not_authorized')
            if not link or link.get('actor')!=asdict(actor):return rejected('session_not_found')
            binding=tx.get('bindings',link['active_operation'])
            if not binding or binding['actor']!=asdict(actor):raise ContractError('Session 綁定損壞。')
            return {'status':'session_restored','operation_id':binding['operation_id'],
                    'args':clone(binding['args']),'session_id':actor.session_id,
                    'scope':'task_reference_only'}
        try:return self.store.atomic(read,read_only=True)
        except StoreUnavailable:return pending('lookup_unavailable')
