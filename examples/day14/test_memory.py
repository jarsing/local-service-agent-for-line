from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from dataclasses import replace
import json
from .test_support import MemoryCase
from .memory import COLLECTION, owner_key, BadToken, PreferenceChanged, PreferenceMemory

class MemoryTests(MemoryCase):
    def test_proposal_never_persists_value(self):
        p=self.memory.propose(self.actor,'vegetarian','propose')
        self.assertNotIn(COLLECTION,self.store.inspect());self.assertEqual(self.memory.inspect(self.actor)['status'],'empty')
        self.assertLessEqual(len('m14:approve:'+p['token']),300)
    def test_explicit_approval_persists_one_enum(self):
        _,r=self.save();row=self.store.inspect()[COLLECTION][owner_key(self.actor)]
        self.assertEqual(row['dietary_type'],'vegetarian');self.assertEqual(r['status'],'memory_saved')
        self.assertNotIn('session_id',json.dumps(row));self.assertNotIn('request_text',row)
    def test_cross_session_identity(self):
        self.save();other_session=replace(self.actor,session_id='NEW_SESSION')
        self.assertEqual(self.memory.inspect(other_session)['dietary_type'],'vegetarian')
    def test_other_user_isolated(self):
        self.save();self.assertIsNone(self.memory.inspect(self.other)['dietary_type'])
    def test_tenant_isolated(self):
        self.save();actor=replace(self.actor,tenant_id='other-tenant');self.grant(actor,True)
        self.assertIsNone(self.memory.inspect(actor)['dietary_type'])
    def test_wrong_owner_token(self):
        p=self.memory.propose(self.actor,'vegan','x')
        with self.assertRaises(BadToken): self.memory.approve(self.other,p['token'])
    def test_tampered_token(self):
        p=self.memory.propose(self.actor,'vegan','x');token=p['token'];token=('A' if token[0]!='A' else 'B')+token[1:]
        with self.assertRaises(BadToken): self.memory.approve(self.actor,token)
    def test_unknown_enum_refused(self):
        for v in ('母親糖尿病',{},'','any'):
            with self.subTest(v=v),self.assertRaises(ValueError): self.memory.propose(self.actor,v,'x')
    def test_expiry_does_not_refresh(self):
        p=self.memory.propose(self.actor,'vegan','x');self.clock.now+=timedelta(seconds=300)
        self.assertEqual(self.memory.approve(self.actor,p['token'])['status'],'expired_memory_card')
        self.assertNotIn(COLLECTION,self.store.inspect())
    def test_repeated_approval_no_second_write(self):
        p,r=self.save();self.assertEqual(self.memory.approve(self.actor,p['token'])['status'],'already_applied')
        self.assertEqual(self.memory.inspect(self.actor)['revision'],r['revision'])
    def test_concurrent_same_card(self):
        p=self.memory.propose(self.actor,'vegan','same')
        with ThreadPoolExecutor(2) as pool: results=list(pool.map(lambda _:self.memory.approve(self.actor,p['token']),range(2)))
        self.assertEqual(sorted(x['status'] for x in results),['already_applied','memory_saved'])
        self.assertEqual(self.memory.inspect(self.actor)['revision'],1)
    def test_update_still_requires_consent(self):
        self.save();p=self.memory.propose(self.actor,'ovo_lacto','update')
        self.assertEqual(self.memory.inspect(self.actor)['dietary_type'],'vegetarian')
        self.memory.approve(self.actor,p['token']);self.assertEqual(self.memory.inspect(self.actor)['dietary_type'],'ovo_lacto')
    def test_cancel_update_keeps_original(self):
        self.save();p=self.memory.propose(self.actor,'vegan','update');self.memory.cancel(self.actor,p['token'])
        self.assertEqual(self.memory.inspect(self.actor)['dietary_type'],'vegetarian')
        self.assertEqual(self.memory.approve(self.actor,p['token'])['status'],'stale_memory_card')
    def test_two_different_pending_cards_first_wins(self):
        p=self.memory.propose(self.actor,'vegan','A');q=self.memory.propose(self.actor,'ovo_lacto','B')
        self.memory.approve(self.actor,p['token'])
        self.assertEqual(self.memory.approve(self.actor,q['token'])['status'],'stale_memory_card')
    def test_forget_strips_value_and_timestamp(self):
        self.save('vegan');self.memory.forget(self.actor,'f')
        row=self.store.inspect()[COLLECTION][owner_key(self.actor)]
        self.assertNotIn('dietary_type',row);self.assertNotIn('consented_at',row)
        self.assertNotIn('vegan',json.dumps(row));self.assertEqual(self.memory.inspect(self.actor)['status'],'empty')
    def test_old_confirm_cannot_resurrect_after_forget(self):
        p,_=self.save();self.memory.forget(self.actor,'f')
        self.assertEqual(self.memory.approve(self.actor,p['token'])['status'],'stale_memory_card')
    def test_pending_card_invalidated_by_forget(self):
        p=self.memory.propose(self.actor,'vegan','x');self.memory.forget(self.actor,'f')
        self.assertEqual(self.memory.approve(self.actor,p['token'])['status'],'stale_memory_card')
    def test_forget_replay_is_idempotent(self):
        self.save();a=self.memory.forget(self.actor,'same-event');b=self.memory.forget(self.actor,'same-event')
        self.assertEqual(a,b)
    def test_reconsent_new_card_is_allowed(self):
        self.save();self.memory.forget(self.actor,'f');_,r=self.save('lacto','new-explicit-intent')
        self.assertEqual(r['dietary_type'],'lacto')
    def test_authorization_rechecked_for_reads_and_writes(self):
        p,_=self.save();self.grant(self.actor,False)
        for f in (lambda:self.memory.inspect(self.actor),lambda:self.memory.approve(self.actor,p['token']),lambda:self.memory.forget(self.actor,'f')):
            with self.assertRaises(PermissionError): f()
    def test_cached_snapshot_rejected_after_update(self):
        self.save();v=self.memory.inspect(self.actor)['revision'];self.save('ovo_lacto','change')
        with self.assertRaises(PreferenceChanged): self.memory.assert_revision(self.actor,v)
    def test_fresh_instance_reads_persisted_state(self):
        self.save();fresh=PreferenceMemory(self.store,'synthetic-secret-'+'a'*32,clock=self.clock)
        self.assertEqual(fresh.inspect(self.actor)['dietary_type'],'vegetarian')
    def test_signed_forget_proposal_needs_click(self):
        self.save();p=self.memory.propose(self.actor,'','f',operation='forget')
        self.assertEqual(self.memory.inspect(self.actor)['status'],'saved')
        self.memory.approve(self.actor,p['token']);self.assertEqual(self.memory.inspect(self.actor)['status'],'empty')

    def test_same_event_different_proposal_value_cannot_claim_original_result(self):
        a=self.memory.propose(self.actor,'vegetarian','collision')
        b=self.memory.propose(self.actor,'vegan','collision')
        self.assertNotEqual(a['token'],b['token'])
        self.memory.approve(self.actor,a['token'])
        self.assertEqual(self.memory.approve(self.actor,b['token'])['status'],'stale_memory_card')
