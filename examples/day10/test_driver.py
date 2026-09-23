"""每一組獨立 Python 行程執行，避免不同日次 demo/runtime 模組撞名。"""
from __future__ import annotations
import argparse
import importlib
import io
import json
from pathlib import Path
import sys
import unittest
from evidence import no_network, write_json


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--day',choices=['day02','day08','day09','day10'],required=True)
    p.add_argument('--modules',nargs='+',required=True)
    p.add_argument('--json',type=Path,required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    allowed={'day02':{'test_demo'},'day08':{'test_confirmation'},
             'day09':{'test_handoff','test_reporting','test_adk_offline'},
             'day10':{'test_recovery','test_packaging','test_adk_offline'}}
    if not set(args.modules)<=allowed[args.day]: p.error('測試模組不在固定清單內。')
    sys.path.insert(0,str(root/args.day))
    # 每個 child 只有這些固定模組；不靠檔名猜數量。
    data={'day':args.day,'modules':args.modules,'success':False,'run':0,'passed':0,
          'failures':0,'errors':0,'skipped':0,'network':'Python socket/DNS blocked'}
    stream=io.StringIO()
    try:
        with no_network():
            suite=unittest.TestSuite()
            for name in args.modules:
                module=importlib.import_module(name)
                suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        data.update(run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
            skipped=len(result.skipped),passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
            success=result.wasSuccessful() and result.testsRun>0 and not result.skipped)
    except Exception as exc:
        data['errors']=1
        data['import_error_type']=type(exc).__name__
        if isinstance(exc,(ImportError,ModuleNotFoundError)):
            data['status']='dependency_unavailable'
        stream.write('測試未完整執行：'+type(exc).__name__+'\n')
    write_json(args.json,data)
    print(stream.getvalue(),end='')
    print(json.dumps(data,ensure_ascii=False))
    return 0 if data['success'] else 1


if __name__=='__main__':
    raise SystemExit(main())
