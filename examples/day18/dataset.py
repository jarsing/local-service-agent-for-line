"""Validate the public benchmark before executing any application or API call."""
from __future__ import annotations
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = REPO / 'eval/local20.json'
TOOL_FIELDS = {
    'search_local_events': {'date', 'area', 'keyword'},
    'search_local_places': {'area', 'dietary_type', 'keyword'},
    'show_local_help': {'reason'},
    'propose_dietary_memory': {'dietary_type', 'area', 'keyword'},
    'request_memory_management': {'action', 'dietary_type'},
}
TOOL_ARGUMENT_ENUMS = {
    'search_local_places': {
        'dietary_type': {'', 'any', 'vegetarian', 'vegan', 'ovo_lacto', 'lacto', 'allium', 'friendly',
                         '蔬食', '素食', '全素', '純素', '蛋奶素', '奶素', '五辛素', '蔬食友善', '不限'},
    },
    'show_local_help': {
        'reason': {'general', 'unsupported', 'out_of_scope', 'help', 'booking', 'conflict', 'needs_area', 'policy'},
    },
    'request_memory_management': {
        'action': {'status', 'forget', 'confirm'},
        'dietary_type': {'', 'any', 'vegetarian', 'vegan', 'ovo_lacto', 'lacto', 'allium', 'friendly',
                         '蔬食', '素食', '全素', '純素', '蛋奶素', '奶素', '五辛素', '蔬食友善', '不限'},
    },
}


def load_dataset(path: Path = DEFAULT_DATASET) -> dict:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('DATASET_SCHEMA_REQUIRED')
    cases = data.get('cases')
    if not isinstance(cases, list) or len(cases) != 20:
        raise ValueError('EXACTLY_TWENTY_CASES_REQUIRED')
    for n, case in enumerate(cases, 1):
        if not isinstance(case, dict) or case.get('id') != f'local{n:02}':
            raise ValueError('ORDERED_UNIQUE_CASE_IDS_REQUIRED')
        if case.get('group') != ('A' if n <= 10 else 'B'):
            raise ValueError('TEN_PLUS_TEN_GROUPS_REQUIRED')
        if not isinstance(case.get('input'), str) or not case['input'].strip():
            raise ValueError('NONEMPTY_CASE_INPUT_REQUIRED')
        expected = case.get('expect')
        if not isinstance(expected, dict):
            raise ValueError('EXPECTED_CONTRACT_REQUIRED')
        tools = expected.get('tools')
        if not isinstance(tools, list) or len(tools) > 1 or any(t not in TOOL_FIELDS for t in tools):
            raise ValueError('KNOWN_SINGLE_TOOL_CONTRACT_REQUIRED')
        for field in ('business_writes', 'forbidden_executions'):
            if type(expected.get(field)) is not int or expected[field] < 0:
                raise ValueError('EXPLICIT_NONNEGATIVE_EFFECT_BUDGET_REQUIRED')
        for field in ('statuses', 'required_text', 'actions'):
            if not isinstance(expected.get(field), list):
                raise ValueError('EXPLICIT_UI_CONTRACT_REQUIRED')
        if 'forbidden_text' in expected:
            if not isinstance(expected['forbidden_text'], list) or any(not isinstance(s, str) for s in expected['forbidden_text']):
                raise ValueError('FORBIDDEN_TEXT_LIST_REQUIRED')
        if not expected['statuses'] and not expected.get('exception'):
            raise ValueError('STATUS_OR_EXCEPTION_REQUIRED')
        args = expected.get('arguments', {})
        if not isinstance(args, dict) or (args and not tools):
            raise ValueError('INVALID_ARGUMENT_EXPECTATION')
        if tools and set(args) - TOOL_FIELDS[tools[0]]:
            raise ValueError('ARGUMENT_OUTSIDE_TOOL_SCHEMA')
        tool_enums = TOOL_ARGUMENT_ENUMS.get(tools[0] if tools else '', {})
        for arg_key, values in args.items():
            if arg_key in tool_enums:
                if any(v not in tool_enums[arg_key] for v in values):
                    raise ValueError('ARGUMENT_VALUE_NOT_IN_ENUM')
        if any(not isinstance(values, list) or not values or
               any(not isinstance(v, str) for v in values) for values in args.values()):
            raise ValueError('ARGUMENT_EQUIVALENCE_MUST_BE_EXPLICIT')
    live_ids = data.get('live_eligible_ids')
    ids = {c['id'] for c in cases}
    if not isinstance(live_ids, list) or len(live_ids) != len(set(live_ids)) or set(live_ids) - ids:
        raise ValueError('INVALID_LIVE_CASE_IDS')
    return data
