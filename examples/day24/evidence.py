"""Deterministic evidence checks. No network or backend calls in this module.

A digest checks content identity, not the truth of a transport-origin claim.
Usage fields remain unknown when absent. Candidate + thought billing is text-only.
"""
from __future__ import annotations
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / 'eval/local20.json'
LIVE_IDS = ('local01','local02','local09','local11','local12','local13','local17','local18','local19')
AB_IDS = ('local11','local12','local19')
MODEL = 'gemini-2.5-flash'
TOOL_FIELDS = {
 'search_local_events': ('date','area','keyword'),
 'search_local_places': ('area','dietary_type','keyword'),
 'show_local_help': ('reason',),
 'propose_dietary_memory': ('dietary_type','area','keyword'),
 'request_memory_management': ('action','dietary_type'),
}
DIETS = ('','any','vegetarian','vegan','ovo_lacto','lacto','allium','friendly','蔬食','素食','全素','純素','蛋奶素','奶素','五辛素','蔬食友善','不限')
ENUMS = {
 'search_local_places': {'dietary_type': DIETS},
 'show_local_help': {'reason': ('','unsupported')},
 'request_memory_management': {'action': ('inspect','update','forget'), 'dietary_type': DIETS},
}
COMPARE_FIELDS = ('case_id','input_sha256','dataset_sha256','model_id','endpoint',
 'instruction_sha256','tools_sha256','source_tree_sha256','config_base_sha256',
 'sdk_version','sdk_attempts','measurement_scope','rate_card_sha256')


def encoded(value: Any) -> bytes:
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(encoded(value))


def load(path: Path) -> Any:
    def no_constants(value):
        raise ValueError('NONFINITE_JSON_'+value)
    return json.loads(path.read_text(encoding='utf-8'),parse_constant=no_constants)


def dataset(path: Path = DATASET) -> dict:
    d = load(path)
    if [c.get('id') for c in d.get('cases',[])] != [f'local{i:02}' for i in range(1,21)]:
        raise ValueError('FIXED_TWENTY_IDS_REQUIRED')
    if tuple(d.get('live_eligible_ids',[])) != LIVE_IDS:
        raise ValueError('FIXED_NINE_LIVE_IDS_REQUIRED')
    for c in d['cases']:
        if not isinstance(c.get('input'),str) or not c['input'].strip():
            raise ValueError('CASE_INPUT_REQUIRED')
    return d


def nonnegative_int(n: Any) -> int:
    if type(n) is not int or n < 0:
        raise ValueError('NONNEGATIVE_INTEGER_REQUIRED')
    return n


def finite_time(value: Any) -> float:
    if type(value) not in (int,float) or not math.isfinite(value) or value < 0:
        raise ValueError('FINITE_NONNEGATIVE_TIME_REQUIRED')
    return float(value)


def field(data: dict, snake: str, camel: str):
    if snake in data and camel in data and data[snake] != data[camel]:
        raise ValueError('AMBIGUOUS_FIELD_'+snake)
    return data[snake] if snake in data else data.get(camel)


def usage(response: dict, budget: int) -> dict:
    raw = field(response,'usage_metadata','usageMetadata')
    if not isinstance(raw,dict):
        return {'cost_status':'UNKNOWN','reason':'USAGE_MISSING','usd':None}
    out = {}
    for short,snake,camel in (
        ('input','prompt_token_count','promptTokenCount'),
        ('output','candidates_token_count','candidatesTokenCount'),
        ('thoughts','thoughts_token_count','thoughtsTokenCount'),
        ('total','total_token_count','totalTokenCount')):
        n = field(raw,snake,camel)
        out[short] = nonnegative_int(n) if n is not None else None
    out['thoughts_origin'] = 'OBSERVED' if out['thoughts'] is not None else 'MISSING'
    if out['thoughts'] is None and budget == 0:
        out['thoughts'] = 0
        out['thoughts_origin'] = 'INFERRED_FROM_EXPLICIT_DISABLED_BUDGET'
    if any(out[x] is None for x in ('input','output','thoughts','total')):
        return dict(out,cost_status='UNKNOWN',reason='INCOMPLETE_USAGE',usd=None)
    if budget == 0 and out['thoughts'] != 0:
        return dict(out,cost_status='INVALID',reason='THOUGHTS_WITH_DISABLED_BUDGET',usd=None)
    for snake,camel in (('cached_content_token_count','cachedContentTokenCount'),
                        ('tool_use_prompt_token_count','toolUsePromptTokenCount')):
        n = field(raw,snake,camel)
        if n is not None and nonnegative_int(n) != 0:
            return dict(out,cost_status='UNSUPPORTED',reason='CACHE_OR_TOOL_USE_USAGE',usd=None)
    details = field(raw,'prompt_tokens_details','promptTokensDetails') or []
    if any(d.get('modality') not in ('TEXT','MODALITY_UNSPECIFIED') for d in details):
        return dict(out,cost_status='UNSUPPORTED',reason='NON_TEXT_PRICING',usd=None)
    if out['total'] != out['input']+out['output']+out['thoughts']:
        return dict(out,cost_status='INVALID',reason='TOKEN_TOTAL_MISMATCH',usd=None)
    return dict(out,cost_status='COMPLETE',reason=None,usd=None)


def estimate(usage_row: dict, rate: dict, model_id: str) -> dict:
    out = dict(usage_row)
    if rate.get('model_id') != model_id or rate.get('currency') != 'USD' or rate.get('scope') != 'standard_text_no_cache_no_grounding':
        raise ValueError('RATE_SCOPE_MISMATCH')
    if out['cost_status'] != 'COMPLETE':
        return out
    a,b = Decimal(rate['input_usd_per_million']),Decimal(rate['output_usd_per_million'])
    if not a.is_finite() or not b.is_finite() or min(a,b) < 0:
        raise ValueError('INVALID_RATE')
    amount = (Decimal(out['input'])*a + Decimal(out['output']+out['thoughts'])*b)/Decimal(1_000_000)
    out['usd'] = str(amount)
    return out


def calls(response: dict) -> list[dict]:
    candidates = response.get('candidates')
    if not isinstance(candidates,list) or len(candidates) != 1:
        raise ValueError('ONE_RESPONSE_CANDIDATE_REQUIRED')
    c = candidates[0]
    finish = field(c,'finish_reason','finishReason')
    if finish not in ('STOP',None):
        raise ValueError('MODEL_DID_NOT_FINISH_NORMALLY')
    result = []
    for part in c.get('content',{}).get('parts',[]):
        f = field(part,'function_call','functionCall')
        if f is None:
            continue
        if not isinstance(f,dict):
            raise ValueError('FUNCTION_CALL_OBJECT_REQUIRED')
        name,args = f.get('name'),f.get('args')
        if name not in TOOL_FIELDS or not isinstance(args,dict):
            raise ValueError('TOOL_SCHEMA_MISMATCH')
        if set(args) != set(TOOL_FIELDS[name]) or any(not isinstance(v,str) for v in args.values()):
            raise ValueError('TOOL_ARGUMENT_SCHEMA_MISMATCH')
        for k,values in ENUMS.get(name,{}).items():
            if k in args and args[k] not in values:
                raise ValueError('TOOL_ENUM_MISMATCH')
        result.append({'name':name,'arguments':args})
    if len(result) != 1:
        raise ValueError('EXACTLY_ONE_TOOL_REQUIRED')
    return result


def route_grade(case: dict, selected: list[dict]) -> dict:
    failures = []
    if [r['name'] for r in selected] != case['expect']['tools']:
        failures.append('TOOL_NAME_MISMATCH')
    if len(selected) != 1:
        failures.append('SINGLE_TOOL_REQUIRED')
    else:
        for k,values in case['expect'].get('arguments',{}).items():
            if selected[0]['arguments'].get(k,'') not in values:
                failures.append('ARGUMENT_MISMATCH:'+k)
    return {'status':'FAIL' if failures else 'PASS','issues':failures,
            'scope':'SDK_MODEL_TOOL_REQUEST_ONLY','backend':'NOT_EVALUATED','ui':'NOT_EVALUATED'}


def comparable(a: dict, b: dict) -> list[str]:
    issues = []
    for key in COMPARE_FIELDS:
        if a.get(key) is None or b.get(key) is None or a[key] != b[key]:
            issues.append('IDENTITY_MISMATCH:'+key)
    for row in (a,b):
        for key in COMPARE_FIELDS:
            if key.endswith('_sha256'):
                v = row.get(key)
                if not isinstance(v,str) or len(v)!=64 or any(c not in '0123456789abcdef' for c in v):
                    issues.append('INVALID_DIGEST:'+key)
    if a.get('budget') != 0 or b.get('budget') != 1024:
        issues.append('BUDGET_PAIR_MISMATCH')
    # Returned version is evidence about the served model, not a substitute for requested ID.
    if not a.get('served_model_version') or a.get('served_model_version') != b.get('served_model_version'):
        issues.append('SERVED_MODEL_VERSION_MISSING_OR_CHANGED')
    if a.get('origin') != 'DIRECT_SDK_CAPTURE' or b.get('origin') != 'DIRECT_SDK_CAPTURE':
        issues.append('CAPTURE_ORIGIN_MISMATCH')
    return sorted(set(issues))


def safe_read(root: Path, relative: str, sha: str) -> dict:
    p = (root/relative).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError('ARTIFACT_OUTSIDE_CAPTURE_OR_MISSING')
    if digest(p.read_bytes()) != sha:
        raise ValueError('ARTIFACT_HASH_MISMATCH')
    return load(p)
