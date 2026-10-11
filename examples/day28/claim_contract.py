"""Proposed claim adapter for the existing Day 11 get/put/atomic interface.

Only offline contract tests accompany this candidate. Firestore transactions,
verified LINE identity resolution, schema migration, and phone delivery are NOT_RUN.
New volunteer_grants/service_controls documents are a proposed schema, not existing
production data. A VerifiedVolunteer value is NOT itself an authentication proof.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Protocol


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedVolunteer:
    tenant_id: str
    user_id: str

    def __post_init__(self) -> None:
        if any(type(x) is not str or not x for x in (self.tenant_id, self.user_id)):
            raise ContractError('INVALID_PRINCIPAL')


class Tx(Protocol):
    def get(self, kind: str, ident: str) -> dict | None: ...
    def put(self, kind: str, ident: str, value: dict) -> None: ...


def scope_key(*parts: str) -> str:
    value = json.dumps(parts, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def claim_patch(row: dict, grant: dict | None, control: dict | None,
                actor: VerifiedVolunteer, expected_version: int) -> dict | None:
    """Return a patch, or None for a retry by the same already-assigned volunteer."""
    if type(expected_version) is not int or expected_version < 1:
        raise ContractError('INVALID_CLAIM_VERSION')
    version = row.get('claim_version')
    if type(version) is not int or version < 1:
        raise ContractError('SCHEMA_MIGRATION_REQUIRED')
    owner = row.get('actor')
    if not isinstance(owner, dict) or owner.get('tenant_id') != actor.tenant_id:
        raise PermissionError('TENANT_DENIED')
    service = row.get('service_id')
    if type(service) is not str or not service:
        raise ContractError('SERVICE_REQUIRED')
    if not isinstance(grant, dict) or not (
        grant.get('allowed') is True and grant.get('role') == 'volunteer'
        and grant.get('tenant_id') == actor.tenant_id
        and grant.get('user_id') == actor.user_id
        and grant.get('service_id') == service
    ):
        raise PermissionError('VOLUNTEER_DENIED')
    if not isinstance(control, dict) or not (
        control.get('tenant_id') == actor.tenant_id
        and control.get('service_id') == service
        and control.get('mode') == 'SERVING'
    ):
        raise ContractError('SERVICE_PAUSED_OR_UNCONFIGURED')
    status, claimed = row.get('status'), row.get('human_claimed')
    if status == 'human_claimed':
        if claimed is not True or type(row.get('claimed_by')) is not str:
            raise ContractError('CORRUPT_CLAIM_STATE')
        if row['claimed_by'] == actor.user_id:
            return None
        raise ContractError('ALREADY_CLAIMED')
    if status != 'pending_human_review' or claimed is not False:
        raise ContractError('INVALID_STATE')
    if row.get('claimed_by') is not None:
        raise ContractError('CORRUPT_CLAIM_STATE')
    if version != expected_version:
        raise ContractError('STALE_CLAIM_VERSION')
    return {'status': 'human_claimed', 'human_claimed': True,
            'claimed_by': actor.user_id, 'claim_version': version + 1}


def check_original_binding(row, binding, operation_id: str, request_id: str) -> None:
    if not isinstance(row, dict) or not isinstance(binding, dict):
        raise ContractError('REQUEST_OR_BINDING_NOT_FOUND')
    if type(request_id) is not str or not request_id or row.get('request_id') != request_id:
        raise ContractError('REQUEST_ID_MISMATCH')
    if row.get('operation_id') != operation_id or binding.get('operation_id') != operation_id:
        raise ContractError('OPERATION_ID_MISMATCH')
    for field in ('actor', 'args', 'payload_hash'):
        if field not in row or field not in binding or row[field] != binding[field]:
            raise ContractError('BINDING_MISMATCH')
    args = binding['args']
    if not isinstance(args, dict) or row.get('request_text') != args.get('request_text') or row.get('event_id') != args.get('event_id'):
        raise ContractError('PAYLOAD_MISMATCH')


def claim_in_tx(tx: Tx, actor: VerifiedVolunteer,
                operation_id: str, request_id: str, expected_version: int) -> dict:
    """Call only within store.atomic(); all reads precede any write."""
    if not isinstance(actor, VerifiedVolunteer):
        raise TypeError('VERIFIED_PRINCIPAL_REQUIRED')
    if type(operation_id) is not str or re.fullmatch(r'[0-9a-f]{64}', operation_id) is None:
        raise ContractError('INVALID_OPERATION_ID')
    row = tx.get('requests', operation_id)
    binding = tx.get('bindings', operation_id)
    check_original_binding(row, binding, operation_id, request_id)
    service = row.get('service_id')
    if type(service) is not str or not service:
        raise ContractError('SERVICE_REQUIRED')
    grant = tx.get('volunteer_grants', scope_key(actor.tenant_id, actor.user_id, service))
    control = tx.get('service_controls', scope_key(actor.tenant_id, service))
    patch = claim_patch(row, grant, control, actor, expected_version)
    if patch is None:
        return dict(row)
    updated = {**row, **patch}
    tx.put('requests', operation_id, updated)
    return updated
