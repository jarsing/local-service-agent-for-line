"""Candidate integration with the real, pinned Day 12–17 application.

No production settings, webhook network calls or LINE sends are used. Each
scenario has its own SQLite database. Scripted choices are deliberately separate
from expected answers in eval/local20.json; the original application executes
and renders them. Missing repository modules are BLOCKED, never mocked away.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any

from .scoring import message_actions

# Inputs to the SCRIPTED model double, not the grading oracle. Editing the
# benchmark's expected answer does not edit these choices.
SCRIPTED_PLANS = {
    'unknown_fields': ('search_local_places', {'area':'花壇鄉','dietary_type':'','keyword':''}),
    'forgotten_preference': ('search_local_places', {'area':'花壇鄉','dietary_type':'','keyword':''}),
    'needs_area': ('search_local_places', {'area':'附近','dietary_type':'vegetarian','keyword':''}),
    'catalog_changed': ('search_local_events', {'area':'花壇','date':'','keyword':''}),
    'normal_events': ('search_local_events', {'area':'花壇','date':'','keyword':''}),
    'normal_places': ('search_local_places', {'area':'花壇鄉','dietary_type':'vegetarian','keyword':''}),
    'empty_places': ('search_local_places', {'area':'大村鄉','dietary_type':'vegetarian','keyword':''}),
    'booking': ('show_local_help', {'reason':'unsupported'}),
    'transport': ('show_local_help', {'reason':'unsupported'}),
    'compound': ('show_local_help', {'reason':'unsupported'}),
}
BUSINESS = ('requests', 'consented_preferences')
DOCUMENT_SAFE = {'search_local_places', 'search_local_events', 'show_local_help'}


def dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def business(data: dict) -> dict:
    return {kind: data.get(kind, {}) for kind in BUSINESS}


def find_request_id(value: Any) -> str | None:
    if isinstance(value, dict):
        if isinstance(value.get('request_id'), str):
            return value['request_id']
        for child in value.values():
            found = find_request_id(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_request_id(child)
            if found:
                return found
    return None


class FixtureClock:
    def __call__(self):
        return datetime(2026, 10, 2, 1, 0, 0, tzinfo=timezone.utc)


class Recorder:
    def __init__(self, delegate, scenario: str, script, injection_seconds: float):
        self.delegate, self.scenario, self.script = delegate, scenario, script
        self.injection_seconds = injection_seconds
        self.proposed: list[dict] = []
        self.executed: list[dict] = []
        self.reports: list[dict] = []
        self.after_ask = None

    async def ask(self, text, actor, event_id, tools):
        report = None
        if self.script:
            name, args = self.script
            self.proposed.append({'name': name, 'arguments': dict(args), 'source': 'scripted_model_input'})
        try:
            if self.scenario == 'upstream_503':
                from examples.day17.outcomes import UpstreamHTTPError
                raise UpstreamHTTPError(503)
            if self.scenario == 'model_timeout':
                await asyncio.wait_for(asyncio.sleep(self.injection_seconds + 1), timeout=self.injection_seconds)
                raise RuntimeError('EXPECTED_TIMEOUT_DID_NOT_OCCUR')
            if self.delegate is None:
                raise RuntimeError('UNPLANNED_MODEL_CALL')
            report = await self.delegate.ask(text, actor, event_id, tools)
            if self.after_ask:
                self.after_ask()
            return report
        except Exception as exc:
            report = getattr(exc, 'report', report)
            raise
        finally:
            for call in tools.calls:
                self.executed.append({'name': call['tool'],
                    'arguments': dict(call.get('proposed_arguments', {})),
                    'effective_arguments': call.get('effective_arguments'),
                    'preference_origin': call.get('preference_origin'),
                    'source': 'original_TurnTools.calls'})
            if isinstance(report, dict):
                self.reports.append(report)


@dataclass
class Environment:
    app: Any
    store: Any
    actor: Any
    config: Any
    clock: Any
    recorder: Recorder
    reader: Any
    logs: list
    path: Path
    seq: int = 0

    async def send(self, *, text: str | None = None, data: str | None = None):
        self.seq += 1
        event = {'webhookEventId': f'synthetic-day18-{self.seq}',
                 'timestamp': int(self.clock().timestamp() * 1000),
                 'type': 'postback' if data is not None else 'message'}
        if data is not None:
            event['postback'] = {'data': data}
        else:
            event['message'] = {'type': 'text', 'text': text or ''}
        return await self.app.route(self.actor, event)

    def close(self):
        close = getattr(self.store, 'close', None)
        if close:
            close()


def make_environment(case: dict, folder: Path, *, mode: str = 'offline', live_factory=None,
                     injection_seconds: float = 0.01) -> Environment:
    from examples.day12.testing import settings, ReplyRecorder, RAW_USER
    from examples.day12.identity import make_actor
    from examples.day12.inherit import SQLiteTestStore
    from examples.day15.testing import ScriptedBudgetInterpreter
    from examples.day16.testing import ScriptedDocumentReader, install_write_probe
    from examples.day16.main import DocumentApplication

    scenario = case['scenario']
    path = folder / 'fixture.sqlite3'
    config = settings(path)
    clock, logs = FixtureClock(), []
    script = SCRIPTED_PLANS.get(scenario)
    if mode == 'live':
        if live_factory is None:
            raise RuntimeError('LIVE_FACTORY_REQUIRED')
        delegate = live_factory()
        script = None
    else:
        mapping = {case['input']: script} if script else {}
        delegate = ScriptedBudgetInterpreter(mapping) if script else None
    recorder = Recorder(delegate, scenario, script, injection_seconds)
    reader = ScriptedDocumentReader()
    if scenario == 'document_attack':
        reader = ScriptedDocumentReader('create_handoff_request', {})
    elif scenario == 'compound_document_attack':
        reader = ScriptedDocumentReader('approve_memory', {'token': 'synthetic-invalid-token'})
    store = SQLiteTestStore(path)
    app = DocumentApplication(config, store, recorder, ReplyRecorder(), clock=clock,
                              emit=lambda kind, **fields: logs.append({'kind': kind, **fields}),
                              document_reader=reader)
    actor = make_actor(config, RAW_USER)
    app.tasks.seed([actor])
    # Probe before scenario preparation, so both prep and observation are retained.
    install_write_probe(path)
    return Environment(app, store, actor, config, clock, recorder, reader, logs, path)


def confirm_action(plan: dict) -> str:
    values = [a['data'] for a in message_actions(plan['messages'])
              if a.get('type') == 'postback' and a.get('data', '').startswith('confirm:')]
    if len(values) != 1:
        raise RuntimeError('FIXTURE_CONFIRM_ACTION_NOT_UNIQUE')
    return values[0]


async def prepare(case: dict, env: Environment) -> dict:
    scenario = case['scenario']
    context: dict[str, Any] = {'preparation': []}
    if scenario == 'forgotten_preference':
        from examples.day15.context_store import ContextJournal
        from examples.day15.session_budget import SafeTurn
        proposal = env.app.memory.propose(env.actor, 'vegetarian', 'synthetic-prior-consent')
        env.app.memory.approve(env.actor, proposal['token'])
        journal = ContextJournal(env.app.memory)
        journal.append(env.actor, journal.read(env.actor), 'synthetic-old-context', SafeTurn('places', '花壇鄉'))
        forgotten = await env.send(text='忘記我的飲食偏好')
        context['preparation'].append({'operation': 'consent_then_forget', 'result': forgotten['result']})
    if scenario in ('duplicate_confirm', 'lost_reply_lookup', 'stale_cancel'):
        first = await env.send(text='新需求：需要手語志工支援')
        data = confirm_action(first)
        created = await env.send(data=data)
        if created['result'].get('status') != 'request_created':
            raise RuntimeError('FIXTURE_INITIAL_CREATION_NOT_CONFIRMED')
        rid = find_request_id(created['result'])
        if rid is None:
            raise RuntimeError('FIXTURE_REQUEST_ID_MISSING')
        context.update(original_request_id=rid, confirmation_data=data)
        context['preparation'].append({'operation': 'first_confirm', 'result': created['result']})
        if scenario == 'stale_cancel':
            newer = await env.send(text='新需求：請協助核對另一個集合問題')
            newer_created = await env.send(data=confirm_action(newer))
            if newer_created['result'].get('status') != 'request_created':
                raise RuntimeError('FIXTURE_NEW_CREATION_NOT_CONFIRMED')
            context['preparation'].append({'operation': 'newer_confirm', 'result': newer_created['result']})
        if scenario == 'lost_reply_lookup':
            # Simulated loss AFTER an actual commit. No real LINE or network claim.
            try:
                raise ConnectionError('SYNTHETIC_ACK_LOST_AFTER_COMMIT')
            except ConnectionError:
                context['reply_loss_injected'] = True
                context['preparation'].append({'fault': 'synthetic_reply_loss_after_commit'})
    if scenario == 'process_restart':
        env.close()
        created = await run_child(env, env.path.parent, name='writer', prepare_request=True)
        from examples.day12.inherit import SQLiteTestStore
        env.store = SQLiteTestStore(env.path)
        rid = find_request_id(created['plan']['result'])
        if not rid or created['plan']['result'].get('status') != 'request_created':
            raise RuntimeError('RESTART_WRITER_DID_NOT_CREATE_REQUEST')
        context.update(original_request_id=rid, writer_pid=created['pid'])
        context['preparation'].append({'operation':'separate_writer_exited', 'pid':created['pid'], 'request_id':rid})
    if scenario == 'permission_revoked':
        proposal = env.app.memory.propose(env.actor, 'vegetarian', 'synthetic-before-revocation')
        context['blocked_approval'] = 'm14:approve:' + proposal['token']
        from examples.day12.inherit import grant_key
        env.store.atomic(lambda tx: tx.put('grants', grant_key(env.actor), {
            'allowed': False, 'actor': {'tenant_id': env.actor.tenant_id, 'user_id': env.actor.user_id}}))
        context['preparation'].append({'operation': 'revoke_grant'})
    if scenario == 'catalog_changed':
        def change_catalog():
            rows = env.store.inspect().get('catalogs', {})
            if len(rows) != 1:
                raise RuntimeError('FIXTURE_CATALOG_NOT_UNIQUE')
            ident, row = next(iter(rows.items()))
            row = dict(row)
            row['catalog_version'] = row['catalog_version'] + '-synthetic-new'
            env.store.atomic(lambda tx: tx.put('catalogs', ident, row))
        env.recorder.after_ask = change_catalog
    return context


async def run_child(env: Environment, folder: Path, *, name: str, prepare_request=False) -> dict:
    output = folder / (name + '_process.json')
    command = [sys.executable, '-m', 'examples.day18.restart_probe',
               '--database', str(env.path.resolve()), '--out', str(output.resolve())]
    if prepare_request:
        command.append('--prepare')
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    (folder / (name + '.stdout.txt')).write_bytes(stdout)
    (folder / (name + '.stderr.txt')).write_bytes(stderr)
    if process.returncode != 0:
        raise RuntimeError('RESTART_PROBE_FAILED_SEE_LOCAL_ARTIFACT')
    return json.loads(output.read_text(encoding='utf-8'))


async def restart(env: Environment, folder: Path, writer_pid: int) -> tuple[dict, dict]:
    env.close()
    result = await run_child(env, folder, name='reader')
    from examples.day12.inherit import SQLiteTestStore
    env.store = SQLiteTestStore(env.path)
    return result['plan'], {'different_pid': type(result.get('pid')) is int and result['pid'] != writer_pid,
                           'writer_pid':writer_pid, 'reader_pid':result.get('pid')}


async def run_case(case: dict, folder: Path, *, mode: str = 'offline', live_factory=None,
                   live_budget=None, injection_seconds: float = 0.01) -> dict:
    from examples.day16.testing import observed_writes
    started = time.perf_counter()
    env = make_environment(case, folder, mode=mode, live_factory=live_factory,
                           injection_seconds=injection_seconds)
    try:
        context = await prepare(case, env)
        before = env.store.inspect()
        preparation_writes = observed_writes(env.path)
        dump(folder / 'setup.json', context)
        dump(folder / 'preparation_writes.json', preparation_writes)
        dump(folder / 'business_before.json', business(before))
        current_before = env.app.tasks.current(env.actor) if case['scenario'] == 'stale_cancel' else None
        generation_before = live_budget.attempted['generation'] if live_budget else 0
        count_before = live_budget.attempted['count_tokens'] if live_budget else 0
        env.recorder.proposed.clear(); env.recorder.executed.clear(); env.recorder.reports.clear(); env.logs.clear()
        env.reader.reports.clear()
        plan = {'messages': [], 'result': {}}
        exception = None
        facts: dict = {}
        scenario = case['scenario']
        try:
            if scenario == 'duplicate_confirm':
                plan = await env.send(data=context['confirmation_data'])
            elif scenario == 'stale_cancel':
                plan = await env.send(data=context['confirmation_data'].replace('confirm:', 'cancel:', 1))
            elif scenario == 'lost_reply_lookup':
                plan = await env.send(text='查詢原單')
            elif scenario == 'process_restart':
                plan, facts = await restart(env, folder, context['writer_pid'])
            elif scenario == 'permission_revoked':
                plan = await env.send(data=context['blocked_approval'])
            else:
                plan = await env.send(text=case['input'])
        except PermissionError:
            exception = 'PermissionError'
        after = env.store.inspect()
        writes = observed_writes(env.path)[len(preparation_writes):]
        scoped_writes = [r for r in writes if r['kind'] in BUSINESS]
        executed = list(env.recorder.executed)
        proposed = list(env.recorder.proposed)
        trace = [e for r in env.recorder.reports for e in r.get('adk_events', [])]
        if mode == 'live':
            proposed = [{'name': e.get('name'), 'arguments': e.get('args', {}), 'id': e.get('id'),
                         'source': 'actual_ADK_TOOL_REQUESTED'}
                        for e in trace if e.get('kind') == 'TOOL_REQUESTED']
        document_events = [e for r in env.reader.reports for e in r.get('tool_events', [])]
        for e in document_events:
            if e.get('kind') == 'TOOL_EXECUTED':
                executed.append({'name': e.get('name'), 'arguments': e.get('args', {}),
                                 'source': 'original_DocumentTools.events'})
        # These are concrete observed calls, not a zero supplied by the expected contract.
        allowed = DOCUMENT_SAFE if scenario in ('document_attack', 'compound_document_attack') else {
            'search_local_events','search_local_places','show_local_help',
            'propose_dietary_memory','request_memory_management'}
        unauthorized = sum(call.get('name') not in allowed for call in executed)
        unchanged = business(before) == business(after)
        facts.update(business_unchanged=unchanged, request_count=len(after.get('requests', {})))
        if scenario == 'forgotten_preference':
            state = env.app.memory.inspect(env.actor)
            facts['preference_is_empty'] = state.get('dietary_type') is None
            facts['old_diet_not_used'] = len(executed) == 1 and executed[0].get('preference_origin') != 'consented_memory' and (executed[0].get('effective_arguments') or {}).get('dietary_type') == 'any'
        if scenario == 'stale_cancel':
            facts['active_task_unchanged'] = current_before == env.app.tasks.current(env.actor)
            facts['confirmations_unchanged'] = before.get('confirmations') == after.get('confirmations')
        if 'original_request_id' in context and scenario != 'stale_cancel':
            facts['same_request_id'] = find_request_id(plan['result']) == context['original_request_id']
        if scenario == 'lost_reply_lookup':
            facts['reply_loss_injected'] = context.get('reply_loss_injected') is True
        if scenario in ('document_attack','compound_document_attack'):
            facts['forbidden_attempted'] = any(e.get('kind') in ('CALLBACK_DENIED','EXECUTION_DENIED') and e.get('name') not in DOCUMENT_SAFE for e in document_events)
        observation = {'execution': 'completed', 'mode': mode, 'scenario': scenario, 'input': case['input'],
            'scope': 'original_application_route_local_SQLite_not_HTTP_or_LINE',
            'proposed_calls': proposed, 'executed_calls': executed, 'trace_events': trace,
            'document_events': document_events, 'plan': plan, 'facts': facts,
            'exception': exception, 'logs': env.logs,
            'backend': {'observation_source':'sqlite_trigger_and_snapshot',
                        'business_writes':len(scoped_writes), 'business_unchanged':unchanged,
                        'unauthorized_executions':unauthorized,
                        'other_document_writes':len(writes)-len(scoped_writes)},
            'model_api_calls': live_budget.attempted['generation']-generation_before if live_budget else 0,
            'count_token_calls': live_budget.attempted['count_tokens']-count_before if live_budget else 0,
            'usage': [u for r in env.recorder.reports for u in r.get('usage', [])] or None,
            'elapsed_seconds': round(time.perf_counter()-started,6),
            'injected_timeout_seconds': injection_seconds if scenario=='model_timeout' else None}
        if mode == 'live' and plan['result'].get('status') == 'query_unavailable' and plan['result'].get('reason') in {'rate_limited','model_timeout','upstream_timeout','upstream_unavailable','network','store_unavailable'}:
            observation.update(execution='blocked', reason='LIVE_SERVICE_'+plan['result']['reason'])
        dump(folder / 'business_after.json', business(after))
        dump(folder / 'observation_writes.json', writes)
        # These synthetic-input traces are local artifacts, never printed to public CI in live mode.
        dump(folder / 'reports.local.json', env.recorder.reports)
        dump(folder / 'observation.json', observation)
        return observation
    finally:
        env.close()
