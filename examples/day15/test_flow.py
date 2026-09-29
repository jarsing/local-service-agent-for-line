"""New signed webhook integration, original SQLite/consent, scripted model/LINE."""
import json
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient

from examples.day12.testing import settings, ReplyRecorder, event, post, RAW_USER
from examples.day12.identity import make_actor
from examples.day12.inherit import SQLiteTestStore
from examples.day14.test_support import Clock
from examples.day14.test_flow import action_data
from .main import BudgetApplication, create_app
from .testing import ScriptedBudgetInterpreter
from .context_store import ContextJournal, COLLECTION


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = settings(Path(self.tmp.name) / "state.sqlite3")
        self.clock = Clock()
        self.store = SQLiteTestStore(self.config.sqlite_path)
        self.sender = ReplyRecorder()
        self.interpreter = ScriptedBudgetInterpreter({
            "查花壇": ("search_local_places", {"area": "花壇鄉"}),
            "以後幫我記住蔬食": ("propose_dietary_memory",
                               {"dietary_type": "vegetarian"}),
        })
        self.app = BudgetApplication(
            self.config, self.store, self.interpreter, self.sender, clock=self.clock
        )
        self.actor = make_actor(self.config, RAW_USER)
        self.app.tasks.seed([self.actor])
        self.client = TestClient(create_app(self.app))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.seq = 0

    def send(self, text=None, data=None):
        self.seq += 1
        ev = event("synthetic-day15-" + str(self.seq), text=text, data=data)
        ev["timestamp"] = int(self.clock().timestamp() * 1000)
        response = post(self.client, self.config, ev)
        self.assertEqual(response.status_code, 200)
        return self.sender.sent[-1]

    def test_previous_area_then_followup(self):
        self.send("查花壇")
        self.send("剛才那個鄉鎮再找吃的")
        self.assertEqual(self.interpreter.reports[-1]["tool_events"][0]
                         ["effective_arguments"]["area"], "花壇鄉")

    def test_forget_clears_context_and_keeps_old_card_invalid(self):
        offer = self.send("以後幫我記住蔬食")
        old = action_data(offer, "m14:approve:")
        self.send(data=old)
        self.send("查花壇")
        self.send("忘記我的飲食偏好")
        self.assertFalse(ContextJournal(self.app.memory).read(self.actor).window.turns)
        self.send(data=old)
        self.assertIsNone(self.app.memory.inspect(self.actor)["dietary_type"])
        rows = self.store.inspect()
        for forbidden in ("vegetarian", "dietary_type", "以後幫我記住"):
            self.assertNotIn(forbidden, json.dumps(rows.get(COLLECTION, {})))

    def test_three_buttons_without_model(self):
        self.send("我要預約")
        self.assertEqual(len(self.interpreter.reports), 0)

    def test_original_request_still_one(self):
        message = self.send("新需求：需要手語志工支援")
        data = action_data(message, "confirm:")
        self.send(data=data)
        self.send(data=data)
        self.assertEqual(len(self.store.inspect()["requests"]), 1)

    def test_bad_signature_no_sender(self):
        response = post(self.client, self.config, event("bad", text="查花壇"),
                        signature_override="invalid")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.sender.sent, [])

    def test_counter_failure_prevents_model_and_returns_help(self):
        self.interpreter.limit = 1
        self.send("查花壇")
        self.assertEqual(self.interpreter.reports, [])
        self.assertIn("查詢", json.dumps(self.sender.sent[-1], ensure_ascii=False))

    def test_same_event_no_duplicate_projection(self):
        ev = event("same", text="查花壇")
        ev["timestamp"] = int(self.clock().timestamp() * 1000)
        post(self.client, self.config, ev)
        post(self.client, self.config, ev)
        self.assertEqual(len(self.interpreter.reports), 1)

    def test_no_personalized_reply_plan_persisted(self):
        self.send("查花壇")
        for row in self.store.inspect().get("line_events", {}).values():
            self.assertIsNone(row.get("plan"))

    def test_area_button_also_supplies_short_context(self):
        self.send(data="d14:area:花壇鄉")
        self.send("剛才那個鄉鎮再找吃的")
        self.assertEqual(self.interpreter.reports[-1]["tool_events"][0]
                         ["effective_arguments"]["area"], "花壇鄉")
