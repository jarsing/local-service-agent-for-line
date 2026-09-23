"""實際相依範圍的離線回歸；數量動態彙總，不把 SDK 未執行算成功。"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
from evidence import create_run,execution_info,sources,write_json

HERE=Path(__file__).resolve().parent
CORE=[('day02',['test_demo']),('day08',['test_confirmation']),
      ('day09',['test_handoff','test_reporting']),('day10',['test_recovery','test_packaging'])]
SDK=[('day09',['test_adk_offline']),('day10',['test_adk_offline'])]


def main() -> int:
    p=argparse.ArgumentParser(description='Day 1 規格、Day 2/8/9/10 的具名離線回歸')
    p.add_argument('--sdk',action='store_true',help='核心外加真正 ADK 的腳本模型整合')
    p.add_argument('--group',choices=['core','sdk','all'],default='core',help='供 CI 分開 job 執行')
    p.add_argument('--out',type=Path,default=HERE/'output')
    p.add_argument('--origin',choices=['reader_local','author_local','assistant_check'],default='reader_local')
    args=p.parse_args(); group='all' if args.sdk else args.group
    output=create_run(args.out,'verify'); before=sources()
    report={'mode':'OFFLINE_VERIFICATION','selected_group':group,'execution':execution_info(args.origin),
            'source_files':before,'groups':[],'success':False}
    selected=(CORE if group=='core' else SDK if group=='sdk' else CORE+SDK)
    for index,(day,modules) in enumerate(selected,1):
        target=output/f'{index:02d}-{day}.json'
        command=[sys.executable,str(HERE/'test_driver.py'),'--day',day,'--modules',*modules,'--json',str(target)]
        try:
            result=subprocess.run(command,cwd=HERE.parents[1],capture_output=True,text=True,timeout=180,check=False)
            text=result.stdout+result.stderr; code=result.returncode
            item=json.loads(target.read_text('utf-8')) if target.is_file() else {'success':False,'status':'missing_report'}
        except subprocess.TimeoutExpired:
            text='TEST_PROCESS_TIMEOUT\n'; code=124; item={'success':False,'status':'timeout'}
        item.update(exit_code=code,command=command)
        item['success']=bool(item.get('success') and code==0)
        report['groups'].append(item)
        with (output/f'{index:02d}-{day}.txt').open('x',encoding='utf-8') as f:f.write(text)
        print(text,end='')
    report['source_unchanged']=before==sources()
    report['success']=bool(report['groups']) and all(g['success'] for g in report['groups']) and report['source_unchanged']
    report['totals']={key:sum(g.get(key,0) for g in report['groups'])
                      for key in ('run','passed','failures','errors','skipped')}
    report['sdk_status']='not_requested' if group=='core' else ('passed' if all(g['success'] for g in report['groups'][-len(SDK):]) else 'not_passed')
    write_json(output/'verification.json',report)
    print('總結：',report['totals'],'success=',report['success'])
    print('驗證報告：',output/'verification.json')
    return 0 if report['success'] else 1


if __name__=='__main__':
    raise SystemExit(main())
