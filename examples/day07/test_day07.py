"""驗證來源鏈、場次配對、欄位差異、複核決定與查詢版本；不呼叫 API。"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from fixtures import setup, inputs, approved, notice_for, PNG, NEW_PNG, field
from versioning import *
from ui import write_matching,write_review,write_summary,js

class ImportTests(unittest.TestCase):
    def test_import_preserves_fields_and_gets_stable_id(self):
        b,_,_=setup();c,_,_,_,_=inputs()
        self.assertEqual(b['events'][0]['fields'],c['events'][0]['field_evidence'])
        self.assertTrue(b['events'][0]['id'].startswith('evt-'))
    def test_same_import_keeps_event_identity(self):
        a,_,_=setup();b,_,_=setup();self.assertEqual(a['events'][0]['id'],b['events'][0]['id'])
        self.assertNotEqual(a['version_id'],b['version_id'])
    def test_bad_catalog_digest(self):
        c,a,r,cb,rb=inputs();a['catalog_sha256']='x'
        with self.assertRaises(ValueError):import_day06(c,a,r,catalog_bytes=cb,record_bytes=rb,image_bytes=PNG)
    def test_bad_record_digest(self):
        c,a,r,cb,rb=inputs();a['record_sha256']='x'
        with self.assertRaises(ValueError):import_day06(c,a,r,catalog_bytes=cb,record_bytes=rb,image_bytes=PNG)
    def test_bad_image_digest(self):
        c,a,r,cb,rb=inputs()
        with self.assertRaises(ValueError):import_day06(c,a,r,catalog_bytes=cb,record_bytes=rb,image_bytes=NEW_PNG)
    def test_value_mismatch(self):
        c,a,r,cb,rb=inputs();c['events'][0]['time']='wrong';cb=encoded(c);a['catalog_sha256']=digest(cb)
        with self.assertRaises(ValueError):import_day06(c,a,r,catalog_bytes=cb,record_bytes=rb,image_bytes=PNG)
    def test_schema_rejects_string_boolean(self):
        b,_,_=setup();f=deepcopy(b['events'][0]['fields']);f['accessibility']=field('true','可通行')
        with self.assertRaises(ValueError):validate_fields(f)
    def test_snapshot_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'test.json';save(p,{'a':1})
            with self.assertRaises(FileExistsError):save(p,{'a':2})
            self.assertEqual(load(p),{'a':1})

class MatchingDiffTests(unittest.TestCase):
    def test_reorder_not_changes(self):
        b,c,m=setup(change=False);p=make_plan(b,c,m);self.assertEqual(p['rows'],[])
    def test_source_changed_fields_same(self):
        b,c,m=setup(change=False);p=make_plan(b,c,m);self.assertTrue(p['source_changed']);self.assertEqual(p['required_review_keys'],[])
    def test_time_change_not_other_event(self):
        b,c,m=setup();p=make_plan(b,c,m);self.assertEqual(len(p['rows']),1)
        self.assertEqual(p['rows'][0]['event_id'],b['events'][0]['id'])
        self.assertEqual(p['rows'][0]['field'],'time')
    def test_quote_only_is_change(self):
        b,c,m=setup(change=False);c['events'][1]['time']['quote']='活動時間：07:30~11:00';m['candidate_sha256']=fingerprint(c)
        p=make_plan(b,c,m);self.assertEqual(p['rows'][0]['change'],'evidence');self.assertEqual(p['rows'][0]['changed_parts'],['quote'])
    def test_unknown_becomes_known(self):
        b,c,m=setup(change=False);c['events'][0]['meeting_time']=field('13:00');m['candidate_sha256']=fingerprint(c)
        p=make_plan(b,c,m);self.assertEqual(p['rows'][0]['field'],'meeting_time')
    def test_known_becomes_unknown(self):
        b,c,m=setup(change=False);c['events'][1]['time']=field();m['candidate_sha256']=fingerprint(c)
        p=make_plan(b,c,m);self.assertIn('status',p['rows'][0]['changed_parts'])
    def test_date_and_time_linked(self):
        b,c,m=setup();p=make_plan(b,c,m);eid=b['events'][0]['id']
        self.assertEqual(set(p['required_review_keys']),{eid+':'+k for k in ['time','date','meeting_time']})
    def test_name_change_keeps_identity_with_explicit_mapping(self):
        b,c,m=setup(change=False);c['events'][1]['name']=field('重新命名的走讀');m['candidate_sha256']=fingerprint(c)
        p=make_plan(b,c,m);self.assertEqual(p['rows'][0]['event_id'],b['events'][0]['id'])
    def test_duplicate_mapping_rejected(self):
        b,c,m=setup();m['matches'][1]['event_id']=m['matches'][0]['event_id']
        with self.assertRaises(ValueError):make_plan(b,c,m)
    def test_unmatched_rejected(self):
        b,c,m=setup();m['matches'][0]['event_id']=None
        with self.assertRaises(ValueError):make_plan(b,c,m)
    def test_stale_matching_rejected(self):
        b,c,m=setup();c['notes'].append('new note')
        with self.assertRaises(ValueError):make_plan(b,c,m)
    def test_confirmation_required(self):
        b,c,m=setup();m['confirmed']=False
        with self.assertRaises(ValueError):make_plan(b,c,m)
    def test_missing_index_rejected(self):
        b,c,m=setup();m['matches'].pop()
        with self.assertRaises(ValueError):make_plan(b,c,m)
    def test_removed_event_marked(self):
        b,c,m=setup();c['events']=c['events'][:1];m['matches']=m['matches'][:1];m['candidate_sha256']=fingerprint(c)
        p=make_plan(b,c,m);self.assertEqual(p['removed_event_ids'],[b['events'][0]['id']])
    def test_new_event_explicit(self):
        b,c,m=setup();m['matches'][0]['event_id']='NEW';p=make_plan(b,c,m)
        self.assertEqual(len(p['rows']),9);self.assertTrue(p['projected_events'][0]['id'].startswith('evt-'))
    def test_whitespace_comparison_keeps_original(self):
        left=field('07:30');right=field(' 07:30 ');self.assertEqual(triple_diff(left,right),[])
        self.assertEqual(right['value'],' 07:30 ')

class EnrichmentTests(unittest.TestCase):
    def test_year_from_external_evidence(self):
        b,_,_=setup();r=enrich_dates(b,notice_for(b));e=r['events'][0]
        self.assertEqual(effective(e)['date'],'2026-09-19');self.assertIsNone(e['fields']['date']['value'])
        self.assertEqual(e['fields']['date']['quote'],'09.19')
    def test_wrong_month_day_rejected(self):
        b,_,_=setup();n=notice_for(b);n['bindings'][0]['date']='2026-09-20'
        with self.assertRaises(ValueError):enrich_dates(b,n)
    def test_quote_not_in_notice_rejected(self):
        b,_,_=setup();n=notice_for(b);n['bindings'][0]['year_quote']='2026 偽物'
        with self.assertRaises(ValueError):enrich_dates(b,n)
    def test_published_time_not_substituted_for_year(self):
        b,_,_=setup();n=notice_for(b);n['text']='活動資料';n['bindings'][0]['year_quote']='活動資料'
        with self.assertRaises(ValueError):enrich_dates(b,n)
    def test_notice_needs_same_event_confirmation(self):
        b,_,_=setup();n=notice_for(b);n['bindings'][0]['same_event_confirmed']=False
        with self.assertRaises(ValueError):enrich_dates(b,n)
    def test_reuse_notice_only_when_raw_date_unchanged(self):
        b,c,m=setup();b=enrich_dates(b,notice_for(b));m['base_sha256']=fingerprint(b)
        p=make_plan(b,c,m);a=next(e for e in p['projected_events'] if e['id']==b['events'][0]['id'])
        self.assertEqual(effective(a)['date'],'2026-09-19')
    def test_date_evidence_change_drops_enrichment(self):
        b,c,m=setup();b=enrich_dates(b,notice_for(b));c['events'][1]['date']=field(None,'09.20','unclear')
        m.update(base_sha256=fingerprint(b),candidate_sha256=fingerprint(c));p=make_plan(b,c,m)
        a=next(e for e in p['projected_events'] if e['id']==b['events'][0]['id']);self.assertNotIn('date',a['enrichments'])
    def test_notice_venue_mismatch_rejected(self):
        b,_,_=setup();n=notice_for(b);n['text']='2026 年教學活動。9/19 彰化大佛環山步道。'
        n['bindings'][0]['event_quote']='9/19 彰化大佛環山步道'
        with self.assertRaises(ValueError) as ctx:
            enrich_dates(b,n)
        self.assertIn('不符，需人工處理衝突',str(ctx.exception))

class AdoptionTests(unittest.TestCase):
    def setUp(self):
        self.b,self.c,self.m=setup();self.p=make_plan(self.b,self.c,self.m);self.d=approved(self.p)
    def test_apply_new_version_and_preserve_old(self):
        old=deepcopy(self.b);a,u=apply_review(self.b,self.c,self.p,self.d,active_version=self.b['version_id'])
        self.assertEqual(self.b,old);self.assertEqual(a['parent_version'],self.b['version_id'])
        self.assertEqual(u['changed_fields'],1)
    def test_review_bound_to_plan(self):
        self.d['plan_sha256']='x'
        with self.assertRaises(ValueError):apply_review(self.b,self.c,self.p,self.d,active_version=self.b['version_id'])
    def test_stale_active_rejected(self):
        with self.assertRaises(ValueError):apply_review(self.b,self.c,self.p,self.d,active_version='other')
    def test_related_field_unchecked_rejected(self):
        self.d['checked_keys']=self.d['checked_keys'][:1]
        with self.assertRaises(ValueError):apply_review(self.b,self.c,self.p,self.d,active_version=self.b['version_id'])
    def test_image_confirmation_required_even_no_change(self):
        b,c,m=setup(change=False);p=make_plan(b,c,m);d=approved(p);d['original_image_checked']=False
        with self.assertRaises(ValueError):apply_review(b,c,p,d,active_version=b['version_id'])
    def test_override_preserves_model(self):
        prior=deepcopy(self.c);e=self.b['events'][0]['id'];self.d['overrides']=[{'event_id':e,'field':'time','triple':field('08:15~11:00'),'reason':'離線核對修訂'}]
        a,_=apply_review(self.b,self.c,self.p,self.d,active_version=self.b['version_id'])
        self.assertEqual(self.c,prior);self.assertEqual(next(x for x in a['events'] if x['id']==e)['fields']['time']['value'],'08:15~11:00')
    def test_override_without_reason_rejected(self):
        e=self.b['events'][0]['id'];self.d['overrides']=[{'event_id':e,'field':'time','triple':field('08:15'),'reason':''}]
        with self.assertRaises(ValueError):apply_review(self.b,self.c,self.p,self.d,active_version=self.b['version_id'])
    def test_override_linked_field_unchecked_rejected(self):
        b,c,m=setup(change=False);p=make_plan(b,c,m);d=approved(p)
        e=b['events'][0]['id']
        d['overrides']=[{'event_id':e,'field':'time','triple':field('08:15~11:00'),'reason':'離線核對修訂'}]
        d['checked_keys']=[e+':time']
        with self.assertRaises(ValueError):
            apply_review(b,c,p,d,active_version=b['version_id'])
        d['checked_keys']=[e+':time',e+':date']
        with self.assertRaises(ValueError):
            apply_review(b,c,p,d,active_version=b['version_id'])
        d['checked_keys'].append(e+':meeting_time')
        a,_=apply_review(b,c,p,d,active_version=b['version_id'])
        self.assertEqual(next(x for x in a['events'] if x['id']==e)['fields']['time']['value'],'08:15~11:00')
    def test_missing_reviewer_rejected(self):
        self.d['reviewer']=''
        with self.assertRaises(ValueError):apply_review(self.b,self.c,self.p,self.d,active_version=self.b['version_id'])

class QueryTests(unittest.TestCase):
    def setUp(self):
        self.b,self.c,m=setup();self.p=make_plan(self.b,self.c,m);self.a,_=apply_review(self.b,self.c,self.p,approved(self.p),active_version=self.b['version_id'])
    def q(self,phase,**args):return query_phase(self.b,self.c,self.p,self.a,args,phase)['result']
    def test_before_is_old_time(self):self.assertEqual(self.q('before',keyword='走讀 A')['events'][0]['time'],'07:30~11:00')
    def test_pending_masks_changed_time(self):
        r=self.q('pending',keyword='走讀 A');self.assertEqual(r['status'],'pending_review');self.assertIsNone(r['events'][0]['time'])
        self.assertEqual(r['events'][0]['venue'],'教學廣場')
    def test_pending_does_not_expose_old_field_evidence(self):
        r=self.q('pending',keyword='走讀 A');self.assertNotIn('field_evidence',r['events'][0])
    def test_unaffected_event_still_searchable(self):
        r=self.q('pending',keyword='走讀 B');self.assertEqual(r['status'],'ok');self.assertEqual(r['events'][0]['time'],'13:30~16:00')
    def test_after_is_new_time(self):self.assertEqual(self.q('after',keyword='走讀 A')['events'][0]['time'],'08:00~11:00')
    def test_unknown_accessibility_stays_unknown(self):self.assertIsNone(self.q('after',keyword='走讀 A')['events'][0]['accessibility'])
    def test_query_records_actual_previous_tool(self):
        q=query_phase(self.b,self.c,self.p,self.a,{'keyword':'走讀 A'},'after')
        self.assertEqual(q['api_calls'],0);self.assertEqual(q['trace'][0]['name'],'search_local_events')
    def test_new_name_search_still_reports_pending(self):
        b,c,m=setup(change=False);c['events'][1]['name']=field('改名場次');m['candidate_sha256']=fingerprint(c);p=make_plan(b,c,m)
        r=query_phase(b,c,p,None,{'keyword':'改名'},'pending')['result']
        self.assertEqual(len(r['events']),1);self.assertEqual(r['status'],'pending_review')
    def test_new_date_filter_does_not_hide_pending_event(self):
        b,c,m=setup(change=False);c['events'][1]['date']=field('2026-09-20');m['candidate_sha256']=fingerprint(c);p=make_plan(b,c,m)
        r=query_phase(b,c,p,None,{'date':'2026-09-20'},'pending')['result']
        self.assertEqual(r['status'],'pending_review');self.assertIsNone(r['events'][0]['date'])
    def test_without_adoption_after_rejected(self):
        with self.assertRaises(ValueError):query_phase(self.b,self.c,self.p,None,{'keyword':'A'},'after')

class UITests(unittest.TestCase):
    def test_script_payload_escaped(self):self.assertNotIn('</script>',js({'x':'</script><script>alert(1)</script>'}))
    def test_pages_are_generated_from_data(self):
        b,c,m=setup();p=make_plan(b,c,m)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);a=root/'before.png';z=root/'after.png';a.write_bytes(PNG);z.write_bytes(NEW_PNG)
            write_matching(root/'MATCH.html',b,c,a,z);write_review(root/'REVIEW.html',b,c,p,a,z)
            self.assertIn('matching.json',(root/'MATCH.html').read_text())
            self.assertIn('decision.json',(root/'REVIEW.html').read_text())
    def test_report_escapes_values(self):
        b,c,m=setup();b['source_kind']='<script>'
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'REPORT.html';write_summary(target,b,None,None,[],None)
            self.assertIn('&lt;script&gt;',target.read_text())

if __name__=='__main__':unittest.main()
