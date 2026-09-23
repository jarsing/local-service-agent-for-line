"""報告是實際結果的視圖；失敗、跳脫字元與模式都要如實顯示。"""
from pathlib import Path
import json
import tempfile
import unittest
from reporting import build_report
from provenance import create_run, write_json, source_snapshot

class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_failed_run_is_not_presented_as_created(self):
        p = self.root / "failure.html"
        build_report({"mode": "OFFLINE_ADK", "origin": "assistant_check", "success": False,
                      "error": {"type": "ModuleNotFoundError"}}, p)
        text = p.read_text("utf-8")
        self.assertIn("未通過／未完整執行", text)
        self.assertIn("尚無可核對的已建立資料", text)
        self.assertNotIn("已建立資料的狀態為", text)

    def test_model_text_is_escaped_not_executed(self):
        p = self.root / "escaped.html"
        build_report({"success": True, "mode": "OFFLINE_ADK", "final_count": 0,
                      "model_turns": [{"label": "回覆", "final_text": "<script>alert(1)</script>"}]}, p)
        text = p.read_text("utf-8")
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)

    def test_report_is_static_and_identifies_execution_origin(self):
        p = self.root / "report.html"
        build_report({"mode": "OFFLINE_CORE", "origin": "assistant_check", "success": True,
                      "final_count": 1, "results": []}, p)
        text = p.read_text("utf-8")
        self.assertNotIn("<button", text)
        self.assertIn("assistant_check", text)
        self.assertIn("靜態結果報告", text)

    def test_existing_report_is_not_overwritten(self):
        p = self.root / "report.html"
        p.write_text("原始紀錄", "utf-8")
        with self.assertRaises(FileExistsError):
            build_report({"success": False}, p)
        self.assertEqual(p.read_text("utf-8"), "原始紀錄")

    def test_run_paths_are_unique_and_json_is_append_only(self):
        a, b = create_run(self.root, "demo"), create_run(self.root, "demo")
        self.assertNotEqual(a, b)
        p = a / "report.json"
        write_json(p, {"success": True, "thoughts": None})
        with self.assertRaises(FileExistsError):
            write_json(p, {"success": False})
        self.assertEqual(json.loads(p.read_text("utf-8")), {"success": True, "thoughts": None})

    def test_source_manifest_includes_original_day08_and_no_output(self):
        source = source_snapshot()
        self.assertIn("../day08/confirmation.py", source)
        self.assertIn("handoff.py", source)
        self.assertNotIn("output", str(list(source)))

if __name__ == "__main__":
    unittest.main(verbosity=2)
