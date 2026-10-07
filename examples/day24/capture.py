"""Plan or explicitly capture 9 SDK routes + 6 A/B rows. Never sends LINE messages.

This is a versioned direct-SDK experiment, NOT the production ADK interpreter.
No expected answer, case ID, DB record, user ID, or credential enters model input.
The real Gemini path needs google-genai==2.23.0 and has not been Live-validated
by the offline tests. Defaults only produce an unexecuted experiment plan.
"""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone
from .evidence import ROOT, DATASET, MODEL, LIVE_IDS, AB_IDS, TOOL_FIELDS, ENUMS, encoded, digest, save, dataset

HERE = Path(__file__).resolve().parent
VERSION = 'day24-direct-routing-v1'
CONFIG = {'temperature':0,'candidate_count':1,'max_output_tokens':2048,
          'automatic_function_calling':{'disable':True},
          'tool_config':{'function_calling_config':{'mode':'AUTO'}}}
DESCRIPTIONS = {
 'search_local_events':'查地方活動公開快照；沒有集合資訊時由後端說明未知。',
 'search_local_places':'查精選蔬食店家快照；缺鄉鎮由後端追問，不保證即時營業。',
 'show_local_help':'不支援需求或超出服務範圍的固定安全入口；reason 為 unsupported。',
 'propose_dietary_memory':'提出飲食記憶確認；使用者未按同意前不得保存。',
 'request_memory_management':'要求查看、更正、忘記偏好的操作介面；不直接確認修改。',
}


def validate_declarations(tools: list[dict]) -> None:
    for t in tools:
        params = t.get('parameters', {})
        for prop_name, prop in params.get('properties', {}).items():
            if 'enum' in prop:
                if any(v == '' for v in prop['enum']):
                    raise ValueError(f"EMPTY_ENUM_FORBIDDEN:{t['name']}.{prop_name}")


def tool_declarations() -> list[dict]:
    tools = []
    for name, fields in TOOL_FIELDS.items():
        properties = {f:{'type':'STRING'} for f in fields}
        for k, values in ENUMS.get(name,{}).items():
            # OpenAPI / Gemini API strictly forbids empty string in enum arrays.
            if values and not any(v == '' for v in values):
                properties[k]['enum'] = list(values)
        tools.append({'name':name,'description':DESCRIPTIONS[name],
             'parameters':{'type':'OBJECT','properties':properties,'required':list(fields)}})
    validate_declarations(tools)
    return tools


def revision() -> dict:
    def git(*args):
        p = subprocess.run(['git','-C',str(ROOT),*args],capture_output=True,text=True,timeout=5)
        return p.stdout.strip() if p.returncode == 0 else None
    try:
        head,status = git('rev-parse','HEAD'),git('status','--porcelain')
    except (OSError,subprocess.SubprocessError):
        head,status = None,None
    return {'source_commit':head,'working_tree_dirty':bool(status) if status is not None else None}


def create_plan(path: Path = DATASET, instruction_path: Path | None = None) -> dict:
    data = dataset(path)
    instruction = (instruction_path or HERE/'instruction.txt').read_text(encoding='utf-8')
    tools = tool_declarations()
    source = {p.name:digest(p.read_bytes()) for p in sorted(HERE.glob('*.py'))}
    index = {c['id']:c for c in data['cases']}
    items = [{'key':f'route-{cid}','case_id':cid,'group':'route','budget':0} for cid in LIVE_IDS]
    for i,cid in enumerate(AB_IDS):
        for group,budget in ((('A',0),('B',1024)) if i%2==0 else (('B',1024),('A',0))):
            items.append({'key':f'{cid}-{group}','case_id':cid,'group':group,'budget':budget})
    for item in items:
        item['input'] = index[item['case_id']]['input']
        item['input_sha256'] = digest(item['input'].encode())
    return {
        'schema_version':VERSION,'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'runtime':{'python':platform.python_version(),'system':platform.system()},
        'state':'PLANNED_NOT_EXECUTED','model_id':MODEL,'endpoint':'generateContent:v1beta:DeveloperAPI',
        'sdk_version':'2.23.0','sdk_attempts':1,'measurement_scope':'single_generate_content_call_no_queue_no_backend',
        'dataset_sha256':digest(path.read_bytes()),'instruction':instruction,'tools':tools,
        'instruction_sha256':digest(instruction.encode()),'tools_sha256':digest(encoded(tools)),
        'config_base':CONFIG,'config_base_sha256':digest(encoded(CONFIG)),
        'source_files':source,'source_tree_sha256':digest(encoded(source)),
        'rate_card_sha256':digest((HERE/'rate_card.json').read_bytes()),
        'origin':'DIRECT_SDK_CAPTURE','request_count_limit':15,'items':items,**revision()}


def request_for(plan: dict, item: dict) -> dict:
    config = dict(plan['config_base'])
    config.update(system_instruction=plan['instruction'],tools=[{'function_declarations':plan['tools']}],
                  thinking_config={'thinking_budget':item['budget'],'include_thoughts':False})
    return {'model':plan['model_id'],'contents':item['input'],'config':config}


class GenaiTransport:
    def __init__(self,key: str, timeout_ms: int):
        if importlib.metadata.version('google-genai') != '2.23.0':
            raise ValueError('PIN_GOOGLE_GENAI_2_23_0')
        from google import genai
        from google.genai import types
        self.types = types
        self.client = genai.Client(api_key=key,http_options=types.HttpOptions(
            api_version='v1beta',timeout=timeout_ms,retry_options=types.HttpRetryOptions(attempts=1)))

    def generate(self, request: dict) -> dict:
        response = self.client.models.generate_content(model=request['model'],contents=request['contents'],
            config=self.types.GenerateContentConfig(**request['config']))
        # This is the complete SDK object serialization, not raw HTTP bytes.
        return response.model_dump(mode='json',by_alias=True,exclude_none=False)

    def close(self):
        self.client.close()


def execute(plan: dict, out: Path, transport, *, interval: float = 2.0, sleeper=time.sleep, clock=time.perf_counter) -> None:
    previous_end = None
    for item in plan['items']:
        if previous_end is not None:
            sleeper(max(0,interval-(clock()-previous_end)))
        request = request_for(plan,item)
        folder = out/'calls'/item['key']
        save(folder/'request.json',request)
        record = {k:plan[k] for k in ('origin','model_id','endpoint','sdk_version','sdk_attempts',
            'measurement_scope','dataset_sha256','instruction_sha256','tools_sha256',
            'source_tree_sha256','config_base_sha256','rate_card_sha256')}
        record.update({k:item[k] for k in ('case_id','input_sha256','budget','group')})
        record.update(key=item['key'],started_at_utc=datetime.now(timezone.utc).isoformat(),
                      request_sha256=digest((folder/'request.json').read_bytes()))
        started = clock()
        try:
            response = transport.generate(request)
            elapsed = (clock()-started)*1000
            save(folder/'sdk_response.json',response)
            record.update(status='CAPTURED',elapsed_ms=elapsed,
                          response_sha256=digest((folder/'sdk_response.json').read_bytes()))
        except Exception as exc:
            elapsed = (clock()-started)*1000
            code = getattr(exc,'code',None)
            status_text = getattr(exc,'status',None)
            msg = getattr(exc,'message',None)
            safe_msg = str(msg).split('\n')[0][:500] if (msg and isinstance(msg,str)) else None
            # Never save str(exc): it can include credentials, headers, or private request text.
            record.update(status='ERROR',elapsed_ms=elapsed,error_type=type(exc).__name__,
                          error_code=code if type(code) is int else None,
                          error_status=status_text if isinstance(status_text,str) else None,
                          error_message=safe_msg)
        previous_end = clock()
        save(folder/'record.json',record)
    save(out/'capture_state.json',{'state':'ATTEMPTED_ALL_PLANNED_CALLS','planned_calls':len(plan['items']),
                                  'line_calls':0,'tool_executions':0,'backend_scope':'NOT_EXECUTED'})


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,default=DATASET)
    p.add_argument('--instruction',type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--capture',action='store_true')
    p.add_argument('--approve-external',action='store_true')
    p.add_argument('--max-calls',type=int,default=15)
    p.add_argument('--interval',type=float,default=2.0)
    p.add_argument('--timeout-ms',type=int,default=18000)
    args=p.parse_args(argv)
    if args.max_calls!=15 or args.interval<0.5 or args.interval>60 or not 1000<=args.timeout_ms<=18000:
        p.error('Require exactly 15 calls, interval 0.5..60 seconds, timeout 1000..18000ms')
    plan=create_plan(args.dataset,args.instruction)
    plan['transport_policy']={'interval_seconds':args.interval,'timeout_ms':args.timeout_ms,
                              'concurrency':1,'automatic_retries':0}
    args.out.mkdir(parents=True,exist_ok=False)
    save(args.out/'plan.json',plan)
    (args.out/'dataset.json').write_bytes(args.dataset.read_bytes())
    (args.out/'rate_card.json').write_bytes((HERE/'rate_card.json').read_bytes())
    if not args.capture:
        print('PLANNED_NOT_EXECUTED: 9 routes + 6 A/B; no external call.')
        return 0
    if not args.approve_external:
        p.error('--capture requires --approve-external; plan saved but no request made')
    if os.getenv('GOOGLE_GENAI_USE_VERTEXAI','').lower() not in ('','0','false'):
        p.error('This experiment only supports Developer API')
    key=os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        save(args.out/'capture_state.json',{'state':'BLOCKED','reason':'API_KEY_MISSING'})
        return 2
    try:
        transport=GenaiTransport(key,args.timeout_ms)
    except Exception as exc:
        save(args.out/'capture_state.json',{'state':'BLOCKED','reason':'SDK_SETUP_'+type(exc).__name__})
        return 2
    try:
        execute(plan,args.out,transport,interval=args.interval)
    finally:
        transport.close()
    print('Capture files saved. Run audit; capture completion is not a PASS verdict.')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
