"""新手機確認接點；沿用 Day 8 issue 與 Day 11 prepare/create/lookup。

持久化的「稍後同意」是 Day 12 新增程式，不假稱原 Day 8 記憶體 decide 能跨行程。
"""
from dataclasses import asdict
from .inherit import (HandoffService, Operation, SendArgs, key, operation_id, confirmation_key,
    session_key, catalog_key, draft_key, grant_key, authorized, check_binding, clone,
    utcnow, iso, time_of, operation_fingerprint, rejected, pending, ContractError)

class LineTasks:
    def __init__(self, store, catalog, *, clock=utcnow):
        self.store, self.catalog, self.clock = store, catalog, clock
        self.original = HandoffService(store, clock=clock)

    def current(self, actor):
        return self.original.restore_session(actor)

    def offer(self, actor, request_text: str, webhook_event_id: str, *, new_intent=False):
        if not request_text.strip() or len(request_text) > 1200:
            return rejected('invalid_arguments')
        # 事件識別為這次明確需求配置原鍵；後續確認／查回不重算 key。
        send_key = 'send-' + key(actor.tenant_id, actor.user_id, webhook_event_id)
        oid = key(actor.tenant_id, actor.user_id, send_key)
        def prior(tx):
            if not authorized(tx, actor):
                return rejected('not_authorized')
            binding = tx.get('bindings', oid)
            if binding:
                if binding['actor'] != asdict(actor) or binding['args']['request_text'] != request_text:
                    return rejected('idempotency_conflict')
                return {'status':'offer_existing', 'args':clone(binding['args'])}
            return None
        previous = self.store.atomic(prior, read_only=True)
        if previous:
            return previous
        active = self.current(actor)
        if active['status'] == 'session_restored' and not new_intent:
            return {'status':'active_task_exists', 'args':active['args']}
        if active['status'] not in ('session_not_found', 'session_restored'):
            return active
        operation = Operation(draft_id='draft-' + key(webhook_event_id), revision=1,
            event_id=self.catalog.event['id'], catalog_version=self.catalog.snapshot['catalog_version'],
            request_text=request_text, displayed_event=clone(self.catalog.event))
        try:
            # 初次只 issue；絕不在此 approved=True。
            args = self.original.prepare(actor, operation, ttl_seconds=300,
                                         approved=False, idempotency_key=send_key)
        except ContractError:
            # 同事件競爭／提交後回覆遺失：只接受完全相符的既有 binding。
            existing = self.store.atomic(prior, read_only=True)
            if existing:
                return existing
            raise
        return {'status':'offer_created', 'args':args.values()}

    def describe_offer(self, actor, args):
        def read(tx):
            if not authorized(tx, actor):
                return rejected('not_authorized')
            binding = tx.get('bindings', operation_id(actor,args))
            issue = check_binding(binding, actor, args)
            c = tx.get('confirmations', confirmation_key(actor,args))
            if issue or not c:
                return rejected(issue or 'unconfirmed_operation')
            return {'status': c['status'], 'args': args.values(), 'expires_at': c['expires_at']}
        return self.store.atomic(read, read_only=True)

    def decide(self, actor, confirmation_id: str, approved: bool):
        if type(approved) is not bool:
            raise ValueError('確認選擇必須由受驗簽 postback 的路由決定。')
        def decide_tx(tx):
            ok = authorized(tx,actor)
            link = tx.get('sessions',session_key(actor))
            cid = key(actor.tenant_id,actor.user_id,confirmation_id)
            conf = tx.get('confirmations',cid)
            binding = tx.get('bindings',conf['operation_id']) if conf else None
            if not ok: return rejected('not_authorized')
            if (not conf or not binding or conf['owner'] != asdict(actor)
                    or binding['actor'] != asdict(actor)):
                return rejected('confirmation_not_found')
            if (not link or link.get('actor') != asdict(actor)
                    or link.get('active_operation') != conf['operation_id']):
                return rejected('superseded')
            args = SendArgs(**binding['args'])
            catalog = tx.get('catalogs',catalog_key(actor,args.event_id))
            draft = tx.get('drafts',binding['draft_key'])
            row = tx.get('requests',conf['operation_id'])
            if conf['execution_allowed'] is not False:
                return rejected('invalid_confirmation_record')
            if row is not None:
                return {'status':'existing_request', 'args':args.values()}
            if conf['status'] not in ('awaiting_confirmation','confirmation_recorded'):
                return rejected(conf['status'])
            if not approved:
                if conf['status'] == 'confirmation_recorded':
                    return rejected('already_confirmed')
                conf['status'] = 'cancelled'
                tx.put('confirmations',cid,conf)
                return rejected('cancelled')
            now=self.clock()
            if now < time_of(conf['created_at']): return rejected('clock_error')
            if now >= time_of(conf['expires_at']): return rejected('expired')
            if not catalog or catalog.get('data_status') != 'adopted': return rejected('data_pending')
            if catalog['catalog_version'] != conf['snapshot']['catalog_version']:
                return rejected('version_changed')
            if (not draft or operation_fingerprint(Operation(**draft)) != conf['fingerprint']
                    or catalog['displayed_event'] != conf['snapshot']['displayed_event']):
                return rejected('content_changed')
            if conf['status'] == 'awaiting_confirmation':
                conf['status']='confirmation_recorded'
                conf['decision_source']='verified_line_postback'
                conf['receipt']={'confirmation_id':confirmation_id,
                    'operation_fingerprint':conf['fingerprint'],
                    'catalog_version':conf['snapshot']['catalog_version'], 'recorded_at':iso(now)}
                tx.put('confirmations',cid,conf)
            return {'status':'confirmation_recorded', 'args':args.values()}
        decision=self.store.atomic(decide_tx)
        if decision['status'] in ('confirmation_recorded','existing_request'):
            # 另一筆交易做原 Day 11 授權／原內容核對，不把確認布林當通行證。
            args=SendArgs(**decision['args'])
            if decision['status']=='existing_request':
                return self.original.lookup(actor,args)
            return self.original.create(actor,args)
        return decision

    def status(self, actor):
        active=self.current(actor)
        if active['status']!='session_restored': return active
        args=SendArgs(**active['args'])
        result=self.original.lookup(actor,args)
        if result['status']=='pending_verification' and result.get('observation')=='not_found':
            offer=self.describe_offer(actor,args)
            if offer['status']=='awaiting_confirmation':
                if self.clock() >= time_of(offer['expires_at']):
                    return rejected('expired')
                return {'status':'awaiting_confirmation','args':args.values(), 'expires_at':offer['expires_at']}
            if offer['status'] in ('cancelled','expired','content_changed','version_changed'):
                return rejected(offer['status'])
        return result

    def catalog_is_current(self, actor):
        def read(tx):
            ok=authorized(tx,actor)
            c=tx.get('catalogs',catalog_key(actor,self.catalog.event['id']))
            return bool(ok and c and c.get('data_status')=='adopted'
                and c.get('catalog_version')==self.catalog.snapshot['catalog_version']
                and c.get('displayed_event')==self.catalog.event)
        return self.store.atomic(read,read_only=True)

    def seed(self, actors):
        """僅 CLI／本機測試呼叫：不由 Webhook 偷偷新增 grant 或重設現有資料。"""
        snapshot=self.catalog.snapshot
        def write(tx):
            entries=[]
            for actor in actors:
                gk=grant_key(actor);ck=catalog_key(actor,self.catalog.event['id'])
                g=tx.get('grants',gk);c=tx.get('catalogs',ck)
                if g is None: entries.append(('grants',gk,{'allowed':True,'actor':{
                    'tenant_id':actor.tenant_id,'user_id':actor.user_id}}))
                if c is None: entries.append(('catalogs',ck,{'data_status':'adopted',
                    'catalog_version':snapshot['catalog_version'],'displayed_event':clone(self.catalog.event)}))
                elif c.get('catalog_version') != snapshot['catalog_version'] or c.get('displayed_event') != self.catalog.event:
                    raise ContractError('目錄與既有資料不同，停止自動覆寫；另做版本更新。')
            seen=set()
            for kind,ident,value in entries:
                if (kind,ident) not in seen:
                    tx.create(kind,ident,value);seen.add((kind,ident))
        self.store.atomic(write)
