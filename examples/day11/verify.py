"""保留原 Day 10 入口，分組接 Day 11；來源和測試數量動態彙總。"""
import argparse,json,os,subprocess,sys
from pathlib import Path
from evidence import new_run,dump,execution,source_manifest
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--group',choices=['core','sdk','emulator','all'],default='core')
    p.add_argument('--sdk',action='store_true',help='核心＋ADK，不含尚未啟動的模擬器')
    p.add_argument('--origin',choices=['reader_local','author_local','assistant_check'],default='reader_local')
    p.add_argument('--out',type=Path,default=HERE/'output')
    a=p.parse_args();folder=new_run(a.out,'verify');source=source_manifest()
    selected=['core','sdk'] if a.sdk else ['core','sdk','emulator'] if a.group=='all' else [a.group]
    report={'mode':'OFFLINE_VERIFICATION','groups':[],'execution':execution(a.origin),'source_files':source,
            'selected':selected,'success':False,
            'counting_unit':'test executions in selected groups; backend-specific contract runs are not new independent user scenarios'}
    plans=[]
    for group in selected:
        if group in ('core','sdk'):
            plans.append(('upstream-'+group,[sys.executable,str(REPO/'examples/day10/verify.py'),
                '--group',group,'--origin',a.origin,'--out',str(folder/('upstream-'+group))],group,True))
        module={'core':'test_core','sdk':'test_adk_offline','emulator':'test_emulator'}[group]
        plans.append(('day11-'+group,[sys.executable,str(HERE/'test_driver.py'),'--module',module,
            '--origin',a.origin,'--out',str(folder/('day11-'+group))],group,False))
    for name,cmd,group,upstream in plans:
        try:
            env=dict(os.environ);env['LOCAL_EXECUTION_ORIGIN']=a.origin
            result=subprocess.run(cmd,cwd=REPO,env=env,capture_output=True,text=True,timeout=300 if group=='emulator' else 180)
            code=result.returncode;stdout=result.stdout;stderr=result.stderr
        except subprocess.TimeoutExpired as exc:
            code=124;stdout='';stderr='CHILD_TEST_TIMEOUT\n'
        (folder/(name+'.stdout.txt')).write_text(stdout,encoding='utf-8')
        (folder/(name+'.stderr.txt')).write_text(stderr,encoding='utf-8')
        outputs=list((folder/name).glob('verify-*/verification.json')) if upstream else list((folder/name).glob('tests.json'))
        raw=json.loads(outputs[0].read_text('utf-8')) if len(outputs)==1 else {}
        totals=raw.get('totals',{}) if upstream else raw
        item={'name':name,'group':group,'command':cmd,'exit_code':code,'source':'existing_day10_verifier' if upstream else 'day11_test_driver',
            'result_file':str(outputs[0].relative_to(folder)) if len(outputs)==1 else None,
            'success':bool(code==0 and raw.get('success')),
            'status':raw.get('status','executed' if raw else 'missing_report'),
            'unavailable':bool(raw.get('unavailable') or raw.get('sdk_status')=='not_passed' and totals.get('run',0)==0)}
        if upstream and item['unavailable']:item['status']='upstream_dependency_unavailable'
        for field in ('run','passed','failures','errors','skipped'):item[field]=totals.get(field,0)
        report['groups'].append(item)
        print(name,':', {k:item[k] for k in ('run','passed','failures','errors','skipped','exit_code','status')})
    report['totals']={k:sum(g[k] for g in report['groups']) for k in ('run','passed','failures','errors','skipped')}
    report['source_unchanged']=source==source_manifest()
    report['success']=bool(report['groups']) and all(g['success'] for g in report['groups']) and report['source_unchanged']
    report['unexecuted_groups']=[g['name'] for g in report['groups'] if not g['success'] and g['run']==0]
    report['exit_code']=0 if report['success'] else 1
    dump(folder/'verification.json',report)
    print('本次合計：',report['totals'],'success=',report['success']);print('報告：',folder/'verification.json')
    return report['exit_code']

if __name__=='__main__':raise SystemExit(main())
