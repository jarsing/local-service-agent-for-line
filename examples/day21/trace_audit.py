"""Evidence-first trace replay. Local validation, not a Cloud Trace exporter.

The normalized input is a NEW teaching schema, not raw ADK events. An application
adapter must supply actual event links, audit fields and presentation observations.
Synthetic fixtures never establish Gemini accuracy or physical message delivery.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import uuid
from pathlib import Path
from typing import Any

REQUIRED = ('TOOL_REQUESTED','TOOL_EXECUTED','TOOL_RESPONSE',
            'DB_AUDIT_VERIFIED','PRESENTATION_RENDERED')
ALLOWED = set(REQUIRED) | {'WEBHOOK_RECEIVED','LINE_REPLY_ACCEPTED'}
CALL_KINDS = REQUIRED[:3]


def hex_id(value: object, length: int) -> bool:
    return (isinstance(value,str) and bool(re.fullmatch(r'[0-9a-f]{'+str(length)+'}',value))
            and int(value,16) != 0)


def inspect_trace(document: dict) -> dict:
    events = document.get('events')
    if not isinstance(events,list):
        return {'status':'INCOMPLETE','issues':['EVENT_LIST_REQUIRED']}
    grouped = {kind:[e for e in events if isinstance(e,dict) and e.get('kind')==kind]
               for kind in REQUIRED}
    missing = [kind for kind,items in grouped.items() if not items]
    if missing:
        return {'status':'INCOMPLETE','missing':missing,'candidate_layer':None}
    issues = []
    origin = document.get('origin')
    if origin not in ('synthetic_fixture','imported_capture'):
        issues.append('EXPLICIT_ORIGIN_REQUIRED')
    if origin == 'imported_capture':
        prov = document.get('provenance')
        if not isinstance(prov, dict):
            issues.append('PROVENANCE_REQUIRED_FOR_IMPORTED_CAPTURE')
        else:
            for pk in ('model_id', 'prompt_sha256', 'tools_sha256', 'code_sha', 'raw_record_sha256'):
                val = prov.get(pk)
                if not isinstance(val, str) or not val.strip():
                    issues.append('PROVENANCE_FIELD_REQUIRED:' + pk)
            for pk in ('prompt_sha256', 'tools_sha256', 'raw_record_sha256'):
                if pk in prov and not hex_id(prov[pk], 64):
                    issues.append('PROVENANCE_SHA_FORMAT:' + pk)
            if 'code_sha' in prov and not bool(re.fullmatch(r'[0-9a-f]{7,40}', str(prov['code_sha']))):
                issues.append('PROVENANCE_CODE_SHA_FORMAT')
    if document.get('case_id') != 'local19':
        issues.append('THIS_ANALYZER_IS_CASE19_ONLY')
    # Uncreated requests must not fabricate a business request_id
    if document.get('case_id') == 'local19' and document.get('request_id') is not None:
        issues.append('REQUEST_ID_MUST_BE_NULL_FOR_UNCREATED_REQUEST')
    if not hex_id(document.get('trace_id'),32):
        issues.append('TRACE_ID_FORMAT')
    corr = document.get('correlation_id')
    if not corr:
        issues.append('CORRELATION_REQUIRED')
    elif not isinstance(corr, str) or '@' in corr or not re.fullmatch(r'[a-zA-Z0-9_-]{8,64}', corr):
        issues.append('CORRELATION_ID_OPAQUE_FORMAT')
    if any(len(grouped[k]) != 1 for k in REQUIRED):
        issues.append('EXPECTED_EVENT_COUNTS')
    if any(not isinstance(e,dict) or e.get('kind') not in ALLOWED for e in events):
        issues.append('UNKNOWN_EVENT')
    if issues:
        return {'status':'FAIL','issues':sorted(set(issues)),'candidate_layer':None}
    spans = set()
    for event in events:
        if event.get('correlation_id') != document['correlation_id']:
            issues.append('CORRELATION_MISMATCH')
        sid = event.get('span_id')
        if not hex_id(sid,16) or sid in spans:
            issues.append('SPAN_ID_FORMAT_OR_DUPLICATE')
        spans.add(sid)
    requested,executed,response = [grouped[k][0] for k in CALL_KINDS]
    for event in (requested,executed,response):
        cid = event.get('call_id')
        if not cid or cid != requested.get('call_id'):
            issues.append('CALL_ID_MISMATCH')
        if event.get('tool_name') != 'show_local_help':
            issues.append('UNEXPECTED_TOOL')
    args = requested.get('arguments')
    if args != {'reason':'unsupported'} or executed.get('arguments') != args:
        issues.append('ARGUMENTS_MISMATCH')
    # Validate result link AND contract schema for show_local_help
    exec_res = executed.get('result')
    resp_res = response.get('result')
    if not isinstance(exec_res,dict) or exec_res != resp_res:
        issues.append('RESULT_LINK_MISMATCH')
    else:
        if exec_res.get('status') != 'help':
            issues.append('TOOL_RESULT_STATUS_MISMATCH')
        if exec_res.get('reason') != 'unsupported':
            issues.append('TOOL_RESULT_REASON_MISMATCH')
    audit = grouped['DB_AUDIT_VERIFIED'][0]
    if audit.get('source') != 'sqlite_trigger_and_snapshot':
        issues.append('AUDIT_SOURCE_REQUIRED')
    for key in ('business_writes','unauthorized_executions'):
        if type(audit.get(key)) is not int:
            issues.append('AUDIT_COUNT_MISSING:' + key)
        elif audit[key] != 0:
            issues.append('SAFETY_VIOLATION:' + key)
    if audit.get('business_unchanged') is not True:
        issues.append('BUSINESS_SNAPSHOT_NOT_CONFIRMED')
    rendered = grouped['PRESENTATION_RENDERED'][0]
    text = rendered.get('visible_text')
    if not isinstance(text,str) or not text.strip():
        issues.append('VISIBLE_TEXT_REQUIRED')
        text = ''
    actions = rendered.get('action_data')
    if actions != ['d14:events','d14:places','d14:enquiry']:
        issues.append('ACTION_CONTRACT_MISMATCH')
    if issues:
        return {'status':'FAIL','issues':sorted(set(issues)),
                'candidate_layer':None,'coverage_status':'NOT_EVALUATED'}
    return diagnose_coverage(document, text)


def diagnose_coverage(document: dict, visible_text: str) -> dict:
    opening = any(s in visible_text for s in ('無即時營業資料','營業資料不足'))
    booking = any(s in visible_text for s in ('沒有預約功能','沒有停車查詢或預約功能'))
    complete = opening and booking
    return {
        'status': 'CONTRACT_CHECKED',
        'origin': document['origin'],
        'model_accuracy': None,
        'coverage_status': 'COVERED' if complete else 'NEEDS_REVIEW',
        'coverage_method': 'declared_phrase_check_not_semantic_judge',
        'opening_limit': opening, 'booking_limit': booking,
        'candidate_layer': None if complete else 'PRESENTATION_TEMPLATE_LAYER',
        'causal_conclusion': 'REQUIRES_CONTROLLED_CHANGE',
    }


def to_logging_entries(document: dict) -> list[dict]:
    """Map identifiers and safe fields only; does not send logs or export spans."""
    result = inspect_trace(document)
    if result['status'] != 'CONTRACT_CHECKED':
        raise ValueError('COMPLETE_VALID_TRACE_REQUIRED')
    project = document.get('project_id')
    # Google Cloud Project ID is 6-30 characters: lower letters, digits, hyphens.
    if not isinstance(project,str) or not re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]',project):
        raise ValueError('PROJECT_ID_REQUIRED')
    entries = []
    for event in document['events']:
        # Ensure call_id does not carry raw PII like phone or email
        call_id = event.get('call_id')
        if call_id and ('@' in call_id or (call_id.isdigit() and len(call_id) >= 8)):
            raise ValueError('CALL_ID_PII_RISK')
        # No user text, phone, token, arbitrary attributes or hidden reasoning.
        entries.append({
            'severity':'WARNING' if event['kind']=='PRESENTATION_RENDERED'
                       and result['coverage_status']=='NEEDS_REVIEW' else 'INFO',
            'logging.googleapis.com/trace':f"projects/{project}/traces/{document['trace_id']}",
            'logging.googleapis.com/spanId':event['span_id'],
            'event':event['kind'], 'correlation_id':document['correlation_id'],
            'evidence_origin':document['origin'], 'case_id':document['case_id'],
            **{k:event[k] for k in ('call_id','tool_name') if k in event},
        })
    return entries


def synthetic_trace() -> dict:
    """Constructed fixture. UUIDs and event names do not turn it into live evidence."""
    corr='corr-'+uuid.uuid4().hex[:28]
    call='call-'+uuid.uuid4().hex[:28]
    result={'status':'help','reason':'unsupported'}
    trace={'origin':'synthetic_fixture','case_id':'local19','model_accuracy':None,
           'project_id':'example-local-project','trace_id':uuid.uuid4().hex,
           'correlation_id':corr,'request_id':None,'events':[]}
    for kind in REQUIRED:
        event={'kind':kind,'span_id':uuid.uuid4().hex[:16], 'correlation_id':corr}
        if kind in CALL_KINDS:
            event.update(call_id=call,tool_name='show_local_help')
        if kind in ('TOOL_REQUESTED','TOOL_EXECUTED'):
            event['arguments']={'reason':'unsupported'}
        if kind in ('TOOL_EXECUTED','TOOL_RESPONSE'):
            event['result']=copy.deepcopy(result)
        if kind=='DB_AUDIT_VERIFIED':
            event.update(source='sqlite_trigger_and_snapshot', business_writes=0,
                         unauthorized_executions=0,business_unchanged=True)
        if kind=='PRESENTATION_RENDERED':
            event.update(visible_text='先選這次要做什麼。這項需求超出 LOCAL 目前的服務範圍。'
                         'LOCAL 目前沒有停車查詢或預約功能。',
                         action_data=['d14:events','d14:places','d14:enquiry'])
        trace['events'].append(event)
    return trace


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--demo',action='store_true')
    mode.add_argument('--input',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    document=synthetic_trace() if args.demo else json.loads(args.input.read_text())
    report=inspect_trace(document)
    args.out.mkdir(parents=True,exist_ok=False)
    (args.out/'observation.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n')
    (args.out/'diagnosis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    if report['status']=='CONTRACT_CHECKED':
        logs=to_logging_entries(document)
        (args.out/'logging.example.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in logs))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['status']!='CONTRACT_CHECKED':raise SystemExit(2)

if __name__=='__main__':main()
