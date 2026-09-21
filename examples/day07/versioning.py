"""來源、場次、差異與採用分開；這是可重現的單機教學流程。"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import uuid

from bridge import schema, search_tool

FIELDS = ('name', 'date', 'area', 'time', 'venue', 'meeting_time', 'meeting_point', 'accessibility')
CRITICAL = set(FIELDS)
GROUPS = ({'date', 'time', 'meeting_time'}, {'area', 'venue', 'meeting_point'})
NS = uuid.UUID('dac4f0e3-9bd9-40f3-a0d1-1c935690de48')


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def fingerprint(data) -> str:
    return digest(encoded(data))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def save(path: Path, data, *, replace: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not replace:
        with path.open('xb') as f:
            f.write(encoded(data))
    else:
        # 可替換的是本機流程指標／衍生畫面，原始輸出與版本快照各自保留。
        temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        temp.write_bytes(encoded(data))
        temp.replace(path)


def folder(output: Path, prefix='run') -> Path:
    p = output / f'{prefix}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}'
    p.mkdir(parents=True, exist_ok=False)
    return p


def require(ok: bool, message: str):
    if not ok:
        raise ValueError(message)


def stamp(value: str):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None, '時間需要時區。')


def normalize(value):
    """只整理文字首尾空白與 Unicode 組成；原始引句照原樣保存。"""
    return unicodedata.normalize('NFC', value).strip() if isinstance(value, str) else value


def triple_diff(left: dict, right: dict) -> list[str]:
    return [k for k in ('value', 'quote', 'status')
            if type(left[k]) is not type(right[k]) or normalize(left[k]) != normalize(right[k])]


def validate_fields(fields: dict) -> dict:
    return schema().PosterEvent.model_validate(fields).model_dump()


def import_day06(catalog: dict, audit: dict, record: dict, *, catalog_bytes: bytes,
                 record_bytes: bytes, image_bytes: bytes) -> dict:
    require(catalog.get('kind') == 'reviewed_poster_data', '需要 Day 6 核對後目錄。')
    require(audit.get('kind') == 'LOCAL_DAY06_REVIEW', '需要 Day 6 人工核對紀錄。')
    require(audit.get('catalog_sha256') == digest(catalog_bytes), '目錄與核對紀錄的雜湊不同。')
    require(audit.get('record_sha256') == digest(record_bytes), '擷取與核對紀錄的雜湊不同。')
    require(audit.get('source_sha256') == digest(image_bytes) == record['source']['sha256'], '原圖雜湊不符。')
    require(catalog['source']['sha256'] == digest(image_bytes), '目錄指向不同圖片。')
    require(bool(audit.get('reviewer')), '缺少既有核對者。')
    selected = next((x for x in record['runs'] if x['condition'] == audit.get('selected_condition', 'guided')), None)
    require(selected is not None and selected['status'] == 'EXTRACTED', '採用組尚未有有效欄位。')
    events = []
    require(0 < len(catalog['events']) <= 10, '本範例接收一到十筆場次。')
    require(len({e['id'] for e in catalog['events']}) == len(catalog['events']), 'Day 6 場次識別重複。')
    for old in catalog['events']:
        fields = validate_fields(old['field_evidence'])
        require(all(old[k] == fields[k]['value'] for k in FIELDS), '採用值與欄位依據不一致。')
        require(bool(fields['name']['value']), '活動名稱待核對。')
        # 首次匯入才指派身分；更新沿用這個 ID，而非重新用新圖雜湊計算。
        event_id = 'evt-' + uuid.uuid5(NS, old['id']).hex[:20]
        events.append({'id': event_id, 'day06_id': old['id'], 'fields': fields,
                       'enrichments': {}, 'review_ref': digest(encoded(audit))})
    return {'kind': 'LOCAL_VERSIONED_CATALOG', 'version_id': 'v-' + uuid.uuid4().hex,
            'parent_version': None, 'created_at': now(), 'events': events,
            'source': deepcopy(record['source']), 'source_kind': 'day06_import',
            'notes': deepcopy(selected['extraction'].get('notes', [])),
            'provenance': {'day06_catalog_sha256': digest(catalog_bytes),
                           'day06_record_sha256': digest(record_bytes),
                           'day06_audit_sha256': fingerprint(audit),
                           'day06_mode': record.get('mode'), 'day06_origin': record.get('origin'),
                           'requested_model': record.get('requested_model'),
                           'config': deepcopy(record.get('config', {})),
                           'selected_condition': selected['condition']}}


def month_day(text: str | None):
    if not text:
        return None
    # 完整西元日期優先，其次月日。日後更複雜的區間另外定義型別。
    m = re.search(r'\b\d{4}[-/.](\d{1,2})[-/.](\d{1,2})\b', text)
    if m:
        return int(m[1]), int(m[2])
    m = re.search(r'(?<!\d)(\d{1,2})\s*[./月-]\s*(\d{1,2})(?:日)?(?!\d)', text)
    return (int(m[1]), int(m[2])) if m else None


def enrich_dates(base: dict, notice: dict) -> dict:
    """外部公告只新增採用依據，不更改圖片 fields 的 value／quote／status。"""
    require(notice.get('approved') is True and bool(notice.get('reviewer', '').strip()), '公告需要人工確認與核對者。')
    text = notice.get('text', '')
    require(bool(text.strip()) and bool(notice.get('source_ref', '').strip()), '需要公告原文與來源。')
    stamp(notice['retrieved_at'])
    if notice.get('published_at'):
        stamp(notice['published_at'])
    out = deepcopy(base)
    events = {e['id']: e for e in out['events']}
    seen = set()
    require(bool(notice.get('bindings')), '至少指定一場的日期依據。')
    for binding in notice['bindings']:
        eid = binding['event_id']
        require(eid in events and eid not in seen, '公告綁定的場次需存在且唯一。')
        seen.add(eid)
        require(binding.get('same_event_confirmed') is True, '先確認公告和圖片是同一屆、同一場次。')
        value = binding['date']
        d = date.fromisoformat(value)
        require(d.isoformat() == value, '日期需為 YYYY-MM-DD。')
        qy, qe = binding['year_quote'], binding['event_quote']
        require(bool(qy.strip()) and bool(qe.strip()) and qy in text and qe in text, '引句須能在保存的公告原文找到。')
        require(str(d.year) in qy or f'{d.year-1911}年' in qy, '年份引句未支持指定的西元年／民國年。')
        raw = events[eid]['fields']['date']
        require(raw['value'] is None, '此步只補圖片缺少的年份，不覆寫既有完整日期。')
        require(month_day(raw['quote']) == (d.month, d.day), '公告日期與圖片月日不同，需要來源衝突處理。')
        require(month_day(qe) == (d.month, d.day), '活動引句未支持這個月日。')
        venue_val = normalize(events[eid]['fields']['venue']['value'] or '')
        name_val = normalize(events[eid]['fields']['name']['value'] or '')
        norm_qe = normalize(qe)
        venue_matches = bool(venue_val and (venue_val in norm_qe or norm_qe in venue_val))
        name_matches = bool(name_val and (name_val in norm_qe or norm_qe in name_val))
        require(venue_matches or name_matches,
                f'公告引句「{qe}」與活動地點「{venue_val}」或名稱「{name_val}」不符，需人工處理衝突。')
        events[eid]['enrichments']['date'] = {
            'value': value, 'source_ref': notice['source_ref'], 'text_sha256': digest(text.encode()),
            'year_quote': qy, 'event_quote': qe, 'published_at': notice.get('published_at'),
            'retrieved_at': notice['retrieved_at'], 'reviewer': notice['reviewer'],
            'method': 'reviewed_notice_year_plus_image_month_day'}
    out['parent_version'] = base['version_id']
    out['version_id'] = 'v-' + uuid.uuid4().hex
    out['created_at'] = now()
    out['enrichment_notice_sha256'] = fingerprint(notice)
    return out


def candidate_from_record(record: dict, *, source_kind: str) -> dict:
    require(source_kind in ('teaching_revision', 'official_revision', 'offline_fixture'), '請標示來源版本的種類。')
    group = next((x for x in record['runs'] if x['condition'] == 'guided' and x['status'] == 'EXTRACTED'), None)
    require(group is not None, '新圖需要有效的 guided 擷取結果。')
    fields = schema().Extraction.model_validate(group['extraction']).model_dump()
    require(bool(fields['events']), '新圖沒有場次，請回原圖核對。')
    return {'kind': 'LOCAL_CANDIDATE', 'candidate_id': 'x-' + uuid.uuid4().hex,
            'source_kind': source_kind, 'source': deepcopy(record['source']),
            'events': fields['events'], 'notes': fields['notes'],
            'extraction_ref': fingerprint(record), 'mode': record.get('mode'),
            'origin': record.get('origin'), 'requested_model': record.get('requested_model'),
            'config': deepcopy(record.get('config', {})),
            'duration_seconds': group.get('duration_seconds'), 'usage': deepcopy(group.get('usage'))}


def matching_template(base: dict, candidate: dict) -> dict:
    matches = []
    for i, fields in enumerate(candidate['events']):
        found = [e['id'] for e in base['events']
                 if normalize(e['fields']['name']['value']) == normalize(fields['name']['value'])]
        matches.append({'new_index': i, 'event_id': found[0] if len(found) == 1 else None})
    return {'kind': 'LOCAL_MATCHING', 'base_sha256': fingerprint(base),
            'candidate_sha256': fingerprint(candidate), 'reviewer': '', 'confirmed': False,
            'source_relation': '', 'matches': matches}


def make_plan(base: dict, candidate: dict, matching: dict) -> dict:
    require(matching.get('kind') == 'LOCAL_MATCHING' and matching.get('confirmed') is True,
            '場次配對須經人工確認。')
    require(bool(matching.get('reviewer', '').strip()) and bool(matching.get('source_relation', '').strip()),
            '請留下配對者及來源關係，例如官方修訂或教學修訂。')
    require(matching['base_sha256'] == fingerprint(base), '配對對應的舊資料已不同。')
    require(matching['candidate_sha256'] == fingerprint(candidate), '配對對應的新擷取已不同。')
    index_map = matching['matches']
    indices = [m['new_index'] for m in index_map]
    require(all(type(i) is int for i in indices) and sorted(indices) == list(range(len(candidate['events']))),
            '新圖每筆資料都需要一個唯一配對。')
    old_map = {e['id']: e for e in base['events']}
    used, rows, projected = set(), [], []
    for match in sorted(index_map, key=lambda m: m['new_index']):
        i, eid = match['new_index'], match['event_id']
        require(eid == 'NEW' or eid in old_map, '配對未完成：請選既有活動或新增。')
        if eid == 'NEW':
            eid = 'evt-' + uuid.uuid5(NS, candidate['candidate_id'] + ':' + str(i)).hex[:20]
            old = None
        else:
            require(eid not in used, '兩個候選場次不能共用同一個活動身分。')
            used.add(eid)
            old = old_map[eid]
        fields = validate_fields(candidate['events'][i])
        inherited = {}
        if old and not triple_diff(old['fields']['date'], fields['date']):
            inherited = deepcopy(old.get('enrichments', {}))
        entry = {'id': eid, 'fields': fields, 'new_index': i, 'enrichments': inherited,
                 'previous_review_ref': old.get('review_ref') if old else None}
        projected.append(entry)
        for key in FIELDS:
            changed = triple_diff(old['fields'][key], fields[key]) if old else ['value', 'quote', 'status']
            if changed:
                rows.append({'key': eid + ':' + key, 'event_id': eid, 'field': key,
                             'change': 'added' if old is None else ('value' if 'value' in changed else 'evidence'),
                             'changed_parts': changed, 'before': deepcopy(old['fields'][key]) if old else None,
                             'after': deepcopy(fields[key])})
    removed = sorted(set(old_map) - used)
    required = {row['key'] for row in rows}
    pending = {}
    for row in rows:
        eid, field = row['event_id'], row['field']
        targets = {field}
        for group in GROUPS:
            if field in group:
                targets |= group
        required.update(eid + ':' + f for f in targets)
        pending.setdefault(eid, set()).update(targets & CRITICAL)
    for eid in removed:
        pending[eid] = set(CRITICAL)
    notes_changed = base.get('notes', []) != candidate.get('notes', [])
    # notes 異動提醒複核者注意模型疑點，待核欄位仍精確鎖定直接變動與連動欄位。
    return {'kind': 'LOCAL_REVIEW_PLAN', 'plan_id': 'p-' + uuid.uuid4().hex,
            'created_at': now(), 'base_sha256': fingerprint(base),
            'candidate_sha256': fingerprint(candidate), 'matching_sha256': fingerprint(matching),
            'base_version': base['version_id'], 'candidate_id': candidate['candidate_id'],
            'source_changed': base['source']['sha256'] != candidate['source']['sha256'],
            'source_kind': candidate['source_kind'], 'source_relation': matching['source_relation'],
            'rows': rows, 'required_review_keys': sorted(required), 'removed_event_ids': removed,
            'pending_fields': {k: sorted(v) for k, v in pending.items()},
            'notes_changed': notes_changed, 'notes_before': base.get('notes', []),
            'notes_after': candidate.get('notes', []), 'projected_events': projected}


def apply_review(base: dict, candidate: dict, plan: dict, decision: dict, *, active_version: str) -> tuple[dict, dict]:
    require(active_version == base['version_id'] == plan['base_version'], '採用前的版本已變更，請重建差異。')
    require(plan['base_sha256'] == fingerprint(base) and plan['candidate_sha256'] == fingerprint(candidate),
            '複核計畫的輸入版本不同。')
    require(decision.get('kind') == 'LOCAL_ADOPTION_DECISION', '複核決定格式不符。')
    require(decision.get('plan_sha256') == fingerprint(plan), '複核決定不是這份差異計畫。')
    require(decision.get('approved') is True and decision.get('original_image_checked') is True,
            '請先對照新圖，確認重要資訊與其他醒目異動。')
    require(bool(decision.get('reviewer', '').strip()), '需要核對者。')
    stamp(decision['reviewed_at'])
    checked = set(decision.get('checked_keys', []))
    require(set(plan['required_review_keys']) <= checked, '變動與連動欄位尚未全部核對。')
    require(set(plan['removed_event_ids']) == set(decision.get('confirmed_removed', [])), '請確認消失場次的處理。')
    events = deepcopy(plan['projected_events'])
    entries = {e['id']: e for e in events}
    override_keys = set()
    for patch in decision.get('overrides', []):
        eid, key = patch['event_id'], patch['field']
        require(eid in entries and key in FIELDS and (eid, key) not in override_keys, '修訂欄位需唯一且存在。')
        require(eid + ':' + key in checked, '手動修改的欄位也需要核對。')
        linked = set()
        for group in GROUPS:
            if key in group:
                linked |= group
        missing = {eid + ':' + f for f in linked} - checked
        require(not missing, f'手動修改欄位「{key}」需連同群組欄位一起核對，缺少：{", ".join(sorted(missing))}')
        override_keys.add((eid, key))
        require(bool(patch.get('reason', '').strip()), '修訂需要原因。')
        entries[eid]['fields'][key] = deepcopy(patch['triple'])
        if key == 'date':
            entries[eid]['enrichments'].pop('date', None)
    for entry in events:
        entry['fields'] = validate_fields(entry['fields'])
        require(bool(entry['fields']['name']['value']), '活動名稱仍待核對。')
        entry['review_ref'] = fingerprint(decision)
        entry.pop('new_index', None)
    require(bool(events), '全部刪除的資料版本另行設計，本範例需至少一場。')
    adopted = {'kind': 'LOCAL_VERSIONED_CATALOG', 'version_id': 'v-' + uuid.uuid4().hex,
               'parent_version': base['version_id'], 'created_at': now(), 'events': events,
               'source': deepcopy(candidate['source']), 'source_kind': candidate['source_kind'],
               'notes': candidate['notes'], 'provenance': {'base_sha256': fingerprint(base),
                   'candidate_sha256': fingerprint(candidate), 'plan_sha256': fingerprint(plan),
                   'decision_sha256': fingerprint(decision), 'source_relation': plan['source_relation']}}
    audit = {'kind': 'LOCAL_DAY07_ADOPTION', 'created_at': now(), 'base_version': base['version_id'],
             'adopted_version': adopted['version_id'], 'reviewer': decision['reviewer'],
             'decision_sha256': fingerprint(decision), 'catalog_sha256': fingerprint(adopted),
             'changed_fields': len(plan['rows']), 'reviewed_keys': sorted(checked),
             'original_image_checked': True, 'source_kind': candidate['source_kind'],
             'author_observation': decision.get('author_observation', '')}
    return adopted, audit


def effective(event: dict) -> dict:
    result = {k: event['fields'][k]['value'] for k in FIELDS}
    for k, info in event.get('enrichments', {}).items():
        result[k] = info['value']
    return result


def search(snapshot: dict, args: dict) -> tuple[dict, list]:
    data = {'version': snapshot['version_id'], 'events': []}
    lookup = {}
    for event in snapshot['events']:
        values = effective(event)
        row = {'id': event['id'], **values, 'source': snapshot['source']['source_ref'],
               'updated_at': snapshot['source'].get('source_updated_at')}
        lookup[row['id']] = {**deepcopy(row), 'field_evidence': deepcopy(event['fields']),
                             'enrichments': deepcopy(event.get('enrichments', {}))}
        row['area'] = row['area'] or ''
        data['events'].append(row)
    trace = []
    tool = search_tool().make_search_tool(data, lambda kind, **kw: trace.append({'kind': kind, **deepcopy(kw)}))
    result = tool(**args)
    result['events'] = [lookup[e['id']] for e in result['events']]
    result['source_kind'] = snapshot['source_kind']
    result['unknown_fields'] = [e['id'] + '.' + k for e in result['events'] for k in FIELDS if e[k] is None]
    return result, trace


def query_phase(base: dict, candidate: dict | None, plan: dict | None, adopted: dict | None,
                args: dict, phase: str) -> dict:
    require(phase in ('before', 'pending', 'after'), '查詢階段不符。')
    if phase == 'after':
        require(adopted is not None, '尚未有採用版本。')
    snapshot = adopted if phase == 'after' else base
    result, trace = search(snapshot, args)
    if phase == 'pending':
        require(candidate is not None and plan is not None, '需要新圖與配對後的差異計畫。')
        # 篩選時查看新舊候選的聯集，避免日期／名稱改動使待核場次從查詢中消失。
        proposal = {'version_id': 'pending:' + candidate['candidate_id'], 'source': candidate['source'],
                    'source_kind': candidate['source_kind'], 'events': plan['projected_events']}
        maybe, _ = search(proposal, args)
        ids = {e['id'] for e in result['events']} | {e['id'] for e in maybe['events']}
        by_id = {e['id']: e for e in result['events']}
        original = {e['id']: e for e in base['events']}
        for eid in ids - set(by_id):
            if eid in original:
                v = effective(original[eid])
                by_id[eid] = {'id': eid, **v, 'source': base['source']['source_ref'],
                              'updated_at': base['source'].get('source_updated_at')}
            else:
                by_id[eid] = {'id': eid, **{k: None for k in FIELDS}, 'source': candidate['source']['source_ref'], 'updated_at': None}
        notices = []
        for eid in sorted(ids):
            event = by_id[eid]
            affected = set(plan['pending_fields'].get(eid, []))
            if eid not in original:
                affected.update(FIELDS)
            if affected:
                for key in affected:
                    event[key] = None
                # 對外結果不附上已遮蔽欄位的舊原文；歷史資料仍在 before 快照。
                event.pop('field_evidence', None)
                event.pop('enrichments', None)
                event['update_status'] = 'pending_review'
                event['pending_fields'] = sorted(affected)
                notices.append({'event_id': eid, 'fields': sorted(affected),
                                'source_ref': candidate['source']['source_ref']})
        result['events'] = [by_id[eid] for eid in sorted(ids)]
        result['status'] = 'pending_review' if notices else ('ok' if ids else 'not_found')
        result['pending_updates'] = notices
        result['candidate_version'] = candidate['candidate_id']
        result['source_kind'] = candidate['source_kind']
        result['unknown_fields'] = [e['id'] + '.' + k for e in result['events'] for k in FIELDS if e[k] is None]
    return {'kind': 'LOCAL_DAY07_QUERY', 'created_at': now(), 'phase': phase, 'api_calls': 0,
            'base_sha256': fingerprint(base), 'plan_sha256': fingerprint(plan) if plan else None,
            'adopted_sha256': fingerprint(adopted) if adopted else None,
            'query': deepcopy(args), 'result': result, 'trace': trace}
