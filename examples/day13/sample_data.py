"""Synthetic renderer inputs only. These are not author, LINE or Firestore results."""
from copy import deepcopy

ARGS = {'confirmation_id': 'synthetic_confirmation_001', 'request_text': '需要手語志工支援',
        'idempotency_key': 'synthetic_send_key', 'event_id': 'synthetic_event'}
OFFER = {'status': 'awaiting_confirmation', 'args': ARGS,
         'expires_at': '2026-09-27T01:05:00+00:00'}
ROW = {'request_id': 'req-SYNTHETIC-001', 'request_text': ARGS['request_text'], 'args': ARGS,
       'status': 'pending_human_review', 'human_claimed': False,
       'created_at': '2026-09-27T01:01:00+00:00'}
RECEIPT = {'status': 'request_created', 'request_id': ROW['request_id'], 'request': ROW}

def examples():
    return deepcopy({'confirmation': OFFER, 'receipt': RECEIPT,
                     'pending': {'status': 'pending_verification'},
                     'expired': {'status': 'expired'}, 'cancelled': {'status': 'cancelled'},
                     'superseded': {'status': 'superseded'}})
