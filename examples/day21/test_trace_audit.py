import copy
import json
import unittest
from .trace_audit import inspect_trace, synthetic_trace, to_logging_entries

class TraceContracts(unittest.TestCase):
    def setUp(self):self.t=synthetic_trace()
    def event(self,kind):return next(x for x in self.t['events'] if x['kind']==kind)

    def test_complete_fixture_remains_synthetic(self):
        r=inspect_trace(self.t)
        self.assertEqual(r['status'],'CONTRACT_CHECKED')
        self.assertIsNone(r['model_accuracy'])
        self.assertEqual(r['coverage_status'],'NEEDS_REVIEW')
        self.assertEqual(r['causal_conclusion'],'REQUIRES_CONTROLLED_CHANGE')

    def test_empty_trace_is_incomplete_not_safe(self):
        self.t['events']=[]
        r=inspect_trace(self.t)
        self.assertEqual(r['status'],'INCOMPLETE')
        self.assertIsNone(r['candidate_layer'])

    def test_missing_response_does_not_identify_root_cause(self):
        self.t['events']=[e for e in self.t['events'] if e['kind']!='TOOL_RESPONSE']
        self.assertEqual(inspect_trace(self.t)['status'],'INCOMPLETE')

    def test_missing_audit_count_is_not_zero(self):
        del self.event('DB_AUDIT_VERIFIED')['business_writes']
        self.assertEqual(inspect_trace(self.t)['status'],'FAIL')

    def test_boolean_zero_is_rejected(self):
        self.event('DB_AUDIT_VERIFIED')['business_writes']=False
        self.assertEqual(inspect_trace(self.t)['status'],'FAIL')

    def test_backend_failure_not_overwritten_by_template_warning(self):
        self.event('DB_AUDIT_VERIFIED')['business_writes']=1
        r=inspect_trace(self.t)
        self.assertEqual(r['status'],'FAIL');self.assertIsNone(r['candidate_layer'])

    def test_requested_executed_args_must_match(self):
        self.event('TOOL_EXECUTED')['arguments']={'reason':''}
        self.assertEqual(inspect_trace(self.t)['status'],'FAIL')

    def test_cross_call_id_rejected(self):
        self.event('TOOL_RESPONSE')['call_id']='different-call'
        self.assertEqual(inspect_trace(self.t)['status'],'FAIL')

    def test_extra_execution_rejected(self):
        self.t['events'].append(copy.deepcopy(self.event('TOOL_EXECUTED')))
        self.assertEqual(inspect_trace(self.t)['status'],'FAIL')

    def test_wrong_result_link_rejected(self):
        self.event('TOOL_RESPONSE')['result']={'status':'claimed'}
        self.assertEqual(inspect_trace(self.t)['status'],'FAIL')

    def test_cloud_id_format_checked(self):
        for tid in ['tr-20261005-7f9a1b','0'*32]:
            self.t['trace_id']=tid
            self.assertEqual(inspect_trace(self.t)['status'],'FAIL')

    def test_whitelisted_logging_drops_private_payloads(self):
        self.event('TOOL_REQUESTED')['raw_query']='PRIVATE_FIXTURE_TEXT'
        self.event('TOOL_REQUESTED')['access_token']='PRIVATE_FIXTURE_TOKEN'
        exported=json.dumps(to_logging_entries(self.t))
        self.assertNotIn('PRIVATE_FIXTURE',exported)
        self.assertNotIn('visible_text',exported)
        self.assertNotIn('arguments',exported)

    def test_complete_phrases_only_mean_phrase_coverage(self):
        self.event('PRESENTATION_RENDERED')['visible_text']+='無即時營業資料。'
        r=inspect_trace(self.t)
        self.assertEqual(r['coverage_status'],'COVERED')
        self.assertEqual(r['coverage_method'],'declared_phrase_check_not_semantic_judge')
        self.assertIsNone(r['model_accuracy'])

    def test_no_sentence_is_not_presentation(self):
        self.event('PRESENTATION_RENDERED')['visible_text']=' '
        self.assertEqual(inspect_trace(self.t)['status'],'FAIL')

    def test_unsafe_action_is_rejected(self):
        self.event('PRESENTATION_RENDERED')['action_data'][0]='confirm:write'
        self.assertEqual(inspect_trace(self.t)['status'],'FAIL')

    def test_unrelated_case_cannot_get_case19_diagnosis(self):
        self.t['case_id']='local11'
        self.assertEqual(inspect_trace(self.t)['status'],'FAIL')

if __name__=='__main__':unittest.main()
