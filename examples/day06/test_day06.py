"""資料、回覆判讀、人工核對與 Day 5 工具介接的離線測試。"""
from __future__ import annotations

import base64
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest

from pydantic import ValidationError
from schema import Extraction, FIELDS, as_catalog
from counterexample import fixture, demonstrate
from reporting import digest, dump_json, render, js_json, read_key
from run import image_mime, parse_response
from review import validate_review, export_review
from query import search_reviewed, validate_catalog, execute

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
STAMP="2026-09-19T10:00:00+00:00"

def payload(data=None,reason="STOP",thought=False):
    return NS(candidates=[NS(finish_reason=reason,content=NS(parts=[NS(text=json.dumps(data or fixture(),ensure_ascii=False),thought=thought)]))],
              usage_metadata=None,model_version="offline_fixture",response_id="fixture",prompt_feedback=None)


def record_and_review():
    rec={"kind":"LOCAL_DAY06_EXTRACTION","mode":"OFFLINE_FIXTURE","origin":"assistant_test",
         "run_id":"offline-fixture","source":{"stored_name":"source.png","mime_type":"image/png","sha256":digest(PNG),
         "source_ref":"offline:fixture","source_updated_at":None},
         "runs":[{"condition":"guided","status":"EXTRACTED","extraction":fixture(),"raw_text":json.dumps(fixture()),"duration_seconds":0.0}]}
    blob=(json.dumps(rec,ensure_ascii=False,indent=2)+'\n').encode()
    review={"kind":"poster_human_review","record_sha256":digest(blob),"source_sha256":digest(PNG),
            "reviewer":"離線測試角色","approved":True,"reviewed_at":STAMP,
            "extraction":fixture(),"correction_notes":"","author_observation":""}
    return rec,blob,review

class SchemaTests(unittest.TestCase):
    def test_stated_fixture(self): self.assertEqual(Extraction.model_validate(fixture()).events[0].meeting_time.value,"09:00")
    def test_null_stays_null(self): self.assertIsNone(Extraction.model_validate(fixture()).events[0].accessibility.value)
    def test_false_is_known_false(self):
        d=fixture();d['events'][0]['accessibility']={"value":False,"quote":"路線含階梯，不適合輪椅","status":"stated"}
        self.assertIs(Extraction.model_validate(d).events[0].accessibility.value,False)
    def test_string_bool_rejected(self):
        d=fixture();d['events'][0]['accessibility']={"value":"false","quote":"階梯","status":"stated"}
        with self.assertRaises(ValidationError): Extraction.model_validate(d)
    def test_stated_requires_quote(self):
        d=fixture();d['events'][0]['name']['quote']=None
        with self.assertRaises(ValidationError): Extraction.model_validate(d)
    def test_missing_requires_null(self):
        d=fixture();d['events'][0]['accessibility']['value']=True
        with self.assertRaises(ValidationError): Extraction.model_validate(d)
    def test_unclear_date_preserves_visible_text(self):
        d=fixture();d['events'][0]['date']={"value":None,"quote":"9/26","status":"unclear"}
        self.assertIsNone(Extraction.model_validate(d).events[0].date.value)
    def test_invalid_date_rejected(self):
        d=fixture();d['events'][0]['date']['value']='2026-02-30'
        with self.assertRaises(ValidationError): Extraction.model_validate(d)
    def test_extra_field_rejected(self):
        d=fixture();d['events'][0]['price']=100
        with self.assertRaises(ValidationError): Extraction.model_validate(d)
    def test_schema_requires_all_field_keys(self):
        d=fixture();del d['events'][0]['meeting_time']
        with self.assertRaises(ValidationError): Extraction.model_validate(d)
    def test_ten_event_limit(self):
        d=fixture();d['events']*=11
        with self.assertRaises(ValidationError): Extraction.model_validate(d)
    def test_schema_valid_wrong_time_counterexample(self):
        r=demonstrate();self.assertTrue(r['schema_valid']);self.assertFalse(r['matches_expected'])

class ResponseTests(unittest.TestCase):
    def test_valid_response_parsed(self): self.assertEqual(parse_response(payload())['status'],'EXTRACTED')
    def test_truncated_response_keeps_text(self):
        r=parse_response(payload(reason='MAX_TOKENS'));self.assertEqual(r['status'],'RESPONSE_INCOMPLETE');self.assertTrue(r['raw_text'])
    def test_missing_usage_is_unknown(self): self.assertTrue(all(x is None for x in parse_response(payload())['usage'].values()))
    def test_thought_text_is_not_visible_output(self): self.assertEqual(parse_response(payload(thought=True))['raw_text'],'')
    def test_blocked_response(self):
        p=payload();p.prompt_feedback=NS(block_reason="SAFETY");self.assertEqual(parse_response(p)['status'],'RESPONSE_INCOMPLETE')
    def test_invalid_schema_preserves_raw(self):
        p=payload({"events":[{}],"notes":[]});r=parse_response(p);self.assertEqual(r['status'],'SCHEMA_ERROR');self.assertTrue(r['raw_text'])
    def test_mime_from_bytes(self): self.assertEqual(image_mime(PNG),'image/png')
    def test_text_with_png_extension_not_accepted(self):
        with self.assertRaises(ValueError): image_mime(b'not an image')
    def test_script_text_encoded(self): self.assertNotIn('</script>',js_json({'x':'</script><script>alert(1)</script>'}))
    def test_explicit_key_file(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'key.env';p.write_text('GEMINI_API_KEY="offline-only"\n',encoding='utf-8');self.assertEqual(read_key(p),'offline-only')

class ReviewTests(unittest.TestCase):
    def test_correct_review(self):
        rec,blob,r=record_and_review();e,c=validate_review(rec,blob,r);self.assertEqual(c,[]);self.assertEqual(len(e.events),1)
    def test_review_bound_to_record(self):
        rec,blob,r=record_and_review();r['record_sha256']='wrong'
        with self.assertRaises(ValueError): validate_review(rec,blob,r)
    def test_review_bound_to_image(self):
        rec,blob,r=record_and_review();r['source_sha256']='wrong'
        with self.assertRaises(ValueError): validate_review(rec,blob,r)
    def test_review_needs_human_confirmation(self):
        rec,blob,r=record_and_review();r['approved']=False
        with self.assertRaises(ValueError): validate_review(rec,blob,r)
    def test_changed_value_needs_reason(self):
        rec,blob,r=record_and_review();r['extraction']['events'][0]['time']['value']='09:45'
        with self.assertRaises(ValueError): validate_review(rec,blob,r)
    def test_changed_value_recorded(self):
        rec,blob,r=record_and_review();r['extraction']['events'][0]['time']['value']='09:45';r['correction_notes']='測試用修改原因'
        e,c=validate_review(rec,blob,r);self.assertEqual(c[0]['before']['value'],'09:30');self.assertEqual(c[0]['after']['value'],'09:45')
    def test_source_updated_at_not_invented(self):
        rec,_,_=record_and_review();c=as_catalog(Extraction.model_validate(fixture()),rec['source'],STAMP,'測試角色');self.assertIsNone(c['events'][0]['updated_at'])
    def test_real_data_not_relabelled_synthetic(self):
        rec,_,_=record_and_review();c=as_catalog(Extraction.model_validate(fixture()),rec['source'],STAMP,'測試角色');self.assertEqual(c['kind'],'reviewed_poster_data')
    def test_export_keeps_original(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);run=root/'extract';run.mkdir();rec,blob,r=record_and_review()
            (run/'verification.json').write_bytes(blob);(run/'source.png').write_bytes(PNG);dump_json(root/'review.json',r)
            out=export_review(run,root/'review.json',root);self.assertTrue((out/'catalog.reviewed.json').exists());self.assertEqual((run/'verification.json').read_bytes(),blob)
    def test_html_has_local_review_and_original_image(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);rec,blob,_=record_and_review();(p/'verification.json').write_bytes(blob);(p/'source.png').write_bytes(PNG)
            render(p,rec);s=(p/'REPORT.html').read_text();self.assertIn('data:image/png;base64',s);self.assertIn('review.json',s)

    def test_baseline_can_be_selected_for_review(self):
        rec,blob,r=record_and_review()
        base=deepcopy(rec['runs'][0]);base['condition']='baseline'
        rec['runs'].append(base)
        blob=(json.dumps(rec,ensure_ascii=False,indent=2)+'\n').encode()
        r['record_sha256']=digest(blob);r['selected_condition']='baseline'
        parsed,changes=validate_review(rec,blob,r)
        self.assertEqual(changes,[]);self.assertEqual(parsed.events[0].time.value,'09:30')
    def test_invalid_review_condition_rejected(self):
        rec,blob,r=record_and_review();r['selected_condition']='invented'
        with self.assertRaises(ValueError):validate_review(rec,blob,r)
    def test_template_markers_in_source_are_literal(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);rec,blob,_=record_and_review()
            rec['source']['source_ref']='SOURCE BLOCKS FORM SCRIPT METADATA'
            (p/'verification.json').write_bytes(blob);(p/'source.png').write_bytes(PNG)
            render(p,rec);s=(p/'REPORT.html').read_text()
            self.assertIn('<small>SOURCE BLOCKS FORM SCRIPT METADATA</small>',s)

class Day05BridgeTests(unittest.TestCase):
    def setUp(self):
        rec,_,_=record_and_review();self.data=as_catalog(Extraction.model_validate(fixture()),rec['source'],STAMP,'測試角色')
    def test_original_search_tool_finds_poster(self):
        result,events=search_reviewed(self.data,{'date':'2026-09-26','area':'彰化市','keyword':'走讀'})
        self.assertEqual(result['status'],'ok');self.assertEqual(result['events'][0]['meeting_time'],'09:00');self.assertTrue(any(x['kind']=='TOOL_EXECUTED' for x in events))
    def test_unknown_fields_remain_unknown(self):
        result,_=search_reviewed(self.data,{'keyword':'走讀'});self.assertTrue(any(x.endswith('.accessibility') for x in result['unknown_fields']))
    def test_unknown_area_can_still_search_by_name(self):
        e=self.data['events'][0];e['area']=None;e['field_evidence']['area']={'value':None,'quote':None,'status':'not_shown'}
        result,_=search_reviewed(self.data,{'keyword':'走讀'});self.assertIsNone(result['events'][0]['area'])
    def test_unknown_area_not_guessed_for_filter(self):
        e=self.data['events'][0];e['area']=None;e['field_evidence']['area']={'value':None,'quote':None,'status':'not_shown'}
        result,_=search_reviewed(self.data,{'area':'彰化市'});self.assertEqual(result['status'],'not_found')
    def test_other_date_not_found(self):
        result,_=search_reviewed(self.data,{'date':'2026-09-27'});self.assertEqual(result['status'],'not_found')
    def test_catalog_edits_must_match_reviewed_fields(self):
        self.data['events'][0]['name']='更動的活動'
        with self.assertRaises(ValueError): validate_catalog(self.data)
    def test_activity_time_does_not_replace_meeting_time(self):
        result,_=search_reviewed(self.data,{'keyword':'走讀'});e=result['events'][0];self.assertNotEqual(e['time'],e['meeting_time'])
    def test_query_saves_hashes(self):
        import contextlib,io
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);dump_json(p/'catalog.json',self.data)
            with contextlib.redirect_stdout(io.StringIO()): r,folder=execute(p/'catalog.json',{'date':'','area':'','keyword':'走讀'},p)
            self.assertEqual(r['api_calls'],0);self.assertTrue((folder/'query.json').exists());self.assertEqual(r['catalog_sha256'],digest((p/'catalog.json').read_bytes()))

if __name__=='__main__': unittest.main()
