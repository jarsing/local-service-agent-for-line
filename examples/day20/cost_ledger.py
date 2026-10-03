"""Explicit-price cost ledger for uncached text generateContent responses.

No Gemini client. --demo uses declared synthetic arithmetic inputs, not timings.
Imported JSON is caller-provided evidence, not independently authenticated billing.
The calling adapter must copy measured usage, grade, identities and raw-record hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def amount(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('DECIMAL_STRING_REQUIRED')
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('INVALID_DECIMAL') from exc
    if not number.is_finite() or number < 0:
        raise ValueError('NONNEGATIVE_FINITE_VALUE_REQUIRED')
    return number


def count(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError('NONNEGATIVE_INTEGER_USAGE_REQUIRED')
    return value


@dataclass(frozen=True)
class RateCard:
    model_id: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    source_url: str
    checked_date: str
    scope: str = 'standard_text_no_cache_no_grounding'

    @classmethod
    def read(cls, path: Path):
        row = json.loads(path.read_text())
        for key in ('model_id', 'source_url', 'checked_date'):
            if not isinstance(row.get(key), str) or not row[key]:
                raise ValueError('PRICE_PROVENANCE_REQUIRED')
        if row.get('scope') != 'standard_text_no_cache_no_grounding':
            raise ValueError('UNSUPPORTED_PRICE_SCOPE')
        return cls(row['model_id'], amount(row['input_usd_per_million']),
                   amount(row['output_usd_per_million']), row['source_url'], row['checked_date'])


def calculate_text_cost(usage: dict, rate: RateCard, model_id: str,
                        usd_to_twd: Decimal) -> dict:
    if model_id != rate.model_id:
        raise ValueError('MODEL_PRICE_MISMATCH')
    if usage.get('output_semantics') != 'candidates_excludes_thoughts':
        raise ValueError('OUTPUT_TOKEN_SEMANTICS_REQUIRED')
    inputs = count(usage.get('prompt_token_count'))
    outputs = count(usage.get('candidates_token_count'))
    thoughts = count(usage.get('thoughts_token_count'))
    cached = count(usage.get('cached_content_token_count'))
    if cached or usage.get('grounding_used') is not False:
        raise ValueError('UNSUPPORTED_CACHE_OR_GROUNDING')
    fx = amount(usd_to_twd)
    if fx == 0:
        raise ValueError('POSITIVE_FX_REQUIRED')
    usd = (Decimal(inputs) * rate.input_usd_per_million
           + Decimal(outputs + thoughts) * rate.output_usd_per_million) / Decimal(1_000_000)
    # Keep full precision; formatting is a presentation decision, not ledger data.
    return {'raw_usd': str(usd), 'estimated_twd': str(usd * fx),
            'usd_to_twd': str(fx), 'scope': rate.scope,
            'billed_output_tokens': outputs + thoughts}


IDENTITY_KEYS = ('case_id', 'input_sha256', 'model_id', 'endpoint', 'prompt_sha256',
                 'tools_sha256', 'catalog_sha256', 'scorer_sha256', 'code_sha', 'config_base_sha256')


def validate_comparable(first: dict, second: dict) -> None:
    for key in IDENTITY_KEYS:
        if not first.get(key) or first.get(key) != second.get(key):
            raise ValueError('COMPARISON_IDENTITY_MISMATCH:' + key)
    for row in (first, second):
        if type(row.get('attempts')) is not int or row['attempts'] != 1:
            raise ValueError('SINGLE_ATTEMPT_REQUIRED')
    if first.get('thinking_budget') == second.get('thinking_budget'):
        raise ValueError('NO_DECLARED_VARIABLE')


def select_cases(dataset_path: Path) -> list[dict]:
    dataset = json.loads(dataset_path.read_text())
    cases = dataset.get('cases', [])
    by_id = {c['id']: c for c in cases}
    if len(cases) != 20 or len(by_id) != 20:
        raise ValueError('BASELINE_TWENTY_REQUIRED')
    # Explicit corrected selection: local14 is an injected upstream failure.
    required = {'local11': 'search_local_events', 'local12': 'search_local_places',
                'local19': 'show_local_help'}
    selected = []
    for cid, tool in required.items():
        case = by_id[cid]
        if case['expect']['tools'] != [tool]:
            raise ValueError('CASE_TOOL_MISMATCH:' + cid)
        selected.append({'case_id': cid, 'input': case['input'], 'tool': tool,
                         'input_sha256': hashlib.sha256(case['input'].encode()).hexdigest()})
    return selected


def generate_cases_template(dataset_path: Path) -> list[dict]:
    """Generate the 6-row comparative sampling template from eval/local20.json."""
    selected = select_cases(dataset_path)
    rows = []
    for case in selected:
        for setting_name, budget in [('A', 0), ('B', 1024)]:
            rows.append({
                'origin': 'imported_capture',
                'case_id': case['case_id'],
                'setting': setting_name,
                'input_sha256': case['input_sha256'],
                'model_id': 'gemini-2.5-flash',
                'endpoint': 'generateContent',
                'prompt_sha256': '<待同次執行回填>',
                'tools_sha256': '<待同次執行回填>',
                'catalog_sha256': '<待同次執行回填>',
                'scorer_sha256': '<待同次執行回填>',
                'code_sha': '<待同次執行回填>',
                'config_base_sha256': '<待同次執行回填>',
                'raw_record_sha256': '<待同次執行回填>',
                'grade_record_sha256': '<待同次執行回填>',
                'thinking_budget': budget,
                'attempts': 1,
                'contract_status': 'NOT_RUN',
                'coverage_status': 'NOT_EVALUATED',
                'latency_scope': 'agent_round',
                'latency_ms': None,
                'usage': None,
            })
    return rows


def adapt_genai_usage(raw_usage: dict) -> dict:
    """Adapt raw Google GenAI SDK UsageMetadata into cost ledger format."""
    if not isinstance(raw_usage, dict):
        raise ValueError('RAW_USAGE_DICT_REQUIRED')

    prompt = count(raw_usage.get('prompt_token_count', 0))
    candidates = count(raw_usage.get('candidates_token_count', 0))
    thoughts = count(raw_usage.get('thoughts_token_count', 0))
    cached = count(raw_usage.get('cached_content_token_count', 0))
    grounding = raw_usage.get('grounding_used', False)

    # In GenAI SDK, if candidates_token_count includes thoughts, caller must separate them.
    semantics = raw_usage.get('output_semantics', 'candidates_excludes_thoughts')
    if semantics != 'candidates_excludes_thoughts':
        raise ValueError('OUTPUT_TOKEN_SEMANTICS_REQUIRED')

    return {
        'prompt_token_count': prompt,
        'candidates_token_count': candidates,
        'thoughts_token_count': thoughts,
        'cached_content_token_count': cached,
        'grounding_used': grounding,
        'output_semantics': semantics,
    }


def evaluate_latency_budget(latency_ms: int | None, budget_ms: int = 5000) -> dict:
    """Evaluate whether latency fits inside a LINE webhook response window."""
    if latency_ms is None:
        return {'status': 'NOT_MEASURED', 'latency_ms': None, 'budget_ms': budget_ms}
    if type(latency_ms) is not int or latency_ms < 0:
        raise ValueError('NONNEGATIVE_INTEGER_LATENCY_REQUIRED')

    remaining = budget_ms - latency_ms
    if remaining >= 1500:
        status = 'SAFE'
    elif remaining >= 0:
        status = 'WARNING'
    else:
        status = 'TIMEOUT_RISK'

    return {
        'status': status,
        'latency_ms': latency_ms,
        'budget_ms': budget_ms,
        'remaining_ms': remaining,
        'within_budget': remaining >= 0,
    }


def format_cost_summary(priced_row: dict) -> str:
    """Generate concise one-line cost summary for LINE developer logging."""
    model_id = priced_row.get('model_id', 'unknown')
    cost = priced_row.get('cost')
    if not cost:
        return f"{model_id} | Cost Unknown (Missing Usage)"

    usage = priced_row.get('usage', {})
    p = usage.get('prompt_token_count', 0)
    c = usage.get('candidates_token_count', 0)
    t = usage.get('thoughts_token_count', 0)
    twd = Decimal(cost['estimated_twd']).quantize(Decimal('0.0001'))
    usd = Decimal(cost['raw_usd']).quantize(Decimal('0.000001'))

    return f"{model_id} | {p} in + {c} out ({t} think) | NT$ {twd} (USD ${usd})"


def summarize_ledger(results: list[dict]) -> dict:
    """Summarize token totals and costs across priced rows."""
    total_billed_tokens = 0
    total_usd = Decimal('0')
    total_twd = Decimal('0')
    priced_count = 0
    missing_count = 0
    pass_count = 0

    for row in results:
        cost = row.get('cost')
        if cost is not None:
            priced_count += 1
            total_billed_tokens += cost.get('billed_output_tokens', 0)
            total_usd += Decimal(cost['raw_usd'])
            total_twd += Decimal(cost['estimated_twd'])
        else:
            missing_count += 1
        if row.get('contract_status') == 'PASS':
            pass_count += 1

    return {
        'total_rows': len(results),
        'priced_rows': priced_count,
        'missing_usage_rows': missing_count,
        'contract_pass_rows': pass_count,
        'total_billed_output_tokens': total_billed_tokens,
        'total_raw_usd': str(total_usd),
        'total_estimated_twd': str(total_twd),
    }


def price_row(row: dict, rate: RateCard, fx: Decimal) -> dict:
    if row.get('origin') not in ('synthetic_fixture', 'imported_capture'):
        raise ValueError('EXPLICIT_OBSERVATION_ORIGIN_REQUIRED')
    if row.get('origin') == 'imported_capture':
        for key in (*IDENTITY_KEYS, 'raw_record_sha256', 'grade_record_sha256'):
            if not isinstance(row.get(key), str) or not row[key]:
                raise ValueError('IMPORTED_EVIDENCE_REFERENCE_REQUIRED:' + key)
        if row.get('latency_scope') not in ('model_only', 'agent_round'):
            raise ValueError('LATENCY_SCOPE_REQUIRED')
        if row.get('latency_ms') is not None:
            amount(str(row['latency_ms']))
    grade = row.get('contract_status')
    if grade not in ('PASS', 'FAIL', 'BLOCKED', 'NOT_RUN'):
        raise ValueError('CONTRACT_STATUS_REQUIRED')
    result = dict(row)
    if row.get('usage') is None:
        result.update(cost=None, cost_status='UNKNOWN_USAGE',
                      quality_eligible=False)
        return result
    result['cost'] = calculate_text_cost(row['usage'], rate, row['model_id'], fx)
    result['cost_status'] = 'SYNTHETIC_ARITHMETIC' if row['origin'] == 'synthetic_fixture' else 'ESTIMATED_FROM_IMPORTED_USAGE'
    result['quality_eligible'] = grade == 'PASS'
    return result


def demo_rows() -> list[dict]:
    return [{'case_id': 'synthetic-arithmetic', 'origin': 'synthetic_fixture',
             'model_id': 'gemini-2.5-flash', 'config': name,
             'contract_status': 'NOT_RUN', 'coverage_status': 'NOT_EVALUATED',
             'latency_ms': None, 'latency_scope': 'NOT_MEASURED',
             'usage': {'prompt_token_count': 1000, 'candidates_token_count': 100,
                       'thoughts_token_count': thoughts, 'cached_content_token_count': 0,
                       'grounding_used': False, 'output_semantics': 'candidates_excludes_thoughts'}}
            for name, thoughts in [('formula-a', 0), ('formula-b', 250)]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    origin = parser.add_mutually_exclusive_group(required=True)
    origin.add_argument('--demo', action='store_true', help='Run synthetic arithmetic demo')
    origin.add_argument('--input', type=Path, help='Input captured observation rows JSON')
    origin.add_argument('--init-cases', type=Path, help='Generate 6-row sampling template from eval/local20.json')
    parser.add_argument('--rates', type=Path, default=Path(__file__).with_name('pricing.checked.json'))
    parser.add_argument('--fx', default='32')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=False)

    if args.init_cases:
        rows = generate_cases_template(args.init_cases)
        template_file = args.out / 'cases_template.json'
        template_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
        print(f"Generated 6-row template ({len(rows)} rows) to {template_file}")
        return

    rate = RateCard.read(args.rates)
    rows = demo_rows() if args.demo else json.loads(args.input.read_text())
    if not isinstance(rows, list) or not rows:
        parser.error('NONEMPTY_OBSERVATION_LIST_REQUIRED')
    results = [price_row(row, rate, amount(args.fx)) for row in rows]
    summary = summarize_ledger(results)
    report = {
        'mode': 'SYNTHETIC_ARITHMETIC' if args.demo else 'IMPORTED_NOT_INDEPENDENTLY_AUTHENTICATED',
        'model_api_calls': 0,
        'billing_verified': False,
        'fx_kind': 'explicit_assumption',
        'rates_sha256': hashlib.sha256(args.rates.read_bytes()).hexdigest(),
        'summary': summary,
        'rows': results,
        'missing_usage_rows': summary['missing_usage_rows'],
    }
    (args.out / 'ledger.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
