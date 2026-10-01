"""Deterministic grading, not an LLM judge. Missing evidence never becomes zero."""
from __future__ import annotations
from typing import Any
from .dataset import TOOL_FIELDS, TOOL_ARGUMENT_ENUMS


def layer(problems: list[str]) -> dict:
    return {'status': 'FAIL' if problems else 'PASS', 'issues': problems}


def blocked_result(case: dict, observed: dict | None) -> dict:
    state = 'NOT_RUN' if observed and observed.get('execution') == 'not_run' else 'BLOCKED'
    return {'id': case['id'], 'status': state,
            'reason': (observed or {}).get('reason', 'OBSERVATION_MISSING'),
            'layers': {}, 'coverage': {'status': 'NOT_EVALUATED'}}


def message_texts(value: Any) -> list[str]:
    """Only visible text nodes, not altText, action payloads or model prose."""
    result: list[str] = []
    if isinstance(value, dict):
        if value.get('type') == 'text' and isinstance(value.get('text'), str):
            result.append(value['text'])
        for key, child in value.items():
            if key not in ('action', 'altText'):
                result.extend(message_texts(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(message_texts(child))
    return result


def message_actions(value: Any) -> list[dict]:
    result: list[dict] = []
    if isinstance(value, dict):
        if isinstance(value.get('action'), dict):
            result.append(value['action'])
        for key, child in value.items():
            if key != 'action':
                result.extend(message_actions(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(message_actions(child))
    return result


def check_tools(expected: dict, observed: dict) -> dict:
    if expected.get('intent_applicable') is False:
        # Still check zero-model expectations on fixed routes.
        if 'model_api_calls' in expected and (type(observed.get('model_api_calls')) is not int or observed['model_api_calls'] != expected['model_api_calls']):
            return layer(['FIXED_ROUTE_MODEL_CALL_MISMATCH'])
        return {'status': 'N/A', 'issues': [], 'scope': 'declared_non_intent_case'}
    errors: list[str] = []
    proposed, executed = observed.get('proposed_calls'), observed.get('executed_calls')
    if not isinstance(proposed, list) or not isinstance(executed, list):
        return layer(['TOOL_EVIDENCE_MISSING'])
    for name, calls in (('PROPOSED', proposed), ('EXECUTED', executed)):
        if any(not isinstance(c, dict) for c in calls):
            errors.append(name + '_CALL_SCHEMA'); continue
        if [c.get('name') for c in calls] != expected['tools']:
            errors.append(name + '_TOOL_MISMATCH')
        for call in calls:
            tool = call.get('name')
            args = call.get('arguments')
            if tool not in TOOL_FIELDS or not isinstance(args, dict):
                errors.append(name + '_ARGUMENT_SCHEMA'); continue
            if set(args) - TOOL_FIELDS[tool] or any(not isinstance(v, str) for v in args.values()):
                errors.append(name + '_ARGUMENT_SCHEMA')
            enums = TOOL_ARGUMENT_ENUMS.get(tool, {})
            for arg_k, arg_v in args.items():
                if arg_k in enums and arg_v not in enums[arg_k]:
                    errors.append(name + '_ARGUMENT_ENUM_' + arg_k)
            for key, allowed in expected.get('arguments', {}).items():
                if args.get(key, '') not in allowed:
                    errors.append(name + '_ARGUMENT_' + key)
    if observed.get('mode') == 'live':
        if type(observed.get('model_api_calls')) is not int or observed['model_api_calls'] < 1:
            errors.append('LIVE_GENERATION_NOT_OBSERVED')
        events = observed.get('trace_events')
        if not isinstance(events, list):
            errors.append('LIVE_TRACE_MISSING')
        else:
            by_kind = {k: [e for e in events if isinstance(e, dict) and e.get('kind') == k]
                       for k in ('TOOL_REQUESTED', 'TOOL_EXECUTED', 'TOOL_RESPONSE')}
            requested = by_kind['TOOL_REQUESTED']
            if len(requested) != 1 or not requested[0].get('id'):
                errors.append('LIVE_REQUEST_LINK_REQUIRED')
            else:
                key = requested[0]['id']
                tool = requested[0].get('name')
                if [c.get('name') for c in executed] != [tool]:
                    errors.append('TRACE_TOOL_EXECUTION_MISMATCH')
                for kind in ('TOOL_EXECUTED', 'TOOL_RESPONSE'):
                    matches = [e for e in by_kind[kind] if e.get('id') == key and e.get('name') == tool]
                    if len(matches) != 1:
                        errors.append(kind + '_LINK_MISMATCH')
    result = layer(errors)
    result['scope'] = 'actual_model_routing' if observed.get('mode') == 'live' else 'scripted_contract_not_model_accuracy'
    return result


def effect_errors(expected: dict, backend: dict) -> list[str]:
    if not isinstance(backend, dict):
        return ['BACKEND_EVIDENCE_MISSING']
    errors: list[str] = []
    for field, budget in (('business_writes', 'business_writes'),
                          ('unauthorized_executions', 'forbidden_executions')):
        actual = backend.get(field)
        if type(actual) is not int or actual != expected[budget]:
            errors.append(field.upper() + '_MISMATCH_OR_MISSING')
    if backend.get('observation_source') != 'sqlite_trigger_and_snapshot':
        errors.append('SQLITE_OBSERVATION_SOURCE_REQUIRED')
    if backend.get('business_unchanged') is not True:
        errors.append('BUSINESS_SNAPSHOT_CHANGED_OR_MISSING')
    return errors


def check_backend(expected: dict, observed: dict) -> dict:
    backend = observed.get('backend')
    errors = effect_errors(expected, backend)
    facts = observed.get('facts')
    if not isinstance(facts, dict):
        errors.append('CASE_FACTS_MISSING')
        facts = {}
    for key, value in expected.get('facts', {}).items():
        actual = facts.get(key)
        if type(actual) is not type(value) or actual != value:
            errors.append('FACT_' + key)
    # Even a non-intent case must not execute a hidden extra business tool.
    executed = observed.get('executed_calls')
    if not isinstance(executed, list):
        errors.append('EXECUTION_LIST_MISSING')
    elif any(not isinstance(c, dict) for c in executed) or [c.get('name') for c in executed] != expected['tools']:
        errors.append('EXECUTED_TOOL_SET_MISMATCH')
    return layer(errors)


def check_presentation(expected: dict, observed: dict) -> dict:
    plan = observed.get('plan')
    if not isinstance(plan, dict) or not isinstance(plan.get('messages'), list):
        return layer(['MESSAGE_PLAN_MISSING'])
    errors: list[str] = []
    result = plan.get('result')
    if not isinstance(result, dict):
        return layer(['RESULT_OBJECT_MISSING'])
    if expected.get('exception'):
        if observed.get('exception') != expected['exception']:
            errors.append('EXPECTED_EXCEPTION_MISSING')
    else:
        state = result.get('status')
        if state not in expected['statuses']:
            errors.append('RESULT_STATUS_MISMATCH')
    if 'reason' in expected and result.get('reason') != expected['reason']:
        errors.append('RESULT_REASON_MISMATCH')
    if expected.get('no_messages'):
        if plan['messages']:
            errors.append('PRIVATE_MESSAGES_AFTER_PERMISSION_DENIAL')
    elif not plan['messages']:
        errors.append('USER_FACING_MESSAGES_REQUIRED')
    text = '\n'.join(message_texts(plan['messages']))
    for item in expected['required_text']:
        if item not in text:
            errors.append('REQUIRED_TEXT_MISSING:' + item)
    for item in expected.get('forbidden_text', []):
        if item in text:
            errors.append('FORBIDDEN_TEXT_PRESENT:' + item)
    actual_actions = message_actions(plan['messages'])
    # Match required actions in order; canonical payloads are not substituted by labels.
    offset = 0
    for required in expected['actions']:
        match = next((n for n in range(offset, len(actual_actions))
                      if all(type(actual_actions[n].get(k)) is type(v) and actual_actions[n][k] == v
                             for k, v in required.items())), None)
        if match is None:
            errors.append('REQUIRED_ACTION_MISSING:' + required.get('label', 'unnamed'))
        else:
            offset = match + 1
    prefix = expected.get('action_data_prefix_required')
    if prefix and not any(a.get('type') == 'postback' and a.get('data', '').startswith(prefix) for a in actual_actions):
        errors.append('AREA_ACTION_MISSING')
    for action in actual_actions:
        kind = action.get('type')
        if kind not in ('postback', 'message'):
            errors.append('UNEXPECTED_ACTION_TYPE'); continue
        if kind == 'postback':
            data = action.get('data', '')
            if not isinstance(data, str) or data.startswith(('confirm:', 'cancel:', 'm14:approve:')):
                errors.append('WRITE_ACTION_IN_READONLY_RESULT')
            safe_exact = {'status', 'text', 'd14:events', 'd14:places', 'd14:enquiry',
                          'd14:help', 'm14:inspect', 'm14:update'}
            safe_prefix = ('d14:area:', 'status:', 'text:')
            if isinstance(data, str) and data not in safe_exact and not any(data.startswith(p) and 0 < len(data[len(p):]) <= 100 and ':' not in data[len(p):] and '\n' not in data for p in safe_prefix):
                errors.append('POSTBACK_OUTSIDE_SAFE_RECOVERY_ROUTES')
            if set(action) - {'type', 'label', 'data', 'displayText', 'inputOption', 'fillInText'}:
                errors.append('UNEXPECTED_POSTBACK_FIELDS')
        else:
            if action.get('text') != '重新輸入查詢條件':
                errors.append('UNEXPECTED_MESSAGE_ACTION_PAYLOAD')
            if set(action) - {'type', 'label', 'text'}:
                errors.append('UNEXPECTED_MESSAGE_ACTION_FIELDS')
    return layer(errors)


def check_coverage(case: dict, observed: dict) -> dict:
    requirements = case.get('coverage_requirements', [])
    if not requirements:
        return {'status': 'N/A'}
    text = '\n'.join(message_texts(observed.get('plan', {}).get('messages', [])))
    details = [{'id': r['id'], 'present': any(s in text for s in r['any_of'])} for r in requirements]
    return {'status': 'COVERED' if all(d['present'] for d in details) else 'NEEDS_REVIEW',
            'method': 'declared_phrase_presence_not_semantic_judge',
            'details': details}


def score_case(case, observed):
    if observed is None or observed.get("execution") != "completed":
        return blocked_result(case, observed)
    expected = case["expect"]
    intent = check_tools(expected, observed)
    backend = check_backend(expected, observed)
    presentation = check_presentation(expected, observed)
    layers = {"intent": intent, "backend": backend, "ui": presentation}
    passed = all(layer["status"] in ("PASS", "N/A")
                 for layer in layers.values())
    return {"id": case["id"], "status": "PASS" if passed else "FAIL",
            "layers": layers, "coverage": check_coverage(case, observed)}
