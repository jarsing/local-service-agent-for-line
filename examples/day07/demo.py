"""先用離線資料看懂版本流程；此輸出不屬於 Gemini／作者的真實海報實驗。"""
from __future__ import annotations
import argparse
from pathlib import Path
from fixtures import setup,approved,PNG,NEW_PNG
from versioning import folder,save,make_plan,apply_review,query_phase
from ui import write_matching,write_review,write_summary


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('output/day07'));a=p.parse_args(argv)
    out=folder(a.output,'demo');b,c,m=setup();plan=make_plan(b,c,m);d=approved(plan)
    after,audit=apply_review(b,c,plan,d,active_version=b['version_id'])
    for name,obj in [('base.json',b),('candidate.json',c),('matching.json',m),('plan.json',plan),('decision.json',d),('catalog.after.json',after),('adoption.json',audit)]:save(out/name,obj)
    (out/'source_before.png').write_bytes(PNG);(out/'source_after.png').write_bytes(NEW_PNG)
    save(out/'session.json',{'kind':'LOCAL_DAY07_SESSION','origin':'offline_demo','warning':'離線夾具，不是 Gemini 或作者實測。'})
    queries=[]
    for phase in ['before','pending','after']:
        q=query_phase(b,c,plan,after,{'keyword':'教學走讀 A'},phase);queries.append(q);save(out/'queries'/f'{phase}.json',q)
        print(phase,q['result']['status'],q['result']['events'][0]['time'])
    write_matching(out/'MATCH.html',b,c,out/'source_before.png',out/'source_after.png')
    write_review(out/'REVIEW.html',b,c,plan,out/'source_before.png',out/'source_after.png')
    write_summary(out/'REPORT.html',b,c,plan,queries,audit)
    print('這是離線示範，圖片為一像素佔位圖；不是活動海報擷取結果。')
    print('報告：',out/'REPORT.html')
    return 0

if __name__=='__main__':raise SystemExit(main())
