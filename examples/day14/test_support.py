"""合成角色與測試資料；無真人資料、無遠端 API。"""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from examples.day12.inherit import Actor, SQLiteTestStore, grant_key
from .memory import PreferenceMemory

class Clock:
    def __init__(self): self.now=datetime(2026,9,28,1,tzinfo=timezone.utc)
    def __call__(self): return self.now

class MemoryCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=SQLiteTestStore(Path(self.tmp.name)/'tasks.sqlite3');self.clock=Clock()
        self.actor=Actor('synthetic-tenant','synthetic-user','session-A')
        self.other=Actor('synthetic-tenant','synthetic-other','session-B')
        self.memory=PreferenceMemory(self.store,'synthetic-secret-'+'a'*32,clock=self.clock)
        self.grant(self.actor,True);self.grant(self.other,True)
    def grant(self,actor,allowed):
        self.store.atomic(lambda tx:tx.put('grants',grant_key(actor),
            {'allowed':allowed,'actor':{'tenant_id':actor.tenant_id,'user_id':actor.user_id}}))
    def save(self,value='vegetarian',event='save-1',actor=None):
        actor=actor or self.actor
        p=self.memory.propose(actor,value,event)
        return p,self.memory.approve(actor,p['token'])
