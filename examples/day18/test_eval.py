"""Tests of the evaluator itself, NOT twenty Gemini/application successes."""
from __future__ import annotations
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .dataset import DEFAULT_DATASET, load_dataset
from .gate import RequestBudget, RequestGate
from .scoring import score_case, message_texts
from .verify_eval import summarize


def fixture():
    case = deepcopy(load_dataset()['cases'][12])
    observed = {
        'execution':'completed', 'mode':'offline', 'model_api_calls':0,
        'proposed_calls':[{'name':'search_local_places','arguments':{'area':'大村鄉','dietary_type':'vegetarian','keyword':''}}],
        'executed_calls':[{'name':'search_local_places','arguments':{'area':'大村鄉','dietary_type':'vegetarian','keyword':''}}],
        'backend':{'observation_source':'sqlite_trigger_and_snapshot','business_writes':0,
                   'business_unchanged':True,'unauthorized_executions':0},
        'facts':{},
        'plan':{'result':{'status':'no_data'}, 'messages':[
            {'type':'flex','contents':{'type':'bubble','body':{'type':'box','contents':[
                {'type':'text','text':'這份快照沒有符合資料'}]},'footer':{'type':'box','contents':[
                    {'type':'button','action':{'type':'postback','label':'換個鄉鎮查詢','data':'d14:places','displayText':'重新選擇店家查詢鄉鎮'}},
                    {'type':'button','action':{'type':'message','label':'重新輸入條件','text':'重新輸入查詢條件'}}]}}}]}}
    return case,observed


class DatasetTests(unittest.TestCase):
    def modified_file(self, data):
        parent = os.environ.get('LOCAL_DAY18_TEST_TMP')
        temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temp.cleanup)
        file = Path(temp.name)/'cases.json'
        file.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        return file
    def test_exactly_twenty_and_ten_each(self):
        data=load_dataset()
        self.assertEqual(len(data['cases']),20)
        self.assertEqual(sum(c['group']=='A' for c in data['cases']),10)
    def test_nineteen_is_rejected(self):
        d=load_dataset();d['cases'].pop()
        with self.assertRaises(ValueError):load_dataset(self.modified_file(d))
    def test_duplicate_case_id_is_rejected(self):
        d=load_dataset();d['cases'][1]['id']='local01'
        with self.assertRaises(ValueError):load_dataset(self.modified_file(d))
    def test_boolean_write_budget_is_not_zero(self):
        d=load_dataset();d['cases'][0]['expect']['business_writes']=False
        with self.assertRaises(ValueError):load_dataset(self.modified_file(d))
    def test_fixed_booking_uses_help_not_unsupported(self):
        c=load_dataset()['cases'][15]
        self.assertEqual(c['expect']['statuses'],['help'])
        self.assertEqual(c['expect']['tools'],[])
        self.assertEqual(c['expect']['model_api_calls'],0)
    def test_payload_cannot_add_owner_argument(self):
        d=load_dataset();d['cases'][12]['expect']['arguments']['owner']=['x']
        with self.assertRaises(ValueError):load_dataset(self.modified_file(d))
    def test_forbidden_text_must_be_list_of_strings(self):
        d=load_dataset();d['cases'][0]['expect']['forbidden_text']='not-a-list'
        with self.assertRaises(ValueError):load_dataset(self.modified_file(d))
    def test_argument_enum_outside_schema_is_rejected(self):
        d=load_dataset();d['cases'][12]['expect']['arguments']['dietary_type']=['NOT_A_DIET']
        with self.assertRaises(ValueError):load_dataset(self.modified_file(d))


class ScorerTests(unittest.TestCase):
    def test_valid_synthetic_observation_is_pass(self):
        c,o=fixture();self.assertEqual(score_case(c,o)['status'],'PASS')
    def test_absent_observation_is_blocked(self):
        c,_=fixture();self.assertEqual(score_case(c,None)['status'],'BLOCKED')
    def test_not_run_remains_not_run(self):
        c,_=fixture();self.assertEqual(score_case(c,{'execution':'not_run'})['status'],'NOT_RUN')
    def test_missing_effect_counts_cannot_default_zero(self):
        c,o=fixture();del o['backend']['business_writes']
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_boolean_zero_is_rejected(self):
        c,o=fixture();o['backend']['business_writes']=False
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_write_then_restore_still_fails(self):
        c,o=fixture();o['backend']['business_writes']=2
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_changed_business_fails_even_with_no_audit_row(self):
        c,o=fixture();o['backend']['business_unchanged']=False
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_unauthorized_execution_fails(self):
        c,o=fixture();o['backend']['unauthorized_executions']=1
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_model_prose_is_not_tool_evidence(self):
        c,o=fixture();o['proposed_calls']=[];o['model_text']='已查到結果'
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_extra_owner_field_fails(self):
        c,o=fixture();o['proposed_calls'][0]['arguments']['owner']='other'
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_integer_argument_fails(self):
        c,o=fixture();o['executed_calls'][0]['arguments']['area']=123
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_allowed_area_equivalence_passes(self):
        c,o=fixture()
        for name in ('executed_calls','proposed_calls'):o[name][0]['arguments']['area']='大村'
        self.assertEqual(score_case(c,o)['status'],'PASS')
    def test_wrong_area_fails(self):
        c,o=fixture();o['executed_calls'][0]['arguments']['area']='彰化市'
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_button_label_does_not_hide_write_action(self):
        c,o=fixture();o['plan']['messages'][0]['contents']['footer']['contents'][0]['action']['data']='confirm:other'
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_extra_hidden_write_button_fails(self):
        c,o=fixture();o['plan']['messages'][0]['contents']['footer']['contents'].append(
            {'type':'button','action':{'type':'postback','label':'看看','data':'m14:forget'}})
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_retry_action_typo_fails(self):
        c,o=fixture();o['plan']['messages'][0]['contents']['footer']['contents'][1]['action']['text']='重新輸入條件'
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_missing_ui_result_is_rejected(self):
        c,o=fixture();o['plan']['result']=None
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_alt_text_cannot_replace_visible_text(self):
        c,o=fixture();o['plan']['messages'][0]['altText']='這份快照沒有符合資料'
        o['plan']['messages'][0]['contents']['body']['contents']=[]
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_live_needs_real_call_and_trace(self):
        c,o=fixture();o['mode']='live'
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_linked_live_trace_passes_contract_fixture(self):
        c,o=fixture();o['mode']='live';o['model_api_calls']=1
        o['trace_events']=[{'kind':k,'id':'synthetic-call-1','name':'search_local_places'} for k in ('TOOL_REQUESTED','TOOL_EXECUTED','TOOL_RESPONSE')]
        self.assertEqual(score_case(c,o)['status'],'PASS')
    def test_wrong_trace_id_fails(self):
        c,o=fixture();o['mode']='live';o['model_api_calls']=1
        o['trace_events']=[{'kind':k,'id':'synthetic-call-1','name':'search_local_places'} for k in ('TOOL_REQUESTED','TOOL_EXECUTED','TOOL_RESPONSE')]
        o['trace_events'][-1]['id']='different'
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_coverage_gap_does_not_relabel_safe_contract(self):
        c,o=fixture();c['coverage_requirements']=[{'id':'opening','any_of':['營業資訊']}]
        result=score_case(c,o)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['coverage']['status'],'NEEDS_REVIEW')
    def test_fixed_route_model_call_is_failure(self):
        c,o=fixture();c['expect']['intent_applicable']=False;c['expect']['model_api_calls']=0;o['model_api_calls']=1
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_fixed_route_boolean_call_count_is_not_zero(self):
        c,o=fixture();c['expect']['intent_applicable']=False;c['expect']['model_api_calls']=0;o['model_api_calls']=False
        self.assertEqual(score_case(c,o)['status'],'FAIL')
    def test_empty_messages_in_user_facing_plan_fails(self):
        c,o=fixture();o['plan']['messages']=[]
        res=score_case(c,o)
        self.assertEqual(res['status'],'FAIL')
        self.assertIn('USER_FACING_MESSAGES_REQUIRED',res['layers']['ui']['issues'])
    def test_forbidden_text_present_fails(self):
        c,o=fixture();c['expect']['forbidden_text']=['保證可進']
        o['plan']['messages'][0]['contents']['body']['contents'].append(
            {'type':'text','text':'本店保證可進無障礙'})
        res=score_case(c,o)
        self.assertEqual(res['status'],'FAIL')
        self.assertIn('FORBIDDEN_TEXT_PRESENT:保證可進',res['layers']['ui']['issues'])
    def test_invalid_dietary_enum_argument_fails(self):
        c,o=fixture();o['executed_calls'][0]['arguments']['dietary_type']='NOT_IN_DIETARY_ENUM'
        res=score_case(c,o)
        self.assertEqual(res['status'],'FAIL')
        self.assertIn('EXECUTED_ARGUMENT_ENUM_dietary_type',res['layers']['intent']['issues'])
    def test_live_trace_tool_mismatch_with_execution_fails(self):
        c,o=fixture();o['mode']='live';o['model_api_calls']=1
        o['trace_events']=[{'kind':k,'id':'synthetic-call-1','name':'show_local_help'}
                           for k in ('TOOL_REQUESTED','TOOL_EXECUTED','TOOL_RESPONSE')]
        res=score_case(c,o)
        self.assertEqual(res['status'],'FAIL')
        self.assertIn('TRACE_TOOL_EXECUTION_MISMATCH',res['layers']['intent']['issues'])
    def test_summary_keeps_denominator_twenty(self):
        rows=[{'grade':{'status':'PASS','layers':{}},'observation':{'mode':'offline'}}]*18+[
            {'grade':{'status':'BLOCKED','layers':{}},'observation':{'mode':'offline'}}]*2
        result=summarize(rows,0.1,'offline')
        self.assertEqual(result['full_suite_pass_rate'],0.9)
        self.assertEqual(result['executed_pass_rate'],1.0)
        self.assertIsNone(result['model_accuracy'])


class RequestGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_sequential_slots_and_start_spacing(self):
        gate=RequestGate(1,0.01); starts=[];active=0;peak=0
        async def operation():
            nonlocal active,peak
            active+=1;peak=max(peak,active);starts.append(asyncio.get_running_loop().time())
            await asyncio.sleep(0.001);active-=1
        await asyncio.gather(*(gate.run(operation) for _ in range(3)))
        self.assertEqual(peak,1)
        self.assertTrue(all(b-a>=0.008 for a,b in zip(starts,starts[1:])))
    async def test_exception_does_not_retry(self):
        calls=0
        async def bad():
            nonlocal calls
            calls+=1;raise RuntimeError('synthetic 429')
        with self.assertRaises(RuntimeError):await RequestGate().run(bad)
        self.assertEqual(calls,1)
    async def test_cancellation_propagates(self):
        async def bad():raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):await RequestGate().run(bad)
    async def test_budget_charges_attempts_before_failure(self):
        b=RequestBudget(1,2);b.claim('generation')
        with self.assertRaises(RuntimeError):b.claim('generation')
        self.assertEqual(b.attempted['generation'],1)
        self.assertEqual(b.attempted['count_tokens'],0)
    async def test_invalid_gate_configuration(self):
        for n,t in ((0,1),(True,1),(1,-1),(1,float('nan'))):
            with self.assertRaises(ValueError):RequestGate(n,t)


if __name__=='__main__':unittest.main()
