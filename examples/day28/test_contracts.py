"""Synthetic contract tests. Not Firestore, LINE, or production authentication."""
import copy
import unittest
from claim_contract import (ContractError, VerifiedVolunteer, scope_key,
                            claim_in_tx)
from health_example import reproduce


class MemoryTx:
    """No concurrency emulation: verifies read-before-write and value contracts."""
    def __init__(self, docs):
        self.docs = copy.deepcopy(docs)
        self.writes = []
    def get(self, kind, ident):
        if self.writes:
            raise AssertionError('READ_AFTER_WRITE')
        return copy.deepcopy(self.docs.get((kind, ident)))
    def put(self, kind, ident, value):
        self.writes.append((kind, ident))
        self.docs[kind, ident] = copy.deepcopy(value)


class ClaimContracts(unittest.TestCase):
    def setUp(self):
        self.actor = VerifiedVolunteer('test-tenant', 'volunteer-one')
        self.op = scope_key('synthetic-operation')
        self.rid = 'SYNTHETIC-REQUEST-DO-NOT-TREAT-AS-LIVE'
        owner = {'tenant_id': 'test-tenant', 'user_id': 'test-owner', 'session_id': 'test-session'}
        args = {'request_text': '合成服務詢問', 'event_id': 'test-event'}
        self.row = {'request_id': self.rid, 'operation_id': self.op,
                    'actor': owner, 'args': args, 'payload_hash': scope_key('synthetic-payload'),
                    'request_text': args['request_text'], 'event_id': args['event_id'],
                    'service_id': 'local_demo_service_desk',
                    'status': 'pending_human_review', 'human_claimed': False,
                    'claim_version': 1, 'claimed_by': None}
        self.binding = {k: copy.deepcopy(self.row[k]) for k in ('operation_id','actor','args','payload_hash')}
        self.grant_key = scope_key('test-tenant', 'volunteer-one', 'local_demo_service_desk')
        self.control_key = scope_key('test-tenant', 'local_demo_service_desk')
        self.docs = {('requests', self.op): self.row, ('bindings', self.op): self.binding,
                     ('volunteer_grants', self.grant_key):
                        {'allowed': True, 'role': 'volunteer', 'tenant_id': 'test-tenant',
                         'user_id': 'volunteer-one', 'service_id': 'local_demo_service_desk'},
                     ('service_controls', self.control_key):
                        {'tenant_id':'test-tenant','service_id':'local_demo_service_desk','mode':'SERVING'}}
    def run_claim(self, version=1, rid=None):
        tx=MemoryTx(self.docs)
        return tx, claim_in_tx(tx,self.actor,self.op,rid or self.rid,version)
    def reject(self, reason, exc=ContractError):
        tx=MemoryTx(self.docs)
        with self.assertRaisesRegex(exc,reason):
            claim_in_tx(tx,self.actor,self.op,self.rid,1)
        self.assertEqual(tx.writes,[])
    def test_accepted_preserves_id_and_owner(self):
        tx,result=self.run_claim()
        self.assertEqual((result['request_id'],result['claim_version'],result['status']),
                         (self.rid,2,'human_claimed'))
        self.assertEqual(result['actor'],self.row['actor'])
        self.assertEqual(tx.writes,[('requests',self.op)])
    def test_same_volunteer_retry_no_write(self):
        _,result=self.run_claim();self.docs['requests',self.op]=result
        tx,again=self.run_claim()
        self.assertEqual(again,result);self.assertEqual(tx.writes,[])
    def test_other_claimant_rejected(self):
        self.row.update(status='human_claimed',human_claimed=True,claimed_by='other',claim_version=2)
        self.reject('ALREADY_CLAIMED')
    def test_paused_rejected(self):
        self.docs['service_controls',self.control_key]['mode']='PAUSED'
        self.reject('SERVICE_PAUSED_OR_UNCONFIGURED')
    def test_missing_control_rejected(self):
        self.docs.pop(('service_controls',self.control_key))
        self.reject('SERVICE_PAUSED_OR_UNCONFIGURED')
    def test_missing_grant_rejected(self):
        self.docs.pop(('volunteer_grants',self.grant_key))
        self.reject('VOLUNTEER_DENIED',PermissionError)
    def test_disabled_grant_rejected(self):
        self.docs['volunteer_grants',self.grant_key]['allowed']=False
        self.reject('VOLUNTEER_DENIED',PermissionError)
    def test_grant_service_scope_rejected(self):
        self.docs['volunteer_grants',self.grant_key]['service_id']='wrong-service'
        self.reject('VOLUNTEER_DENIED',PermissionError)
    def test_stale_version_rejected(self):
        self.row['claim_version']=2;self.reject('STALE_CLAIM_VERSION')
    def test_missing_version_requires_migration(self):
        self.row.pop('claim_version');self.reject('SCHEMA_MIGRATION_REQUIRED')
    def test_boolean_not_integer_version(self):
        self.row['claim_version']=True;self.reject('SCHEMA_MIGRATION_REQUIRED')
    def test_boolean_input_version_rejected(self):
        with self.assertRaisesRegex(ContractError,'INVALID_CLAIM_VERSION'):
            self.run_claim(version=True)
    def test_inconsistent_claim_state_rejected(self):
        self.row['human_claimed']=True;self.reject('INVALID_STATE')
    def test_binding_change_rejected(self):
        self.row['payload_hash']='changed';self.reject('BINDING_MISMATCH')
    def test_request_id_not_document_key(self):
        tx=MemoryTx(self.docs)
        with self.assertRaisesRegex(ContractError,'INVALID_OPERATION_ID'):
            claim_in_tx(tx,self.actor,self.rid,self.rid,1)
        self.assertEqual(tx.writes,[])
    def test_cross_tenant_rejected(self):
        self.row['actor']['tenant_id']='other';self.binding['actor']['tenant_id']='other'
        self.reject('TENANT_DENIED',PermissionError)
    def test_false_request_id_rejected(self):
        with self.assertRaisesRegex(ContractError,'REQUEST_ID_MISMATCH'):
            self.run_claim(rid='SYNTHETIC-OTHER-REQUEST')


class HealthContracts(unittest.TestCase):
    def test_wrong_export_is_404(self):
        self.assertEqual(reproduce()['wrong_export_health'],404)
    def test_correct_export_is_200(self):
        self.assertEqual(reproduce()['correct_export_health'],200)
    def test_mount_path_is_distinct(self):
        r=reproduce()
        self.assertEqual((r['mounted_root_health'],r['mounted_prefixed_health']),(404,200))
    def test_synthetic_scope_kept(self):
        r=reproduce()
        self.assertEqual(r['production_root_cause'],'UNCONFIRMED')
        self.assertEqual(r['external_calls'],0)


if __name__ == '__main__':
    unittest.main()
