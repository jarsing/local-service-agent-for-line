"""可定位的合成傳輸故障；不更動 Day 9 SQLite 交易，也不假造真實斷網。"""
from __future__ import annotations
from enum import Enum
from threading import Lock
from typing import Any, Callable
from records import SendArgs, ReceiptReader
from upstream import Actor, HandoffService


class Fault(str, Enum):
    NONE = 'none'
    BEFORE_WRITE = 'before_write'
    AFTER_COMMIT = 'after_commit'


class SyntheticTimeout(TimeoutError):
    """只在教學傳輸接點拋出；上層不從錯誤訊息猜資料庫狀態。"""


class FaultTransport:
    def __init__(self, service: HandoffService, reader: ReceiptReader, *,
                 fault: Fault = Fault.NONE, lookup_unavailable: bool = False,
                 repeat_fault: bool = False,
                 emit: Callable[..., None] | None = None):
        if not isinstance(fault, Fault):
            raise TypeError('fault 必須是 Fault。')
        self.service = service
        self.reader = reader
        self.fault = fault
        self.lookup_unavailable = lookup_unavailable
        self.repeat_fault = repeat_fault
        self.emit = emit or (lambda kind, **values: None)
        self.create_calls = 0
        self.lookup_calls = 0
        self._lock = Lock()

    def create(self, actor: Actor, args: SendArgs) -> dict[str, Any]:
        with self._lock:
            self.create_calls += 1
            attempt = self.create_calls
            fault = self.fault if attempt == 1 or self.repeat_fault else Fault.NONE
        self.emit('TRANSPORT_CREATE', attempt=attempt, args=args.tool_args())
        if fault is Fault.BEFORE_WRITE:
            self.emit('FAULT_INJECTED', point=fault.value, attempt=attempt)
            raise SyntheticTimeout('SYNTHETIC_TRANSPORT_TIMEOUT')
        receipt = self.service.create(actor=actor, **args.tool_args())
        # Day 9 create() 在 conn.commit() 後才回傳成功回條。
        # 保留後端稽核事件，但不把遺失的回條放進 caller 的 timeout 結果。
        self.emit('BACKEND_RETURNED', attempt=attempt, result=receipt)
        if fault is Fault.AFTER_COMMIT and receipt['status'] in ('request_created', 'already_created'):
            self.emit('FAULT_INJECTED', point=fault.value, attempt=attempt)
            raise SyntheticTimeout('SYNTHETIC_TRANSPORT_TIMEOUT')
        return receipt

    def lookup(self, actor: Actor, args: SendArgs) -> dict[str, Any]:
        with self._lock:
            self.lookup_calls += 1
        self.emit('TRANSPORT_LOOKUP', args=args.tool_args())
        if self.lookup_unavailable:
            self.emit('FAULT_INJECTED', point='lookup_unavailable')
            raise SyntheticTimeout('SYNTHETIC_LOOKUP_TIMEOUT')
        result = self.reader.lookup(actor, args)
        self.emit('LOOKUP_RETURNED', result=result)
        return result
