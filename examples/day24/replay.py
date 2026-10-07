"""Replay captured read-only choices through the existing local application.

This is a later local execution using a scripted interpreter, not the original
SDK call's downstream events, and not a Live ADK run. No model/LINE API is called.
No replacement backend is supplied if the original Day 12-18 modules are absent.
"""
from __future__ import annotations
import argparse
import asyncio
from pathlib import Path
from .evidence import load,save,dataset,digest
from .audit import audit
from .capture import revision

READ_ONLY={'search_local_events','search_local_places','show_local_help'}

async def run(capture: Path,out: Path) -> int:
    report=audit(capture)
    cases={c['id']:c for c in dataset(capture/'dataset.json')['cases']}
    out.mkdir(parents=True,exist_ok=False)
    try:
        from examples.day18.local_adapter import run_case,SCRIPTED_PLANS
        from examples.day18.scoring import score_case
    except ModuleNotFoundError as exc:
        save(out/'summary.json',{'status':'BLOCKED','reason':'BASELINE_MODULE_MISSING',
                                'module':exc.name,'executed':0,'denominator':9})
        return 2
    results=[]
    # Sequential by design: scripted fixture override is process-local, restored below.
    for row in report['rows']:
        if row['group']!='route':continue
        case=cases[row['case_id']]
        if row['status']!='CAPTURED' or len(row.get('calls',[]))!=1 or row['calls'][0]['name'] not in READ_ONLY:
            results.append({'id':case['id'],'status':'BLOCKED','reason':'NO_VALID_READONLY_CAPTURE'})
            continue
        name,args=row['calls'][0]['name'],row['calls'][0]['arguments']
        previous=SCRIPTED_PLANS.get(case['scenario'])
        folder=out/case['id'];folder.mkdir()
        try:
            SCRIPTED_PLANS[case['scenario']]=(name,args)
            obs=await run_case(case,folder,mode='offline')
            grade=score_case(case,obs)
            result={'id':case['id'],'status':grade['status'],'grade':grade,
                    'source_request_sha256':digest((capture/'calls'/row['key']/'request.json').read_bytes()),
                    'source_response_sha256':digest((capture/'calls'/row['key']/'sdk_response.json').read_bytes()),
                    'observation':obs,'origin':'CAPTURED_CHOICE_REPLAYED_LOCALLY_WITH_SCRIPTED_INTERPRETER',
                    'original_live_downstream':False,**revision()}
        except Exception as exc:
            result={'id':case['id'],'status':'BLOCKED','reason':type(exc).__name__}
        finally:
            if previous is None:SCRIPTED_PLANS.pop(case['scenario'],None)
            else:SCRIPTED_PLANS[case['scenario']]=previous
        save(folder/'replay.json',result);results.append(result)
    summary={'denominator':9,'passed':sum(r['status']=='PASS' for r in results),
             'status':'PASS' if len(results)==9 and all(r['status']=='PASS' for r in results) else 'NOT_PASSED',
             'scope':'later_local_backend_execution_not_original_live_chain',
             'external_model_calls':0,'line_calls':0,'rows':results}
    save(out/'summary.json',summary)
    print({k:v for k,v in summary.items() if k!='rows'})
    return 0 if summary['status']=='PASS' else 2


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(argv);return asyncio.run(run(a.run,a.out))

if __name__=='__main__':raise SystemExit(main())
