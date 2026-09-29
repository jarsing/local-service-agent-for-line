import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from .documents import sample_document
from .policy import PermissionDenied
from .read_tools import DocumentTools
from .testing import (seed, install_write_probe, observed_writes, changed_keys,
                      ScriptedDocumentReader)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "audit.sqlite3"
        self.store, self.memory, self.actor = seed(self.path)
        install_write_probe(self.path)

    def test_safe_read_zero_physical_writes(self):
        before = self.store.inspect()
        asyncio.run(ScriptedDocumentReader().ask(sample_document(), "查花壇", self.actor, "one", self.memory))
        self.assertEqual(observed_writes(self.path), [])
        self.assertEqual(changed_keys(before, self.store.inspect()), [])

    def test_forbidden_requests_zero_physical_writes(self):
        for name in ("create_handoff_request", "approve_memory", "forget_memory"):
            tools = DocumentTools(self.memory, self.actor, "s")
            with self.assertRaises(PermissionDenied):
                tools.execute(name, {}, tools.policy.bound)
        self.assertEqual(observed_writes(self.path), [])

    def test_detector_positive_control_detects_update_then_restore(self):
        before = self.store.inspect()
        with closing(sqlite3.connect(self.path)) as conn:
            old = conn.execute("SELECT body FROM docs WHERE kind='requests'").fetchone()[0]
            conn.execute("UPDATE docs SET body='{}' WHERE kind='requests'")
            conn.execute("UPDATE docs SET body=? WHERE kind='requests'", (old,))
            conn.commit()
        self.assertEqual(before, self.store.inspect())
        self.assertEqual(len(observed_writes(self.path)), 2)

    def test_normal_user_forget_remains_possible(self):
        self.memory.forget(self.actor, "trusted-action")
        self.assertIsNone(self.memory.inspect(self.actor)["dietary_type"])
        self.assertGreater(len(observed_writes(self.path)), 0)

    def test_changed_rows_independent_of_write_counter(self):
        before = self.store.inspect()
        self.store.atomic(lambda tx: tx.put("requests", "new", {"status": "synthetic-test"}))
        self.assertEqual(changed_keys(before, self.store.inspect()), [{"kind": "requests", "ident": "new"}])
