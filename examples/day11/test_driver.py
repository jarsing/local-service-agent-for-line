"""單一群組測試入口，輸出具名結果與真實退出碼；未執行不能變 PASS。"""
import argparse,importlib,io,json,os,sys,unittest
from pathlib import Path
from contextlib import nullcontext,redirect_stdout,redirect_stderr
from evidence import dump,execution,no_network

class Result(unittest.TextTestResult):
    def startTest(self,test):
        super().startTest(test);self.names.append(test.id())
    def addSuccess(self,test):
        super().addSuccess(test);self.passes.append(test.id())

def main():
    p=argparse.ArgumentParser();p.add_argument('--module',required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--origin',default='reader_local')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    report={'module':a.module,'execution':execution(a.origin),'success':False,'run':0,'passed':0,
        'failures':0,'errors':0,'skipped':0,'unavailable':False}
    required={'test_adk_offline':['google.adk','google.genai'], 'test_emulator':['google.cloud.firestore','google.auth']}.get(a.module,[])
    # 先驗相依；這是 dependency probe，不是執行那些測試。
    try:
        for module in required:importlib.import_module(module)
        if a.module=='test_emulator':
            from firestore_store import validate_target
            validate_target('demo-local-day11','day11-probe')
    except Exception as exc:
        report.update(status='dependency_or_emulator_configuration_unavailable',unavailable=True,
            error_type=type(exc).__name__,missing_module=getattr(exc,'name',None),exit_code=2)
        dump(a.out/'tests.json',report);print(json.dumps(report,ensure_ascii=False));return 2
    output=io.StringIO()
    use_net=a.module=='test_emulator'
    try:
        with nullcontext() if use_net else no_network():
            suite=unittest.defaultTestLoader.loadTestsFromName(a.module)
            class Detailed(Result):
                def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.names=[];self.passes=[]
            with redirect_stdout(output),redirect_stderr(output):
                result=unittest.TextTestRunner(stream=output,verbosity=2,resultclass=Detailed).run(suite)
        report.update(status='executed',run=result.testsRun,passed=len(result.passes),failures=len(result.failures),
            errors=len(result.errors),skipped=len(result.skipped),test_names=result.names,passed_names=result.passes,
            failed_names=[t.id() for t,_ in result.failures],error_names=[t.id() for t,_ in result.errors],
            success=bool(result.testsRun>0 and result.wasSuccessful() and not result.skipped),
            network='local Firestore emulator RPC' if use_net else 'Python socket/DNS blocked in test interpreter')
    except Exception as exc:
        report.update(status='harness_error',error_type=type(exc).__name__,success=False,errors=1)
        output.write(type(exc).__name__+': '+str(exc)+'\n')
    code=0 if report['success'] else 1;report['exit_code']=code
    (a.out/'tests.txt').write_text(output.getvalue(),encoding='utf-8')
    dump(a.out/'tests.json',report)
    print(output.getvalue(),end='');print(json.dumps(report,ensure_ascii=False))
    return code

if __name__=='__main__':raise SystemExit(main())
