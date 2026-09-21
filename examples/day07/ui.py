"""產生不依賴網站服務的場次配對與複核頁；表單在瀏覽器下載 JSON。"""
from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from versioning import FIELDS, GROUPS, effective, fingerprint, matching_template

LABELS = dict(zip(FIELDS, ('活動名稱','活動日期','鄉鎮市區','活動時間','活動場地','集合時間','集合地點','全程輪椅通行')))
STYLE = '''body{font-family:system-ui,-apple-system,sans-serif;max-width:1280px;margin:32px auto;padding:0 22px;line-height:1.65;color:#152b35;background:#f6f8f9}h1{font-size:30px}h2{font-size:23px}small{color:#465b66}section,.card{background:white;padding:20px;border:1px solid #d3dfe3;border-radius:10px;margin:18px 0}table{width:100%;border-collapse:collapse}th,td{padding:9px;text-align:left;border-bottom:1px solid #d5dee2;vertical-align:top}input,textarea,select,button{font:inherit}textarea{width:97%;min-height:110px}button{padding:10px 18px;margin:12px 8px 0 0;cursor:pointer}input[type=text]{width:90%;padding:8px}.images{display:flex;gap:20px}.images figure{width:48%;margin:0}.images img{width:100%;max-height:540px;object-fit:contain;background:#e9eff2}.notice{background:#fff4d4;padding:12px;border-left:5px solid #9e6e00}.error{color:#aa2030;white-space:pre-wrap}code,pre{overflow-wrap:anywhere;white-space:pre-wrap}summary{cursor:pointer}.tag{font-size:13px;border-radius:3px;padding:3px 8px;background:#e4edf1}@media(max-width:750px){.images{display:block}.images figure{width:100%}table{font-size:14px}}'''


def js(data):
    return json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def image(path: Path) -> str:
    mime = {'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}[path.suffix.lower()]
    return 'data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode()


def pair_images(before: Path, after: Path, source_kind: str) -> str:
    label = '教學用修訂版／非主辦公告' if source_kind == 'teaching_revision' else ('離線測試資料' if source_kind == 'offline_fixture' else '候選新來源')
    return f'<div class="images"><figure><img src="{image(before)}"><figcaption>前篇採用的原圖</figcaption></figure><figure><img src="{image(after)}"><figcaption>{html.escape(label)}</figcaption></figure></div>'


COMMON = '''function download(name,obj){const a=document.createElement('a');const u=URL.createObjectURL(new Blob([JSON.stringify(obj,null,2)+'\\n'],{type:'application/json'}));a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),3000)}
function el(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n}
function fail(e){document.getElementById('error').textContent=e.message||String(e)}
'''


def write_matching(path: Path, base: dict, candidate: dict, before: Path, after: Path):
    data = {'base':base, 'candidate':candidate, 'template':matching_template(base,candidate)}
    document = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LOCAL Day 7｜先對上同一場</title><style>STYLE</style>
<h1>新海報換了排序，還是同一場活動嗎？</h1><p>先確認場次身分，再比較欄位。名稱相同的選項只是建議，請對照原圖確認。</p>IMAGES
<section><table><thead><tr><th>新圖場次</th><th>配對到已核對活動</th></tr></thead><tbody id="matches"></tbody></table>
<p>核對者 <input id="reviewer" type="text"></p><p>來源關係（例如：教學副本只修改一個活動時段，其他場次相同）<input id="relation" type="text"></p>
<label><input id="confirmed" type="checkbox">我已確認場次對應及兩份來源的關係。</label><br><button id="save">儲存 matching.json</button><p id="error" class="error"></p></section>
<script>const D=DATA;COMMON
const rows=[];
D.candidate.events.forEach((fields,i)=>{const tr=el('tr');tr.append(el('td',`${i+1}. ${fields.name.value||'名稱待核對'} ｜ ${fields.area.value||'地區待核對'} ｜ ${fields.date.quote||''}`));const td=el('td'),sel=el('select');sel.append(new Option('請選擇場次',''));D.base.events.forEach(e=>sel.append(new Option(`${e.fields.name.value} (${e.id})`,e.id)));sel.append(new Option('新出現的活動','NEW'));sel.value=D.template.matches[i].event_id||'';td.append(sel);tr.append(td);document.getElementById('matches').append(tr);rows.push(sel)});
document.getElementById('save').onclick=()=>{try{const r=document.getElementById('reviewer').value.trim(),relation=document.getElementById('relation').value.trim();if(!r||!relation||!document.getElementById('confirmed').checked)throw Error('請填核對者、來源關係並確認。');const ids=rows.map(x=>x.value);if(ids.includes(''))throw Error('每筆場次都需要配對。');const old=ids.filter(x=>x!=='NEW');if(new Set(old).size!==old.length)throw Error('同一個舊活動被配對兩次。');download('matching.json',{...D.template,reviewer:r,source_relation:relation,confirmed:true,matches:ids.map((event_id,new_index)=>({new_index,event_id}))})}catch(e){fail(e)}};
</script></html>'''
    for key, value in [('STYLE',STYLE),('IMAGES',pair_images(before,after,candidate['source_kind'])),('DATA',js(data)),('COMMON',COMMON)]:
        document = document.replace(key, value, 1)
    path.write_text(document,encoding='utf-8')


def write_review(path: Path, base: dict, candidate: dict, plan: dict, before: Path, after: Path):
    data = {'base':base,'candidate':candidate,'plan':plan,'labels':LABELS,'groups':[sorted(g) for g in GROUPS],'plan_sha256':fingerprint(plan)}
    document = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LOCAL Day 7｜差異引導複核</title><style>STYLE</style>
<h1>資料改了哪裡？把注意力放在這幾格。</h1><p class="notice">MODEL_LABEL。這是差異引導人工核對；採用之前，候選值和已核對答案分開。</p>IMAGES
<section id="summary"></section><section><h2>變動與連動欄位</h2><p>對照圖中原文，再勾選已核對。模型讀錯時可修訂右側三元組，並在下方填原因；原始模型輸出仍保留。</p><div id="changes"></div></section>
<section><details><summary>未變欄位與先前採用值</summary><pre id="unchanged"></pre><h3>模型漏讀了變動？額外核對欄位</h3><p>下列欄位原先未列入差異。有需要再編修、勾選並填原因。</p><div id="extra"></div></details><h2>消失場次與圖片疑點</h2><div id="removed"></div><pre id="notes"></pre></section>
<section><p>核對者 <input id="reviewer" type="text"></p><p>修改原因／其他原圖觀察<textarea id="reason"></textarea></p><p>作者心得（一兩句即可）<textarea id="observation"></textarea></p>
<label><input id="image_checked" type="checkbox">我已對照新圖、確認重要日期／地點與取消或延期等醒目資訊，並檢查場次配對。</label><br>
<button id="save">儲存 decision.json</button><p id="error" class="error"></p></section>
<script>const D=DATA;COMMON
const P=D.plan,old=Object.fromEntries(D.base.events.map(e=>[e.id,e])),fresh=Object.fromEntries(P.projected_events.map(e=>[e.id,e]));
document.getElementById('summary').textContent=`來源檔案${P.source_changed?'不同':'相同'}；${P.rows.length} 個欄位三元組有差異；${P.required_review_keys.length} 個變動／連動欄位待核對。`;
const controls=[];P.required_review_keys.forEach(key=>{const ix=key.indexOf(':'),eid=key.slice(0,ix),field=key.slice(ix+1),entry=fresh[eid];if(!entry)return;const row=P.rows.find(x=>x.key===key);const card=el('div');card.className='card';card.append(el('strong',`${entry.fields.name.value||eid} → ${D.labels[field]}`));card.append(el('p',row?`變動：${row.changed_parts.join(' / ')}`:'連動資訊：和變動欄位一起核對'));card.append(el('pre','上一版：'+JSON.stringify(old[eid]?.fields[field]??null,null,2)));const input=el('textarea');input.value=JSON.stringify(entry.fields[field],null,2);card.append(input);const label=el('label'),check=el('input');check.type='checkbox';label.append(check,document.createTextNode('已對照原圖核對此欄位'));card.append(label);document.getElementById('changes').append(card);controls.push({key,eid,field,input,check,required:true,initial:JSON.stringify(entry.fields[field])})});
const removals=[];P.removed_event_ids.forEach(eid=>{const l=el('label'),c=el('input');c.type='checkbox';l.append(c,document.createTextNode(`確認新圖已移除／本次不採用：${old[eid].fields.name.value}`));document.getElementById('removed').append(l,el('br'));removals.push({eid,c})});
document.getElementById('notes').textContent=JSON.stringify({before:P.notes_before,after:P.notes_after},null,2);
const unchanged=[];P.projected_events.forEach(e=>Object.keys(D.labels).forEach(k=>{if(!P.required_review_keys.includes(e.id+':'+k))unchanged.push({event:e.fields.name.value,field:k,triple:e.fields[k],enrichment:e.enrichments[k]||null})}));document.getElementById('unchanged').textContent=JSON.stringify(unchanged,null,2);
P.projected_events.forEach(e=>Object.keys(D.labels).forEach(field=>{const key=e.id+':'+field;if(P.required_review_keys.includes(key))return;const box=el('details');box.append(el('summary',`${e.fields.name.value} → ${D.labels[field]}`));const input=el('textarea');input.value=JSON.stringify(e.fields[field],null,2);box.append(input);const hint=el('p');hint.className='tag';hint.style.display='none';hint.style.margin='6px 0';hint.style.color='#8a5b00';box.append(hint);const check=el('input');check.type='checkbox';const label=el('label');label.append(check,document.createTextNode('這個額外欄位也已核對'));box.append(label);document.getElementById('extra').append(box);controls.push({key,eid:e.id,field,input,check,hint,required:false,initial:JSON.stringify(e.fields[field])})}));
const updateHints=()=>{controls.forEach(c=>{if(!c.hint)return;let mod=false;try{mod=JSON.stringify(JSON.parse(c.input.value))!==c.initial;}catch(_){}if(mod){const g=(D.groups||[]).find(x=>x.includes(c.field));if(g){const need=g.filter(f=>f!==c.field).map(f=>D.labels[f]||f);c.hint.textContent=`此欄位修改將觸發連動核對，請一併在變動或額外欄位核對：${need.join('、')}`;c.hint.style.display='block';}else{c.hint.style.display='none';}}else{c.hint.style.display='none';}})};
controls.forEach(c=>{if(c.hint)c.input.oninput=updateHints;});
document.getElementById('save').onclick=()=>{try{const reviewer=document.getElementById('reviewer').value.trim(),reason=document.getElementById('reason').value.trim();if(!reviewer||!document.getElementById('image_checked').checked)throw Error('請填核對者並確認已看過原圖。');if(controls.some(c=>c.required&&!c.check.checked)||removals.some(r=>!r.c.checked))throw Error('請完成變動／連動欄位和移除場次的核對。');const overrides=[];controls.forEach(c=>{const triple=JSON.parse(c.input.value);if(JSON.stringify(triple)!==c.initial){if(!c.check.checked)throw Error(`額外修改的欄位（${D.labels[c.field]||c.field}）也需要勾選核對。`);if(!reason)throw Error('修改欄位需要原因。');overrides.push({event_id:c.eid,field:c.field,triple,reason})}});const checkedSet=new Set(controls.filter(c=>c.check.checked).map(c=>c.key));overrides.forEach(o=>{const g=(D.groups||[]).find(x=>x.includes(o.field));if(g){const missing=g.filter(f=>!checkedSet.has(o.event_id+':'+f)).map(f=>D.labels[f]||f);if(missing.length){const entry=fresh[o.event_id],name=entry?.fields?.name?.value||o.event_id;throw Error(`手動修改「${name}」的「${D.labels[o.field]||o.field}」需連同群組欄位一起核對，尚缺少：${missing.join('、')}`);}}});download('decision.json',{kind:'LOCAL_ADOPTION_DECISION',plan_sha256:D.plan_sha256,approved:true,original_image_checked:true,reviewer,reviewed_at:new Date().toISOString(),checked_keys:controls.filter(c=>c.check.checked).map(c=>c.key),confirmed_removed:removals.map(r=>r.eid),overrides,correction_notes:reason,author_observation:document.getElementById('observation').value.trim()})}catch(e){fail(e)}};
</script></html>'''
    label = '教學用修訂圖，非主辦新公告' if candidate['source_kind']=='teaching_revision' else '請對照原圖與來源'
    for key,value in [('STYLE',STYLE),('MODEL_LABEL',label),('IMAGES',pair_images(before,after,candidate['source_kind'])),('DATA',js(data)),('COMMON',COMMON)]:
        document = document.replace(key,value,1)
    path.write_text(document,encoding='utf-8')


def write_summary(path: Path, base: dict, candidate: dict | None, plan: dict | None, queries: list[dict], adoption: dict | None):
    blocks=[]
    if plan:
        blocks.append('<h2>欄位差異</h2><table><tr><th>活動／欄位</th><th>上一版</th><th>候選新值</th><th>變動</th></tr>')
        names={e['id']:e['fields']['name']['value'] for e in plan['projected_events']}
        for r in plan['rows']:
            blocks.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in [str(names.get(r['event_id'],r['event_id']))+' / '+LABELS[r['field']],r['before'],r['after'],r['changed_parts']])+'</tr>')
        blocks.append('</table>')
    blocks.append('<h2>同一個問題，查詢前後</h2>')
    for q in queries:
        label={'before':'更新前','pending':'新版待核','after':'採用新版後'}[q['phase']]
        blocks.append('<section><h3>'+label+' · '+html.escape(q['result']['status'])+'</h3><table><tr><th>活動</th><th>日期</th><th>活動時間</th><th>狀態</th></tr>')
        for event in q['result']['events']:
            blocks.append('<tr>'+''.join('<td>'+html.escape(str(v) if v is not None else '待確認')+'</td>' for v in [event.get('name'),event.get('date'),event.get('time'),event.get('update_status','已採用')])+'</tr>')
        blocks.append('</table><details><summary>完整工具結果</summary><pre>'+html.escape(json.dumps(q['result'],ensure_ascii=False,indent=2))+'</pre></details></section>')
    meta={'base_version':base['version_id'],'mode':candidate.get('mode') if candidate else None,
          'source_kind':candidate.get('source_kind') if candidate else base['source_kind'],
          'model':candidate.get('requested_model') if candidate else None,
          'config':candidate.get('config') if candidate else None,'adoption':adoption}
    body=''.join(blocks)
    path.write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LOCAL Day 7 結果</title><style>'+STYLE+'</style><h1>LOCAL Day 7｜同一活動，更新前後怎麼查？</h1><p class="notice">來源性質：'+html.escape(str(meta['source_kind']))+'；擷取模式：'+html.escape(str(meta['mode']))+'</p>'+body+'<details><summary>實驗與版本紀錄</summary><pre>'+html.escape(json.dumps(meta,ensure_ascii=False,indent=2))+'</pre></details></html>',encoding='utf-8')
