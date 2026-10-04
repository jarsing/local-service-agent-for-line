import copy
import json
import unittest
from .trace_audit import inspect_trace, synthetic_trace, to_logging_entries

class TraceContracts(unittest.TestCase):
    def setUp(self):
        self.t=synthetic_trace()

    def event(self,kind):
        return next(x for x in self.t['events'] if x['kind']==kind)

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
        self.assertEqual(r['status'],'FAIL')
        self.assertIsNone(r['candidate_layer'])

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

    def test_uncreated_request_must_not_have_request_id(self):
        self.t['request_id']='REQ-FAKE-123'
        r=inspect_trace(self.t)
        self.assertEqual(r['status'],'FAIL')
        self.assertIn('REQUEST_ID_MUST_BE_NULL_FOR_UNCREATED_REQUEST',r['issues'])

    def test_wrong_tool_result_status_not_presentation_candidate(self):
        for k in ('TOOL_EXECUTED','TOOL_RESPONSE'):
            self.event(k)['result']={'status':'success','reason':'unsupported'}
        r=inspect_trace(self.t)
        self.assertEqual(r['status'],'FAIL')
        self.assertIsNone(r['candidate_layer'])
        self.assertIn('TOOL_RESULT_STATUS_MISMATCH',r['issues'])

    def test_wrong_tool_result_reason_not_presentation_candidate(self):
        for k in ('TOOL_EXECUTED','TOOL_RESPONSE'):
            self.event(k)['result']={'status':'help','reason':'general'}
        r=inspect_trace(self.t)
        self.assertEqual(r['status'],'FAIL')
        self.assertIsNone(r['candidate_layer'])
        self.assertIn('TOOL_RESULT_REASON_MISMATCH',r['issues'])

    def test_imported_capture_requires_provenance(self):
        self.t['origin']='imported_capture'
        r=inspect_trace(self.t)
        self.assertEqual(r['status'],'FAIL')
        self.assertIn('PROVENANCE_REQUIRED_FOR_IMPORTED_CAPTURE',r['issues'])

    def test_imported_capture_valid_provenance_passes(self):
        self.t['origin']='imported_capture'
        self.t['provenance']={
            'model_id':'gemini-2.5-flash',
            'prompt_sha256':'a'*64,
            'tools_sha256':'b'*64,
            'code_sha':'cc20b77',
            'raw_record_sha256':'c'*64
        }
        r=inspect_trace(self.t)
        self.assertEqual(r['status'],'CONTRACT_CHECKED')

    def test_public_logging_rejects_pii_correlation_or_call_id(self):
        self.t['correlation_id']='user@example.com'
        for e in self.t['events']:
            e['correlation_id']='user@example.com'
        self.assertEqual(inspect_trace(self.t)['status'],'FAIL')
        # Test call_id PII rejection in to_logging_entries
        self.setUp()
        for e in self.t['events']:
            e['call_id'] = '0912345678'
        with self.assertRaises(ValueError):
            to_logging_entries(self.t)

    def test_project_id_length_boundary(self):
        # 5 chars is too short, 31 chars is too long
        self.t['project_id']='a-b-c'
        with self.assertRaises(ValueError):
            to_logging_entries(self.t)
        self.t['project_id']='a' * 31
        with self.assertRaises(ValueError):
            to_logging_entries(self.t)
        self.t['project_id']='valid-project-id-2026'
        entries=to_logging_entries(self.t)
        self.assertTrue(len(entries) > 0)

if __name__=='__main__':
    unittest.main()
