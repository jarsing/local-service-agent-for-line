"""標準函式庫即可執行的真正 SQLite 故障實驗；每輪另存，不冒充 Gemini。"""
from __future__ import annotations
import argparse
from pathlib import Path
import sqlite3
from evidence import create_run, execution_info, no_network, sources, write_json, sha256
from scenarios import SCENARIOS, prepare_case
from proof import check_case
from records import sqlite_rows
from reporting import build_report


def snapshot(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    src = sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()


def execute_case(name: str, output: Path) -> dict:
    case = prepare_case(name, output)
    steps = []
    snapshot(case.db_path, output/'step-00.sqlite3')
    while case.controller.next_tool:
        phase = case.controller.phase
        result = case.controller.execute(case.controller.next_tool, case.actor, case.args)
        steps.append({'phase': phase, 'result': result, 'rows_after': len(sqlite_rows(case.db_path))})
        snapshot(case.db_path, output/f'step-{len(steps):02d}.sqlite3')
    case.trace.save(output/'events.jsonl')
    proof = check_case(case, [s['result'] for s in steps])
    return {'name': name, 'send_args': case.args.tool_args(), 'confirmation': case.confirmation,
            'confirmation_source': 'test_harness_explicit_approval', 'steps': steps, 'proof': proof,
            'final_rows': sqlite_rows(case.db_path), 'database': str(output.name)+'/handoff.sqlite3',
            'files': {p.name: sha256(p) for p in sorted(output.iterdir()) if p.is_file()}}


def main() -> int:
    parser = argparse.ArgumentParser(description='Day 10 核心示範：模擬傳輸、真實 SQLite')
    parser.add_argument('--out', type=Path, default=Path(__file__).parent/'output')
    parser.add_argument('--origin', choices=['reader_local','author_local','assistant_check'], default='reader_local')
    parser.add_argument('--case', choices=['all', *SCENARIOS], default='all')
    args = parser.parse_args()
    output = create_run(args.out, 'core')
    before = sources()
    report = {'mode': 'OFFLINE_CORE', 'execution': execution_info(args.origin),
              'source_files': before, 'cases': [], 'success': False}
    try:
        with no_network():
            for name in SCENARIOS if args.case == 'all' else [args.case]:
                report['cases'].append(execute_case(name, output/name))
        report['success'] = before == sources()
    except Exception as exc:
        report['error'] = {'type': type(exc).__name__}
    report['source_unchanged'] = before == sources()
    write_json(output/'report.json', report)
    build_report(report, output/'REPORT.html')
    print('核心結果：', report['success'], '報告：', output/'REPORT.html')
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
