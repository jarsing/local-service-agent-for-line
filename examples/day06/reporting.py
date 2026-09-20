"""保存執行紀錄，產生海報／欄位並排的本機核對畫面。"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
import uuid
from schema import FIELDS, LABELS


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump_json(path: Path, data: object):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def new_folder(root: Path, label: str) -> Path:
    folder = root / (datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ-") + label + "-" + uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def packages() -> dict:
    result = {}
    for name in ("google-genai", "google-adk", "pydantic", "httpx"):
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = None
    return result


def sources_sha() -> dict:
    here = Path(__file__).resolve().parent
    return {p.name: digest(p.read_bytes()) for p in sorted(here.glob("*.py"))} | {
        "requirements.txt": digest((here / "requirements.txt").read_bytes())}


def read_key(path: Path | None) -> str:
    import os
    if path is None:
        key = os.environ.get("GEMINI_API_KEY", "").strip()
    else:
        values = {}
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" in line:
                name, value = line.split("=", 1)
                values[name.strip()] = value.strip().strip('\"').strip("'")
        key = values.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY_REQUIRED")
    return key


def error_info(exc: Exception) -> dict:
    code = getattr(exc, "code", None)
    return {"type": type(exc).__name__, "http_code": code if type(code) is int else None}


def js_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render(folder: Path, record: dict):
    esc = lambda value: html.escape(str(value), quote=True)
    blocks = []
    available = {}
    for turn in record.get("runs", []):
        parsed = turn.get("extraction")
        if turn["status"] == "EXTRACTED" and parsed and parsed.get("events"):
            available[turn["condition"]] = parsed
        rows = []
        for index, event in enumerate((parsed or {}).get("events", []), 1):
            for key in FIELDS:
                f = event[key]
                value = "null" if f["value"] is None else json.dumps(f["value"], ensure_ascii=False)
                rows.append(f'<tr><td>{index}</td><td>{LABELS[key]}</td><td>{esc(value)}</td><td>{esc(f["quote"] or "—")}</td><td>{esc(f["status"])}</td></tr>')
        blocks.append(f'<section><h2>{"一般提示" if turn["condition"] == "baseline" else "欄位提示"}</h2>'
                      f'<p>狀態：{esc(turn["status"])} ｜ 呼叫耗時：{esc(turn.get("duration_seconds"))} 秒</p>'
                      '<table><thead><tr><th>筆</th><th>欄位</th><th>模型整理值</th><th>模型摘錄的原文</th><th>狀態</th></tr></thead><tbody>'
                      + ''.join(rows) + '</tbody></table><details><summary>模型原始文字</summary><pre>'
                      + esc(turn.get("raw_text") or "未取得文字") + '</pre></details></section>')
    image = folder / record["source"]["stored_name"]
    encoded = base64.b64encode(image.read_bytes()).decode("ascii")
    selected = "guided" if "guided" in available else ("baseline" if "baseline" in available else None)
    seed = {"kind": "poster_human_review", "selected_condition": selected, "record_sha256": digest((folder / "verification.json").read_bytes()),
            "source_sha256": record["source"]["sha256"], "extraction": available.get(selected),
            "reviewer": "", "approved": False, "reviewed_at": None, "correction_notes": "", "author_observation": ""}
    form = '''<section id="review"><h2>看過原圖，選擇要採用的資料</h2>
<p>先核對活動日、活動時段與集合資訊。欄位若需修改，請同時留下來源文字與修改原因。</p>
<label>採用哪一組作為核對起點？<select id="selected_condition"></select></label>
<p>切換組別會重新載入該組原始欄位。請先選定，再編修資料。</p>
<div id="fields"></div>
<label>修改原因（有改值時必填）<textarea id="reason" rows="2"></textarea></label>
<label>作者判讀心得<textarea id="observation" rows="2" placeholder="哪個欄位最容易看錯？兩組結果有什麼差異？"></textarea></label>
<label>核對者<input id="reviewer" placeholder="填寫自己的姓名或代號"></label>
<p><label><input id="approved" type="checkbox"> 我已對照圖片逐項核對，這是我要採用的內容。</label></p>
<button id="save">儲存 review.json</button><p id="message"></p></section>'''
    script = r'''
const seed = SEED;
const labels = LABELS;
const available = AVAILABLE;
const fields = document.getElementById('fields');
const choice = document.getElementById('selected_condition');
Object.keys(available).forEach(key => {const o=document.createElement('option');o.value=key;o.textContent=key==='baseline'?'一般提示':'欄位提示';choice.appendChild(o)});
choice.value=seed.selected_condition || '';
function drawFields() {
 fields.replaceChildren();
if (seed.extraction) {
 seed.extraction.events.forEach((event, i) => {
  const heading = document.createElement('h3'); heading.textContent = '活動／場次 ' + (i + 1); fields.appendChild(heading);
  Object.keys(labels).forEach(key => {
   const box = document.createElement('div'); box.className = 'editrow';
   const title = document.createElement('strong'); title.textContent = labels[key]; box.appendChild(title);
   const input = document.createElement(key === 'accessibility' ? 'select' : 'input');
   input.dataset.index = i; input.dataset.field = key; input.dataset.part = 'value';
   if(key === 'accessibility') { ['null','true','false'].forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;input.appendChild(o)}); input.value=String(event[key].value); }
   else {input.value = event[key].value ?? ''; input.placeholder='留白表示 null';}
   const status = document.createElement('select'); status.dataset.index=i;status.dataset.field=key;status.dataset.part='status';
   [['stated','圖片有明寫'],['not_shown','圖片沒寫'],['unclear','還需核對']].forEach(([v,t])=>{const o=document.createElement('option');o.value=v;o.textContent=t;status.appendChild(o)});status.value=event[key].status;
   const quote = document.createElement('input');quote.dataset.index=i;quote.dataset.field=key;quote.dataset.part='quote';quote.value=event[key].quote ?? '';quote.placeholder='支持這個欄位的圖片原文';
   box.append(input,status,quote);fields.appendChild(box);
  });
 });
} else {document.getElementById('review').hidden=true;}
}
drawFields();
choice.onchange = () => {
 seed.selected_condition=choice.value;
 seed.extraction=JSON.parse(JSON.stringify(available[choice.value]));
 document.getElementById('approved').checked=false;
 document.getElementById('reason').value='';
 document.getElementById('observation').value='';
 drawFields();
};
document.getElementById('save').onclick = () => {
 const out = JSON.parse(JSON.stringify(seed));
 const message = document.getElementById('message');
 out.reviewer=document.getElementById('reviewer').value.trim();
 out.approved=document.getElementById('approved').checked;
 out.correction_notes=document.getElementById('reason').value.trim();
 out.author_observation=document.getElementById('observation').value.trim();
 if(!out.reviewer || !out.approved){message.textContent='請先填寫核對者並勾選核對完成。';return;}
 fields.querySelectorAll('[data-part]').forEach(el=>{
  let v=el.value;
  if(el.dataset.part==='value' && el.dataset.field==='accessibility') v=v==='null'?null:v==='true';
  else if(el.dataset.part!=='status') v=v.trim()||null;
  out.extraction.events[Number(el.dataset.index)][el.dataset.field][el.dataset.part]=v;
 });
 const changed=JSON.stringify(out.extraction)!==JSON.stringify(seed.extraction);
 if(changed&&!out.correction_notes){message.textContent='你調整了欄位，請補上修改原因。';return;}
 out.reviewed_at=new Date().toISOString();
 const url=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)+'\n'],{type:'application/json'}));
 const a=document.createElement('a');a.href=url;a.download='review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 message.textContent='已準備 review.json。將下載檔交給匯出步驟；原始模型紀錄保持不變。';
};
'''
    inserts = {'SEED': js_json(seed), 'LABELS': js_json(LABELS), 'AVAILABLE': js_json(available)}
    script = re.sub(r'\b(SEED|LABELS|AVAILABLE)\b', lambda m: inserts[m.group(0)], script)
    page = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LOCAL Day 6｜海報與活動資料</title><style>
body{font-family:system-ui,sans-serif;margin:0;color:#1d3038;background:#f6f7f8;line-height:1.6}
header{padding:24px 32px;background:#183d49;color:white}main{padding:24px;max-width:1500px;margin:auto}
.layout{display:grid;grid-template-columns:minmax(250px,36%) 1fr;gap:24px;align-items:start}aside{position:sticky;top:12px}img{width:100%;height:auto}section,aside{background:white;padding:18px;border-radius:10px;margin-bottom:20px}
h1{margin:5px 0}h2{margin-top:0;font-size:22px}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;border-bottom:1px solid #dfe6e9;padding:8px;vertical-align:top;word-break:break-word}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5f6;padding:12px}.editrow{display:grid;grid-template-columns:110px 1fr 125px;gap:8px;margin:12px 0}.editrow input:last-child{grid-column:2/4}input,select,textarea{box-sizing:border-box;padding:8px;font:inherit;max-width:100%;border:1px solid #b5c4c9;border-radius:4px}textarea{width:100%;display:block}label{display:block;margin:12px 0}button{background:#11666a;color:white;border:0;border-radius:5px;padding:12px 20px;font:inherit;cursor:pointer}small{overflow-wrap:anywhere}details{margin:12px 0}@media(max-width:800px){.layout{display:block}aside{position:static}.editrow{display:block}.editrow>*{display:block;width:100%;margin:5px 0}}
</style><header><small>LOCAL · DAY 06</small><h1>一張海報，整理成可以查的活動資料</h1><div>ORIGIN</div></header><main><div class="layout"><aside><h2>本次輸入原圖</h2><img src="data:MIME;base64,IMAGE"><small>SOURCE</small></aside><article>BLOCKS FORM</article></div><details><summary>版本、用量與執行設定</summary><pre>METADATA</pre></details></main><script>SCRIPT</script></html>'''
    replacements = {"ORIGIN": esc(record["origin"]), "MIME": record["source"]["mime_type"],
        "IMAGE": encoded, "SOURCE": esc(record["source"]["source_ref"]), "BLOCKS": ''.join(blocks),
        "FORM": form, "METADATA": esc(json.dumps({k:v for k,v in record.items() if k!='runs'},ensure_ascii=False,indent=2)),
        "SCRIPT": script}
    page = re.sub(r'\b(ORIGIN|MIME|IMAGE|SOURCE|BLOCKS|FORM|METADATA|SCRIPT)\b',
                  lambda m: replacements[m.group(0)], page)
    (folder / "REPORT.html").write_text(page, encoding="utf-8")
