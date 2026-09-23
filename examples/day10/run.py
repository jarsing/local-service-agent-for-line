"""ADK 離線替身／另核准真實 Gemini；只跑一個指定案例，無隱藏批次。"""
from __future__ import annotations
import argparse
import asyncio
from contextlib import nullcontext
import os
from pathlib import Path
from evidence import create_run,execution_info,sources,write_json,no_network
from reporting import build_report


def parse_env(path: Path) -> str | None:
    # 只接受明示檔案，不搜尋其他日次或使用者資料夾；沒有 shell eval。
    result=None
    for line in path.read_text('utf-8').splitlines():
        line=line.strip()
        if line.startswith('GEMINI_API_KEY='):
            value=line.split('=',1)[1].strip()
            if len(value)>1 and value[0]==value[-1] and value[0] in "\"'": value=value[1:-1]
            result=value
    return result


async def execute(args, output):
    from scenarios import prepare_case
    from runtime import run_case
    from google.genai import types
    client=None
    if args.live:
        from google import genai
        from google.adk.models.google_llm import Gemini
        key=parse_env(args.env_file) if args.env_file else os.getenv('GEMINI_API_KEY')
        if not key: raise ValueError('GEMINI_API_KEY_MISSING')
        client=genai.Client(api_key=key,vertexai=False,http_options=types.HttpOptions(
            api_version='v1beta',timeout=12000,retry_options=types.HttpRetryOptions(attempts=1)))
        model=Gemini(model=args.model,client=client,use_interactions_api=False)
    else:
        from scripted_model import ScriptedRecoveryModel
        model=ScriptedRecoveryModel()
    try:
        case=prepare_case(args.case,output/args.case)
        return await run_case(model,case,output/args.case,mode='LIVE_GEMINI' if args.live else 'OFFLINE_ADK')
    finally:
        if client:
            await client.aio.aclose()
            client.close()


def main() -> int:
    p=argparse.ArgumentParser(description='Day 10 ADK；預設固定腳本模型，真實模型需雙旗標及明確模型名稱')
    p.add_argument('--case',choices=['baseline','after_commit','before_write','lookup_unavailable'],default='after_commit')
    p.add_argument('--out',type=Path,default=Path(__file__).parent/'output')
    p.add_argument('--origin',choices=['author_local','assistant_check','reader_local'],default='reader_local')
    p.add_argument('--live',action='store_true'); p.add_argument('--approve-live',action='store_true')
    p.add_argument('--model',help='真實呼叫必填帳號當時支援的精確模型識別；不自動改用其他模型')
    p.add_argument('--env-file',type=Path)
    args=p.parse_args()
    if args.live and (not args.approve_live or not args.model):
        p.error('--live 同時需要 --approve-live 與 --model；每次最多9次模型請求、3次工具呼叫。')
    if not args.live and (args.env_file or args.model or args.approve_live):
        p.error('私人設定與模型選擇僅用在 --live；離線模式不讀金鑰。')
    if args.live and os.getenv('GITHUB_ACTIONS')=='true':
        p.error('Day 10 日常 CI 只允許離線；真實模型評測另有後續核准流程。')
    output=create_run(args.out,'live' if args.live else 'adk'); before=sources()
    report={'mode':'LIVE_GEMINI' if args.live else 'OFFLINE_ADK','execution':execution_info(args.origin),
            'model':args.model if args.live else 'local-day10-scripted','source_files':before,
            'cases':[],'success':False,'external_api_calls':'not_started'}
    try:
        with nullcontext() if args.live else no_network():
            case=asyncio.run(execute(args,output))
        report['cases']=[case]
        report['success']=case['technical_checks_passed']
        report['external_api_calls']=case['model_calls'] if args.live else 0
    except Exception as exc:
        report['error']={'type':type(exc).__name__}
        report['external_api_calls']='unknown_on_error' if args.live else 0
        if isinstance(exc,(ImportError,ModuleNotFoundError)):
            report['sdk_status']='dependency_unavailable'
    report['source_unchanged']=before==sources()
    report['success']=report['success'] and report['source_unchanged']
    write_json(output/'report.json',report); build_report(report,output/'REPORT.html')
    print('技術鏈核對：',report['success'],'報告：',output/'REPORT.html')
    return 0 if report['success'] else 1


if __name__=='__main__':
    raise SystemExit(main())
