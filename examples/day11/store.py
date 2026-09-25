"""小型文件交易介面。SQLite 只當明標的測試 adapter，不是假 Firestore。"""
from __future__ import annotations
from pathlib import Path
from contextlib import closing
import sqlite3
import json
from typing import Callable, Protocol, TypeVar
from domain import clone, ContractError
T = TypeVar('T')


class StoreUnavailable(RuntimeError):
    """可辨識的儲存不可用；不把任意程式錯誤當作查無資料。"""


class Transaction(Protocol):
    def get(self, collection: str, ident: str) -> dict | None: ...
    def put(self, collection: str, ident: str, value: dict) -> None: ...
    def create(self, collection: str, ident: str, value: dict) -> None: ...


class DocumentStore(Protocol):
    mode: str
    def atomic(self, fn: Callable[[Transaction], T], *, read_only: bool=False) -> T: ...
    def inspect(self) -> dict: ...


class SQLiteTx:
    def __init__(self, conn, read_only):
        self.conn=conn;self.read_only=read_only;self.written=False

    def get(self, collection, ident):
        if self.written:
            raise ContractError('交易內先完成所有讀取，再寫入。')
        row=self.conn.execute('SELECT body FROM docs WHERE kind=? AND ident=?',
                              (collection,ident)).fetchone()
        return json.loads(row[0]) if row else None

    def _write(self, collection, ident, value, create):
        if self.read_only: raise ContractError('唯讀交易不能寫入。')
        body=json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True)
        sql=('INSERT INTO docs VALUES (?,?,?)' if create else
             'INSERT INTO docs VALUES (?,?,?) ON CONFLICT(kind,ident) DO UPDATE SET body=excluded.body')
        self.conn.execute(sql,(collection,ident,body));self.written=True

    def put(self, collection, ident, value):self._write(collection,ident,value,False)
    def create(self, collection, ident, value):self._write(collection,ident,value,True)


class SQLiteTestStore:
    mode='SQLITE_TEST_ADAPTER'
    def __init__(self, path: Path | str):
        self.path=Path(path).resolve()
        if str(path)==':memory:':raise ValueError('跨行程示範需要檔案。')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path)) as c:
            c.execute('CREATE TABLE IF NOT EXISTS docs(kind TEXT, ident TEXT, body TEXT NOT NULL, PRIMARY KEY(kind,ident))')
            c.commit()

    def atomic(self, fn, *, read_only=False):
        try:
            conn=sqlite3.connect(self.path,timeout=5,isolation_level=None)
            try:
                if read_only:conn.execute('PRAGMA query_only=ON')
                conn.execute('BEGIN' if read_only else 'BEGIN IMMEDIATE')
                result=fn(SQLiteTx(conn,read_only))
                conn.commit()
                return result
            except BaseException:
                conn.rollback();raise
            finally:conn.close()
        except sqlite3.OperationalError as exc:
            code=getattr(exc,'sqlite_errorcode',0)&255
            if code in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED,sqlite3.SQLITE_CANTOPEN,sqlite3.SQLITE_IOERR):
                raise StoreUnavailable(type(exc).__name__) from exc
            raise

    def inspect(self):
        # 測試端觀察器；不是模型工具。
        conn=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)
        try:
            result={}
            for kind,ident,body in conn.execute('SELECT kind,ident,body FROM docs ORDER BY kind,ident'):
                result.setdefault(kind,{})[ident]=json.loads(body)
            return result
        finally:conn.close()
