"""唯讀重用 Day 8／9；路徑或核心雜湊不符時停下來，不覆蓋前篇。"""
from __future__ import annotations
import hashlib
import importlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DAY09 = REPO / 'examples/day09'
SPEC_PATH = REPO / 'docs/day01/handoff-timeout-001.json'
SPEC_SHA256 = '9a4768046189e6ba0d42637953b8d73e41566f7c573ea0a76b32079b1a762218'


def check_dependencies() -> dict[str, str]:
    lock = json.loads((HERE / 'dependency-lock.json').read_text('utf-8'))
    actual = {}
    for relative, expected in lock['files'].items():
        path = REPO / relative
        if not path.is_file():
            raise RuntimeError(f'缺少前篇相依檔：{relative}；請整合進完整 LOCAL Repo。')
        actual[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual[relative] != expected:
            raise RuntimeError(f'前篇內容與本包基準不同：{relative}；保留新檔，先核對相容性。')
    if hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest() != SPEC_SHA256:
        raise RuntimeError('Day 1 原始規格位元組不同。')
    return actual


check_dependencies()
# Day 9 使用腳本式 import；只接受來自同一 Repo 的模組，避免撞名。
for name in ('dependencies', 'day08_gateway', 'handoff'):
    previous = sys.modules.get(name)
    if previous and Path(getattr(previous, '__file__', '')).resolve() != (DAY09 / f'{name}.py'):
        raise RuntimeError(f'模組名稱衝突：{name}；各日驗證請分別執行。')
if str(DAY09) not in sys.path:
    sys.path.append(str(DAY09))
_handoff = importlib.import_module('handoff')
_gateway = importlib.import_module('day08_gateway')
HandoffService = _handoff.HandoffService
HandoffRequest = _handoff.HandoffRequest
payload_hash = _handoff.payload_hash
Actor = _gateway.Actor
Day08Gateway = _gateway.Day08Gateway
