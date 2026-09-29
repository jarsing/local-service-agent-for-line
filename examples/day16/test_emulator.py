"""Actual Firestore Emulator with a demo project and fresh namespace only."""
import os
import secrets
import unittest
from google.cloud import firestore  # Missing SDK must fail this group.
from examples.day12.inherit import Actor, grant_key
from firestore_store import FirestoreStore
from examples.day14.memory import PreferenceMemory
from .read_tools import DocumentTools, ReadStore
from .policy import PermissionDenied


class EmulatorTests(unittest.TestCase):
    def setUp(self):
        if not os.getenv("FIRESTORE_EMULATOR_HOST"):
            raise RuntimeError("FIRESTORE_EMULATOR_HOST_REQUIRED")
        self.store = FirestoreStore("demo-local-day16", "day11-d16-" + secrets.token_hex(6))
        self.actor = Actor("synthetic-tenant", "synthetic-owner", "A")
        self.store.atomic(lambda tx: tx.put("grants", grant_key(self.actor), {
            "allowed": True, "actor": {"tenant_id": self.actor.tenant_id, "user_id": self.actor.user_id}
        }))
        self.memory = PreferenceMemory(self.store, "synthetic-emulator-" + "s" * 40)
        self.tools = DocumentTools(self.memory, self.actor, "reader-session")

    def test_read_transaction_query(self):
        result = self.tools.execute("search_local_places", {"area": "花壇鄉"}, self.tools.policy.bound)
        self.assertTrue(result["places"])

    def test_forbidden_tool_refused(self):
        with self.assertRaises(PermissionDenied):
            self.tools.execute("forget_memory", {}, self.tools.policy.bound)
        self.assertEqual(self.memory.inspect(self.actor)["revision"], 0)

    def test_latest_revision_checked(self):
        self.memory.forget(self.actor, "authorized-change")
        with self.assertRaises(PermissionDenied):
            self.tools.execute("show_local_help", {}, self.tools.policy.bound)

    def test_read_only_wrapper_stops_accidental_write(self):
        with self.assertRaises(PermissionDenied):
            ReadStore(self.store).atomic(lambda tx: tx.put("requests", "forbidden", {}))
