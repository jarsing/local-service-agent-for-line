"""合成軌跡驗證器測試。不是實際 ADK 事件，也不是 Gemini 結果。"""
from copy import deepcopy
import unittest
from .trace_contract import verify_triplet

class TraceContractTests(unittest.TestCase):
    def triple(self):
        result={'status':'places_result','places':[{'place_id':'SYNTHETIC-P1'}]}
        q={'id':'SYNTHETIC-CALL-A','name':'search_local_places','args':{'area':'花壇鄉'}}
        x={'id':q['id'],'name':q['name'],'args':{'area':'花壇鄉','dietary_type':'','keyword':''},'result':deepcopy(result)}
        r={'id':q['id'],'name':q['name'],'result':deepcopy(result)}
        return [q],[x],[r]
    def test_exact_triplet_accepted(self):
        self.assertTrue(verify_triplet(*self.triple())['trace_linked'])
    def test_missing_execution_rejected(self):
        q,x,r=self.triple()
        with self.assertRaises(RuntimeError):verify_triplet(q,[],r)
    def test_multiple_requests_rejected(self):
        q,x,r=self.triple()
        with self.assertRaises(RuntimeError):verify_triplet(q+q,x,r)
    def test_mismatched_request_id_rejected(self):
        q,x,r=self.triple();q[0]['id']='SYNTHETIC-OTHER'
        with self.assertRaises(RuntimeError):verify_triplet(q,x,r)
    def test_missing_execution_id_rejected(self):
        q,x,r=self.triple();x[0]['id']=None
        with self.assertRaises(RuntimeError):verify_triplet(q,x,r)
    def test_changed_response_result_rejected(self):
        q,x,r=self.triple();r[0]['result']['status']='unearned_success'
        with self.assertRaises(RuntimeError):verify_triplet(q,x,r)
    def test_changed_execution_parameters_rejected(self):
        q,x,r=self.triple();x[0]['args']['dietary_type']='vegan'
        with self.assertRaises(RuntimeError):verify_triplet(q,x,r)
    def test_injected_owner_rejected(self):
        q,x,r=self.triple();q[0]['args']['owner']='another-person'
        with self.assertRaises(RuntimeError):verify_triplet(q,x,r)
    def test_injected_approval_rejected(self):
        q,x,r=self.triple();q[0]['args']['approved']=True
        with self.assertRaises(RuntimeError):verify_triplet(q,x,r)
    def test_unknown_tool_rejected(self):
        q,x,r=self.triple()
        for e in (q[0],x[0],r[0]):e['name']='direct_save_preference'
        with self.assertRaises(RuntimeError):verify_triplet(q,x,r)
    def test_plain_text_result_is_not_trace(self):
        with self.assertRaises(RuntimeError):verify_triplet([],[],[])
    def test_response_tool_name_must_match(self):
        q,x,r=self.triple();r[0]['name']='show_local_help'
        with self.assertRaises(RuntimeError):verify_triplet(q,x,r)

    def test_same_final_filter_cannot_hide_wrong_model_argument(self):
        from .trace_contract import check_development_case
        case={'tool':'search_local_places','diet_argument':'','effective_filter':'vegetarian'}
        wrong=[{'tool':case['tool'],'proposed_arguments':{'dietary_type':'vegetarian'},
                'effective_arguments':{'dietary_type':'vegetarian'}}]
        with self.assertRaisesRegex(AssertionError,'WRONG_PROPOSED_DIET'):
            check_development_case(case,wrong)
    def test_empty_argument_with_server_filter_is_accepted(self):
        from .trace_contract import check_development_case
        case={'tool':'search_local_places','diet_argument':'','effective_filter':'vegetarian'}
        event={'tool':case['tool'],'proposed_arguments':{'dietary_type':''},
               'effective_arguments':{'dietary_type':'vegetarian'}}
        check_development_case(case,[event])
    def test_wrong_effective_filter_is_rejected(self):
        from .trace_contract import check_development_case
        case={'tool':'search_local_places','diet_argument':'','effective_filter':'any'}
        event={'tool':case['tool'],'proposed_arguments':{'dietary_type':''},
               'effective_arguments':{'dietary_type':'vegan'}}
        with self.assertRaisesRegex(AssertionError,'WRONG_EFFECTIVE_FILTER'):
            check_development_case(case,[event])
    def test_proposal_type_is_checked_before_synthetic_confirmation(self):
        from .trace_contract import check_development_case
        case={'tool':'propose_dietary_memory','diet_argument':'ovo_lacto'}
        event={'tool':case['tool'],'proposed_arguments':{'dietary_type':'vegan'}}
        with self.assertRaises(AssertionError):check_development_case(case,[event])
