"""Day 9 ADK 執行入口；預設離線替身，--live 必須另附 --approve-live。"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from day08_gateway import Actor, Day08Gateway
from handoff import HandoffService
from demo import QUESTION, tool_args
from provenance import create_run, write_json, environment, source_snapshot, sha256
from reporting import build_report

DEFAULT_MODEL='gemini-3.8-flash'  # 沿用 Day 8 設定，不代表已驗證所有帳號可用。

def read_key(env_file: Path | None) -> str:
    key=os.getenv('GEMINI_API_KEY','').strip()
    if key:return key
    if env_file:
        for line in env_file.read_text('utf-8').splitlines():
            if line.strip().startswith('GEMINI_API_KEY='):
                return line.strip().split('=',1)[1].strip().strip('"\'')
    raise ValueError('缺少 GEMINI_API_KEY；可指定既有私人 --env-file，不會搜尋其他資料夾。')

async def execute(args,output: Path):
    from runtime import run_two_turns
    from google import genai
    from google.adk.models.google_llm import Gemini
    from google.genai import types
    actor=Actor('local-demo','demo-user','day09-session')
    gateway=Day08Gateway()
    service=HandoffService(output/'handoff.sqlite3',gateway,lambda a:a==actor)
    offer=gateway.prepare(actor,QUESTION)
    confirmation=gateway.record_user_decision(actor,offer['confirmation_id'],approved=True)
    if confirmation['status']!='confirmation_recorded':
        raise RuntimeError('本次 Day 8 前置確認未通過。')
    send_args=tool_args(offer)
    client=None
    try:
        if args.live:
            key=read_key(args.env_file)
            client=genai.Client(api_key=key,vertexai=False,
                http_options=types.HttpOptions(api_version='v1beta',
                    base_url='https://generativelanguage.googleapis.com',timeout=12000,
                    retry_options=types.HttpRetryOptions(attempts=1)))
            model=Gemini(model=args.model,client=client,use_interactions_api=False)
        else:
            from scripted_model import ScriptedHandoffModel
            model=ScriptedHandoffModel(model='day09-scripted',requests=[send_args,send_args])
        report=await run_two_turns(model,service,actor,send_args,
            mode='LIVE_GEMINI' if args.live else 'OFFLINE_ADK',origin=args.origin)
        report.update({'requested_model':args.model if args.live else 'day09-scripted',
            'thinking_level':'LOW','http_attempts':1 if args.live else 0,
            'confirmation_input':'本次測試程式透過 Day 8 核心明確代送 approved=True；非真人點按',
            'confirmation_result':confirmation,'database_sha256':sha256(output/'handoff.sqlite3')})
        return report
    finally:
        if client:
            try:
                await client.aio.aclose()
                client.close()
            except Exception:
                pass  # 關閉連線失敗不覆蓋已取得的實驗紀錄。

def main():
    p=argparse.ArgumentParser(description='Day 9：ADK 建單與同鍵重送；預設離線替身')
    p.add_argument('--live',action='store_true')
    p.add_argument('--approve-live',action='store_true',help='作者核准後才使用；最多6次模型請求，無自動重試')
    p.add_argument('--model',default=DEFAULT_MODEL)
    p.add_argument('--env-file',type=Path)
    p.add_argument('--out',type=Path,default=Path(__file__).parent/'output')
    p.add_argument('--origin',choices=['author_local','assistant_check','reader_local'],default='reader_local')
    args=p.parse_args()
    if args.live and not args.approve_live:
        p.error('--live 需要 --approve-live；請先確認呼叫範圍與費用。')
    os.environ['OTEL_SDK_DISABLED']='true'
    output=create_run(args.out,'live' if args.live else 'adk')
    try:
        if args.live:
            report=asyncio.run(execute(args,output))
        else:
            from verify import no_network
            with no_network():
                report=asyncio.run(execute(args,output))
    except Exception as exc:
        report={'mode':'LIVE_GEMINI' if args.live else 'OFFLINE_ADK','origin':args.origin,
                'success':False,'error':{'type':type(exc).__name__},'environment':environment(),
                'source_files':source_snapshot(),'semantic_review':'not_run'}
    write_json(output/'report.json',report)
    build_report(report,output/'REPORT.html')
    print('結果：',report.get('success'),'報告：',output/'report.json')
    return 0 if report.get('success') else 1

if __name__=='__main__':
    raise SystemExit(main())
