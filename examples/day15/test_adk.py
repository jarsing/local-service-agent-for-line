"""Real ADK Runner with a scripted BaseLlm. Import failure is NOT a pass."""
import json
import tempfile
import unittest
from pathlib import Path
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from examples.day12.inherit import Actor, SQLiteTestStore, grant_key
from examples.day14.memory import PreferenceMemory
from examples.day14.engine import TurnTools
from .adk_budget_router import BudgetAdkInterpreter
from .session_budget import MODEL_ID, ByteCounter, SafeTurn
from .context_store import ContextJournal


class ScriptedModel(BaseLlm):
    model: str = "synthetic-day15-not-gemini"

    async def generate_content_async(self, llm_request, stream=False):
        # Tests orchestration/shape, explicitly not semantic understanding.
        area = "花壇鄉" if "花壇鄉" in json.dumps(
            [c.model_dump(mode="json") for c in llm_request.contents],
            ensure_ascii=False
        ) else ""
        yield LlmResponse(content=types.Content(role="model", parts=[
            types.Part(function_call=types.FunctionCall(
                name="search_local_places",
                args={"area": area, "dietary_type": "", "keyword": ""},
                id="SYNTHETIC-DAY15-CALL"
            ))
        ]))


class AdkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SQLiteTestStore(Path(self.tmp.name) / "state.sqlite3")
        self.actor = Actor("synthetic-t", "synthetic-u", "A")
        self.store.atomic(lambda tx: tx.put("grants", grant_key(self.actor), {
            "allowed": True,
            "actor": {"tenant_id": self.actor.tenant_id, "user_id": self.actor.user_id}
        }))
        self.memory = PreferenceMemory(self.store, "synthetic-" + "s" * 40)
        self.journal = ContextJournal(self.memory)

    async def ask(self, eid):
        router = BudgetAdkInterpreter(
            MODEL_ID, counter=ByteCounter(), model_override=ScriptedModel()
        )
        return await router.ask("剛才那個鄉鎮再找吃的", self.actor, eid,
                                TurnTools(self.memory, self.actor))

    async def test_real_runner_receives_projected_context(self):
        self.journal.append(self.actor, self.journal.read(self.actor), "first",
                            SafeTurn("places", "花壇鄉"))
        result = await self.ask("next")
        self.assertEqual(result["result"]["query"]["area"], "花壇鄉")
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual(result["budget"]["unit"], "utf8_bytes")
        self.assertEqual(result["mode"], "ADK_SCRIPTED")

    async def test_same_prompt_different_backend_preference(self):
        # Static policy mentions enums; compare identical whole model requests.
        p = self.memory.propose(self.actor, "vegan", "one")
        self.memory.approve(self.actor, p["token"])
        a = await self.ask("a")
        p = self.memory.propose(self.actor, "ovo_lacto", "two")
        self.memory.approve(self.actor, p["token"])
        b = await self.ask("b")
        self.assertEqual(a["model_inputs"], b["model_inputs"])
        self.assertEqual(a["result"]["query"]["dietary_type"], "vegan")
        self.assertEqual(b["result"]["query"]["dietary_type"], "ovo_lacto")

    async def test_whole_tool_triplet_and_no_second_generation(self):
        result = await self.ask("a")
        self.assertEqual(len(result["adk_events"]), 3)
        self.assertTrue(result["trace_linkage"]["trace_linked"])
        self.assertEqual(result["model_calls"], 1)

    async def test_fresh_sessions_share_context_not_raw_history(self):
        a = await self.ask("a")
        b = await self.ask("b")
        self.assertNotEqual(a["session_id"], b["session_id"])
        self.assertEqual(b["budget"]["kept_turns"], 1)

    async def test_tools_remain_outside_model_parameters(self):
        result = await self.ask("a")
        for event in result["adk_events"]:
            if "args" in event:
                self.assertNotIn("tool_context", event["args"])
                self.assertNotIn("approved", event["args"])
