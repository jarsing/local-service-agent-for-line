"""把人工核對另存成資料版本；原圖與原始模型輸出仍保留在原 run。"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from schema import Extraction, FIELDS, as_catalog
from reporting import digest, dump_json, new_folder, now


def validate_review(record: dict, record_bytes: bytes, review: dict) -> tuple[Extraction,list[dict]]:
    if review.get("kind")!="poster_human_review" or review.get("approved") is not True:
        raise ValueError("請先完成原圖核對與確認。")
    if not isinstance(review.get("reviewer"),str) or not review["reviewer"].strip():
        raise ValueError("請記錄核對者。")
    if review.get("record_sha256")!=digest(record_bytes) or review.get("source_sha256")!=record["source"]["sha256"]:
        raise ValueError("核對檔與這次圖片／執行紀錄不符。")
    stamp=datetime.fromisoformat(review.get("reviewed_at", "").replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("核對時間需要時區。")
    condition=review.get("selected_condition", "guided")
    if condition not in ("baseline", "guided"):
        raise ValueError("請選擇一般提示或欄位提示作為核對起點。")
    selected=next((x for x in record["runs"] if x["condition"]==condition and x["status"]=="EXTRACTED"),None)
    if selected is None:
        raise ValueError("請先選擇已取得有效欄位結果的一組，再核對。")
    extraction=Extraction.model_validate(review["extraction"])
    before=selected["extraction"]["events"]
    after=extraction.model_dump()["events"]
    if len(before)!=len(after):
        raise ValueError("本版核對介面保留場次數；新增或刪除活動請另做來源整理。")
    changes=[]
    for i,(left,right) in enumerate(zip(before,after)):
        for key in FIELDS:
            if left[key]!=right[key]:
                changes.append({"event_index":i,"field":key,"before":left[key],"after":right[key]})
    if (changes or extraction.notes!=selected["extraction"]["notes"]) and not str(review.get("correction_notes","")).strip():
        raise ValueError("修改欄位時，請記錄修改原因與來源。")
    return extraction,changes


def export_review(run_folder: Path, review_file: Path, output: Path) -> Path:
    record_bytes=(run_folder/"verification.json").read_bytes()
    record=json.loads(record_bytes)
    review_bytes=review_file.read_bytes()
    reviewed=json.loads(review_bytes)
    # 僅讀 run 內的 source 檔；不採用 review 檔指定的檔案路徑。
    image_name=record["source"]["stored_name"]
    if Path(image_name).name!=image_name:
        raise ValueError("圖片名稱應為 run 內的單一檔名。")
    if digest((run_folder/image_name).read_bytes())!=record["source"]["sha256"]:
        raise ValueError("原始圖片內容已不同。")
    extraction,changes=validate_review(record,record_bytes,reviewed)
    catalog=as_catalog(extraction,record["source"],reviewed["reviewed_at"],reviewed["reviewer"])
    folder=new_folder(output,"review")
    dump_json(folder/"catalog.reviewed.json",catalog)
    (folder/"review.json").write_bytes(review_bytes)
    audit={"kind":"LOCAL_DAY06_REVIEW","created_at":now(),"input_mode":record["mode"],
        "input_origin":record["origin"],"input_run_id":record["run_id"],
        "record_sha256":digest(record_bytes),"source_sha256":record["source"]["sha256"],
        "review_file_sha256":digest(review_bytes),"catalog_sha256":digest((folder/"catalog.reviewed.json").read_bytes()),
        "reviewer":reviewed["reviewer"],"reviewed_at":reviewed["reviewed_at"],
        "selected_condition":reviewed.get("selected_condition", "guided"),"changes":changes,
        "correction_notes":reviewed.get("correction_notes",""),"author_observation":reviewed.get("author_observation","")}
    dump_json(folder/"review.audit.json",audit)
    return folder


def main(argv=None):
    p=argparse.ArgumentParser(description="LOCAL Day 6｜匯出人工核對的活動資料")
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--review-file",type=Path,required=True)
    p.add_argument("--output",type=Path,default=Path("output/day06"))
    a=p.parse_args(argv)
    folder=export_review(a.run,a.review_file,a.output)
    print(f"已核對目錄：{folder/'catalog.reviewed.json'}")
    print(f"修改紀錄：{folder/'review.audit.json'}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
