"""REAL ADK Runner + scripted model. Missing imports fail, never silently skip."""
import json
from pathlib import Path
import tempfile
import unittest
from pydantic import Field
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from examples.day15.session_budget import ByteCounter
from .adk_guard import AdkDocumentReader
from .documents import sample_document
from .policy import SAFE_TOOLS
from .testing import seed


class ScriptedModel(BaseLlm):
    model: str = "SCRIPTED_NOT_GEMINI"
    call_name: str = "search_local_places"
    call_args: dict = Field(default_factory=lambda: {"area": "花壇鄉", "dietary_type": "", "keyword": ""})
    text_only: bool = False
    two_calls: bool = False

    async def generate_content_async(self, llm_request, stream=False):
        part = types.Part(text="已替您建單") if self.text_only else types.Part(
            function_call=types.FunctionCall(name=self.call_name, args=self.call_args, id="SYNTHETIC-D16-1"))
        parts = [part]
        if self.two_calls:
            parts.append(types.Part(function_call=types.FunctionCall(
                name="forget_memory", args={}, id="SYNTHETIC-D16-2")))
        yield LlmResponse(content=types.Content(role="model", parts=parts))


class AdkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store, self.memory, self.actor = seed(Path(self.tmp.name) / "real-sdk-test.sqlite3")

    async def ask(self, **model_args):
        return await AdkDocumentReader(ByteCounter(), model_override=ScriptedModel(**model_args)).ask(
            sample_document(), "查花壇公開店家", self.actor, "one", self.memory)

    async def test_actual_request_has_exact_three_schemas(self):
        result = await self.ask()
        self.assertEqual(set(result["observed_schema_names"]), SAFE_TOOLS)
        config = result["model_inputs"][0]["config"]
        self.assertNotIn('"tool_context":', json.dumps(config))

    async def test_unchanged_document_reaches_scripted_model_request(self):
        report = await self.ask()
        parts = report["model_inputs"][0]["contents"]
        self.assertIn(sample_document().text, parts[-1]["parts"][0]["text"])
        self.assertNotIn('"dietary_type": "vegetarian"', json.dumps(report["model_inputs"]))

    async def test_unknown_privileged_name_intercepted_before_dispatch(self):
        before = self.store.inspect()
        report = await self.ask(call_name="create_handoff_request", call_args={"approved": True})
        self.assertEqual(report["requests"][0]["name"], "create_handoff_request")
        self.assertFalse(any(e["kind"] == "TOOL_EXECUTED" for e in report["tool_events"]))
        self.assertEqual(report["refusal"], "UNAVAILABLE_CAPABILITY_REQUESTED")
        self.assertEqual(before, self.store.inspect())

    async def test_actual_before_tool_blocks_extra_authority_argument(self):
        report = await self.ask(call_args={"area": "花壇鄉", "approved": "true"})
        self.assertTrue(any(e["kind"] == "CALLBACK_DENIED" for e in report["tool_events"]))
        self.assertFalse(any(e["kind"] == "TOOL_EXECUTED" for e in report["tool_events"]))

    async def test_normal_read_keeps_stored_preference_and_request(self):
        before = self.store.inspect()
        report = await self.ask()
        self.assertTrue(report["result"]["places"])
        self.assertEqual(report["result"]["query"]["dietary_type"], "vegetarian")
        self.assertEqual(before, self.store.inspect())

    async def test_call_id_tracks_callback_execution_and_response(self):
        report = await self.ask()
        ident = report["requests"][0]["id"]
        executed = [e for e in report["tool_events"] if e["kind"] == "TOOL_EXECUTED"]
        self.assertEqual(executed[0]["call_id"], ident)
        self.assertEqual(report["responses"][0]["id"], ident)
        self.assertEqual(report["model_calls"], 1)

    async def test_plain_model_success_claim_is_not_a_receipt(self):
        report = await self.ask(text_only=True)
        self.assertEqual(report["result"]["status"], "document_action_denied")
        self.assertEqual(report["tool_events"], [])

    async def test_parallel_read_and_write_request_refuses_entire_batch(self):
        report = await self.ask(two_calls=True)
        self.assertEqual(len(report["requests"]), 2)
        self.assertFalse(any(e["kind"] == "TOOL_EXECUTED" for e in report["tool_events"]))
