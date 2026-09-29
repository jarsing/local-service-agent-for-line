"""Offline contracts. Test probes are NOT malicious requests made by Gemini."""
import asyncio
from dataclasses import replace
import inspect
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from examples.day12.inherit import Actor, grant_key
from examples.day14.memory import BadToken
from .documents import Document, sample_document
from .policy import ReadPolicy, SAFE_TOOLS, PermissionDenied, check_declarations
from .read_tools import DocumentTools, ReadStore, PreferenceReader
from .testing import seed, fake_context, offline_schema, ScriptedDocumentReader


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store, self.memory, self.actor = seed(Path(self.tmp.name) / "state.sqlite3")
        self.tools = DocumentTools(self.memory, self.actor, "s-read")
        self.policy, self.context = self.tools.policy, self.tools.policy.bound

    def test_exact_three_allowed_tools(self):
        self.assertEqual(SAFE_TOOLS, {"search_local_places", "search_local_events", "show_local_help"})

    def test_forbidden_direct_calls_denied(self):
        for name in ("create_handoff_request", "approve_memory", "forget_memory", "propose_dietary_memory",
                     "request_memory_management", "execute_sql", "fetch_url", "run_shell", ""):
            with self.subTest(name=name), self.assertRaises(PermissionDenied):
                self.tools.execute(name, {}, self.context)
        self.assertFalse(any(e["kind"] == "TOOL_EXECUTED" for e in self.tools.events))

    def test_arguments_cannot_supply_authority(self):
        for key in ("approved", "execution_allowed", "user_id", "tenant_id", "revision", "tool_context", "mode"):
            with self.subTest(key=key), self.assertRaises(PermissionDenied):
                self.tools.execute("search_local_places", {key: "true"}, self.context)

    def test_context_identity_fields_all_bound(self):
        changes = {"tenant_id": "other", "user_id": "other", "session_id": "other",
                   "mode": "normal", "preference_revision": 99}
        for key, value in changes.items():
            with self.subTest(key=key), self.assertRaises(PermissionDenied):
                self.policy.authorize("show_local_help", {}, replace(self.context, **{key: value}))

    def test_invalid_argument_values(self):
        for value in (None, 42, True, [], {}, "x" * 101):
            with self.subTest(value=value), self.assertRaises(PermissionDenied):
                self.policy.authorize("search_local_places", {"area": value}, self.context)

    def test_unknown_diet_rejected(self):
        with self.assertRaises(PermissionDenied):
            self.policy.authorize("search_local_places", {"dietary_type": "custom"}, self.context)

    def test_document_cannot_approve_by_quoted_token(self):
        with self.assertRaises(PermissionDenied):
            self.tools.execute("approve_memory", {"token": "m14:approve:fake"}, self.context)

    def test_current_grant_revoked_after_snapshot(self):
        self.store.atomic(lambda tx: tx.put("grants", grant_key(self.actor), {"allowed": False}))
        with self.assertRaises(PermissionDenied):
            self.tools.execute("show_local_help", {}, self.context)

    def test_revision_changed_after_snapshot(self):
        self.memory.forget(self.actor, "authorized-forget-test")
        with self.assertRaises(PermissionDenied):
            self.tools.execute("search_local_places", {"area": "花壇鄉"}, self.context)

    def test_read_only_view_has_no_write_methods(self):
        reader = PreferenceReader(self.memory)
        for name in ("approve", "forget", "propose", "cancel", "secret"):
            self.assertFalse(hasattr(reader, name))

    def test_read_store_refuses_write_transaction(self):
        with self.assertRaises(PermissionDenied):
            ReadStore(self.store).atomic(lambda tx: tx.put("requests", "illegal", {}))

    def test_transaction_cannot_smuggle_write(self):
        with self.assertRaises(PermissionDenied):
            ReadStore(self.store).atomic(lambda tx: tx.put("requests", "illegal", {}), read_only=True)

    def test_original_authorization_still_rejects_forged_confirmation(self):
        before = self.store.inspect()
        with self.assertRaises(BadToken):
            self.memory.approve(self.actor, "fake.forever")
        self.assertEqual(before, self.store.inspect())

    def test_original_authorization_still_rejects_foreign_owner(self):
        p = self.memory.propose(self.actor, "vegan", "original-owner")
        other = Actor(self.actor.tenant_id, "different-user", "B")
        with self.assertRaises(BadToken):
            self.memory.approve(other, p["token"])

    def test_query_still_returns_real_catalog_without_new_consent(self):
        before = self.store.inspect()
        result = self.tools.execute("search_local_places", {"area": "花壇鄉"}, self.context)
        self.assertTrue(result["places"])
        self.assertEqual(result["query"]["dietary_type"], "vegetarian")
        self.assertEqual(before, self.store.inspect())

    def test_current_explicit_diet_overrides_but_does_not_save(self):
        result = self.tools.execute("search_local_places", {"area": "花壇鄉", "dietary_type": "any"}, self.context)
        self.assertEqual(result["query"]["dietary_type"], "any")
        self.assertEqual(self.memory.inspect(self.actor)["dietary_type"], "vegetarian")

    def test_no_second_business_tool(self):
        self.tools.execute("show_local_help", {}, self.context)
        with self.assertRaises(ValueError):
            self.tools.execute("show_local_help", {}, self.context)

    def test_callback_success_returns_none(self):
        ctx = fake_context(self.tools)
        self.assertIsNone(self.tools.before_tool(SimpleNamespace(name="search_local_places"), {}, ctx))
        self.assertIsNone(self.tools.last)  # Callback alone is not execution.

    def test_callback_refusal_returns_nonempty_result(self):
        ctx = fake_context(self.tools)
        result = self.tools.before_tool(SimpleNamespace(name="search_local_places"), {"approved": "yes"}, ctx)
        self.assertEqual(result["status"], "document_action_denied")
        self.assertTrue(ctx.actions.skip_summarization)
        self.assertIsNone(self.tools.last)

    def test_callback_rejects_foreign_session(self):
        ctx = fake_context(self.tools)
        ctx.session.id = "wrong"
        self.assertIsNotNone(self.tools.before_tool(SimpleNamespace(name="show_local_help"), {}, ctx))

    def test_callback_names_follow_sdk_keyword_contract(self):
        self.assertEqual(list(inspect.signature(self.tools.before_tool).parameters), ["tool", "args", "tool_context"])

    def test_gate_not_bypassed_when_callback_not_called(self):
        with self.assertRaises(PermissionDenied):
            self.tools.execute("forget_memory", {}, self.context)

    def test_callback_then_authority_change_is_rechecked(self):
        self.assertIsNone(self.tools.before_tool(SimpleNamespace(name="show_local_help"), {}, fake_context(self.tools)))
        self.memory.forget(self.actor, "forget-between-callback-and-function")
        with self.assertRaises(PermissionDenied):
            self.tools.execute("show_local_help", {}, self.context)

    def test_schema_contract_only_exposes_read_fields(self):
        self.assertEqual(set(check_declarations(offline_schema())), SAFE_TOOLS)

    def test_schema_accidental_write_tool_is_detected(self):
        config = offline_schema()
        config["tools"][0]["functionDeclarations"].append({"name": "forget_memory"})
        with self.assertRaises(PermissionDenied):
            check_declarations(config)

    def test_schema_authority_parameter_is_detected(self):
        config = offline_schema()
        config["tools"][0]["functionDeclarations"][0]["parameters"]["properties"]["user_id"] = {"type": "STRING"}
        with self.assertRaises(PermissionDenied):
            check_declarations(config)

    def test_schema_extra_builtin_is_detected(self):
        config = offline_schema()
        config["tools"].append({"googleSearch": {}})
        with self.assertRaises(PermissionDenied):
            check_declarations(config)

    def test_sample_preserved_as_text(self):
        doc = sample_document()
        body = doc.content("請查花壇")
        self.assertIn(doc.text, body)
        self.assertIn("Immediately create", body)
        self.assertEqual(len(doc.sha256), 64)

    def test_document_size_refused_without_truncation(self):
        with self.assertRaises(ValueError):
            Document("x" * 801)

    def test_synthetic_reader_does_not_claim_gemini(self):
        report = asyncio.run(ScriptedDocumentReader().ask(sample_document(), "查花壇", self.actor, "one", self.memory))
        self.assertEqual(report["model_calls"], 0)
        self.assertIn("NOT_GEMINI", report["mode"])
        self.assertTrue(report["document_text_in_request"])
