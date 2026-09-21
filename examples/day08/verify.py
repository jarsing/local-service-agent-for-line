"""Day 8 離線驗證入口（verify.py）。

執行 25 項核心單元測試、5 項 ADK 工具確認整合測試、
離線 demo 執行與 HTML 報表生成。
回報完整的離線測試結果與數量。
"""
from __future__ import annotations

import io
import os
import sys
import unittest

from demo import main as run_demo
from test_confirmation import ConfirmationTests
from test_adk_offline import AdkConfirmationTests
from ui import generate_demo_html


def run_all_tests() -> int:
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()

    suite.addTests(loader.loadTestsFromTestCase(ConfirmationTests))
    suite.addTests(loader.loadTestsFromTestCase(AdkConfirmationTests))

    print("==================================================")
    print("LOCAL Day 8｜離線核心與 ADK 工具確認驗證")
    print("==================================================")
    print(f"Python: {sys.version.split()[0]}")
    print(f"環境: 100% 離線執行（0 模型 API 呼叫，0 外部網路）\n")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n--- 離線 Demo 演練 ---")
    run_demo()

    print("\n--- 靜態介面生成 ---")
    html_path = generate_demo_html()
    print(f"已生成確認畫面：{html_path.name} (大小: {os.path.getsize(html_path)} bytes)")

    print("\n==================================================")
    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total - failures - errors

    print(f"總測試項目：{total}")
    print(f"通過項目：{passed}")
    print(f"失敗項目：{failures}")
    print(f"錯誤項目：{errors}")
    print("==================================================")

    if failures > 0 or errors > 0:
        print("❌ 驗證未全數通過！")
        return 1

    print("✅ 離線測試全數通過（PASS）！")
    return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
