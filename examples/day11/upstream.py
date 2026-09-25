"""唯讀沿用 Day 8 型別／指紋、Day 9 Actor／內容指紋；不改歷史核心。"""
from __future__ import annotations
import hashlib
import importlib
import json
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DAY09 = REPO / 'examples/day09'

def check_dependencies():
    lock = json.loads((HERE/'dependency-lock.json').read_text('utf-8'))
    actual = {}
    for relative, expected in lock['files'].items():
        path = REPO / relative
        if not path.is_file():
            raise RuntimeError(f'缺少前篇：{relative}；請使用完整 LOCAL Repo。')
        actual[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual[relative] != expected:
            raise RuntimeError(f'前篇版本不同：{relative}；先確認相容性，不自動覆寫。')
    return actual
check_dependencies()
for name in ('dependencies', 'day08_gateway', 'handoff'):
    prior = sys.modules.get(name)
    if prior and Path(getattr(prior,'__file__','')).resolve() != (DAY09/f'{name}.py'):
        raise RuntimeError(f'模組撞名：{name}；各日測試使用獨立行程。')
sys.path.append(str(DAY09)) if str(DAY09) not in sys.path else None
_d = importlib.import_module('dependencies')
_h = importlib.import_module('handoff')
Actor = _h.Actor
Operation = _d.Operation
Identity = _d.Identity
ConfirmationStore = _d.ConfirmationStore
operation_fingerprint = _d.operation_fingerprint
payload_hash = _h.payload_hash
