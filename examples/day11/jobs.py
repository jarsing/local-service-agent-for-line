"""可明確啟動的有限 worker：先保存嘗試意圖；租約到期先查回。"""
from __future__ import annotations
from datetime import timedelta
import secrets
from domain import operation_id,iso,time_of,utcnow,pending,rejected,clone
from service import authorized,check_binding
from store import StoreUnavailable


class InjectedTimeout(TimeoutError):pass


class RecoveryWorker:
    def __init__(self,service,*,clock=utcnow,lease_seconds=30,emit=None):
        if not 1<=lease_seconds<=300:raise ValueError('lease_seconds 需介於 1～300。')
        self.service=service;self.store=service.store;self.clock=clock
        self.lease_seconds=lease_seconds;self.emit=emit or (lambda *a,**k:None)

    def claim(self,actor,args,*,expected_tool=None):
        oid=operation_id(actor,args);token=secrets.token_hex(16)
        def reserve(tx):
            ok=authorized(tx,actor);binding=tx.get('bindings',oid);job=tx.get('jobs',oid)
            if not ok:return {'result':rejected('not_authorized')}
            issue=check_binding(binding,actor,args)
            if issue:return {'result':rejected(issue)}
            if job is None:raise RuntimeError('操作缺少工作紀錄。')
            now=self.clock()
            if job['lease_token'] and time_of(job['lease_until'])>now:
                return {'result':pending('worker_busy')}
            phase=job['phase']
            tool='reconcile_handoff_request' if phase=='lookup' else 'create_handoff_request'
            if phase=='done':return {'result':clone(job['last_result'])}
            if phase=='paused':return {'result':pending('recovery_paused')}
            if phase not in ('submit','lookup','retry'):raise RuntimeError('未知工作階段。')
            if expected_tool and expected_tool!=tool:return {'result':rejected('sequence_rejected')}
            counter='lookups' if phase=='lookup' else 'writes'
            limit=1 if counter=='lookups' else 2
            if job[counter]>=limit:return {'result':pending('recovery_budget_exhausted')}
            job[counter]+=1
            # 寫入開始前先保存「下一個 worker 必須查回」；查回中斷則停住。
            job['phase']='paused' if phase=='lookup' else 'lookup'
            job.update(lease_token=token,lease_until=iso(now+timedelta(seconds=self.lease_seconds)),
                       updated_at=iso(now))
            tx.put('jobs',oid,job)
            return {'token':token,'phase':phase,'tool':tool}
        try:return self.store.atomic(reserve)
        except StoreUnavailable:return {'result':pending('claim_unavailable')}

    def finish(self,actor,args,claim,result):
        oid=operation_id(actor,args)
        def update(tx):
            ok=authorized(tx,actor);binding=tx.get('bindings',oid);job=tx.get('jobs',oid)
            if not ok:return False
            if check_binding(binding,actor,args):return False
            if not job or job['lease_token']!=claim['token']:return False
            phase=claim['phase']
            if result['status']=='pending_verification':
                if phase=='submit':next_phase='lookup'
                elif phase=='lookup' and result.get('observation')=='not_found' and job['writes']<2:
                    next_phase='retry'
                else:next_phase='paused'
            else:next_phase='done'
            job.update(phase=next_phase,last_result=clone(result),lease_token=None,
                       lease_until=None,updated_at=iso(self.clock()))
            tx.put('jobs',oid,job);return True
        try:return self.store.atomic(update)
        except StoreUnavailable:return False

    def step(self,actor,args,*,fault='none',crash=None,lookup_unavailable=False,expected_tool=None):
        if fault not in ('none','before_write','after_commit'):raise ValueError('未知故障點。')
        claim=self.claim(actor,args,expected_tool=expected_tool)
        if 'result' in claim:
            # 已完成工作的快取不代替現在的回條核對。
            if claim['result'].get('status') in ('request_created','already_created'):
                return self.service.lookup(actor,args)
            return claim['result']
        self.emit('WORK_CLAIMED',operation_id=operation_id(actor,args),claim=claim)
        try:
            if claim['phase']=='lookup':
                if lookup_unavailable:raise InjectedTimeout('lookup')
                result=self.service.lookup(actor,args)
            else:
                if fault=='before_write':
                    self.emit('FAULT_INJECTED',point=fault)
                    if crash:crash()
                    raise InjectedTimeout('submit')
                result=self.service.create(actor,args)
                self.emit('SERVICE_RESULT',result=result)
                if fault=='after_commit' and result['status'] in ('request_created','already_created'):
                    self.emit('FAULT_INJECTED',point=fault)
                    if crash:crash()
                    raise InjectedTimeout('submit')
        except InjectedTimeout:
            result=pending('lookup_unavailable' if claim['phase']=='lookup' else 'submit_timeout')
        accepted=self.finish(actor,args,claim,result)
        self.emit('WORK_RESULT',claim=claim,result=result,progress_recorded=accepted)
        # stale worker 不可覆蓋新版進度；回條本身仍可是真實，但先請 caller 查證。
        return result if accepted else pending('progress_not_confirmed')

    def run(self,actor,args,*,max_steps=3,lookup_unavailable=False):
        if not 1<=max_steps<=3:raise ValueError('每次啟動最多三個步驟。')
        results=[]
        for _ in range(max_steps):
            value=self.step(actor,args,lookup_unavailable=lookup_unavailable)
            results.append(value)
            if value['status']!='pending_verification' or value.get('observation') not in ('not_found','submit_timeout'):
                break
        return results
