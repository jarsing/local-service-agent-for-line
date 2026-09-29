"""Optional real Firestore Emulator check. Never connects a production project."""
import os
import secrets
import unittest
from examples.day12.inherit import Actor, grant_key
from firestore_store import FirestoreStore
from examples.day14.memory import PreferenceMemory, PreferenceChanged
from .context_store import ContextJournal
from .session_budget import SafeTurn


class EmulatorTests(unittest.TestCase):
    def setUp(self):
        if not os.getenv("FIRESTORE_EMULATOR_HOST"):
            raise RuntimeError("FIRESTORE_EMULATOR_HOST_REQUIRED")
        self.store = FirestoreStore(
            "demo-local-day15", "day11-d15-" + secrets.token_hex(6)
        )
        self.addCleanup(self.store.close)
        self.actor = Actor("synthetic-day15", "synthetic-user", "A")
        self.store.atomic(lambda tx: tx.put("grants", grant_key(self.actor), {
            "allowed": True,
            "actor": {"tenant_id": self.actor.tenant_id, "user_id": self.actor.user_id}
        }))
        self.memory = PreferenceMemory(self.store, "synthetic-" + "s" * 40)
        self.journal = ContextJournal(self.memory)

    def test_write_then_new_journal_read(self):
        s = self.journal.read(self.actor)
        self.journal.append(self.actor, s, "a", SafeTurn("places", "花壇鄉"))
        self.assertEqual(ContextJournal(self.memory).read(self.actor)
                         .window.turns[0].area, "花壇鄉")

    def test_revision_change_rejects_old_context(self):
        s = self.journal.read(self.actor)
        self.memory.forget(self.actor, "forget")
        with self.assertRaises(PreferenceChanged):
            self.journal.append(self.actor, s, "a", SafeTurn("help"))

    def test_same_event_idempotent(self):
        s = self.journal.read(self.actor)
        self.journal.append(self.actor, s, "a", SafeTurn("help"))
        self.assertFalse(self.journal.append(self.actor, s, "a", SafeTurn("help")))

    def test_all_reads_before_write(self):
        self.journal.clear(self.actor)
        s = self.journal.read(self.actor)
        self.assertEqual(s.window.turns, ())
