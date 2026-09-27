"""Validate ADK request/execution/response links without importing the SDK.

Unit tests of this validator are not evidence that Gemini chose a tool.
"""
from __future__ import annotations
from collections.abc import Mapping
from .engine import TOOL_FIELDS


def verify_triplet(requests, executions, responses):
    if len(requests) != 1 or len(executions) != 1 or len(responses) != 1:
        raise RuntimeError('UNVERIFIED_TOOL_TRACE')
    q, x, r = requests[0], executions[0], responses[0]
    call_id = x.get('id')
    name = x.get('name')
    if not isinstance(call_id, str) or not call_id or name not in TOOL_FIELDS:
        raise RuntimeError('INVALID_EXECUTED_TOOL')
    if any(e.get('id') != call_id or e.get('name') != name for e in (q, r)):
        raise RuntimeError('TOOL_ID_MISMATCH')
    args = q.get('args')
    if not isinstance(args, Mapping) or set(args) - set(TOOL_FIELDS[name]):
        raise RuntimeError('TOOL_PAYLOAD_MISMATCH')
    defaults = {k: args.get(k, '') for k in TOOL_FIELDS[name]}
    if defaults != x.get('args') or r.get('result') != x.get('result'):
        raise RuntimeError('TOOL_PAYLOAD_MISMATCH')
    return {'call_id': call_id, 'tool': name, 'trace_linked': True}


def check_development_case(case, tool_events):
    """Compare a predeclared development expectation with an actual tool audit.

    The expected labels belong in reports/tests, never in the model prompt.
    A four-case development check is not an accuracy benchmark.
    """
    if len(tool_events) != 1 or tool_events[0].get('tool') != case['tool']:
        raise AssertionError('UNEXPECTED_TOOL')
    event = tool_events[0]
    if event.get('proposed_arguments', {}).get('dietary_type', '') != case['diet_argument']:
        raise AssertionError('WRONG_PROPOSED_DIET')
    if 'effective_filter' in case:
        if event.get('effective_arguments', {}).get('dietary_type') != case['effective_filter']:
            raise AssertionError('WRONG_EFFECTIVE_FILTER')
