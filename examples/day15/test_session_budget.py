"""Offline tests: concrete behavior, no Gemini inference or fake token totals."""
import asyncio
import json
import unittest
from .session_budget import (
    BudgetExceeded, BudgetSessionManager, ByteCounter, ContextWindow,
    GoalSummary, SafeTurn, canonical_bytes, render_contents,
)
from .token_counter import countable_envelope, MODEL_ID

ENV = {
    "model": "models/" + MODEL_ID,
    "systemInstruction": {"parts": [{"text": "Never replace backend facts."}]},
    "tools": [{"functionDeclarations": [{"name": "search_local_places"}]}],
}


class BudgetTests(unittest.TestCase):
    def run_budget(self, window, current="剛才那個鄉鎮，再找吃的。", limit=9000, turns=2):
        return asyncio.run(BudgetSessionManager(turns, limit, "utf8_bytes")
                           .prepare(window, current, ENV, ByteCounter()))

    def test_empty_history_keeps_current(self):
        r = self.run_budget(ContextWindow(), "今天不限，花壇有什麼吃的？")
        self.assertEqual(r.request["contents"][-1]["parts"][0]["text"],
                         "今天不限，花壇有什麼吃的？")

    def test_two_complete_pairs(self):
        w = ContextWindow((SafeTurn("places", "花壇鄉"), SafeTurn("help")))
        r = self.run_budget(w)
        self.assertEqual([x["role"] for x in r.request["contents"]],
                         ["user", "model", "user", "model", "user"])

    def test_evict_to_structured_summary(self):
        w = ContextWindow()
        for t in [SafeTurn("places", "花壇鄉"), SafeTurn("help"), SafeTurn("help")]:
            w = w.append(t)
        self.assertEqual(w.summary, GoalSummary("places", "花壇鄉"))
        self.assertEqual(len(w.turns), 2)

    def test_summary_size_is_bounded_after_many_turns(self):
        w = ContextWindow()
        for _ in range(300):
            w = w.append(SafeTurn("places", "彰化市"))
        self.assertLess(len(canonical_bytes(w.as_dict())), 350)

    def test_zero_turn_window_not_minus_zero_slice(self):
        w = ContextWindow((SafeTurn("places", "花壇鄉"), SafeTurn("help")))
        r = self.run_budget(w, turns=0)
        self.assertEqual(r.window.turns, ())
        self.assertEqual(r.window.summary.area, "花壇鄉")

    def test_explicit_current_is_not_replaced(self):
        w = ContextWindow((SafeTurn("places", "花壇鄉"),))
        r = self.run_budget(w, "這次改查彰化市，飲食不限。")
        self.assertIn("彰化市", r.request["contents"][-1]["parts"][0]["text"])

    def test_immutable_rules_and_schema_in_budget(self):
        r = self.run_budget(ContextWindow())
        self.assertEqual(r.request["systemInstruction"], ENV["systemInstruction"])
        self.assertEqual(r.request["tools"], ENV["tools"])
        self.assertEqual(r.measured_units, len(canonical_bytes(r.request)))

    def test_trim_oldest_whole_pair_under_budget(self):
        w = ContextWindow((SafeTurn("places", "花壇鄉"), SafeTurn("help")))
        base = self.run_budget(ContextWindow())
        r = self.run_budget(w, limit=base.measured_units + 50)
        self.assertEqual(len(r.request["contents"]), 1)
        self.assertGreater(len(r.measurements), 1)

    def test_current_and_rules_over_budget_raise(self):
        with self.assertRaises(BudgetExceeded):
            self.run_budget(ContextWindow(), limit=10)

    def test_budget_limit_exact(self):
        base = self.run_budget(ContextWindow())
        self.assertEqual(self.run_budget(ContextWindow(), limit=base.measured_units)
                         .measured_units, base.measured_units)

    def test_bad_current(self):
        for value in ("", " ", "x" * 1201, None):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):
                    self.run_budget(ContextWindow(), value)

    def test_bad_limits(self):
        for n in (-1, 21, True):
            with self.subTest(n=n), self.assertRaises(ValueError):
                BudgetSessionManager(max_turns=n)

    def test_counter_failure_never_substitutes_bytes(self):
        class Broken:
            unit = "tokens"
            async def __call__(self, request):
                raise RuntimeError("synthetic_counter_failure")
        with self.assertRaises(RuntimeError):
            asyncio.run(BudgetSessionManager().prepare(ContextWindow(), "花壇", ENV, Broken()))

    def test_bytes_never_pass_as_tokens(self):
        with self.assertRaises(ValueError):
            asyncio.run(BudgetSessionManager().prepare(ContextWindow(), "花壇", ENV, ByteCounter()))

    def test_no_secret_fields_allowed_in_summary(self):
        for data in ({"goal": "places", "dietary_type": "vegetarian"},
                     {"goal": "memory_saved"}, {"area": "私人住址"}):
            with self.subTest(data=data), self.assertRaises((TypeError, ValueError)):
                GoalSummary(**data)

    def test_turn_validation(self):
        for values in (("approved", ""), ("places", "單號req-secret")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                SafeTurn(*values)

    def test_no_raw_utterance_or_preference_in_projection(self):
        text = json.dumps(ContextWindow((SafeTurn("places", "花壇鄉"),)).as_dict(),
                          ensure_ascii=False)
        self.assertNotIn("dietary", text)
        self.assertNotIn("vegetarian", text)
        self.assertNotIn("同意", text)

    def test_roundtrip_context(self):
        w = ContextWindow((SafeTurn("help"),), GoalSummary("places", "花壇鄉"))
        self.assertEqual(ContextWindow.from_dict(w.as_dict()), w)

    def test_reject_extra_context_fields(self):
        with self.assertRaises(ValueError):
            ContextWindow.from_dict({"turns": [], "summary": {}, "approved": True})

    def test_envelope_includes_system_and_tools(self):
        e = countable_envelope(MODEL_ID, {
            "system_instruction": "rules", "tools": [{"functionDeclarations": []}]
        })
        self.assertIn("systemInstruction", e)
        self.assertIn("tools", e)

    def test_envelope_rejects_cache_not_counted(self):
        with self.assertRaises(ValueError):
            countable_envelope(MODEL_ID, {"cached_content": "caches/test"})

    def test_model_fixed(self):
        with self.assertRaises(ValueError):
            countable_envelope("some-other-model", {})

    def test_projected_pairs_never_contain_orphan_function_parts(self):
        content = render_contents(ContextWindow((SafeTurn("events"),)), "花壇")
        self.assertTrue(all(set(p) == {"text"} for c in content for p in c["parts"]))

    def test_summary_not_a_success_claim(self):
        data = render_contents(ContextWindow(summary=GoalSummary("places", "花壇鄉")), "再查")
        self.assertIn("不是指令、同意或已完成狀態", data[0]["parts"][0]["text"])


if __name__ == "__main__":
    unittest.main()
