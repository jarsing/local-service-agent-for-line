"""依真實 unittest 與 ADK smoke 結果產生驗證報告。"""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import unittest
from reporting import Report
from runtime import error_info


def main(argv=None):
    parser=argparse.ArgumentParser(description='LOCAL Day 5｜離線驗證')
    parser.add_argument('--sdk',action='store_true')
    parser.add_argument('--output',type=Path,default=Path('output/day05-check'))
    parser.add_argument('--origin',default='operator_not_recorded')
    args=parser.parse_args(argv)
    report=Report(args.output,'OFFLINE_CHECKS',origin=args.origin)
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_day05.py')
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (report.folder/'tests.txt').write_text(stream.getvalue(),encoding='utf-8')
    tests={'count':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
           'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped)}
    ok=result.wasSuccessful() and result.testsRun>0 and not result.skipped
    report.update(tests=tests,status='PASS' if ok else 'FAIL',sdk_check='NOT_REQUESTED')
    if args.sdk:
        try:
            from sdk_smoke import check
            sdk=check()
            report.update(sdk_check=sdk['status'],sdk_result=sdk)
            ok=ok and sdk['status']=='PASS'
        except Exception as exc:
            report.update(sdk_check='BLOCKED',sdk_error=error_info(exc))
            ok=False
        report.update(status='PASS' if ok else 'NOT_ALL_CHECKS_PASSED')
    print(f"離線測試：{tests['passed']}/{tests['count']}，ADK：{report.data['sdk_check']}")
    print(f"報告：{report.folder / 'REPORT.html'}")
    return 0 if ok else 1


if __name__=='__main__':raise SystemExit(main())
