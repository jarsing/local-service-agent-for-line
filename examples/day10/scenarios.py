"""合成實驗入口；只有此處明確代送同意，查回／建單工具不代人同意。"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from evidence import Trace
from fault import Fault, FaultTransport
from records import SendArgs, ReceiptReader
from reconcile import RecoveryController
from upstream import Actor, Day08Gateway, HandoffService

QUESTION = '請問花壇場次的集合地點在哪裡？'
SCENARIOS = {'baseline': (Fault.NONE, False),
             'after_commit': (Fault.AFTER_COMMIT, False),
             'before_write': (Fault.BEFORE_WRITE, False),
             'lookup_unavailable': (Fault.AFTER_COMMIT, True)}


@dataclass
class Scenario:
    name: str
    actor: Any
    args: SendArgs
    gateway: Any
    service: Any
    transport: FaultTransport
    controller: RecoveryController
    trace: Trace
    confirmation: dict[str, Any]
    db_path: Path


def prepare_case(name: str, directory: Path, *, clock=None,
                 confirmed: bool = True, permitted=None) -> Scenario:
    if name not in SCENARIOS:
        raise ValueError('未知的合成案例。')
    directory.mkdir(parents=True, exist_ok=True)
    db_path = directory / 'handoff.sqlite3'
    if db_path.exists():
        raise FileExistsError('每個案例使用新資料庫；原始 evidence 保持原樣。')
    actor = Actor('local-demo', 'demo-user', 'day10-' + name)
    gateway = Day08Gateway(clock=clock)
    offer = gateway.prepare(actor, QUESTION, idempotency_key='demo-request-001')
    confirmation = (gateway.record_user_decision(actor, offer['confirmation_id'], approved=True)
                    if confirmed else {'status': 'not_confirmed'})
    if confirmed and confirmation['status'] != 'confirmation_recorded':
        raise RuntimeError('合成確認前置條件未完成。')
    args = SendArgs(offer['idempotency_key'], offer['confirmation_id'], QUESTION, gateway.catalog['event']['id'])
    allowed = permitted if permitted is not None else (lambda a: a == actor)
    service = HandoffService(db_path, gateway, allowed, clock=clock)
    trace = Trace()
    fault, unavailable = SCENARIOS[name]
    transport = FaultTransport(service, ReceiptReader(db_path, allowed), fault=fault,
                               lookup_unavailable=unavailable, emit=trace.emit)
    controller = RecoveryController(transport, actor, args, emit=trace.emit)
    return Scenario(name, actor, args, gateway, service, transport, controller, trace, confirmation, db_path)
