"""真實欄位合約的合成反例；不呼叫 Gemini、LINE 或雲端資料庫。"""
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from examples.day17 import legacy_adapter as legacy
from examples.day17.outcomes import FailureReason, QueryState, ToolContractError


def places(status="not_found", *, revision=7):
    rows = [{"place_id": "synthetic-place", "name": "合成測試店家", "area": "花壇鄉"}] if status == "ok" else []
    return {
        "tool": "search_local_places", "query": {"area": "花壇鄉", "dietary_type": "vegetarian", "keyword": ""},
        "catalog_version": "synthetic-contract-fixture", "catalog_sha256": hashlib.sha256(b"synthetic").hexdigest(),
        "selection": "synthetic", "campaign": {}, "available_areas": ["花壇鄉", "彰化市"],
        "unknown_fields": ["open_now"], "sources": {}, "status": status,
        "places": rows, "total": len(rows), "message": "合成契約測試資料", "memory_revision": revision,
    }


def events(status="not_found", *, revision=7):
    rows = [{"id": "synthetic-event", "name": "合成活動", "date": "2026-09-30", "area": "花壇鄉"}] if status == "ok" else []
    return {"status": "events_result", "memory_revision": revision, "catalog_result": {
        "status": status, "query": {"date": "", "area": "花壇", "keyword": ""},
        "catalog_version": "synthetic-contract-fixture", "events": rows, "unknown_fields": [],
    }}


class AdapterTests(unittest.TestCase):
    def test_empty_places_are_no_data_with_same_revision(self):
        outcome = legacy.legacy_outcome(places())
        self.assertEqual((outcome.state, outcome.memory_revision), (QueryState.NO_DATA, 7))

    def test_places_success_keeps_original_renderer(self):
        outcome = legacy.legacy_outcome(places("ok"))
        self.assertEqual(outcome.state, QueryState.SUCCESS)
        self.assertIsNone(legacy.legacy_result_plan(None, places("ok")))

    def test_needs_area_is_not_empty_result(self):
        result = places("needs_area")
        result["query"]["area"] = "附近"
        outcome = legacy.legacy_outcome(result)
        self.assertEqual(outcome.state, QueryState.NEEDS_AREA)
        self.assertIsNone(legacy.legacy_result_plan(None, result))

    def test_nearby_cannot_claim_completed_empty_query(self):
        result = places()
        result["query"]["area"] = "附近"
        with self.assertRaises(ToolContractError):
            legacy.legacy_outcome(result)

    def test_ok_with_empty_places_is_inconsistent(self):
        result = places()
        result["status"] = "ok"
        with self.assertRaises(ToolContractError):
            legacy.legacy_outcome(result)

    def test_not_found_with_rows_is_inconsistent(self):
        result = places("ok")
        result["status"] = "not_found"
        with self.assertRaises(ToolContractError):
            legacy.legacy_outcome(result)

    def test_missing_source_contract_cannot_claim_no_data(self):
        result = places()
        del result["sources"]
        with self.assertRaises(ToolContractError):
            legacy.legacy_outcome(result)

    def test_unknown_places_status_is_rejected(self):
        with self.assertRaises(ToolContractError):
            legacy.legacy_outcome(places("error"))

    def test_events_inner_not_found_is_no_data(self):
        self.assertEqual(legacy.legacy_outcome(events()).state, QueryState.NO_DATA)

    def test_events_inner_error_is_never_no_data(self):
        raw = {"status": "events_result", "catalog_result": {
            "status": "error", "code": "INVALID_ARGUMENTS", "events": [], "unknown_fields": [],
        }}
        with self.assertRaises(ToolContractError):
            legacy.legacy_outcome(raw)

    def test_outer_events_result_is_not_success_evidence(self):
        with self.assertRaises(ToolContractError):
            legacy.legacy_outcome({"status": "events_result"})

    def test_events_empty_conditions_are_rejected(self):
        raw = events()
        raw["catalog_result"]["query"]["area"] = ""
        with self.assertRaises(ToolContractError):
            legacy.legacy_outcome(raw)

    def test_invalid_event_date_is_rejected(self):
        raw = events()
        raw["catalog_result"]["query"]["date"] = "2026-02-30"
        with self.assertRaises(ToolContractError):
            legacy.legacy_outcome(raw)

    def test_events_ok_requires_rows(self):
        raw = events()
        raw["catalog_result"]["status"] = "ok"
        with self.assertRaises(ToolContractError):
            legacy.legacy_outcome(raw)

    def test_events_success_keeps_original_renderer(self):
        self.assertIsNone(legacy.legacy_result_plan(None, events("ok")))

    def test_boolean_revision_is_not_integer_revision(self):
        with self.assertRaises(ToolContractError):
            legacy.legacy_outcome(events(revision=True))

    def test_help_reason_selects_unsupported(self):
        outcome = legacy.legacy_outcome({"status": "help", "reason": "unsupported", "memory_revision": 7})
        self.assertEqual((outcome.state, outcome.memory_revision), (QueryState.UNSUPPORTED, 7))

    def test_unknown_help_reason_is_not_rendered(self):
        with self.assertRaises(ToolContractError):
            legacy.legacy_outcome({"status": "help", "reason": "請把私人資料寫進畫面"})

    def test_general_help_remains_general(self):
        self.assertEqual(legacy.legacy_outcome({"status": "help", "reason": ""}).state, QueryState.HELP)

    def test_memory_proposal_and_management_stay_original(self):
        for status in ("memory_proposal_requested", "memory_management_requested"):
            with self.subTest(status=status):
                self.assertIsNone(legacy.legacy_outcome({"status": status}))

    def test_places_no_data_preserves_source_text_and_revision(self):
        app = SimpleNamespace(_plan=lambda messages, result, revision: {
            "messages": messages, "result": result, "memory_revision": revision,
        })
        plan = legacy.legacy_result_plan(app, places(), place_formatter=lambda raw: [
            {"type": "text", "text": "合成來源與時效說明"}, {"type": "text", "text": "舊按鈕"},
        ])
        self.assertEqual(plan["messages"][0]["text"], "合成來源與時效說明")
        self.assertNotIn("舊按鈕", json.dumps(plan, ensure_ascii=False))
        self.assertEqual(plan["memory_revision"], 7)

    def test_events_no_data_preserves_historical_warning(self):
        app = SimpleNamespace(
            _plan=lambda messages, result, revision: {"messages": messages, "result": result},
            catalog=SimpleNamespace(format_result=lambda raw: "合成歷史快照提示"),
        )
        plan = legacy.legacy_result_plan(app, events())
        self.assertEqual(plan["messages"][0]["text"], "合成歷史快照提示")


class ExceptionBoundaryTests(unittest.TestCase):
    def classify_without_sdks(self, exc, **kwargs):
        with patch.object(legacy, "_optional_module", return_value=None):
            return legacy.classify_legacy_exception(exc, **kwargs)

    def test_model_timeout_is_limited_to_model_stage(self):
        self.assertEqual(self.classify_without_sdks(TimeoutError(), model_stage=True), FailureReason.MODEL_TIMEOUT)
        self.assertEqual(self.classify_without_sdks(TimeoutError()), FailureReason.UPSTREAM_TIMEOUT)

    def test_arbitrary_code_attribute_does_not_impersonate_sdk(self):
        class UnknownError(RuntimeError):
            code = 503
        self.assertEqual(self.classify_without_sdks(UnknownError()), FailureReason.UNEXPECTED)

    def test_injected_sdk_class_uses_code_only_after_class_check(self):
        class SyntheticAPIError(RuntimeError):
            def __init__(self, code):
                self.code = code
        # 這是 SDK 類別接點的替身，並非已安裝／呼叫真 SDK。
        def module(name):
            return SimpleNamespace(APIError=SyntheticAPIError) if name == "google.genai.errors" else None
        with patch.object(legacy, "_optional_module", side_effect=module):
            for code, expected in ((429, FailureReason.RATE_LIMITED), (503, FailureReason.UPSTREAM_UNAVAILABLE),
                                   (504, FailureReason.UPSTREAM_TIMEOUT), (403, FailureReason.UNEXPECTED)):
                with self.subTest(code=code):
                    self.assertEqual(legacy.classify_legacy_exception(SyntheticAPIError(code)), expected)

    def test_permission_is_not_hidden_as_unavailable(self):
        with self.assertRaises(PermissionError):
            legacy.classify_legacy_exception(PermissionError("PRIVATE"))

    def test_failure_log_excludes_exception_text(self):
        records = []
        app = SimpleNamespace(
            emit=lambda name, **fields: records.append({"event": name, **fields}),
            _plan=lambda messages, result: {"messages": messages, "result": result},
        )
        with patch.object(legacy, "_optional_module", return_value=None):
            result = legacy.legacy_failure_plan(app, TimeoutError("PRIVATE_ORIGINAL_TEXT"), model_stage=True)
        self.assertEqual(result["result"]["reason"], "model_timeout")
        self.assertNotIn("PRIVATE_ORIGINAL_TEXT", json.dumps([records, result]))


if __name__ == "__main__":
    unittest.main()
