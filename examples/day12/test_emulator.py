"""真正 Firestore 模擬器上的新手機確認接點；不在此呼叫 LINE 或 Gemini。"""
import secrets
import unittest
from .inherit import DAY11
from firestore_store import FirestoreStore
from .catalog_view import CatalogView
from .tasks import LineTasks
from .testing import settings,RAW_USER
from .identity import make_actor
from .inherit import SendArgs

class EmulatorTests(unittest.TestCase):
    def setUp(self):
        self.store=FirestoreStore('demo-local-day12','day11-d12-test-'+secrets.token_hex(6))
        self.addCleanup(self.store.close);self.actor=make_actor(settings('unused'),RAW_USER)
        self.tasks=LineTasks(self.store,CatalogView());self.tasks.seed([self.actor])
    def test_deferred_postback_confirmation_and_reopen(self):
        offer=self.tasks.offer(self.actor,'請確認集合點','event-emulator')
        self.assertFalse(self.store.inspect().get('requests'))
        first=self.tasks.decide(self.actor,offer['args']['confirmation_id'],True)
        fresh=LineTasks(self.store,CatalogView());second=fresh.status(self.actor)
        self.assertEqual(first['request_id'],second['request_id'])
        self.assertEqual(len(self.store.inspect()['requests']),1)
    def test_no_confirmation_no_create(self):
        offer=self.tasks.offer(self.actor,'尚未確認','event-2')
        result=self.tasks.original.create(self.actor,SendArgs(**offer['args']))
        self.assertEqual(result['status'],'unconfirmed_operation')
