"""真正 google-cloud-firestore adapter；預設只連本機模擬器，絕不靜默退回測試替身。"""
from __future__ import annotations
import os
import re
from urllib.parse import urlsplit
from domain import clone, ContractError
from store import StoreUnavailable


class FirestoreTx:
    def __init__(self, root, transaction, *, read_only):
        self.root=root;self.tx=transaction;self.read_only=read_only;self.written=False
    def ref(self, kind, ident):
        if not re.fullmatch(r'[a-z_]+',kind) or not re.fullmatch(r'[a-f0-9]{64}',ident):
            raise ValueError('文件路徑不符合本篇契約。')
        return self.root.collection(kind).document(ident)
    def get(self, kind, ident):
        if self.written:raise ContractError('交易必須先讀後寫。')
        snap=self.ref(kind,ident).get(transaction=self.tx,retry=None,timeout=10)
        return clone(snap.to_dict()) if snap.exists else None
    def _write(self, kind, ident, value, create):
        if self.read_only:raise ContractError('唯讀交易不能寫入。')
        data=clone(value)
        (self.tx.create if create else self.tx.set)(self.ref(kind,ident),data)
        self.written=True
    def put(self,kind,ident,value):self._write(kind,ident,value,False)
    def create(self,kind,ident,value):self._write(kind,ident,value,True)


def transient_storage_error(exc, errors):
    """接受已分類的 RPC 錯誤；交易重試用盡若包成 ValueError，只認 Aborted cause。"""
    transient = (errors.ServiceUnavailable, errors.DeadlineExceeded,
                 errors.Aborted, errors.ResourceExhausted)
    if isinstance(exc, transient):
        return True
    return isinstance(exc, ValueError) and isinstance(exc.__cause__, errors.Aborted)


def validate_target(project, namespace, *, cloud=False, approve_cloud=False):
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,61}[a-z0-9]',project):
        raise ValueError('請明示有效 project ID。')
    if not re.fullmatch(r'day11-[a-zA-Z0-9_-]{1,80}',namespace):
        raise ValueError('本篇僅操作 day11- 開頭的隔離命名空間。')
    host=os.environ.get('FIRESTORE_EMULATOR_HOST','')
    if cloud:
        if not approve_cloud or host or project.startswith('demo-'):
            raise ValueError('正式 Firestore 需明示核准，且不能設定 emulator host 或 demo project。')
    else:
        if not project.startswith('demo-') or not host or '://' in host:
            raise ValueError('模擬器需 demo- project 與不含協定的 FIRESTORE_EMULATOR_HOST。')
        target=urlsplit('//'+host)
        if (target.hostname not in ('127.0.0.1','localhost','::1') or not target.port
                or target.path or target.query or target.fragment or target.username or target.password):
            raise ValueError('本篇模擬器只允許明示的 loopback host:port。')
    return host


class FirestoreStore:
    def __init__(self,project,namespace,*,cloud=False,approve_cloud=False):
        self.host=validate_target(project,namespace,cloud=cloud,approve_cloud=approve_cloud)
        from google.cloud import firestore
        from google.auth.credentials import AnonymousCredentials
        from google.api_core import exceptions
        self.api=firestore;self.errors=exceptions
        self.client=firestore.Client(project=project,database='(default)',
            **({} if cloud else {'credentials':AnonymousCredentials()}))
        self.root=self.client.collection('local_day11_demo').document(namespace)
        self.mode='FIRESTORE_CLOUD' if cloud else 'FIRESTORE_EMULATOR'
        self.project=project;self.namespace=namespace

    def atomic(self, fn, *, read_only=False):
        @self.api.transactional
        def apply(transaction):
            # fn 只讀寫文件；LLM、LINE、事件輸出與亂數產生放在外面。
            return fn(FirestoreTx(self.root,transaction,read_only=read_only))
        try:
            return apply(self.client.transaction(max_attempts=3,read_only=read_only))
        except Exception as exc:
            if transient_storage_error(exc, self.errors):
                raise StoreUnavailable(type(exc).__name__) from exc
            raise

    def inspect(self):
        # 非原子稽核快照，只在示範子行程已退出、沒有背景 worker 時使用。
        kinds=('bindings','confirmations','requests','jobs','sessions','grants','catalogs','drafts')
        result={}
        for kind in kinds:
            docs=list(self.root.collection(kind).stream(retry=None,timeout=20))
            if docs:result[kind]={d.id:clone(d.to_dict()) for d in docs}
        return result

    def close(self):self.client.close()
