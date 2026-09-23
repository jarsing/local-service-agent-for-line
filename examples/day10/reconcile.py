"""有上限的查回流程；應用端掌握順序，模型不能自創同意、鍵或重試次數。"""
from __future__ import annotations
from threading import RLock
from typing import Any, Callable
from fault import FaultTransport, SyntheticTimeout
from policy import pending_result, error_result, client_text
from records import SendArgs
from upstream import Actor


class RecoveryController:
    """一個已綁定操作：首次送出 → 查回 → 必要時同鍵重送一次。"""
    def __init__(self, transport: FaultTransport, actor: Actor, args: SendArgs, *,
                 emit: Callable[..., None] | None = None):
        if not args.valid():
            raise ValueError('建立流程前需要完整有效參數。')
        self.transport = transport
        self.actor = actor
        self.args = args
        self.phase = 'submit'
        self.last_result: dict[str, Any] | None = None
        self.emit = emit or (lambda kind, **values: None)
        self._lock = RLock()

    @property
    def next_tool(self) -> str | None:
        return {'submit': 'create_handoff_request', 'lookup': 'reconcile_handoff_request',
                'retry': 'create_handoff_request'}.get(self.phase)

    def execute(self, tool_name: str, actor: Actor, args: SendArgs) -> dict[str, Any]:
        with self._lock:
            if actor != self.actor:
                return error_result('wrong_actor')
            if args != self.args:
                return error_result('operation_binding_mismatch')
            if tool_name != self.next_tool or self.phase == 'done':
                return error_result('sequence_rejected')
            phase = self.phase
            if phase in ('submit', 'retry'):
                try:
                    result = self.transport.create(actor, args)
                except SyntheticTimeout:
                    result = pending_result('submit_timeout')
                # 只有首次逾時安排查回；第二次仍逾時就保留未知並停止。
                self.phase = 'lookup' if phase == 'submit' and result['status'] == 'pending_verification' else 'done'
            else:
                try:
                    result = self.transport.lookup(actor, args)
                except SyntheticTimeout:
                    result = pending_result('lookup_unavailable')
                self.phase = ('retry' if result['status'] == 'pending_verification'
                              and result.get('observation') == 'not_found' else 'done')
            self.last_result = result
            self.emit('POLICY_RESULT', phase=phase, next_phase=self.phase,
                      args=args.tool_args(), result=result)
            # 這是本機應用事件／文案；不是 LINE 已送達，也不是 Gemini 原文。
            self.emit('CLIENT_STATUS', source='application_template',
                      phase=phase, text=client_text(result), result=result)
            return result

    def run_to_boundary(self) -> list[dict[str, Any]]:
        """核心示範入口；ADK 路線以真正工具呼叫逐步推進同一個 controller。"""
        results = []
        while self.next_tool is not None:
            if len(results) >= 3:
                raise RuntimeError('RECOVERY_STEP_LIMIT')
            results.append(self.execute(self.next_tool, self.actor, self.args))
        return results
