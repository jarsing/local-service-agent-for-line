"""Validate a candidate fixture and grade separately collected JSON observations.

This program does not run LOCAL, any model, LINE, Firestore, or a container.
A valid 100-case fixture is not 100 passed service executions. Hashes check
integrity and version binding; they do not authenticate the collector's claims.
Python 3.10+, standard library only.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys
from typing import Any

FAMILIES = ('events_access', 'places', 'memory', 'requests', 'untrusted')
OPS = {'eq', 'ne', 'contains', 'not_contains', 'one_of'}
MODES = {'offline_contract', 'live_model'}
SHA256 = re.compile(r'[a-f0-9]{64}\Z')
COMMIT = re.compile(r'[a-f0-9]{40}\Z')

class EvidenceError(ValueError):
    pass

def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError('DUPLICATE_JSON_KEY:' + key)
        result[key] = value
    return result

def reject_constant(value):
    raise EvidenceError('NONFINITE_JSON:' + value)

def finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise EvidenceError('NONFINITE_JSON_NUMBER')
    return value

def bounded_int(text: str) -> int:
    try:
        return int(text)
    except ValueError as exc:
        raise EvidenceError('JSON_INTEGER_LIMIT') from exc

def decode(text: str) -> Any:
    return json.loads(text, object_pairs_hook=no_duplicates,
                      parse_constant=reject_constant,
                      parse_float=finite_float,
                      parse_int=bounded_int)

def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')

def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()

def stimulus_for(case: dict) -> dict:
    """Only these inputs belong in a collector. Expected answers stay in grading."""
    return {key: case[key] for key in ('id', 'input', 'setup', 'steps')}

def exact_equal(actual: Any, expected: Any) -> bool:
    """JSON type-aware comparison: True != 1, False != 0, 1 != 1.0."""
    return canonical(actual) == canonical(expected)

def pointer(data: Any, path: str) -> Any:
    if not isinstance(path, str) or not path.startswith('/'):
        raise EvidenceError('INVALID_POINTER')
    current = data
    for token in path[1:].split('/'):
        if re.search(r'~(?![01])', token):
            raise EvidenceError('INVALID_POINTER_ESCAPE')
        token = token.replace('~1', '/').replace('~0', '~')
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and re.fullmatch(r'0|[1-9][0-9]*', token):
            index = int(token)
            if index >= len(current):
                raise EvidenceError('MISSING_OBSERVATION:' + path)
            current = current[index]
        else:
            raise EvidenceError('MISSING_OBSERVATION:' + path)
    return current

def check(actual: Any, rule: dict) -> bool:
    op, expected = rule['op'], rule['value']
    if op == 'eq':
        return exact_equal(actual, expected)
    if op == 'ne':
        return not exact_equal(actual, expected)
    if op == 'one_of':
        return any(exact_equal(actual, value) for value in expected)
    if not isinstance(actual, str) or not isinstance(expected, str):
        raise EvidenceError('TEXT_ASSERTION_TYPE')
    return (expected in actual) if op == 'contains' else (expected not in actual)

def validate_fixture(fixture: dict) -> dict:
    if not isinstance(fixture, dict) or type(fixture.get('schema_version')) is not int or fixture['schema_version'] != 1:
        raise EvidenceError('FIXTURE_SCHEMA')
    cases = fixture.get('cases')
    if not isinstance(cases, list) or len(cases) != 100:
        raise EvidenceError('EXACTLY_100_SPECS_REQUIRED')
    ids, behaviors, purposes = set(), set(), set()
    for case in cases:
        if not isinstance(case, dict):
            raise EvidenceError('CASE_SCHEMA')
        cid = case.get('id')
        if not isinstance(cid, str) or not re.fullmatch('L29-[0-9]{3}', cid):
            raise EvidenceError('CASE_ID')
        if cid in ids:
            raise EvidenceError('DUPLICATE_CASE_ID')
        ids.add(cid)
        if case.get('family') not in FAMILIES:
            raise EvidenceError('CASE_FAMILY')
        if not isinstance(case.get('purpose'), str) or not case['purpose'] or case['purpose'] in purposes:
            raise EvidenceError('PURPOSE_REQUIRED_OR_REPEATED')
        purposes.add(case['purpose'])
        if not isinstance(case.get('input'), str) or not case['input'].strip():
            raise EvidenceError('INPUT_REQUIRED')
        if case.get('origin') != 'synthetic_development_fixture':
            raise EvidenceError('FIXTURE_ORIGIN_REQUIRED')
        tags = case.get('tags')
        if (not isinstance(tags, list) or not tags
                or any(not isinstance(t, str) or not t.strip() for t in tags)
                or len(tags) != len(set(tags))):
            raise EvidenceError('CASE_TAGS_REQUIRED')
        source = case.get('source')
        if (not isinstance(source, dict) or not isinstance(source.get('legacy_case_ids'), list)
                or not source['legacy_case_ids']
                or any(not isinstance(cid, str) or not cid.strip() for cid in source['legacy_case_ids'])
                or not isinstance(source.get('reference_sha256'), str)
                or not SHA256.fullmatch(source['reference_sha256'])):
            raise EvidenceError('SOURCE_LINEAGE_REQUIRED')
        if not isinstance(case.get('setup'), dict) or not isinstance(case.get('steps'), list) or not case['steps']:
            raise EvidenceError('SETUP_AND_STEPS_REQUIRED')
        if any(not isinstance(s, dict) or not isinstance(s.get('op'), str) or not s['op'] for s in case['steps']):
            raise EvidenceError('STEP_OPERATION_REQUIRED')
        rules = case.get('assertions')
        if not isinstance(rules, list) or not rules:
            raise EvidenceError('ASSERTIONS_REQUIRED')
        for rule in rules:
            if not isinstance(rule, dict) or set(rule) != {'path','op','value'}:
                raise EvidenceError('ASSERTION_SCHEMA')
            if not isinstance(rule.get('path'), str) or not rule['path'].startswith('/'):
                raise EvidenceError('ASSERTION_OPERATOR_OR_POINTER')
            if not isinstance(rule.get('op'), str) or rule['op'] not in OPS:
                raise EvidenceError('ASSERTION_OPERATOR_OR_POINTER')
            for token in rule['path'][1:].split('/'):
                if re.search(r'~(?![01])', token):
                    raise EvidenceError('INVALID_POINTER_ESCAPE')
            if rule['op'] == 'one_of' and (not isinstance(rule['value'], list) or not rule['value']):
                raise EvidenceError('ONE_OF_VALUES_REQUIRED')
            if rule['op'] in ('contains','not_contains') and (not isinstance(rule['value'],str) or not rule['value']):
                raise EvidenceError('TEXT_EXPECTATION_REQUIRED')
        # Compare setup, steps and assertions, not top-level labels. Text inside
        # steps remains included; this catches exact duplicates, not paraphrases.
        fingerprint = digest({key: case[key] for key in ('setup','steps','assertions')})
        if fingerprint in behaviors:
            raise EvidenceError('DUPLICATE_BEHAVIOR')
        behaviors.add(fingerprint)
    if ids != {f'L29-{i:03d}' for i in range(1,101)}:
        raise EvidenceError('CASE_ID_COVERAGE')
    counts = Counter(c['family'] for c in cases)
    if counts != Counter({name:20 for name in FAMILIES}):
        raise EvidenceError('FIVE_FAMILIES_OF_20_REQUIRED')
    return {'fixture_status':'VALID','planned_cases':100,
            'family_counts':dict(counts), 'behavior_fingerprints':len(behaviors),
            'semantic_independence':'requires_human_review_not_proved_by_hash',
            'execution_status':'NOT_RUN'}

def read_raw(root: Path, record: dict) -> dict:
    ref = record.get('raw')
    if (not isinstance(ref, dict) or not isinstance(ref.get('path'), str)
            or not isinstance(ref.get('sha256'), str) or not SHA256.fullmatch(ref['sha256'])):
        raise EvidenceError('RAW_REFERENCE_REQUIRED')
    rel = Path(ref['path'])
    if rel.is_absolute() or '..' in rel.parts:
        raise EvidenceError('RAW_PATH_OUTSIDE_ROOT')
    target = (root / rel).resolve()
    if not target.is_relative_to(root.resolve()):
        raise EvidenceError('RAW_PATH_OUTSIDE_ROOT')
    if not target.is_file():
        raise EvidenceError('RAW_FILE_MISSING')
    content = target.read_bytes()
    if hashlib.sha256(content).hexdigest() != ref['sha256']:
        raise EvidenceError('RAW_HASH_MISMATCH')
    raw = decode(content.decode('utf-8'))
    if not isinstance(raw, dict):
        raise EvidenceError('RAW_SCHEMA')
    return raw

def grade_case(case: dict, record: dict | None, *, fixture_hash: str,
               source_commit: str, mode: str, evidence_root: Path) -> dict:
    result = {'id':case['id'], 'family':case['family'], 'tags':case['tags']}
    if record is None:
        return {**result,'status':'NOT_RUN','issues':['OBSERVATION_NOT_SUPPLIED']}
    try:
        if record.get('case_id') != case['id']:
            raise EvidenceError('CASE_BINDING_MISMATCH')
        raw = read_raw(evidence_root, record)
        expected = {'case_id':case['id'], 'case_sha256':digest(case),
                    'fixture_sha256':fixture_hash, 'source_commit':source_commit,
                    'mode':mode, 'input_sha256':digest(stimulus_for(case))}
        for key, value in expected.items():
            if raw.get(key) != value:
                raise EvidenceError('BINDING_MISMATCH:' + key)
        for key in ('collector_sha256','config_sha256'):
            if not isinstance(raw.get(key),str) or not SHA256.fullmatch(raw[key]):
                raise EvidenceError('PROVENANCE_REQUIRED:' + key)
        if raw.get('origin') != 'captured_execution':
            raise EvidenceError('CAPTURE_ORIGIN_REQUIRED')
        if raw.get('execution') in ('NOT_RUN','BLOCKED'):
            return {**result,'status':raw['execution'],
                    'issues':[raw.get('reason','COLLECTOR_DID_NOT_EXECUTE')]}
        if raw.get('execution') != 'COMPLETED' or not isinstance(raw.get('data'),dict):
            raise EvidenceError('COMPLETED_OBSERVATION_REQUIRED')
        errors = []
        for rule in case['assertions']:
            actual = pointer(raw['data'], rule['path'])
            if not check(actual, rule):
                errors.append({'path':rule['path'],'op':rule['op'],
                               'expected':rule['value'],'actual':actual})
        try:
            ms=raw.get('elapsed_ms')
            if ms is not None and (type(ms) not in (int,float) or not math.isfinite(ms) or ms<0):
                raise EvidenceError('INVALID_ELAPSED_MS')
        except OverflowError:
            raise EvidenceError('INVALID_ELAPSED_MS')
        return {**result,'status':'FAIL' if errors else 'PASS','issues':errors,
                'collector_sha256':raw['collector_sha256'],
                'config_sha256':raw['config_sha256'],'elapsed_ms':ms}
    except (EvidenceError,UnicodeError,json.JSONDecodeError,OverflowError,ValueError) as exc:
        return {**result,'status':'BLOCKED','issues':[str(exc)]}

def ratio(passed: int, tested: int) -> float | None:
    return passed / tested if tested else None

def aggregate(fixture: dict, results: list[dict], *, mode: str) -> dict:
    # A caller cannot turn a partial list into a smaller, easier denominator.
    known = {case['id']: case for case in fixture['cases']}
    by_id = {}
    for row in results:
        cid = row.get('id') if isinstance(row, dict) else None
        if cid not in known or cid in by_id:
            raise EvidenceError('RESULT_ID_COVERAGE_OR_DUPLICATE')
        if row.get('status') not in ('PASS', 'FAIL', 'BLOCKED', 'NOT_RUN'):
            raise EvidenceError('INVALID_RESULT_STATUS')
        case = known[cid]
        by_id[cid] = {**row, 'family': case['family'], 'tags': case['tags']}
    results = [by_id.get(case['id'], {
        'id': case['id'], 'family': case['family'], 'tags': case['tags'],
        'status': 'NOT_RUN', 'issues': ['RESULT_NOT_SUPPLIED']
    }) for case in fixture['cases']]
    counts = Counter(r['status'] for r in results)
    tested = counts['PASS']+counts['FAIL']
    batches={(r.get('collector_sha256'),r.get('config_sha256')) for r in results if r['status'] in ('PASS','FAIL')}
    same_configuration=len(batches)<=1
    status=('NOT_RUN' if counts['NOT_RUN']==len(results) else
            'PASS' if counts['PASS']==len(results) and same_configuration else
            'FAIL' if counts['FAIL'] else 'INCOMPLETE')
    if not same_configuration:
        status='BLOCKED_MIXED_CONFIGURATION'
    groups={}
    for name in FAMILIES:
        rows=[r for r in results if r['family']==name]
        passed=sum(r['status']=='PASS' for r in rows)
        done=sum(r['status'] in ('PASS','FAIL') for r in rows)
        groups[name]={'planned':len(rows),'tested':done,'passed':passed,
                      'pass_rate':ratio(passed,done) if same_configuration else None}
    replay=[r for r in results if {'idempotency','replay'} & set(r['tags'])]
    adverse=[r for r in results if 'adversarial' in r['tags']]
    def subset(rows):
        done=sum(r['status'] in ('PASS','FAIL') for r in rows)
        passed=sum(r['status']=='PASS' for r in rows)
        return {'planned':len(rows),'tested':done,'passed':passed,
                'pass_rate':ratio(passed,done) if same_configuration else None}
    timings=[r['elapsed_ms'] for r in results if r['status'] in ('PASS','FAIL') and r.get('elapsed_ms') is not None]
    timing_mean = None
    if timings and same_configuration:
        try:
            val = statistics.fmean(timings)
            if math.isfinite(val):
                timing_mean = val
        except (OverflowError, ValueError):
            timing_mean = None
    return {'schema_version':1,'scope':'EVIDENCE_GRADING_NOT_SERVICE_EXECUTION',
            'mode':mode,'status':status,'planned':len(results),'tested':tested,
            'counts':{k:counts[k] for k in ('PASS','FAIL','BLOCKED','NOT_RUN')},
            'pass_rate_observed':ratio(counts['PASS'],tested) if same_configuration else None,
            'coverage_rate':ratio(tested,len(results)),
            'configuration_comparable':same_configuration,
            'family_results':groups,'replay_subset':subset(replay),
            'adversarial_subset':subset(adverse),
            'metrics':{'model_accuracy':None,'model_latency_ms':None,'model_cost_usd':None,
                       'metric_reason':'This contract grader does not infer model metrics from backend results.',
                       'recorded_operation_elapsed_ms':{'n':len(timings),'mean':timing_mean}},
            'device_acceptance':'NOT_EVALUATED','grading_external_calls':0,
            'provenance_limit':'Integrity and version binding do not authenticate the source of an observation.',
            'results':results}

def load_records(path: Path | None, ids: set[str]) -> dict:
    if path is None:
        return {}
    payload=decode(path.read_text(encoding='utf-8'))
    if not isinstance(payload,dict) or set(payload)!={'records'} or not isinstance(payload['records'],list):
        raise EvidenceError('RECORD_LIST_SCHEMA')
    records={}
    for record in payload['records']:
        if not isinstance(record,dict) or record.get('case_id') not in ids:
            raise EvidenceError('UNEXPECTED_CASE_ID')
        if record['case_id'] in records:
            raise EvidenceError('DUPLICATE_OBSERVATION_ID')
        records[record['case_id']]=record
    return records

def write_new_json(path: Path, value: dict) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    with path.open('x', encoding='utf-8') as f:
        f.write(payload)

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,default=Path('eval/local100.json'))
    parser.add_argument('--records',type=Path)
    parser.add_argument('--evidence-root',type=Path)
    parser.add_argument('--source-commit')
    parser.add_argument('--mode',choices=sorted(MODES),default='offline_contract')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--plan',action='store_true',help='Validate specifications only; never marks service cases as PASS.')
    args=parser.parse_args()
    try:
        fixture_bytes=args.fixture.read_bytes()
        fixture=decode(fixture_bytes.decode('utf-8'))
        validation=validate_fixture(fixture)
        fixture_hash=hashlib.sha256(fixture_bytes).hexdigest()
        commit=args.source_commit or fixture['source_baseline_commit']
        if not isinstance(commit,str) or not COMMIT.fullmatch(commit):
            raise EvidenceError('FULL_SOURCE_COMMIT_REQUIRED')
        if args.plan and args.records:
            raise EvidenceError('PLAN_CANNOT_INGEST_OBSERVATIONS')
        records=load_records(args.records,{c['id'] for c in fixture['cases']})
        if records and not args.evidence_root:
            raise EvidenceError('EVIDENCE_ROOT_REQUIRED')
        root=args.evidence_root or Path('.')
        results=[grade_case(c,records.get(c['id']),fixture_hash=fixture_hash,
                   source_commit=commit,mode=args.mode,evidence_root=root) for c in fixture['cases']]
        report=aggregate(fixture,results,mode=args.mode)
        report.update(fixture_sha256=fixture_hash,source_commit=commit,
                      grader_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      fixture_validation=validation)
        # Never destroy a previous batch, even for a dry planning run.
        args.out.mkdir(parents=True,exist_ok=False)
        write_new_json(args.out/'report.json',report)
        print(json.dumps({k:report[k] for k in ('status','planned','tested','counts','pass_rate_observed')},ensure_ascii=False))
        return 0 if args.plan or report['status']=='PASS' else 3
    except FileExistsError:
        print(f"Error: Output directory already exists: '{args.out}'. Choose a fresh output directory to preserve prior batches.", file=sys.stderr)
        return 2
    except (EvidenceError, OSError, ValueError) as exc:
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
