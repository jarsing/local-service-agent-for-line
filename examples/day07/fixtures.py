"""明示的離線測試資料：不是主辦公告、模型輸出或作者實測。"""
from __future__ import annotations

import base64
from copy import deepcopy
from versioning import encoded, digest, fingerprint, import_day06, candidate_from_record, matching_template, now

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
NEW_PNG = PNG + b'LOCAL_OFFLINE_FIXTURE'


def field(value=None, quote=None, status=None):
    return {'value':value,'quote':quote if quote is not None else value,
            'status':status or ('stated' if value is not None else 'not_shown')}


def event(name='教學走讀 A', time='07:30~11:00'):
    return {'name':field(name),'date':field(None,'09.19','unclear'),'area':field('彰化市'),
            'time':field(time),'venue':field('教學廣場'),'meeting_time':field(),
            'meeting_point':field(),'accessibility':field()}


def inputs():
    fields=[event(),event('教學走讀 B','13:30~16:00')]
    source={'sha256':digest(PNG),'stored_name':'source.png','mime_type':'image/png',
            'source_ref':'fixture:old-image','source_updated_at':None}
    extraction={'events':fields,'notes':[]}
    rec={'kind':'LOCAL_DAY06_EXTRACTION','mode':'OFFLINE_FIXTURE','origin':'assistant_test',
         'source':source,'requested_model':'offline_fixture','config':{'thinking_level':'LOW'},
         'runs':[{'condition':'guided','status':'EXTRACTED','extraction':extraction}]}
    catalog={'kind':'reviewed_poster_data','version':'fixture-v1','source':source,'review':{'reviewer':'離線測試角色'},
             'events':[{'id':f'poster-{source["sha256"][:12]}-{i+1:02}',
                        **{k:v['value'] for k,v in f.items()},'field_evidence':f} for i,f in enumerate(fields)]}
    rb,cb=encoded(rec),encoded(catalog)
    audit={'kind':'LOCAL_DAY06_REVIEW','reviewer':'離線測試角色','selected_condition':'guided',
           'record_sha256':digest(rb),'source_sha256':digest(PNG),'catalog_sha256':digest(cb),'changes':[]}
    return catalog,audit,rec,cb,rb


def setup(change=True,reorder=True):
    catalog,audit,rec,cb,rb=inputs()
    base=import_day06(catalog,audit,rec,catalog_bytes=cb,record_bytes=rb,image_bytes=PNG)
    fresh=deepcopy(rec)
    fresh['source']={**fresh['source'],'sha256':digest(NEW_PNG),'source_ref':'fixture:new-image'}
    if change:
        fresh['runs'][0]['extraction']['events'][0]['time']=field('08:00~11:00')
    if reorder:
        fresh['runs'][0]['extraction']['events'].reverse()
    candidate=candidate_from_record(fresh,source_kind='offline_fixture')
    matching=matching_template(base,candidate)
    matching.update(confirmed=True,reviewer='離線測試角色',source_relation='離線測試：改時段並交換排序')
    return base,candidate,matching


def approved(plan):
    return {'kind':'LOCAL_ADOPTION_DECISION','approved':True,'original_image_checked':True,
            'reviewer':'離線測試角色','reviewed_at':now(),'plan_sha256':fingerprint(plan),
            'checked_keys':plan['required_review_keys'],'confirmed_removed':plan['removed_event_ids'],
            'overrides':[],'author_observation':'離線案例，供驗證分支，不是作者實測心得。'}


def notice_for(base):
    return {'approved':True,'reviewer':'離線測試角色','source_ref':'fixture:official-text',
            'retrieved_at':now(),'published_at':None,
            'text':'2026 年教學活動。9/19 教學走讀 A。',
            'bindings':[{'event_id':base['events'][0]['id'],'same_event_confirmed':True,
                         'date':'2026-09-19','year_quote':'2026 年教學活動',
                         'event_quote':'9/19 教學走讀 A'}]}
