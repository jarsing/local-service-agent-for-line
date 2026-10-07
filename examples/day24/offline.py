"""Run the unchanged Day 18 application harness, never a replacement 20-item checklist.

Requires the existing repository modules. Missing modules are BLOCKED; no stubs.
Source hashes and logs are saved. This does not run Live Gemini or deploy anything.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone
from .evidence import ROOT,DATASET,dataset,load,save,digest
from .capture import revision


def run(out: Path) -> int:
    dataset()
    out.mkdir(parents=True,exist_ok=False)
    relative=['examples/day12','examples/day13','examples/day14','examples/day15','examples/day16','examples/day17','examples/day18']
    missing=[p for p in relative if not (ROOT/p).is_dir()]
    manifest={'scope':'original_day18_application_harness_no_Gemini_no_LINE',
              'created_at_utc':datetime.now(timezone.utc).isoformat(),
              'dataset_sha256':digest(DATASET.read_bytes()),**revision(),
              'required_baseline_missing':missing,
              'source_hashes':{str(p.relative_to(ROOT)):digest(p.read_bytes()) for folder in relative
                               for p in sorted((ROOT/folder).rglob('*')) if p.is_file() and p.suffix in ('.py','.json')}}
    save(out/'manifest.json',manifest)
    if missing:
        save(out/'summary.json',{'status':'BLOCKED','denominator':20,'executed':0,'passed':None,
              'reason':'BASELINE_MODULES_MISSING','missing':missing,'model_accuracy':None})
        print('BLOCKED: merge public-files into the original repository; no 20-case PASS is claimed.')
        return 2
    command=[sys.executable,'-m','examples.day18.verify_eval','--mode','offline','--dataset',str(DATASET),
             '--out',str((out/'application').resolve())]
    p=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=300)
    (out/'selftest_application.log').write_text(p.stdout+'\n'+p.stderr,encoding='utf-8')
    result_path=out/'application/results.json'
    if not result_path.exists():
        save(out/'summary.json',{'status':'BLOCKED','reason':'HARNESS_RESULT_MISSING','returncode':p.returncode,
                                'denominator':20,'executed':0,'passed':None})
        return 2
    result=load(result_path)
    from examples.day18.scoring import score_case
    idx={r['id']:r for r in result['rows']}
    expected=dataset()['cases']
    if len(result['rows'])!=20 or set(idx)!={c['id'] for c in expected}:
        raise ValueError('FULL_TWENTY_APPLICATION_CASES_REQUIRED')
    grades=[score_case(c,idx[c['id']]['observation']) for c in expected]
    summary={'status':'PASS' if p.returncode==0 and all(g['status']=='PASS' for g in grades) else 'NOT_PASSED',
      'denominator':20,'passed':sum(g['status']=='PASS' for g in grades),
      'executed':sum(g['status'] in ('PASS','FAIL') for g in grades),
      'coverage_needs_review':[g['id'] for g in grades if g.get('coverage',{}).get('status')=='NEEDS_REVIEW'],
      'model_accuracy':None,'result_sha256':digest(result_path.read_bytes()),'returncode':p.returncode}
    save(out/'summary.json',summary);print(summary)
    return 0 if summary['status']=='PASS' else 2


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    return run(p.parse_args(argv).out)

if __name__=='__main__':raise SystemExit(main())
