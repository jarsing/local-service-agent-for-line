"""只有記憶體的對照組。生命週期止於本行程，沒有讀取輸出檔復原的路徑。"""
from __future__ import annotations
from threading import RLock
from domain import clone, ContractError


class MemoryTransaction:
    def __init__(self, documents: dict, *, read_only: bool):
        self.documents = documents
        self.read_only = read_only
        self.written = False

    def get(self, collection: str, ident: str) -> dict | None:
        if self.written:
            raise ContractError('交易內先完成所有讀取，再寫入。')
        value = self.documents.get(collection, {}).get(ident)
        return clone(value) if value is not None else None

    def _write(self, collection: str, ident: str, value: dict, *, create: bool) -> None:
        if self.read_only:
            raise ContractError('唯讀交易不能寫入。')
        rows = self.documents.setdefault(collection, {})
        if create and ident in rows:
            raise ContractError('同一份文件已存在。')
        rows[ident] = clone(value)
        self.written = True

    def put(self, collection: str, ident: str, value: dict) -> None:
        self._write(collection, ident, value, create=False)

    def create(self, collection: str, ident: str, value: dict) -> None:
        self._write(collection, ident, value, create=True)


class MemoryControlStore:
    mode = 'MEMORY_CONTROL'

    def __init__(self):
        self._documents: dict = {}
        self._lock = RLock()

    def atomic(self, fn, *, read_only=False):
        with self._lock:
            candidate = clone(self._documents)
            result = fn(MemoryTransaction(candidate, read_only=read_only))
            if not read_only:
                self._documents = candidate
            return result

    def inspect(self) -> dict:
        # 只讓該行程的測試端觀察；其他行程不能讀取此物件。
        with self._lock:
            return clone(self._documents)
