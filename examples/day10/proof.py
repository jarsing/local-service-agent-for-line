"""獨立斷言：用事件、鍵、回條與 SQLite 交叉核對；不依摘要 success 自證。"""
from __future__ import annotations
from typing import Any
from records import SendArgs, sqlite_rows
from upstream import payload_hash


class EvidenceMismatch(AssertionError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise EvidenceMismatch(message)


def check_case(case, results: list[dict[str, Any]]) -> dict[str, Any]:
    rows = sqlite_rows(case.db_path)
    # 預期來自固定案例規格，而不是用輸出反推。
    expected = {
        'baseline': ['request_created'],
        'after_commit': ['pending_verification', 'already_created'],
        'before_write': ['pending_verification', 'pending_verification', 'request_created'],
        'lookup_unavailable': ['pending_verification', 'pending_verification'],
    }[case.name]
    require([r['status'] for r in results] == expected, 'STATUS_SEQUENCE')
    require(len(rows) == 1, 'FINAL_ROW_COUNT')
    row = rows[0]
    require(row['idempotency_key'] == case.args.idempotency_key, 'ROW_KEY')
    require(row['confirmation_id'] == case.args.confirmation_id, 'ROW_CONFIRMATION')
    require(row['request_text'] == case.args.request_text and row['event_id'] == case.args.event_id, 'ROW_PAYLOAD')
    require(row['tenant_id'] == case.actor.tenant_id and row['user_id'] == case.actor.user_id
            and row['session_id'] == case.actor.session_id, 'ROW_ACTOR')
    require(row['payload_hash'] == payload_hash(case.args.confirmation_id, case.args.request_text, case.args.event_id), 'PAYLOAD_HASH')
    for event in case.trace.events:
        if event['kind'] in ('TRANSPORT_CREATE', 'TRANSPORT_LOOKUP', 'POLICY_RESULT'):
            require(event['args'] == case.args.tool_args(), 'OPERATION_KEY_OR_PAYLOAD_CHANGED')
    for result in results:
        if result['status'] in ('request_created', 'already_created'):
            require(result['request_id'] == row['request_id'], 'RECEIPT_ROW_ID')
            require(result['request']['idempotency_key'] == row['idempotency_key'], 'RECEIPT_KEY')
        if result['status'] == 'pending_verification':
            require(result['claim_completed'] is False and 'request_id' not in result, 'UNKNOWN_CLAIM')
        require(result.get('human_claimed') is False, 'HUMAN_CLAIM')
    expected_calls = {'baseline': (1, 0), 'after_commit': (1, 1),
                      'before_write': (2, 1), 'lookup_unavailable': (1, 1)}[case.name]
    require((case.transport.create_calls, case.transport.lookup_calls) == expected_calls, 'CALL_BUDGET')
    return {'request_id': row['request_id'], 'row_count': len(rows), 'checks': 'passed'}


def check_adk_trace(events: list[dict[str, Any]], args: SendArgs) -> None:
    requested = [e for e in events if e['kind'] == 'TOOL_REQUESTED']
    executed = [e for e in events if e['kind'] == 'TOOL_EXECUTED']
    returned = [e for e in events if e['kind'] == 'TOOL_RESPONSE']
    require(len(requested) > 0 and len(requested) == len(executed) == len(returned), 'ACTUAL_TOOL_COUNTS')
    require(len({(e['turn'], e['id']) for e in requested}) == len(requested), 'UNIQUE_CALL_IDS')
    for req, run, res in zip(requested, executed, returned):
        require(req['id'] and req['id'] == run['id'] == res['id'], 'CALL_RESPONSE_ID')
        require(req['name'] == run['name'] == res['name'], 'TOOL_NAME')
        require(req['args'] == run['args'] == args.tool_args(), 'EXACT_TOOL_ARGS')
        require(run['result'] == res['response'], 'ACTUAL_TOOL_RESULT')
