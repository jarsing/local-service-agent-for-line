"""真正 Firestore Emulator 契約；不觸碰 cloud，不默默退回 SQLite。"""
from dataclasses import replace
import os
import secrets
import unittest
from examples.day12.inherit import Actor, grant_key
from firestore_store import FirestoreStore
from .memory import PreferenceMemory, COLLECTION, owner_key
from .engine import TurnTools

class EmulatorTests(unittest.TestCase):
    def setUp(self):
        self.store=FirestoreStore('demo-local-day14','day11-d14-'+secrets.token_hex(5))
        self.addCleanup(self.store.close)
        self.actor=Actor('synthetic-emulator','synthetic-user','A')
        self.store.atomic(lambda tx:tx.put('grants',grant_key(self.actor),{'allowed':True,'actor':{'tenant_id':self.actor.tenant_id,'user_id':self.actor.user_id}}))
        self.memory=PreferenceMemory(self.store,'SYNTHETIC_'+('a'*32))
    def save(self):
        p=self.memory.propose(self.actor,'vegetarian','a');self.memory.approve(self.actor,p['token']);return p
    def test_cross_session_uses_firestore(self):
        self.save();r=TurnTools(self.memory,replace(self.actor,session_id='B')).execute('search_local_places',{'area':'花壇鄉'})
        self.assertEqual(r['query']['dietary_type'],'vegetarian');self.assertEqual(self.store.mode,'FIRESTORE_EMULATOR')
    def test_forget_document_really_has_no_value(self):
        self.save();self.memory.forget(self.actor,'f')
        row=self.store.atomic(lambda tx:tx.get(COLLECTION,owner_key(self.actor)),read_only=True)
        self.assertNotIn('dietary_type',row)
    def test_stale_card_cannot_restore(self):
        p=self.save();self.memory.forget(self.actor,'f')
        self.assertEqual(self.memory.approve(self.actor,p['token'])['status'],'stale_memory_card')
    def test_proposal_has_no_profile_document(self):
        self.memory.propose(self.actor,'vegan','a')
        row=self.store.atomic(lambda tx:tx.get(COLLECTION,owner_key(self.actor)),read_only=True)
        self.assertIsNone(row)
