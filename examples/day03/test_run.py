"""離線邏輯測試；全部使用合成資料，不呼叫 Google，也不代表 SDK 整合已通過。"""
from __future__ import annotations
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run


def fixture(text="測試用文字，不是真實 Gemini 輸出。", finish="STOP", thought=False):
    return {"candidates": [{"finish_reason": finish, "content": {"parts": [{"text": text, "thought": thought}]}}],
            "model_version": "offline-fixture", "usage_metadata": {"prompt_token_count": 12}}


class Day03Tests(unittest.TestCase):
    def test_case_is_explicitly_synthetic(self):
        self.assertEqual(run.load_case()["kind"], "synthetic_model_input")

    def test_prompt_contains_unknown_and_no_business_authority(self):
        prompt = run.build_prompt(run.load_case())
        self.assertIn('"stored_request": "unknown"', prompt)
        self.assertIn("不執行該動作", prompt)

    def test_prompt_does_not_depend_on_dict_order(self):
        self.assertEqual(run.build_prompt({"a": 1, "b": 2}), run.build_prompt({"b": 2, "a": 1}))

    def test_missing_key_rejected(self):
        with self.assertRaises(ValueError): run.load_key(None, {})

    def test_key_placeholder_rejected(self):
        with self.assertRaises(ValueError): run.load_key(None, {"GEMINI_API_KEY": "YOUR_API_KEY"})

    def test_private_env_file_read(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / ".env"
            f.write_text('# comment\nGEMINI_API_KEY="synthetic-key"\n', encoding="utf-8")
            self.assertEqual(run.load_key(f, {}), "synthetic-key")

    def test_environment_key_has_documented_priority(self):
        self.assertEqual(run.load_key(Path("not-existing"), {"GEMINI_API_KEY": "env-fixture"}), "env-fixture")

    def test_response_with_text_and_stop_is_not_semantic_pass(self):
        result = run.selected_response(fixture())
        self.assertEqual(run.response_status(result), "API_TEXT_RECEIVED")
        self.assertNotIn("semantic_pass", result)

    def test_empty_text_needs_review(self):
        self.assertEqual(run.response_status(run.selected_response(fixture(""))), "API_RESPONSE_NEEDS_REVIEW")

    def test_truncated_text_needs_review(self):
        self.assertEqual(run.response_status(run.selected_response(fixture(finish="MAX_TOKENS"))), "API_RESPONSE_NEEDS_REVIEW")

    def test_thought_text_is_not_presented_as_answer(self):
        self.assertEqual(run.selected_response(fixture("不可當成答案的思考", thought=True))["text"], "")

    def test_missing_usage_is_unknown_not_zero(self):
        self.assertIsNone(run.selected_response({})["usage"]["total_token_count"])

    def test_tool_part_is_not_executed_or_accepted(self):
        raw = fixture()
        raw["candidates"][0]["content"]["parts"].append({"function_call": {"name": "create_request"}})
        self.assertEqual(run.response_status(run.selected_response(raw)), "API_RESPONSE_NEEDS_REVIEW")

    def test_exact_secret_is_redacted(self):
        self.assertEqual(run.safe_text("key=test-secret", "test-secret"), "key=[REDACTED]")

    def test_api_key_pattern_is_redacted(self):
        self.assertEqual(run.safe_text("AIza" + "A" * 35), "[REDACTED]")

    def test_no_live_flag_does_not_read_key_or_call_sdk(self):
        with tempfile.TemporaryDirectory() as t:
            with patch.object(run, "load_key", side_effect=AssertionError("不應讀取")):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = run.main(["--output", t])
            record = json.loads(next(Path(t).glob("run-*/verification.json")).read_text())
            self.assertEqual(code, 2)
            self.assertEqual(record["status"], "BLOCKED_NO_LIVE_CONSENT")
            self.assertEqual(record["generation_invocations"], 0)

    def test_html_escapes_model_text(self):
        with tempfile.TemporaryDirectory() as t:
            with contextlib.redirect_stdout(io.StringIO()): run.main(["--output", t])
            folder = next(Path(t).glob("run-*"))
            record = json.loads((folder / "verification.json").read_text())
            record["response"] = run.selected_response(fixture("<script>alert(1)</script>"))
            record["origin"] = "OFFLINE_TEST_FIXTURE"
            run.write_report(record, folder)
            text = (folder / "REPORT.html").read_text()
            self.assertNotIn("<script>", text)
            self.assertIn("&lt;script&gt;", text)

    def test_source_hashes_have_real_digest(self):
        hashes = run.source_hashes()
        self.assertIn("run.py", hashes)
        self.assertTrue(all(len(v) == 64 for v in hashes.values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
