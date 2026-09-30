"""執行離線契約測試並保存實際計數；不呼叫模型或 LINE API。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
from pathlib import Path
import platform
import sys
import tempfile
import time
import unittest

from .demo import json_text, new_output_directory


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed_ids: list[str] = []
        self.passed_ids: list[str] = []

    def startTest(self, test):
        self.executed_ids.append(test.id())
        super().startTest(test)

    def addSuccess(self, test):
        self.passed_ids.append(test.id())
        super().addSuccess(test)


def main() -> int:
    parser = argparse.ArgumentParser(description="執行離線測試並產生可核對的 JSON 與文字紀錄。")
    parser.add_argument("--out", required=True, help="新建且保持空白的輸出資料夾。")
    args = parser.parse_args()
    try:
        out = new_output_directory(args.out)
    except ValueError as exc:
        parser.error(str(exc))
    test_dir = Path(__file__).resolve().parent / "tests"
    suite = unittest.defaultTestLoader.discover(
        str(test_dir), pattern="test_*.py", top_level_dir=str(test_dir.parents[2]),
    )
    stream = io.StringIO()
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    temporary_root = out / "temporary"
    temporary_root.mkdir()
    previous_tempdir = tempfile.tempdir
    try:
        # 所有 TemporaryDirectory 都留在此次 --out 指定的執行目錄。
        tempfile.tempdir = str(temporary_root)
        result = unittest.TextTestRunner(
            stream=stream, verbosity=2, resultclass=RecordingResult,
        ).run(suite)
    finally:
        tempfile.tempdir = previous_tempdir
    exit_code = 0 if result.wasSuccessful() and result.testsRun > 0 else 1
    report = {
        "mode": "offline_unittest", "started_at_utc": started_at,
        "python_version": platform.python_version(),
        "tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
        "passed": len(result.passed_ids),
        "successful": exit_code == 0, "exit_code": exit_code,
        "duration_seconds": round(time.monotonic() - started, 6),
        "test_ids": result.executed_ids,
        "counting_rule": "unittest test methods; subtests are not counted as extra tests",
        "model_api_calls": 0, "line_api_calls": 0,
        "scope": "query_contract_and_offline_sqlite_fixture",
        "temporary_files_within_output": True,
    }
    log = stream.getvalue()
    (out / "verification.json").write_text(json_text(report), encoding="utf-8")
    (out / "test.log").write_text(log, encoding="utf-8")
    sys.stdout.write(log)
    print(f"驗證紀錄：{out / 'verification.json'}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
