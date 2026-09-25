"""新增的持久化確認檢核；沿用 Day 8 型別與指紋，不灌入它的私人 _records。"""
from __future__ import annotations
from dataclasses import replace
from domain import time_of
from upstream import Operation, operation_fingerprint


def validate_first_write(confirmation, binding, draft, catalog, now):
    if not confirmation or confirmation.get('status')!='confirmation_recorded':
        return 'unconfirmed_operation'
    if confirmation.get('execution_allowed') is not False:
        return 'invalid_confirmation_record'
    if confirmation.get('operation_id')!=binding['operation_id']:
        return 'confirmation_already_used'
    if confirmation.get('owner') != binding['actor']:
        return 'invalid_confirmation_record'
    snap=confirmation.get('snapshot')
    if not isinstance(snap,dict):return 'invalid_confirmation_record'
    try:
        original=Operation(**snap)
        valid_snapshot=operation_fingerprint(original)==confirmation['fingerprint']
    except (TypeError,ValueError,KeyError):
        return 'invalid_confirmation_record'
    if not valid_snapshot or original.request_text!=binding['args']['request_text'] or original.event_id!=binding['args']['event_id']:
        return 'invalid_confirmation_record'
    receipt=confirmation.get('receipt')
    if (not isinstance(receipt,dict) or
        receipt.get('confirmation_id')!=binding['args']['confirmation_id'] or
        receipt.get('operation_fingerprint')!=confirmation['fingerprint'] or
        receipt.get('catalog_version')!=snap['catalog_version']):
        return 'invalid_confirmation_record'
    try:
        created=time_of(confirmation['created_at']);expires=time_of(confirmation['expires_at'])
        recorded=time_of(receipt['recorded_at'])
    except (ValueError,TypeError,KeyError):return 'invalid_confirmation_record'
    if not created<=recorded<expires:return 'invalid_confirmation_record'
    if now < recorded:return 'clock_error'
    if now >= time_of(confirmation['expires_at']):return 'expired'
    if not catalog or catalog.get('data_status')!='adopted':return 'data_pending'
    snap=confirmation['snapshot']
    if catalog['catalog_version']!=snap['catalog_version']:return 'version_changed'
    if not draft:return 'content_changed'
    current=replace(Operation(**draft),catalog_version=catalog['catalog_version'],
                    displayed_event=catalog['displayed_event'])
    if operation_fingerprint(current)!=confirmation['fingerprint']:return 'content_changed'
    return None
