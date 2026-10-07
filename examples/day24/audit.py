"""Recompute tables from complete captured SDK objects; never promote a plan to Live."""
from __future__ import annotations
import argparse
from pathlib import Path
from decimal import Decimal
from .evidence import (DATASET,LIVE_IDS,AB_IDS,COMPARE_FIELDS,MODEL,load,save,dataset,digest,encoded,
                       safe_read,calls,route_grade,usage,estimate,comparable,finite_time)
from .capture import request_for


def audit(root: Path) -> dict:
    plan=load(root/'plan.json')
    data=dataset(root/'dataset.json')
    if digest((root/'dataset.json').read_bytes())!=plan['dataset_sha256']:
        raise ValueError('DATASET_HASH_MISMATCH')
    if digest((root/'rate_card.json').read_bytes())!=plan['rate_card_sha256']:
        raise ValueError('RATE_HASH_MISMATCH')
    if plan.get('model_id')!=MODEL or plan.get('sdk_attempts')!=1:
        raise ValueError('MODEL_OR_ATTEMPTS_MISMATCH')
    if digest(plan['instruction'].encode())!=plan['instruction_sha256']:
        raise ValueError('INSTRUCTION_HASH_MISMATCH')
    if digest(encoded(plan['tools']))!=plan['tools_sha256'] or digest(encoded(plan['config_base']))!=plan['config_base_sha256']:
        raise ValueError('TOOLS_OR_CONFIG_HASH_MISMATCH')
    if digest(encoded(plan['source_files']))!=plan['source_tree_sha256']:
        raise ValueError('SOURCE_TREE_HASH_MISMATCH')
    expected_keys={f'route-{x}' for x in LIVE_IDS}|{f'{x}-{g}' for x in AB_IDS for g in ('A','B')}
    if len(plan['items'])!=15 or {x['key'] for x in plan['items']}!=expected_keys:
        raise ValueError('EXACT_FIFTEEN_ITEMS_REQUIRED')
    found={x.name for x in (root/'calls').iterdir()} if (root/'calls').exists() else set()
    if found-expected_keys:
        raise ValueError('UNPLANNED_CALLS_PRESENT')
    index={c['id']:c for c in data['cases']}
    rows=[]
    for item in plan['items']:
        if item.get('group') == 'route':
            valid = item.get('case_id') in LIVE_IDS and item.get('key') == 'route-'+item['case_id']
        else:
            valid = item.get('group') in ('A','B') and item.get('case_id') in AB_IDS and item.get('key') == item['case_id']+'-'+item['group']
        if not valid:
            raise ValueError('PLAN_KEY_CASE_GROUP_MISMATCH')
        case=index[item['case_id']]
        expected_budget=1024 if item['group']=='B' else 0
        if item['budget']!=expected_budget or item['input']!=case['input'] or item['input_sha256']!=digest(case['input'].encode()):
            raise ValueError('INPUT_OR_BUDGET_DRIFT')
        row={**{k:plan.get(k) for k in COMPARE_FIELDS if k not in ('case_id','input_sha256')},
             **item,'origin':plan['origin'],'route':{'status':'NOT_RUN'},'usage':{'cost_status':'UNKNOWN','usd':None},
             'status':'NOT_RUN','elapsed_ms':None,'served_model_version':None,
             'expected_tools':case['expect']['tools'],'expected_arguments':case['expect'].get('arguments',{})}
        folder=root/'calls'/item['key']
        if not (folder/'record.json').exists():
            rows.append(row);continue
        rec=load(folder/'record.json')
        try:
            for key in COMPARE_FIELDS:
                if rec.get(key)!=row.get(key):
                    raise ValueError('RECORD_IDENTITY_MISMATCH:'+key)
            if rec.get('budget')!=item['budget'] or rec.get('origin')!='DIRECT_SDK_CAPTURE':
                raise ValueError('RECORD_SCOPE_MISMATCH')
            request=safe_read(root,f"calls/{item['key']}/request.json",rec['request_sha256'])
            if request!=request_for(plan,item):
                raise ValueError('SAVED_REQUEST_DOES_NOT_MATCH_FROZEN_PLAN')
            row['elapsed_ms']=finite_time(rec['elapsed_ms'])
            if rec['status']=='ERROR':
                row.update(status='ERROR',error_type=rec.get('error_type'),route={'status':'ERROR'})
                rows.append(row);continue
            if rec['status']!='CAPTURED':
                raise ValueError('CAPTURE_STATUS_REQUIRED')
            response=safe_read(root,f"calls/{item['key']}/sdk_response.json",rec['response_sha256'])
            row['status']='CAPTURED'
            row['served_model_version']=response.get('modelVersion',response.get('model_version'))
            try:
                chosen=calls(response)
                row['calls']=chosen
                row['route']=route_grade(case,chosen)
            except ValueError as exc:
                row['route']={'status':'FAIL','issues':[str(exc)]}
            row['usage']=estimate(usage(response,item['budget']),load(root/'rate_card.json'),plan['model_id'])
        except (ValueError,KeyError,TypeError) as exc:
            row.update(status='INVALID_EVIDENCE',route={'status':'INVALID_EVIDENCE'},
                       usage={'cost_status':'INVALID','usd':None},issue=type(exc).__name__+':'+str(exc))
        rows.append(row)
    by_key={r['key']:r for r in rows}
    routes=[by_key[f'route-{cid}'] for cid in LIVE_IDS]
    pairs=[]
    for cid in AB_IDS:
        a,b=by_key[cid+'-A'],by_key[cid+'-B']
        problems=comparable(a,b)
        if a['status']!='CAPTURED' or b['status']!='CAPTURED': problems.append('PAIR_CAPTURE_INCOMPLETE')
        cost_ok=all(x['usage'].get('cost_status')=='COMPLETE' for x in (a,b))
        route_ok=all(x['route']['status']=='PASS' for x in (a,b))
        pair={'case_id':cid,'status':'NOT_COMPARABLE' if problems else 'COMPARABLE_REQUESTS',
              'issues':problems,'both_routes_pass':route_ok,'cost_complete':cost_ok,
              'delta_model_ms':None,'delta_usd':None,'delta_cost_percent':None,
              'causal_conclusion':'NOT_ESTABLISHED_SINGLE_OBSERVATION_PER_SETTING'}
        if not problems:
            pair['delta_model_ms']=b['elapsed_ms']-a['elapsed_ms']
            if cost_ok:
                av,bv=Decimal(a['usage']['usd']),Decimal(b['usage']['usd'])
                pair['delta_usd']=str(bv-av)
                if av: pair['delta_cost_percent']=str((bv-av)/av*100)
        pairs.append(pair)
    summary={'mode':'OFFLINE_AUDIT_OF_CAPTURE_FILES','route_denominator':9,'ab_denominator':6,
             'route_passed':sum(r['route']['status']=='PASS' for r in routes),
             'route_captured':sum(r['status']=='CAPTURED' for r in routes),
             'route_attempted':sum(r['status'] in ('CAPTURED','ERROR') for r in routes),
             'route_errors':sum(r['status']=='ERROR' for r in routes),
             'route_not_run':sum(r['status']=='NOT_RUN' for r in routes),
             'ab_captured':sum(r['status']=='CAPTURED' for r in rows if r['group']!='route'),
             'comparable_pairs':sum(p['status']=='COMPARABLE_REQUESTS' for p in pairs),
             'complete_cost_rows':sum(r['usage'].get('cost_status')=='COMPLETE' for r in rows if r['group']!='route'),
             'backend_ui':'NOT_EVALUATED_BY_CAPTURE_AUDIT','production':'NOT_EXECUTED',
             'origin_authenticity':'DIGESTS_CHECK_IDENTITY_NOT_EXTERNAL_OCCURRENCE'}
    summary['route_full_denominator_rate']=summary['route_passed']/9 if summary['route_attempted'] else None
    summary['evidence_complete']=all(r['status']=='CAPTURED' for r in rows) and summary['comparable_pairs']==3 and summary['complete_cost_rows']==6
    summary['routing_contract_passed']=all(r['route']['status']=='PASS' for r in rows)
    summary['safe_to_deploy']=False # No backend, transport or deployment assertion is made here.
    return {'summary':summary,'rows':rows,'pairs':pairs}


def table(report: dict) -> str:
    def cell(value):
        if value is None:
            return '待量測'
        if isinstance(value,(dict,list)):
            import json
            value=json.dumps(value,ensure_ascii=False,sort_keys=True)
        return str(value).replace('|','\\|').replace('\n',' ')
    def append_row(values):
        text.append('| '+' | '.join(cell(v) for v in values)+' |')
    text=['# Day 24 擷取核對報告','',
          '直接 SDK 路由與本機後端重播分開；本表沒有 LINE 實機證據。','',
          '## 九題路由：工具要求，不是後端執行','',
          '| 題號 | 原問句 | 預期工具 | 實際工具要求與參數 | 擷取狀態 | 路由判定 |',
          '|---|---|---|---|---|---|']
    for r in report['rows']:
        if r['group']=='route':
            append_row((r['case_id'],r['input'],r['expected_tools'],r.get('calls'),r['status'],r['route']['status']))
    text += ['', '## 六列 A/B：單次模型呼叫觀察','',
             '| 題號 | 組別 | 預算 | 毫秒 | 輸入 | 輸出 | 思考 | 思考來源 | 估計 USD | 路由 |',
             '|---|---|---:|---:|---:|---:|---:|---|---:|---|']
    for r in report['rows']:
        if r['group']!='route':
            u=r['usage']
            append_row((r['case_id'],r['group'],r['budget'],r['elapsed_ms'],u.get('input'),
                        u.get('output'),u.get('thoughts'),u.get('thoughts_origin'),u.get('usd'),r['route']['status']))
    text += ['', '## 配對核對','',
             '| 題號 | 可比較性 | 兩組路由通過 | 成本完整 | B-A 毫秒 | B-A USD | 成本差百分比 |',
             '|---|---|---|---|---:|---:|---:|']
    for pair in report['pairs']:
        append_row((pair['case_id'],pair['status'],pair['both_routes_pass'],pair['cost_complete'],
                    pair['delta_model_ms'],pair['delta_usd'],pair['delta_cost_percent']))
    text += ['', '```json',encoded(report['summary']).decode().rstrip(),'```','',
             'A/B 每題每設定只有一次觀察，差值不是平均效應；來源真實性仍需執行紀錄及人工審閱。']
    return '\n'.join(text)+'\n'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--allow-incomplete',action='store_true')
    args=p.parse_args(argv);args.out.mkdir(parents=True,exist_ok=False)
    result=audit(args.run)
    save(args.out/'audit.json',result)
    (args.out/'TABLES.md').write_text(table(result),encoding='utf-8')
    print(encoded(result['summary']).decode())
    passed=result['summary']['evidence_complete'] and result['summary']['routing_contract_passed']
    return 0 if passed else (0 if args.allow_incomplete else 2)

if __name__=='__main__':raise SystemExit(main())
