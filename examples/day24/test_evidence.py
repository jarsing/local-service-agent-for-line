"""Synthetic responses test the checker, not Gemini. No business APIs are called."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from .evidence import *
from .capture import create_plan,request_for,execute
from .audit import audit

RATE=load(Path(__file__).with_name('rate_card.json'))


def response(tool='show_local_help', args=None, budget=0):
    return {'modelVersion':'synthetic-gemini-3.8-flash-version',
            'candidates':[{'finishReason':'STOP','content':{'parts':[{'functionCall':{
                'name':tool,'args':args if args is not None else {'reason':'unsupported'}}}]}}],
            'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':20,
                             'thoughtsTokenCount':0 if budget==0 else 5,
                             'totalTokenCount':120 if budget==0 else 125}}


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.d=dataset();self.c={c['id']:c for c in self.d['cases']}
        self.r=response()

    def test_dataset_twenty(self):self.assertEqual(len(self.d['cases']),20)
    def test_live_nine(self):self.assertEqual(len(self.d['live_eligible_ids']),9)
    def test_case02_is_forget_not_duplicate(self):self.assertEqual(self.c['local02']['scenario'],'forgotten_preference')
    def test_case09_needs_area_not_write(self):self.assertEqual(self.c['local09']['scenario'],'needs_area')
    def test_case13_is_no_data(self):self.assertEqual(self.c['local13']['input'],'查大村素食')
    def test_case17_is_food_booking(self):self.assertEqual(self.c['local17']['input'],'可以幫我預約明天的爌肉飯嗎')
    def test_plan_fifteen(self):self.assertEqual(len(create_plan()['items']),15)
    def test_three_AB_pairs(self):self.assertEqual(sum(i['group']!='route' for i in create_plan()['items']),6)
    def test_model_is_three_eight(self):self.assertEqual(create_plan()['model_id'],'gemini-3.8-flash')
    def test_no_answers_in_request(self):
        p=create_plan();r=request_for(p,p['items'][0]);self.assertNotIn('expect',r);self.assertNotIn('case_id',r)
    def test_budget_zero(self):
        p=create_plan();self.assertEqual(request_for(p,p['items'][0])['config']['thinking_config']['thinking_budget'],0)
    def test_budget_upper_not_fixed_usage(self):
        p=create_plan();i=next(i for i in p['items'] if i['budget']==1024)
        self.assertEqual(request_for(p,i)['config']['thinking_config']['thinking_budget'],1024)
    def test_automatic_tool_execution_disabled(self):
        p=create_plan();self.assertTrue(request_for(p,p['items'][0])['config']['automatic_function_calling']['disable'])
    def test_no_empty_string_in_tool_enums(self):
        p=create_plan()
        for t in p['tools']:
            for prop_name, prop in t.get('parameters',{}).get('properties',{}).items():
                if 'enum' in prop:
                    self.assertNotIn('', prop['enum'], f"Tool {t['name']}.{prop_name} has empty enum")
    def test_validate_declarations_rejects_empty_enum(self):
        from .capture import validate_declarations
        bad=[{'name':'bad','description':'d','parameters':{'type':'OBJECT','properties':{'x':{'type':'STRING','enum':['']}}}}]
        with self.assertRaises(ValueError):validate_declarations(bad)
    def test_usage_complete(self):self.assertEqual(usage(self.r,0)['cost_status'],'COMPLETE')
    def test_missing_usage_unknown(self):self.assertIsNone(usage({},0)['usd'])
    def test_missing_input_unknown(self):
        del self.r['usageMetadata']['promptTokenCount'];self.assertEqual(usage(self.r,0)['cost_status'],'UNKNOWN')
    def test_missing_output_unknown(self):
        del self.r['usageMetadata']['candidatesTokenCount'];self.assertEqual(usage(self.r,0)['cost_status'],'UNKNOWN')
    def test_missing_total_unknown(self):
        del self.r['usageMetadata']['totalTokenCount'];self.assertEqual(usage(self.r,0)['cost_status'],'UNKNOWN')
    def test_disabled_thoughts_inference_label(self):
        del self.r['usageMetadata']['thoughtsTokenCount'];self.assertEqual(usage(self.r,0)['cost_status'],'UNKNOWN')
    def test_enabled_missing_thoughts_not_inferred(self):
        del self.r['usageMetadata']['thoughtsTokenCount'];self.assertEqual(usage(self.r,1024)['cost_status'],'UNKNOWN')
    def test_total_not_used_to_fill_thoughts(self):
        self.r['usageMetadata']['thoughtsTokenCount']=None;self.assertIsNone(usage(self.r,1024)['thoughts'])
    def test_thoughts_charged_once(self):
        u=estimate(usage(response(budget=1024),1024),RATE,MODEL);self.assertEqual(Decimal(u['usd']),Decimal('0.00016875'))
    def test_rate_wrong_model_rejected(self):
        with self.assertRaises(ValueError):estimate(usage(self.r,0),RATE,'gemini-1.5-flash')
    def test_total_mismatch(self):
        self.r['usageMetadata']['totalTokenCount']=999;self.assertEqual(usage(self.r,0)['cost_status'],'INVALID')
    def test_negative_tokens(self):
        self.r['usageMetadata']['promptTokenCount']=-1
        with self.assertRaises(ValueError):usage(self.r,0)
    def test_boolean_tokens(self):
        self.r['usageMetadata']['promptTokenCount']=True
        with self.assertRaises(ValueError):usage(self.r,0)
    def test_cache_needs_other_rate(self):
        self.r['usageMetadata']['cachedContentTokenCount']=10;self.assertEqual(usage(self.r,0)['cost_status'],'UNSUPPORTED')
    def test_tool_use_tokens_not_ignored(self):
        self.r['usageMetadata']['toolUsePromptTokenCount']=1;self.assertEqual(usage(self.r,0)['cost_status'],'UNSUPPORTED')
    def test_snake_and_camel_conflict(self):
        self.r['usage_metadata']={'prompt_token_count':1}
        with self.assertRaises(ValueError):usage(self.r,0)
    def test_single_call(self):self.assertEqual(len(calls(self.r)),1)
    def test_missing_call(self):
        self.r['candidates'][0]['content']['parts']=[]
        with self.assertRaises(ValueError):calls(self.r)
    def test_extra_call_rejected(self):
        self.r['candidates'][0]['content']['parts']*=2
        with self.assertRaises(ValueError):calls(self.r)
    def test_unknown_tool_rejected(self):
        with self.assertRaises(ValueError):calls(response('create_handoff_request',{}))
    def test_bad_enum(self):
        with self.assertRaises(ValueError):calls(response(args={'reason':'booked'}))
    def test_extra_argument(self):
        with self.assertRaises(ValueError):calls(response(args={'reason':'unsupported','owner':'synthetic'}))
    def test_required_tool_argument_cannot_be_omitted(self):
        with self.assertRaises(ValueError):calls(response(args={}))
    def test_nonstring_arg(self):
        with self.assertRaises(ValueError):calls(response(args={'reason':False}))
    def test_correct_route_not_backend_pass(self):
        grade=route_grade(self.c['local19'],calls(self.r));self.assertEqual(grade['status'],'PASS');self.assertEqual(grade['backend'],'NOT_EVALUATED')
    def test_route_args_are_scored(self):
        r=response('search_local_places',{'area':'彰化市','dietary_type':'vegetarian','keyword':''})
        self.assertEqual(route_grade(self.c['local13'],calls(r))['status'],'FAIL')
    def test_wrong_finish(self):
        self.r['candidates'][0]['finishReason']='MAX_TOKENS'
        with self.assertRaises(ValueError):calls(self.r)
    def test_nan_latency(self):
        with self.assertRaises(ValueError):finite_time(float('nan'))
    def test_bool_latency(self):
        with self.assertRaises(ValueError):finite_time(True)
    def test_same_requested_model_not_sufficient(self):
        a={k:'x' for k in COMPARE_FIELDS};b=dict(a)
        a.update(budget=0,origin='DIRECT_SDK_CAPTURE');b.update(budget=1024,origin='DIRECT_SDK_CAPTURE')
        self.assertIn('SERVED_MODEL_VERSION_MISSING_OR_CHANGED',comparable(a,b))
    def test_hash_format_not_placeholder(self):
        a={k:'x' for k in COMPARE_FIELDS};b=dict(a)
        self.assertTrue(any(x.startswith('INVALID_DIGEST') for x in comparable(a,b)))


class FileAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.plan=create_plan();save(self.root/'plan.json',self.plan)
        (self.root/'dataset.json').write_bytes(DATASET.read_bytes())
        (self.root/'rate_card.json').write_bytes(Path(__file__).with_name('rate_card.json').read_bytes())
    def tearDown(self):self.temp.cleanup()
    def fake_run(self,fail=False):
        cases={c['input']:c for c in dataset()['cases']}
        class FakeTransport:
            def generate(_,request):
                if fail:raise ConnectionError('secret-value-must-not-be-recorded')
                c=cases[request['contents']]
                # Test-only oracle. Not used in real capture transport.
                name=c['expect']['tools'][0];a={k:'' for k in TOOL_FIELDS[name]}
                for k,v in c['expect'].get('arguments',{}).items():a[k]=v[0]
                return response(name,a,request['config']['thinking_config']['thinking_budget'])
        execute(self.plan,self.root,FakeTransport(),interval=0,sleeper=lambda _:None)
    def test_empty_plan_is_not_live_pass(self):
        r=audit(self.root);self.assertEqual(r['summary']['route_captured'],0);self.assertIsNone(r['summary']['route_full_denominator_rate']);self.assertFalse(r['summary']['evidence_complete'])
    def test_fake_transport_end_to_end_checker_only(self):
        self.fake_run();r=audit(self.root);self.assertEqual(r['summary']['route_passed'],9)
        self.assertEqual(r['summary']['complete_cost_rows'],6);self.assertFalse(r['summary']['safe_to_deploy'])
    def test_errors_keep_denominators(self):
        self.fake_run(True);r=audit(self.root);self.assertEqual(r['summary']['route_denominator'],9)
        self.assertEqual(sum(x['status']=='ERROR' for x in r['rows']),15)
        self.assertNotIn('secret-value', ''.join(p.read_text() for p in self.root.rglob('*.json')))
    def test_all_errors_have_zero_rate_not_unexecuted_rate(self):
        self.fake_run(True);r=audit(self.root)
        self.assertEqual(r['summary']['route_attempted'],9)
        self.assertEqual(r['summary']['route_full_denominator_rate'],0.0)
    def test_wrong_route_does_not_pass_routing_gate(self):
        self.fake_run();folder=self.root/'calls/route-local13'
        data=response('show_local_help',{'reason':'unsupported'});save(folder/'sdk_response.json',data)
        record=load(folder/'record.json');record['response_sha256']=digest((folder/'sdk_response.json').read_bytes())
        save(folder/'record.json',record);r=audit(self.root)
        self.assertFalse(r['summary']['routing_contract_passed'])
        self.assertTrue(r['summary']['evidence_complete'])
    def test_generated_tables_keep_denominators_separate(self):
        from .audit import table
        t=table(audit(self.root))
        self.assertIn('九題路由',t);self.assertIn('六列 A/B',t)
    def test_missing_row_not_removed(self):
        self.fake_run();(self.root/'calls/route-local01/record.json').unlink()
        self.assertEqual(audit(self.root)['summary']['route_not_run'],1)
    def test_raw_response_tamper(self):
        self.fake_run();(self.root/'calls/route-local01/sdk_response.json').write_text('{}')
        self.assertEqual(audit(self.root)['rows'][0]['status'],'INVALID_EVIDENCE')
    def test_saved_request_tamper(self):
        self.fake_run();p=self.root/'calls/route-local01/request.json';req=load(p);req['contents']='other';save(p,req)
        rp=p.with_name('record.json');r=load(rp);r['request_sha256']=digest(p.read_bytes());save(rp,r)
        self.assertEqual(audit(self.root)['rows'][0]['status'],'INVALID_EVIDENCE')
    def test_source_hash_checks(self):
        self.plan['source_tree_sha256']='0'*64;save(self.root/'plan.json',self.plan)
        with self.assertRaises(ValueError):audit(self.root)
    def test_dataset_tamper(self):
        (self.root/'dataset.json').write_text('{}')
        with self.assertRaises(ValueError):audit(self.root)
    def test_unplanned_extra_call(self):
        (self.root/'calls/extra').mkdir(parents=True)
        with self.assertRaises(ValueError):audit(self.root)
    def test_duplicate_plan_row(self):
        self.plan['items'][0]=self.plan['items'][1];save(self.root/'plan.json',self.plan)
        with self.assertRaises(ValueError):audit(self.root)
    def test_case_id_cannot_move_to_another_key(self):
        self.plan['items'][0]['case_id']='local02';save(self.root/'plan.json',self.plan)
        with self.assertRaises(ValueError):audit(self.root)
    def test_group_cannot_move_between_denominators(self):
        self.plan['items'][0]['group']='A';save(self.root/'plan.json',self.plan)
        with self.assertRaises(ValueError):audit(self.root)
    def test_path_escape(self):
        with self.assertRaises(ValueError):safe_read(self.root,'../outside.json','0'*64)

if __name__=='__main__':unittest.main()
