"""Small Day 13 presentation adapter; the original consent/write service is unchanged."""
from __future__ import annotations
from starlette.concurrency import run_in_threadpool
from examples.day12.main import Application
from examples.day12.inherit import SendArgs, StoreUnavailable, time_of, pending, rejected
from .messages import checked_cid, render_result, NOTICES, InvalidView

CARD_STATES = set(NOTICES) | {'request_created', 'already_created', 'existing_request', 'awaiting_confirmation'}


def read_bound_status(tasks, actor, cid: str):
    """Read this card's task, not whichever new task happens to be current.

    Reads are observations, not a transaction authorizing future writes. The original
    decide/create path rechecks current task and permissions at the actual operation.
    """
    checked_cid(cid)
    try:
        current = tasks.current(actor)
        if current['status'] != 'session_restored':
            return current
        if current['args']['confirmation_id'] != cid:
            return rejected('superseded')
        args = SendArgs(**current['args'])
        result = tasks.original.lookup(actor, args)
        if result['status'] == 'pending_verification' and result.get('observation') == 'not_found':
            offer = tasks.describe_offer(actor, args)
            if offer['status'] == 'awaiting_confirmation':
                if tasks.clock() >= time_of(offer['expires_at']):
                    result = rejected('expired')
                else:
                    result = {'status': 'awaiting_confirmation', 'args': args.values(),
                              'expires_at': offer['expires_at']}
            elif offer['status'] in ('cancelled', 'expired', 'content_changed', 'version_changed', 'not_authorized'):
                result = rejected(offer['status'])
        # If a new task arrived while reading, do not label its data as this old card.
        latest = tasks.current(actor)
        if latest['status'] != 'session_restored':
            return latest
        if latest['args']['confirmation_id'] != cid:
            return rejected('superseded')
        return result
    except StoreUnavailable:
        return pending('lookup_unavailable')


class FlexApplication(Application):
    """Reuse Day 12 authentication, event deduplication, task service and Reply sender."""
    async def route(self, actor, event):
        data = event.get('postback', {}).get('data', '') if event['type'] == 'postback' else ''
        text = event.get('message', {}).get('text', '')
        if data.startswith(('status:', 'text:')):
            verb, cid = data.split(':', 1)
            try:
                checked_cid(cid)
            except InvalidView:
                result = rejected('confirmation_not_found')
            else:
                result = await run_in_threadpool(read_bound_status, self.tasks, actor, cid)
            return {'messages': [render_result(result, text_only=verb == 'text', confirmation_id=cid
                                if result['status'] in ('pending_verification', 'already_confirmed') else None)],
                    'result': result}
        if data == 'text' or (not data and text in ('文字版', '目前任務文字版')):
            result = await run_in_threadpool(self.tasks.status, actor)
            return {'messages': [render_result(result, text_only=True)], 'result': result}
        # This executes the original decide/status/offer paths. We change presentation,
        # not the returned result or whether the task is authorized to create a row.
        plan = await super().route(actor, event)
        result = plan['result']
        if result.get('status') in CARD_STATES:
            cid = None
            if data.startswith(('confirm:', 'cancel:')):
                proposed = data.split(':', 1)[1]
                try:
                    cid = checked_cid(proposed)
                except InvalidView:
                    pass
            replacement = render_result(result, confirmation_id=cid,
                                        cancelled_after_creation=data.startswith('cancel:'))
            plan = {**plan, 'messages': [replacement] + plan['messages'][1:]}
        return plan
