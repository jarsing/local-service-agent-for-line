"""Day 7 操作入口：匯入、補來源、擷取新圖、配對、複核與查詢。"""
from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys

from bridge import DAY06, hashes
from versioning import (load, save, folder, digest, fingerprint, import_day06, enrich_dates,
                        candidate_from_record, make_plan, apply_review, query_phase, require)
from ui import write_matching, write_review, write_summary


def base_path(session: Path) -> Path:
    return session / ('base.enriched.json' if (session/'base.enriched.json').is_file() else 'base.json')


def images(session: Path):
    before = list(session.glob('source_before.*'))
    after = list(session.glob('source_after.*'))
    require(len(before) == 1 and len(after) == 1, '原圖或新圖檔案不齊。')
    return before[0], after[0]


def refresh(session: Path):
    base = load(base_path(session))
    candidate = load(session/'candidate.json') if (session/'candidate.json').is_file() else None
    plan = load(session/'plan.json') if (session/'plan.json').is_file() else None
    adoption = load(session/'adoption.json') if (session/'adoption.json').is_file() else None
    queries = [load(p) for p in sorted((session/'queries').glob('*.json'))] if (session/'queries').exists() else []
    write_summary(session/'REPORT.html',base,candidate,plan,queries,adoption)


def prepare(args) -> Path:
    cp, ap, rp = args.catalog, args.audit, args.day06_run/'verification.json'
    cat, audit, record = load(cp),load(ap),load(rp)
    name = record['source']['stored_name']
    require(Path(name).name == name, '圖片需在指定擷取目錄內。')
    image = args.day06_run/name
    base = import_day06(cat,audit,record,catalog_bytes=cp.read_bytes(),record_bytes=rp.read_bytes(),image_bytes=image.read_bytes())
    session = folder(args.output)
    for src,name in [(cp,'day06_catalog.reviewed.json'),(ap,'day06_review.audit.json'),(rp,'day06_verification.json')]:
        (session/name).write_bytes(src.read_bytes())
    shutil.copyfile(image, session/('source_before'+image.suffix))
    save(session/'base.json',base)
    save(session/'active.json',{'version_id':base['version_id'],'catalog':'base.json'})
    packages = {}
    for package in ('google-genai','pydantic','httpx'):
        try: packages[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: packages[package]=None
    save(session/'session.json',{'kind':'LOCAL_DAY07_SESSION','origin':args.origin,
                               'python':sys.version,'packages':packages,'source_hashes':hashes()})
    print(f'工作紀錄：{session.resolve()}')
    for e in base['events']:
        print(e['id'],e['fields']['name']['value'],e['fields']['date']['quote'])
    refresh(session)
    return session


def notice_template(session: Path):
    base=load(base_path(session))
    template={'kind':'LOCAL_YEAR_NOTICE','approved':False,'reviewer':'',
              'source_ref':'','published_at':None,'retrieved_at':'','text':'',
              'bindings':[{'event_id':e['id'],'same_event_confirmed':False,'date':'',
                           'year_quote':'','event_quote':'','image_date_quote':e['fields']['date']['quote']}
                          for e in base['events'] if e['fields']['date']['value'] is None]}
    save(session/'notice.template.json',template)
    print(session/'notice.template.json')


def enrich(args):
    s=args.session
    require(not (s/'candidate.json').exists(), '日期補全先於新版擷取與配對，避免比較基準中途改變。')
    notice=load(args.notice)
    base=load(s/'base.json')
    result=enrich_dates(base,notice)
    require(not (s/'base.enriched.json').exists(), '本工作紀錄已補公告來源；另一次調整請保留版本另建紀錄。')
    with (s/'notice.accepted.json').open('xb') as f:
        f.write(args.notice.read_bytes())
    save(s/'base.enriched.json',result)
    save(s/'active.json',{'version_id':result['version_id'],'catalog':'base.enriched.json'},replace=True)
    print('已新增公告依據；Day 6 圖片欄位保持原樣。')
    refresh(s)


def capture(args):
    s=args.session
    require(not (s/'candidate.json').exists(), '此工作紀錄已有候選，另一輪請建立新工作紀錄。')
    if args.from_run:
        record_path=args.from_run/'verification.json'
    else:
        require(args.live and args.image is not None and bool(args.source_ref), '新擷取需要 --live、--image 與 --source-ref。')
        if args.source_kind == 'teaching_revision':
            require(args.edit_manifest is not None,'教學修訂圖需附 revision_editor 產生的 edit.json。')
            edit=load(args.edit_manifest)
            base=load(base_path(s))
            require(edit.get('kind')=='teaching_revision_edit','編修紀錄格式不同。')
            require(edit['original_sha256']==base['source']['sha256'],'教學副本不是來自本次原圖。')
            require(edit['revision_sha256']==digest(args.image.read_bytes()),'教學副本與編修紀錄不符。')
            (s/'edit.json').write_bytes(args.edit_manifest.read_bytes())
        out=s/'new_extraction'
        require(not out.exists(), '已有擷取嘗試；請檢查原紀錄，勿重複執行。')
        out.mkdir()
        command=[sys.executable,str(DAY06/'run.py'),'--live','--condition','guided',
                 '--image',str(args.image.resolve()),'--source-ref',args.source_ref,
                 '--output',str(out.resolve()),'--origin',args.origin]
        if args.env_file:
            command += ['--env-file',str(args.env_file.resolve())]
        if args.source_updated_at:
            command += ['--source-updated-at',args.source_updated_at]
        # 一次新圖擷取，沿用 Day 6 已驗證介面、模型與 LOW；不另寫模型回合。
        result=subprocess.run(command,capture_output=True,text=True)
        (s/'extract.stdout.txt').write_text(result.stdout,encoding='utf-8')
        (s/'extract.stderr.txt').write_text(result.stderr,encoding='utf-8')
        records=list(out.glob('*/verification.json'))
        require(len(records)==1,'未取得唯一的擷取紀錄，請看 extract.stderr.txt。')
        record_path=records[0]
        save(s/'extract_execution.json',{'exit_code':result.returncode,'record_relative':str(record_path.relative_to(s))})
    record=load(record_path)
    require(record.get('mode')=='LIVE_GEMINI','正式擷取入口只接真實 Gemini 紀錄；離線示範使用 demo.py。')
    candidate=candidate_from_record(record,source_kind=args.source_kind)
    name=record['source']['stored_name']
    require(Path(name).name==name,'圖片檔名需在原擷取目錄內。')
    image=record_path.parent/name
    require(digest(image.read_bytes())==candidate['source']['sha256'],'新圖片與擷取紀錄不符。')
    if args.source_kind == 'teaching_revision' and args.from_run:
        require(args.edit_manifest is not None, '教學新圖重用也需要 edit.json。')
        edit=load(args.edit_manifest);base=load(base_path(s))
        require(edit.get('kind')=='teaching_revision_edit' and edit['original_sha256']==base['source']['sha256'], '教學副本來源不符。')
        require(edit['revision_sha256']==digest(image.read_bytes()), '教學副本與擷取圖不符。')
        with (s/'edit.json').open('xb') as f:
            f.write(args.edit_manifest.read_bytes())
    candidate['verification_file_sha256']=digest(record_path.read_bytes())
    (s/'candidate_verification.json').write_bytes(record_path.read_bytes())
    shutil.copyfile(image,s/('source_after'+image.suffix))
    save(s/'candidate.json',candidate)
    before,after=images(s)
    write_matching(s/'MATCH.html',load(base_path(s)),candidate,before,after)
    refresh(s)
    print(f'請開啟場次配對：{s/"MATCH.html"}')


def plan_command(args):
    s=args.session;base=load(base_path(s));candidate=load(s/'candidate.json');matching=load(args.matching)
    plan=make_plan(base,candidate,matching)
    save(s/'matching.json',matching)
    save(s/'plan.json',plan)
    before,after=images(s)
    write_review(s/'REVIEW.html',base,candidate,plan,before,after)
    refresh(s)
    print(f'欄位複核：{s/"REVIEW.html"}')


def apply_command(args):
    s=args.session
    require(not (s/'adoption.json').exists(),'這份工作紀錄已採用，保留既有結果。')
    base=load(base_path(s));candidate=load(s/'candidate.json');plan=load(s/'plan.json');decision=load(args.decision)
    result,audit=apply_review(base,candidate,plan,decision,active_version=load(s/'active.json')['version_id'])
    save(s/'decision.json',decision)
    save(s/'catalog.after.json',result)
    save(s/'adoption.json',audit)
    save(s/'active.json',{'version_id':result['version_id'],'catalog':'catalog.after.json'},replace=True)
    refresh(s)
    print('新版已在本機採用：',result['version_id'])


def query_command(args):
    s=args.session;base=load(base_path(s))
    candidate=load(s/'candidate.json') if (s/'candidate.json').exists() else None
    plan=load(s/'plan.json') if (s/'plan.json').exists() else None
    adopted=load(s/'catalog.after.json') if (s/'catalog.after.json').exists() else None
    result=query_phase(base,candidate,plan,adopted,{'date':args.date,'area':args.area,'keyword':args.keyword},args.phase)
    qdir=s/'queries';qdir.mkdir(exist_ok=True)
    path=qdir/f'{args.phase}-{len(list(qdir.glob("*.json")))+1:02}.json'
    save(path,result)
    print(json.dumps(result['result'],ensure_ascii=False,indent=2))
    print('查詢紀錄：',path)
    refresh(s)


def main(argv=None):
    p=argparse.ArgumentParser(description='LOCAL Day 7｜來源更新、欄位差異與採用')
    sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('prepare');q.add_argument('--catalog',type=Path,required=True);q.add_argument('--audit',type=Path,required=True)
    q.add_argument('--day06-run',type=Path,required=True);q.add_argument('--output',type=Path,default=Path('output/day07'));q.add_argument('--origin',default='operator_not_recorded')
    q=sub.add_parser('notice-template');q.add_argument('--session',type=Path,required=True)
    q=sub.add_parser('enrich');q.add_argument('--session',type=Path,required=True);q.add_argument('--notice',type=Path,required=True)
    q=sub.add_parser('extract');q.add_argument('--session',type=Path,required=True);q.add_argument('--live',action='store_true')
    q.add_argument('--image',type=Path);q.add_argument('--source-ref');q.add_argument('--source-updated-at');q.add_argument('--edit-manifest',type=Path)
    q.add_argument('--from-run',type=Path);q.add_argument('--source-kind',choices=['teaching_revision','official_revision'],required=True)
    q.add_argument('--env-file',type=Path);q.add_argument('--origin',default='operator_not_recorded')
    q=sub.add_parser('plan');q.add_argument('--session',type=Path,required=True);q.add_argument('--matching',type=Path,required=True)
    q=sub.add_parser('apply');q.add_argument('--session',type=Path,required=True);q.add_argument('--decision',type=Path,required=True)
    q=sub.add_parser('query');q.add_argument('--session',type=Path,required=True);q.add_argument('--phase',choices=['before','pending','after'],required=True)
    q.add_argument('--date',default='');q.add_argument('--area',default='');q.add_argument('--keyword',default='')
    a=p.parse_args(argv)
    try:
        if a.action=='prepare':prepare(a)
        elif a.action=='notice-template':notice_template(a.session)
        elif a.action=='enrich':enrich(a)
        elif a.action=='extract':capture(a)
        elif a.action=='plan':plan_command(a)
        elif a.action=='apply':apply_command(a)
        elif a.action=='query':query_command(a)
        return 0
    except (ValueError,KeyError,FileNotFoundError,FileExistsError,TypeError) as e:
        print(f'請檢查：{e}',file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
