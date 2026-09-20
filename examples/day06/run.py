"""兩次獨立的 Gemini 海報擷取：同圖同 schema，比較一般提示與欄位提示。"""
from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path
from pydantic import ValidationError
from schema import Extraction
from prompts import PROMPTS
from reporting import now, digest, dump_json, new_folder, packages, sources_sha, read_key, error_info, render

MODEL = "gemini-3.8-flash"
MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_OUTPUT_TOKENS = 8192


def image_mime(data: bytes) -> str:
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return "image/png"
    if data.startswith(b'\xff\xd8\xff'):
        return "image/jpeg"
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    raise ValueError("請使用 PNG、JPEG 或 WEBP 圖片。")


def make_config():
    from google.genai import types
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=Extraction.model_json_schema(),
        max_output_tokens=MAX_OUTPUT_TOKENS,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
    )


def parse_response(response) -> dict:
    candidates = getattr(response, "candidates", None) or []
    candidate = candidates[0] if candidates else None
    parts = getattr(getattr(candidate,"content",None), "parts", None) or []
    text = ''.join(p.text for p in parts if isinstance(getattr(p,'text',None),str) and not getattr(p,'thought',False))
    reason = getattr(candidate, "finish_reason", None)
    reason = getattr(reason, "value", reason)
    usage = getattr(response, "usage_metadata", None)
    prompt_feedback = getattr(response, "prompt_feedback", None)
    block = getattr(prompt_feedback, "block_reason", None)
    block = getattr(block, "value", block)
    result = {"raw_text": text, "finish_reason": reason, "model_version": getattr(response,"model_version",None),
              "response_id": getattr(response,"response_id",None), "block_reason":block,
              "usage":{k:getattr(usage,k,None) for k in ("prompt_token_count","candidates_token_count","thoughts_token_count","total_token_count")},
              "extraction":None, "validation_errors":[]}
    if reason != "STOP" or not text or block:
        result["status"] = "RESPONSE_INCOMPLETE"
        return result
    try:
        extraction = Extraction.model_validate_json(text)
        result.update(status="EXTRACTED", extraction=extraction.model_dump())
    except ValidationError as exc:
        result.update(status="SCHEMA_ERROR", validation_errors=[{"location":list(e['loc']),"type":e['type']} for e in exc.errors(include_input=False)])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="LOCAL Day 6｜圖片轉活動欄位")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--image",type=Path,required=True)
    parser.add_argument("--source-ref",required=True,help="海報原始網址，或作者提供的來源識別")
    parser.add_argument("--source-updated-at",default=None,help="來源明載的更新時間；沒有就省略")
    parser.add_argument("--env-file",type=Path)
    parser.add_argument("--output",type=Path,default=Path("output/day06"))
    parser.add_argument("--model",default=MODEL)
    parser.add_argument("--origin",default="operator_not_recorded")
    parser.add_argument("--condition",choices=("both","baseline","guided"),default="both")
    args=parser.parse_args(argv)
    if not args.live:
        parser.error("真實模型擷取請加 --live；離線驗證使用 verify.py。")
    if not args.source_ref.strip():
        parser.error("請提供海報來源網址或名稱。")
    data=args.image.read_bytes()
    if not data or len(data)>MAX_IMAGE_BYTES:
        parser.error("本例使用 6 MiB 以內的圖片；先選擇清楚的一張海報。")
    mime=image_mime(data)
    folder=new_folder(args.output,"extract")
    suffix={"image/png":".png","image/jpeg":".jpg","image/webp":".webp"}[mime]
    stored_name="source"+suffix
    (folder/stored_name).write_bytes(data)
    record={"kind":"LOCAL_DAY06_EXTRACTION","mode":"LIVE_GEMINI","run_id":folder.name,
        "origin":args.origin,"started_at":now(),"python":platform.python_version(),"platform":platform.system(),
        "packages":packages(),"code_sha256":sources_sha(),"requested_model":args.model,
        "config":{"api_family":"GenerateContent","api_version":"v1beta","thinking_level":"LOW",
                  "max_output_tokens":MAX_OUTPUT_TOKENS,"timeout_ms":60000,"sdk_total_attempts":1,
                  "response_format":"response_mime_type + response_json_schema","temperature":"not_set"},
        "source":{"original_name":args.image.name,"stored_name":stored_name,"mime_type":mime,
                  "sha256":digest(data),"source_ref":args.source_ref,"source_updated_at":args.source_updated_at},
        "schema":Extraction.model_json_schema(),"runs":[],"status":"STARTED","api_attempts":0}
    client=None
    try:
        key=read_key(args.env_file)
        from google import genai
        from google.genai import types
        config=make_config()
        client=genai.Client(api_key=key,vertexai=False,
            http_options=types.HttpOptions(api_version="v1beta",base_url="https://generativelanguage.googleapis.com",
                timeout=60000,retry_options=types.HttpRetryOptions(attempts=1)))
        print(f"本次報告：{folder / 'REPORT.html'}")
        for condition in (("baseline","guided") if args.condition=="both" else (args.condition,)):
            turn={"condition":condition,"prompt":PROMPTS[condition],"started_at":now()}
            started=time.perf_counter()
            record["api_attempts"]+=1
            try:
                response=client.models.generate_content(model=args.model,
                    contents=[types.Part.from_bytes(data=data,mime_type=mime),PROMPTS[condition]],config=config)
                turn.update(parse_response(response))
                (folder/f"response_{condition}.txt").write_text(turn["raw_text"],encoding="utf-8")
            except Exception as exc:
                turn.update(status="API_ERROR",error=error_info(exc),raw_text="",extraction=None)
            turn["duration_seconds"]=round(time.perf_counter()-started,3)
            record["runs"].append(turn)
            dump_json(folder/"verification.json",record)
            print(condition,turn["status"])
            if turn["status"]=="API_ERROR":
                break
        record["status"]="EXTRACTED" if len(record["runs"])== (2 if args.condition=="both" else 1) and all(t["status"]=="EXTRACTED" for t in record["runs"]) else "NEEDS_REVIEW"
    except Exception as exc:
        record.update(status="BLOCKED",error=error_info(exc))
        print(f"本次受阻：{type(exc).__name__}，詳見 verification.json。")
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass
        record["finished_at"]=now()
        dump_json(folder/"verification.json",record)
        render(folder,record)
    print("請開啟 REPORT.html 對照原圖，儲存 review.json，再執行 review.py。")
    return 0 if record["status"]=="EXTRACTED" else 2

if __name__=="__main__":
    raise SystemExit(main())
