"""執行四題、兩組的比較；每題建立新的 Session，保留所有結果。"""
from __future__ import annotations
import argparse
import asyncio
import logging
from pathlib import Path
from catalog import load_cases
from reporting import Report, read_key
from runtime import DEFAULT_MODEL, run_turn, error_info


def get_parser():
    parser = argparse.ArgumentParser(description="LOCAL Day 5｜有工具／無工具比較")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path, default=Path("output/day05"))
    parser.add_argument("--origin", default="operator_not_recorded")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--case", choices=[x["id"] for x in load_cases()])
    parser.add_argument("--condition", choices=("both","with_tool","without_tool"),default="both")
    return parser


async def compare(args, report, key):
    cases = [c for c in load_cases() if args.case is None or c["id"] == args.case]
    for index, case in enumerate(cases):
        # 交錯兩組順序，減少全部先跑某組造成的時間偏差；每題仍只有一次樣本。
        order = (False, True) if index % 2 == 0 else (True, False)
        for with_tool in order:
            condition = "with_tool" if with_tool else "without_tool"
            if args.condition != "both" and args.condition != condition:
                continue
            turn = await run_turn(case, with_tool=with_tool, key=key, model=args.model,
                record=lambda kind, **fields: report(kind, case_id=case["id"], condition=condition, **fields))
            report.add_turn(turn)
            print(f'{case["id"]} / {condition}: {turn["status"]}')
            if turn["status"] == "ERROR":
                report.update(status="PARTIAL", stopped_at=case["id"], error=turn["error"])
                return 2
    complete = all(t["status"] == "RECORDED" for t in report.data["turns"])
    report.update(status="RECORDED" if complete else "NEEDS_REVIEW",
                  compared_questions=len(cases),
                  model_calls=sum(t["model_calls"] for t in report.data["turns"]),
                  tool_calls=sum(t["tool_calls"] for t in report.data["turns"]))
    return 0 if complete else 1


def main(argv=None):
    parser = get_parser()
    args = parser.parse_args(argv)
    if not args.live:
        parser.error("真實呼叫請在核准後加 --live；離線檢查使用 verify.py。")
    report = Report(args.output, "LIVE_COMPARISON", origin=args.origin)
    try:
        key = read_key(args.env_file)
        report.secrets = (key,)
        logging.getLogger("google").setLevel(logging.CRITICAL)
        print(f"本次報告：{report.folder / 'REPORT.html'}")
        return asyncio.run(compare(args, report, key))
    except Exception as exc:
        report.update(status="ERROR", error=error_info(exc))
        print(f"請查看報告中的錯誤類型：{type(exc).__name__}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
