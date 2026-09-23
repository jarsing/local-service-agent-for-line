"""只讀載入 Day 8 的確認核心；不複製或修改前篇的業務規則。"""
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path
import sys

BASE_COMMIT = "b479f9fe321769c2e9525d82d3a175b8ba23d49b"
CORE_PATH = Path(__file__).resolve().parents[1] / "day08" / "confirmation.py"
EXPECTED_CORE_BLOB = "f4f70dd68e69b5a5a33ccf9b46850ebf35bdaa94"

def load_day08_core():
    if not CORE_PATH.is_file():
        raise RuntimeError("缺少 examples/day08/confirmation.py；請整合進既有 LOCAL Repo 後執行。")
    data = CORE_PATH.read_bytes()
    digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if digest != EXPECTED_CORE_BLOB:
        raise RuntimeError("Day 8 核心與已核對基準不同；請保留新檔，先核對相容性，不覆蓋前篇。")
    name = "local_day08_confirmation_core"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, CORE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

day08 = load_day08_core()
Identity = day08.Identity
Operation = day08.Operation
ConfirmationStore = day08.ConfirmationStore
operation_fingerprint = day08.operation_fingerprint
