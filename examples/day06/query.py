"""沿用 Day 5 的 Python 搜尋工具；用已核對海報資料完成本機查詢。"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from schema import FIELDS, Extraction, PosterEvent
from reporting import dump_json, digest, new_folder, now

DAY05 = Path(__file__).resolve().parents[1] / "day05" / "catalog.py"


def load_day05(path: Path=DAY05):
    spec=importlib.util.spec_from_file_location("local_day05_catalog",path)
    if spec is None or spec.loader is None:
        raise ImportError("請確認同一 Repo 內的 examples/day05/catalog.py。")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_catalog(data: dict):
    if data.get("kind")!="reviewed_poster_data" or not data.get("review",{}).get("reviewer"):
        raise ValueError("本篇入口使用 review.py 匯出的已核對海報目錄。")
    events=data.get("events")
    if not isinstance(events,list) or not events or len(events)>10:
        raise ValueError("活動筆數不符。")
    if len({x["id"] for x in events})!=len(events):
        raise ValueError("活動識別碼重複。")
    for event in events:
        parsed=PosterEvent.model_validate(event["field_evidence"])
        for key in FIELDS:
            if event[key]!=getattr(parsed,key).value:
                raise ValueError("查詢值與核對欄位不一致。")
        if not event.get("name") or not event.get("source"):
            raise ValueError("活動名稱與來源需要存在。")


def search_reviewed(data: dict, args: dict, *, day05_path: Path=DAY05) -> tuple[dict,list[dict]]:
    validate_catalog(data)
    day05=load_day05(day05_path)
    # Day 5 的比對器對 area 使用子字串運算；未知地區轉成空字串供比對，
    # 結果仍換回含 null 的原資料，避免空字串成為真實欄位值。
    from copy import deepcopy
    searchable=deepcopy(data)
    for event in searchable["events"]:
        if event["area"] is None:
            event["area"]=""
    records=[]
    tool=day05.make_search_tool(searchable,lambda kind,**fields:records.append({"kind":kind,**deepcopy(fields)}))
    result=tool(**args)
    originals={event["id"]:event for event in data["events"]}
    result["events"]=[deepcopy(originals[event["id"]]) for event in result.get("events",[])]
    result["unknown_fields"]=[f'{event["id"]}.{key}' for event in result["events"]
        for key in (*FIELDS,"updated_at") if event.get(key) is None]
    result["data_kind"]=data["kind"]
    records.append({"kind":"DAY06_RESULT_NORMALIZED","result":deepcopy(result)})
    return result,records


def execute(catalog_file: Path, args: dict, output: Path, *, day05_path: Path=DAY05):
    blob=catalog_file.read_bytes();data=json.loads(blob)
    if not any(args.values()):
        args["keyword"]=data["events"][0]["name"][:80]
    result,events=search_reviewed(data,args,day05_path=day05_path)
    folder=new_folder(output,"query")
    evidence={"kind":"LOCAL_DAY06_QUERY","mode":"LOCAL_PYTHON_TOOL","created_at":now(),
        "catalog_sha256":digest(blob),"day05_catalog_sha256":digest(day05_path.read_bytes()),
        "query":args,"result":result,"events":events,"api_calls":0}
    dump_json(folder/"query.json",evidence)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print(f"查詢紀錄：{folder/'query.json'}")
    return evidence,folder


def main(argv=None):
    p=argparse.ArgumentParser(description="LOCAL Day 6｜用 Day 5 工具查核對後的海報資料")
    p.add_argument("--catalog",type=Path,required=True)
    p.add_argument("--date",default="");p.add_argument("--area",default="");p.add_argument("--keyword",default="")
    p.add_argument("--output",type=Path,default=Path("output/day06"))
    a=p.parse_args(argv)
    evidence,_=execute(a.catalog,{"date":a.date,"area":a.area,"keyword":a.keyword},a.output)
    return 0 if evidence["result"]["status"] in ("ok","not_found") else 2

if __name__=="__main__":
    raise SystemExit(main())
