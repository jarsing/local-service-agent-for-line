from dataclasses import replace
from .test_support import MemoryCase
from .engine import TurnTools
from .memory import PreferenceChanged
from .places import PlacesCatalog

class EngineTests(MemoryCase):
    def turn(self,actor=None,**kw): return TurnTools(self.memory,actor or self.actor,**kw)
    def test_today_does_not_save(self):
        t=self.turn();r=t.execute('search_local_places',{'area':'花壇鄉','dietary_type':'vegetarian'})
        self.assertEqual(r['preference_origin'],'this_turn');self.assertIsNone(self.memory.inspect(self.actor)['dietary_type'])
    def test_cross_session_applies_saved(self):
        self.save();t=self.turn(replace(self.actor,session_id='session-new'));r=t.execute('search_local_places',{'area':'花壇鄉'})
        self.assertEqual(r['query']['dietary_type'],'vegetarian');self.assertEqual(r['preference_origin'],'consented_memory')
        self.assertEqual(t.calls[0]['proposed_arguments']['dietary_type'],'')
    def test_current_explicit_preference_overrides_saved(self):
        self.save('vegan');r=self.turn().execute('search_local_places',{'area':'彰化市','dietary_type':'ovo_lacto'})
        self.assertEqual(r['query']['dietary_type'],'ovo_lacto');self.assertEqual(self.memory.inspect(self.actor)['dietary_type'],'vegan')
    def test_explicit_any_does_not_forget(self):
        self.save('vegan');r=self.turn().execute('search_local_places',{'dietary_type':'any'})
        self.assertEqual(r['query']['dietary_type'],'any');self.assertEqual(self.memory.inspect(self.actor)['dietary_type'],'vegan')
    def test_after_forget_no_hidden_filter(self):
        self.save();self.memory.forget(self.actor,'f');r=self.turn().execute('search_local_places',{'area':'花壇鄉'})
        self.assertEqual(r['query']['dietary_type'],'any');self.assertEqual(r['preference_origin'],'none')
    def test_proposal_tool_is_not_consent(self):
        r=self.turn().execute('propose_dietary_memory',{'dietary_type':'vegetarian'})
        self.assertFalse(r['stored']);self.assertEqual(self.memory.inspect(self.actor)['status'],'empty')
    def test_model_approved_flag_rejected(self):
        with self.assertRaises(ValueError): self.turn().execute('propose_dietary_memory',{'dietary_type':'vegan','approved':True})
    def test_owner_arg_rejected(self):
        with self.assertRaises(ValueError): self.turn().execute('search_local_places',{'owner':'someone'})
    def test_model_forget_only_proposes(self):
        self.save();self.turn().execute('request_memory_management',{'action':'forget'})
        self.assertEqual(self.memory.inspect(self.actor)['status'],'saved')
    def test_unknown_operation_refused(self):
        with self.assertRaises(ValueError): self.turn().execute('create_booking',{})
    def test_one_business_tool_bound(self):
        t=self.turn();t.execute('search_local_places',{})
        with self.assertRaises(ValueError):t.execute('search_local_places',{})
    def test_stale_before_tool_refused(self):
        self.save();t=self.turn();self.memory.forget(self.actor,'f')
        with self.assertRaises(PreferenceChanged): t.execute('search_local_places',{})
    def test_revoke_during_lookup_refused(self):
        self.save();memory=self.memory;actor=self.actor
        class RevokingCatalog(PlacesCatalog):
            def search(inner,*args,**kw):
                result=super().search(*args,**kw);memory.forget(actor,'concurrent-forget');return result
        with self.assertRaises(PreferenceChanged): self.turn(places=RevokingCatalog()).execute('search_local_places',{})
    def test_equal_results_still_have_different_tool_conditions(self):
        a=self.turn().execute('search_local_places',{'area':'花壇鄉'})
        self.save();b=self.turn().execute('search_local_places',{'area':'花壇鄉'})
        self.assertEqual(a['places'],b['places']);self.assertNotEqual(a['query'],b['query'])
    def test_no_previous_user_leak(self):
        self.save('vegan');r=self.turn(self.other).execute('search_local_places',{})
        self.assertEqual(r['query']['dietary_type'],'any')
