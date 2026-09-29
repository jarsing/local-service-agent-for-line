"""Real SQLite adapter + original PreferenceMemory, using synthetic identities."""
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from examples.day14.test_support import MemoryCase
from examples.day12.inherit import Actor
from examples.day14.memory import PreferenceChanged
from .context_store import ContextJournal, ContextChanged, project_result, COLLECTION
from .session_budget import SafeTurn


class JournalTests(MemoryCase):
    def setUp(self):
        super().setUp()
        self.journal = ContextJournal(self.memory)

    def add(self, event="a"):
        s = self.journal.read(self.actor)
        self.journal.append(self.actor, s, event, SafeTurn("places", "花壇鄉"))
        return s

    def test_persist_and_new_session(self):
        self.add()
        new = Actor(self.actor.tenant_id, self.actor.user_id, "new-backend-session")
        self.assertEqual(self.journal.read(new).window.turns[0].area, "花壇鄉")

    def test_other_owner_empty(self):
        self.add()
        self.assertFalse(self.journal.read(self.other).window.turns)

    def test_other_tenant_empty(self):
        self.add()
        other = Actor("another-tenant", self.actor.user_id, "new")
        self.grant(other, True)
        self.assertFalse(self.journal.read(other).window.turns)

    def test_denied_read(self):
        self.add()
        self.grant(self.actor, False)
        with self.assertRaises(PermissionError):
            self.journal.read(self.actor)

    def test_denied_append(self):
        s = self.journal.read(self.actor)
        self.grant(self.actor, False)
        with self.assertRaises(PermissionError):
            self.journal.append(self.actor, s, "b", SafeTurn("help"))

    def test_forget_invalidates_context(self):
        self.save()
        self.add()
        self.memory.forget(self.actor, "forget")
        self.assertFalse(self.journal.read(self.actor).window.turns)
        self.assertFalse(self.journal.read(self.actor).window.summary.goal)

    def test_update_invalidates_old_snapshot(self):
        self.add()
        s = self.journal.read(self.actor)
        self.save("ovo_lacto")
        with self.assertRaises(PreferenceChanged):
            self.journal.assert_current(self.actor, s)

    def test_old_append_after_forget_fails(self):
        self.add()
        s = self.journal.read(self.actor)
        self.memory.forget(self.actor, "forget")
        with self.assertRaises(PreferenceChanged):
            self.journal.append(self.actor, s, "b", SafeTurn("help"))

    def test_expiry(self):
        self.add()
        self.clock.now += timedelta(seconds=900)
        self.assertFalse(self.journal.read(self.actor).window.turns)

    def test_mid_request_expiry_is_conflict(self):
        self.add()
        s = self.journal.read(self.actor)
        self.clock.now += timedelta(seconds=900)
        with self.assertRaises(ContextChanged):
            self.journal.assert_current(self.actor, s)

    def test_expired_snapshot_cannot_reseed_old_context(self):
        self.add()
        s = self.journal.read(self.actor)
        self.clock.now += timedelta(seconds=900)
        with self.assertRaises(ContextChanged):
            self.journal.append(self.actor, s, "b", SafeTurn("places", "花壇鄉"))

    def test_idempotent_same_event(self):
        s = self.add()
        self.assertFalse(self.journal.append(self.actor, s, "a", SafeTurn("places", "花壇鄉")))
        self.assertEqual(self.journal.read(self.actor).generation, 1)

    def test_stale_context_cannot_overwrite(self):
        s = self.add()
        with self.assertRaises(ContextChanged):
            self.journal.append(self.actor, s, "new-event", SafeTurn("help"))

    def test_parallel_cas_one_winner(self):
        s = self.journal.read(self.actor)
        def run(i):
            try:
                return self.journal.append(self.actor, s, str(i), SafeTurn("help"))
            except ContextChanged:
                return False
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(run, (1, 2)))
        self.assertEqual(results.count(True), 1)

    def test_clear_does_not_forget_consented_value(self):
        self.save()
        self.add()
        self.journal.clear(self.actor)
        self.assertEqual(self.memory.inspect(self.actor)["dietary_type"], "vegetarian")
        self.assertFalse(self.journal.read(self.actor).window.turns)

    def test_no_raw_payload_in_sqlite_context(self):
        self.save()
        self.add("private-event-value")
        records = self.store.inspect()[COLLECTION]
        text = repr(records)
        for forbidden in ("private-event-value", "vegetarian", "dietary_type", "consented_at"):
            self.assertNotIn(forbidden, text)

    def test_older_goal_survives_pruning(self):
        self.add()
        for eid in ("b", "c", "d"):
            s = self.journal.read(self.actor)
            self.journal.append(self.actor, s, eid, SafeTurn("help"))
        s = self.journal.read(self.actor)
        self.assertEqual(s.window.summary.area, "花壇鄉")
        self.assertEqual(len(s.window.turns), 2)

    def test_project_result_ignores_private_fields(self):
        t = project_result({"tool": "search_local_places",
                            "query": {"area": "花壇鄉", "dietary_type": "vegetarian"},
                            "approved": True, "request_id": "req-private"})
        self.assertEqual(t, SafeTurn("places", "花壇鄉"))

    def test_projection_does_not_trust_model_prose(self):
        t = project_result({"model_text": "記住私人住址", "status": "help"})
        self.assertEqual(t, SafeTurn("help"))

    def test_same_event_different_projection_rejected(self):
        s = self.add()
        with self.assertRaises(ContextChanged):
            self.journal.append(self.actor, s, "a", SafeTurn("places", "彰化市"))
