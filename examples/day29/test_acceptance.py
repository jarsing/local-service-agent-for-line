"""Scorer/configuration tests only; synthetic records here are not LOCAL results."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from acceptance import (EvidenceError, aggregate, canonical, check, decode, digest,
                        grade_case, load_records, pointer, stimulus_for, validate_fixture)
from model_route import ModelRoute, make_client

ROOT=Path(__file__).resolve().parents[2]
FIXTURE_PATH=ROOT/'eval/local100.json'
FIXTURE=decode(FIXTURE_PATH.read_text(encoding='utf-8'))
FH=hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest()
COMMIT=FIXTURE['source_baseline_commit']

class GraderTests(unittest.TestCase):
    def setUp(self):
        home=ROOT/'out/day29/test-tmp'
        home.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=home)
        self.root=Path(self.tmp.name)
        self.case=deepcopy(FIXTURE['cases'][0])
        self.case['assertions']=[{'path':'/business/writes','op':'eq','value':0}]
        self.raw={'case_id':self.case['id'],'case_sha256':digest(self.case),
                  'fixture_sha256':FH,'source_commit':COMMIT,'mode':'offline_contract',
                  'input_sha256':digest(stimulus_for(self.case)),
                  'collector_sha256':'1'*64,'config_sha256':'2'*64,
                  'origin':'captured_execution','execution':'COMPLETED',
                  'data':{'business':{'writes':0}},'elapsed_ms':None}
    def tearDown(self):
        self.tmp.cleanup()
    def record(self):
        b=canonical(self.raw)
        (self.root/'synthetic-observation.json').write_bytes(b)
        return {'case_id':self.case['id'],'raw':{'path':'synthetic-observation.json','sha256':hashlib.sha256(b).hexdigest()}}
    def grade(self,record=None):
        return grade_case(self.case, self.record() if record is None else record,
                          fixture_hash=FH,source_commit=COMMIT,mode='offline_contract',evidence_root=self.root)
    def test_fixture_has_100_specs_not_service_passes(self):
        v=validate_fixture(FIXTURE)
        self.assertEqual(v['planned_cases'],100)
        self.assertEqual(v['execution_status'],'NOT_RUN')
    def test_boolean_schema_rejected(self):
        f=deepcopy(FIXTURE);f['schema_version']=True
        with self.assertRaisesRegex(EvidenceError,'FIXTURE_SCHEMA'):validate_fixture(f)
        f=deepcopy(FIXTURE);f['cases'][0]['tags']=[]
        with self.assertRaisesRegex(EvidenceError,'CASE_TAGS_REQUIRED'):validate_fixture(f)
        f=deepcopy(FIXTURE);f['cases'][0]['tags']=['t1','t1']
        with self.assertRaisesRegex(EvidenceError,'CASE_TAGS_REQUIRED'):validate_fixture(f)
    def test_partial_results_keep_100_denominator(self):
        r=aggregate(FIXTURE,[self.grade()],mode='offline_contract')
        self.assertEqual(r['planned'],100);self.assertEqual(r['tested'],1)
        self.assertEqual(r['counts']['NOT_RUN'],99);self.assertEqual(r['status'],'INCOMPLETE')
    def test_empty_results_stay_not_run(self):
        r=aggregate(FIXTURE,[],mode='offline_contract')
        self.assertEqual(r['counts']['NOT_RUN'],100);self.assertIsNone(r['pass_rate_observed'])
    def test_duplicate_results_rejected(self):
        r=self.grade()
        with self.assertRaises(EvidenceError):aggregate(FIXTURE,[r,r],mode='offline_contract')
    def test_result_cannot_forge_group_or_tags(self):
        r=self.grade();r['family']='places';r['tags']=['idempotency']
        out=aggregate(FIXTURE,[r],mode='offline_contract')
        self.assertEqual(out['family_results']['events_access']['tested'],1)
        self.assertEqual(out['replay_subset']['tested'],0)
    def test_bad_raw_hash_type_blocked(self):
        r=self.record();r['raw']['sha256']=None
        self.assertEqual(self.grade(r)['status'],'BLOCKED')
    def test_duplicate_id_rejected(self):
        f=deepcopy(FIXTURE);f['cases'][1]['id']=f['cases'][0]['id']
        with self.assertRaisesRegex(EvidenceError,'DUPLICATE_CASE_ID'):validate_fixture(f)
    def test_renaming_question_does_not_hide_duplicate_behavior(self):
        f=deepcopy(FIXTURE); c=deepcopy(f['cases'][0]); c.update(id=f['cases'][1]['id'],purpose='duplicate-renamed',input='只是換句話說')
        f['cases'][1]=c
        with self.assertRaisesRegex(EvidenceError,'DUPLICATE_BEHAVIOR'):validate_fixture(f)
    def test_missing_assertions_rejected(self):
        f=deepcopy(FIXTURE);f['cases'][0]['assertions']=[]
        with self.assertRaisesRegex(EvidenceError,'ASSERTIONS_REQUIRED'):validate_fixture(f)
    def test_json_duplicate_key_rejected(self):
        with self.assertRaises(EvidenceError):decode('{"x":0,"x":1}')
    def test_nonfinite_json_rejected(self):
        with self.assertRaises(EvidenceError):decode('{"x":NaN}')
        with self.assertRaises(EvidenceError):decode('{"x":Infinity}')
        with self.assertRaises(EvidenceError):decode('{"x":1e309}')
        with self.assertRaises(EvidenceError):decode('{"x":' + '9'*4302 + '}')
    def test_no_observation_is_not_run(self):
        r=grade_case(self.case,None,fixture_hash=FH,source_commit=COMMIT,mode='offline_contract',evidence_root=self.root)
        self.assertEqual(r['status'],'NOT_RUN')
    def test_no_records_never_becomes_100_percent(self):
        rs=[{'id':c['id'],'family':c['family'],'tags':c['tags'],'status':'NOT_RUN'} for c in FIXTURE['cases']]
        r=aggregate(FIXTURE,rs,mode='offline_contract')
        self.assertIsNone(r['pass_rate_observed']);self.assertEqual(r['status'],'NOT_RUN')
    def test_valid_synthetic_unit_record_passes(self):
        self.assertEqual(self.grade()['status'],'PASS')
    def test_false_result_fails(self):
        self.raw['data']['business']['writes']=1
        self.assertEqual(self.grade()['status'],'FAIL')
    def test_missing_counter_not_defaulted_to_zero(self):
        self.raw['data']['business']={}
        self.assertEqual(self.grade()['status'],'BLOCKED')
    def test_boolean_not_integer(self):
        self.raw['data']['business']['writes']=False
        self.assertEqual(self.grade()['status'],'FAIL')
    def test_null_not_missing(self):
        self.case['assertions'][0]['value']=None;self.raw['case_sha256']=digest(self.case)
        self.raw['data']['business']['writes']=None
        self.assertEqual(self.grade()['status'],'PASS')
    def test_wrong_fixture_hash_blocked(self):
        self.raw['fixture_sha256']='3'*64
        self.assertEqual(self.grade()['status'],'BLOCKED')
    def test_wrong_source_commit_blocked(self):
        self.raw['source_commit']='4'*40
        self.assertEqual(self.grade()['status'],'BLOCKED')
    def test_wrong_case_hash_blocked(self):
        self.raw['case_sha256']='5'*64
        self.assertEqual(self.grade()['status'],'BLOCKED')
    def test_wrong_stimulus_hash_blocked(self):
        self.raw['input_sha256']='6'*64
        self.assertEqual(self.grade()['status'],'BLOCKED')
    def test_raw_file_modification_blocked(self):
        r=self.record();(self.root/'synthetic-observation.json').write_text('{}')
        self.assertEqual(self.grade(r)['status'],'BLOCKED')
    def test_outside_path_blocked(self):
        r=self.record();r['raw']['path']='../forbidden.json'
        self.assertEqual(self.grade(r)['status'],'BLOCKED')
    def test_abs_path_blocked(self):
        r=self.record();r['raw']['path']=str(self.root/'synthetic-observation.json')
        self.assertEqual(self.grade(r)['status'],'BLOCKED')
    def test_synthetic_record_not_production_evidence(self):
        self.raw['origin']='synthetic_unit_test'
        self.assertEqual(self.grade()['status'],'BLOCKED')
    def test_live_record_not_mixed_with_offline(self):
        self.raw['mode']='live_model'
        self.assertEqual(self.grade()['status'],'BLOCKED')
    def test_invalid_elapsed_not_silently_zeroed(self):
        self.raw['elapsed_ms']=-1
        self.assertEqual(self.grade()['status'],'BLOCKED')
        self.raw['elapsed_ms']=10**400
        self.assertEqual(self.grade()['status'],'BLOCKED')
        r1=self.grade()
        r1['elapsed_ms']=1e308
        r2=deepcopy(r1); r2['id']='L29-002'
        rep=aggregate(FIXTURE,[r1,r2],mode='offline_contract')
        self.assertIsNone(rep['metrics']['recorded_operation_elapsed_ms']['mean'])
    def test_duplicate_observation_rejected(self):
        r=self.record();p=self.root/'records.json';p.write_text(json.dumps({'records':[r,r]}))
        with self.assertRaisesRegex(EvidenceError,'DUPLICATE_OBSERVATION_ID'):load_records(p,{self.case['id']})
    def test_unknown_case_not_ignored(self):
        r=self.record();r['case_id']='L29-999';p=self.root/'records.json';p.write_text(json.dumps({'records':[r]}))
        with self.assertRaisesRegex(EvidenceError,'UNEXPECTED_CASE_ID'):load_records(p,{self.case['id']})
    def test_mixed_config_not_aggregated(self):
        r=self.grade(); s={**r,'id':'L29-002','config_sha256':'9'*64}
        report=aggregate(FIXTURE,[r,s],mode='offline_contract')
        self.assertEqual(report['status'],'BLOCKED_MIXED_CONFIGURATION');self.assertIsNone(report['pass_rate_observed'])
    def test_expected_answers_not_in_collector_stimulus(self):
        self.assertEqual(set(stimulus_for(self.case)),{'id','input','setup','steps'})
    def test_pointer_escapes(self):
        self.assertEqual(pointer({'a/b':{'x~y':[7]}},'/a~1b/x~0y/0'),7)
        f=deepcopy(FIXTURE)
        f['cases'][0]['assertions']=[{'path':'/a~2b','op':'eq','value':0}]
        with self.assertRaisesRegex(EvidenceError,'INVALID_POINTER_ESCAPE'):validate_fixture(f)
        f['cases'][0]['assertions']=[{'path':'/valid','op':[],'value':0}]
        with self.assertRaisesRegex(EvidenceError,'ASSERTION_OPERATOR_OR_POINTER'):validate_fixture(f)
    def test_one_of_is_type_aware(self):
        self.assertFalse(check(False,{'op':'one_of','value':[0,1]}))
    def test_retained_input_file_is_not_overwritten(self):
        from acceptance import write_new_json
        p=self.root/'report.json';write_new_json(p,{'original':True});before=p.read_bytes()
        with self.assertRaises(FileExistsError):write_new_json(p,{'original':False})
        self.assertEqual(p.read_bytes(),before)
        p2=self.root/'bad.json'
        with self.assertRaises(ValueError):write_new_json(p2,{'nan':float('nan')})
        self.assertFalse(p2.exists())

class RouteTests(unittest.TestCase):
    def test_developer_route(self):
        r=make_client(ModelRoute('developer','test-model'),lambda **kw:kw,api_key='synthetic-key')
        self.assertFalse(r['vertexai'])
    def test_vertex_route(self):
        cred=object();r=make_client(ModelRoute('vertex','test-model','sample-project','us-central1'),lambda **kw:kw,credentials=cred)
        self.assertTrue(r['vertexai']);self.assertIs(r['credentials'],cred)
    def test_no_cloud_fallback_without_key(self):
        with self.assertRaises(ValueError):make_client(ModelRoute('developer','test-model'),lambda **kw:kw)
    def test_no_vertex_route_without_region(self):
        with self.assertRaises(ValueError):make_client(ModelRoute('vertex','test-model','sample-project'),lambda **kw:kw,credentials=object())
    def test_conflicting_key_rejected(self):
        with self.assertRaises(ValueError):make_client(ModelRoute('vertex','test-model','sample-project','us-central1'),lambda **kw:kw,api_key='synthetic',credentials=object())
    def test_no_unsupported_backend_fallback(self):
        with self.assertRaises(ValueError):make_client(ModelRoute('other','test-model'),lambda **kw:kw)

if __name__=='__main__':unittest.main()
