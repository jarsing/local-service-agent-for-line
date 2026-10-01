"""Entry point: scorer self-tests or 20-case evaluation. No remote writes."""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time
import unittest

from .dataset import DEFAULT_DATASET, REPO, load_dataset
from .gate import RequestGate, RequestBudget
from .scoring import score_case


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+'\n', encoding='utf-8')


def file_hash(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(dataset: Path, args) -> dict:
    paths = sorted((REPO / 'examples/day18').glob('*.py')) + [dataset]
    originals = ['examples/day14/main.py','examples/day14/model_contract.py','examples/day15/policy.py',
                 'examples/day15/adk_budget_router.py','examples/day16/main.py',
                 'examples/day17/legacy_adapter.py','examples/day17/messages.py']
    paths += [REPO / p for p in originals if (REPO / p).is_file()]
    packages = {}
    for name in ('google-adk','google-genai','fastapi','httpx'):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    def git(*flags):
        try:
            process = subprocess.run(['git','-C',str(REPO),*flags], text=True, capture_output=True, check=True, timeout=5)
            return process.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    status = git('status','--porcelain')
    return {'created_at':datetime.now(timezone.utc).isoformat(), 'python':platform.python_version(),
            'mode':args.mode, 'packages':packages, 'source_commit':git('rev-parse','HEAD'),
            'working_tree_dirty':bool(status) if status is not None else None,
            'files':{str(p.relative_to(REPO)) if p.is_relative_to(REPO) else p.name:file_hash(p) for p in paths},
            'missing_baseline_files':[p for p in originals if not (REPO / p).is_file()],
            'selected_ids':args.case, 'concurrency':args.concurrency, 'request_interval_seconds':args.interval,
            'sdk_attempts':1, 'injected_timeout_seconds':args.injection_seconds,
            'measurement_scope':'local_application_route_and_SQLite_not_deployment_or_LINE_delivery'}


def self_test(out: Path | None) -> int:
    parent = out or REPO / 'out/day18'
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='scorer-selftest-', dir=parent) as temp:
        previous = os.environ.get('LOCAL_DAY18_TEST_TMP')
        os.environ['LOCAL_DAY18_TEST_TMP'] = temp
        try:
            from . import test_eval
            suite = unittest.defaultTestLoader.loadTestsFromModule(test_eval)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
        finally:
            if previous is None:
                os.environ.pop('LOCAL_DAY18_TEST_TMP',None)
            else:
                os.environ['LOCAL_DAY18_TEST_TMP'] = previous
    return 0 if result.testsRun and result.wasSuccessful() else 1


def summarize(rows: list[dict], elapsed: float, mode: str) -> dict:
    counts = Counter(r['grade']['status'] for r in rows)
    completed = counts['PASS'] + counts['FAIL']
    live = [r for r in rows if r['observation'].get('mode') == 'live' and
            r['observation'].get('execution') == 'completed' and
            r['grade'].get('layers',{}).get('intent',{}).get('status') in ('PASS','FAIL')]
    return {'total_cases':20,'completed_cases':completed,
            'counts':{name:counts[name] for name in ('PASS','FAIL','BLOCKED','NOT_RUN')},
            'full_suite_pass_rate':counts['PASS']/20,
            'executed_pass_rate':counts['PASS']/completed if completed else None,
            'live_intent_applicable_executed':len(live),
            'live_intent_passed':sum(r['grade']['layers']['intent']['status']=='PASS' for r in live),
            'model_accuracy':None if mode=='offline' else 'see_live_intent_denominator',
            'elapsed_seconds_including_queue':round(elapsed,6),
            'all_twenty_passed':counts['PASS']==20}


async def evaluate(data: dict, args, out: Path) -> int:
    from .local_adapter import run_case
    selected = set(args.case or [c['id'] for c in data['cases']])
    gate = RequestGate(args.concurrency, args.interval)
    slots = asyncio.Semaphore(args.concurrency)
    budget = None
    create_live = None
    live_setup_error = None
    if args.mode == 'live':
        budget = RequestBudget(args.max_model_calls,args.max_count_calls)
        try:
            from .live_adapter import factory
            create_live = factory(gate,budget)
        except Exception as exc:
            live_setup_error = type(exc).__name__
    started = time.perf_counter()
    async def run(case):
        queued = time.perf_counter()
        folder = out / 'cases' / case['id']
        folder.mkdir(parents=True)
        if case['id'] not in selected or (args.mode=='live' and case['id'] not in data['live_eligible_ids']):
            observed = {'execution':'not_run','mode':args.mode,'reason':'NOT_SELECTED_OR_NOT_LIVE_APPLICABLE'}
        elif live_setup_error:
            observed = {'execution':'blocked','mode':'live','reason':'LIVE_SETUP_'+live_setup_error}
        else:
            async with slots:
                try:
                    observed = await run_case(case,folder,mode=args.mode,live_factory=create_live,
                                              live_budget=budget,injection_seconds=args.injection_seconds)
                except Exception as exc:
                    # No exception body: it may contain credentials or private request text.
                    observed = {'execution':'blocked','mode':args.mode,'reason':'ADAPTER_'+type(exc).__name__}
                    if isinstance(exc, ModuleNotFoundError):
                        observed['missing_module'] = exc.name
        observed['wall_with_queue_seconds'] = round(time.perf_counter()-queued,6)
        grade = score_case(case,observed)
        dump(folder / 'observation.json',observed)
        dump(folder / 'grade.json',grade)
        return {'id':case['id'],'input':case['input'],'group':case['group'],
                'grade':grade,'observation':observed}
    rows = await asyncio.gather(*(run(case) for case in data['cases']))
    summary = summarize(rows,time.perf_counter()-started,args.mode)
    result = {'summary':summary, 'rows':rows, 'external_attempts':budget.attempted if budget else {'generation':0,'count_tokens':0}}
    dump(out / 'results.json', result)
    report = ['# LOCAL Day 18 評測報告','',f'模式：`{args.mode}`。完整題集分母固定為 20。',
              '離線不是 Gemini 成績；Live 不是雲端部署或 LINE 送達驗證。','',
              '| 題號 | 結果 | 工具／意圖 | 後端 | 訊息計畫 | 需求完整度 |',
              '|---|---|---|---|---|---|']
    for row in rows:
        g=row['grade']; layers=g.get('layers',{})
        report.append('| '+ ' | '.join([row['id'],g['status'],
            *(layers.get(k,{}).get('status','—') for k in ('intent','backend','ui')),
            g.get('coverage',{}).get('status','—')])+' |')
    report += ['', '## 同次結果', '', '```json',json.dumps(summary,ensure_ascii=False,indent=2),'```',
               '', '## 逐題問題', '']
    for row in rows:
        g=row['grade']
        if g['status']!='PASS' or g.get('coverage',{}).get('status')=='NEEDS_REVIEW':
            report += [f"### {row['id']}", '```json', json.dumps(g,ensure_ascii=False,indent=2),'```','']
    (out / 'REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print('本次報告：',out / 'REPORT.md')
    return 1 if summary['counts']['FAIL'] else 2 if summary['counts']['BLOCKED'] else 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=DEFAULT_DATASET)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--validate-only',action='store_true')
    parser.add_argument('--mode',choices=('offline','live'),default='offline')
    parser.add_argument('--case',action='append',help='Repeat for each explicitly selected case ID.')
    parser.add_argument('--approve-external',action='store_true')
    parser.add_argument('--max-model-calls',type=int)
    parser.add_argument('--max-count-calls',type=int)
    parser.add_argument('--concurrency',type=int,default=1)
    parser.add_argument('--interval',type=float,default=1.0)
    parser.add_argument('--injection-seconds',type=float,default=0.01)
    args=parser.parse_args(argv)
    if args.self_test:
        return self_test(args.out)
    data=load_dataset(args.dataset)
    if args.validate_only:
        print('題集結構有效：20 題；這不是情境測試或模型通過成績。')
        return 0
    if args.out is None:
        parser.error('--out is required and must be a new directory')
    if args.case and (len(args.case)!=len(set(args.case)) or set(args.case)-{c['id'] for c in data['cases']}):
        parser.error('case IDs must be unique IDs in the benchmark')
    RequestGate(args.concurrency,args.interval)  # Validate before filesystem/API work.
    if not 0 < args.injection_seconds <= 18:
        parser.error('injection seconds must be in (0, 18]')
    if args.mode=='live':
        if not args.approve_external or not args.case or not args.max_model_calls or not args.max_count_calls:
            parser.error('live requires explicit approval, case IDs and both request limits')
        if set(args.case)-set(data['live_eligible_ids']):
            parser.error('selected live cases must be naturally routed, non-injection cases')
        RequestBudget(args.max_model_calls,args.max_count_calls)
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    dump(out/'run_manifest.json',manifest(args.dataset,args))
    return asyncio.run(evaluate(data,args,out))


if __name__=='__main__':
    raise SystemExit(main())
