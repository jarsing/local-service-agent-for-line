"""固定卡片只呈現可信後端結果；通過格式檢查不等於取得業務權限。

No model-authored layout, actions, URLs, receipt IDs or status decisions.
The local validator deliberately covers only the emitted subset, not the entire LINE API.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any, Mapping

# 本篇刻意採保守的內部預算；不是宣称完整覆蓋 LINE API 的全部限制。
ALT_BUDGET = 350                 # UTF-16 code units
TEXT_BUDGET = 4500
BUBBLE_BYTE_BUDGET = 24000
CID = re.compile(r'[A-Za-z0-9_-]{1,100}\Z')
RID = re.compile(r'req-[A-Za-z0-9_-]{1,100}\Z')
TAIPEI = timezone(timedelta(hours=8))
LABEL = '花壇場次（歷史教學快照）'
DISCLAIMER = '詢問尚未通知服務窗口；這不是預約成立。'
HEADER = '#243746'
INK = '#243746'
MUTED = '#526371'
AMBER = '#7A4B00'
AMBER_BG = '#FFF4D6'
NOTICE_BG = '#EDF1F4'


class InvalidView(ValueError):
    """The selected backend fields cannot be safely rendered."""


def units(text: str) -> int:
    return len(text.encode('utf-16-le')) // 2


def _string(value: Any, name: str, maximum: int) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise InvalidView(name)
    try:
        value.encode('utf-8', 'strict')
    except UnicodeError as exc:
        raise InvalidView(name) from exc
    # Refuse invisible directional/control characters, rather than changing the saved request.
    if any((ord(c) < 32 and c not in '\n\t') or ord(c) == 127 or
           0x202A <= ord(c) <= 0x202E or 0x2066 <= ord(c) <= 0x2069 for c in value):
        raise InvalidView(name)
    return value


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidView(name)
    return value


def checked_cid(value: Any) -> str:
    value = _string(value, 'confirmation_id', 100)
    if CID.fullmatch(value) is None:
        raise InvalidView('confirmation_id')
    return value


def _date(value: Any) -> str:
    try:
        parsed = datetime.fromisoformat(_string(value, 'timestamp', 80))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('missing timezone')
    except (ValueError, TypeError) as exc:
        raise InvalidView('timestamp') from exc
    return parsed.astimezone(TAIPEI).strftime('%Y/%m/%d %H:%M:%S（臺灣時間）')


def _clip(text: str, budget: int) -> str:
    if units(text) <= budget:
        return text
    kept = []
    used = 0
    for char in text:
        cost = units(char)
        if used + cost > budget - 1:
            break
        kept.append(char)
        used += cost
    return ''.join(kept) + '…'


@dataclass(frozen=True)
class Action:
    label: str
    data: str
    display: str

    def as_dict(self) -> dict[str, str]:
        return {'type': 'postback', 'label': self.label,
                'data': self.data, 'displayText': self.display}


@dataclass(frozen=True)
class View:
    state: str
    title: str
    badge: str
    fields: tuple[tuple[str, str], ...]
    note: str
    actions: tuple[Action, ...]
    alt: str


def _read_actions(cid: str | None) -> tuple[Action, ...]:
    if cid:
        return (Action('查詢這筆進度', 'status:' + cid, '查詢這筆詢問的進度'),
                Action('這筆文字版', 'text:' + cid, '顯示這筆詢問的文字版'))
    return (Action('查詢目前任務', 'status', '查詢原單'),
            Action('目前任務文字版', 'text', '顯示目前任務文字版'))


def confirmation_view(result: Mapping[str, Any]) -> View:
    if result.get('status') != 'awaiting_confirmation':
        raise InvalidView('confirmation status')
    args = _mapping(result.get('args'), 'args')
    cid = checked_cid(args.get('confirmation_id'))
    # We display the entire saved request; never shorten the thing a person is approving.
    request = _string(args.get('request_text'), 'request_text', 1200)
    expiry = _date(result.get('expires_at'))
    actions = (Action('確認送出', 'confirm:' + cid, '確認送出這份詢問'),
               Action('取消這次詢問', 'cancel:' + cid, '取消這份詢問'),
               Action('先看文字版', 'text:' + cid, '顯示這份確認的文字版'))
    alt = (f'【待確認｜尚未建單】{LABEL}。原確認有效至 {expiry}。'
           f'{DISCLAIMER} 點開確認、取消，或選文字版。')
    return View('awaiting_confirmation', '先確認這份詢問', '待確認 · 尚未建單',
                (('活動', LABEL), ('詢問原文（使用者提供）', request), ('原確認期限', expiry)),
                '期限從原確認建立時起算；重新打開或切換文字版不延長。\n' + DISCLAIMER,
                actions, alt)


def receipt_view(result: Mapping[str, Any], *, cancelled_after_creation: bool = False) -> View:
    state = result.get('status')
    if state not in ('request_created', 'already_created', 'existing_request'):
        raise InvalidView('receipt status')
    row = _mapping(result.get('request'), 'request')
    rid = _string(result.get('request_id'), 'request_id', 110)
    if RID.fullmatch(rid) is None or row.get('request_id') != rid:
        raise InvalidView('inconsistent request_id')
    if row.get('status') != 'pending_human_review' or row.get('human_claimed') is not False:
        raise InvalidView('unsupported business state')
    args = _mapping(row.get('args'), 'args')
    cid = checked_cid(args.get('confirmation_id'))
    request = _string(row.get('request_text'), 'request_text', 1200)
    if request != args.get('request_text'):
        raise InvalidView('inconsistent request_text')
    created = _date(row.get('created_at'))
    title = '詢問已保存' if state == 'request_created' else '找到原本的詢問'
    note = DISCLAIMER
    if cancelled_after_creation:
        note = '這筆詢問已保存；舊確認卡的取消按鈕不會撤銷已建立的請求。\n' + note
    alt = f'【待人工覆核】{title}。單號 {rid}。{note} 可查詢這筆進度或顯示文字版。'
    return View(str(state), title, '待人工覆核 · 尚未通知窗口',
                (('單號', rid), ('詢問原文（使用者提供）', request), ('建立時間', created)),
                note, _read_actions(cid), alt)


NOTICES = {
    'expired': ('原確認已過期', '已過期 · 本次未建單',
                '這張確認卡的原期限已到。需要重新整理內容時，請輸入「新需求：」加上詢問。'),
    'cancelled': ('這次詢問已取消', '已取消 · 本次未建單',
                  '已取消這次尚未建單的確認。再點舊卡也不會把它改成同意。'),
    'superseded': ('這張卡屬於較早的任務', '舊卡失效',
                   '目前對話已經換到另一件事。這次沒有替舊卡送出，也沒有把新任務冒充原單。'),
    'pending_verification': ('目前還要查證', '結果待查證',
                            '目前無法核對這筆結果。請稍後查詢原單；先不要重新送出另一份。'),
    'not_authorized': ('目前無法顯示這筆資料', '需要核對權限',
                       '本次沒有顯示私人詢問或單號。請聯絡教學服務管理者。'),
    'confirmation_not_found': ('找不到這份確認', '確認無法使用',
                              '請回到目前任務查看狀態；這次沒有替你重新確認。'),
    'session_not_found': ('目前沒有可查的任務', '尚無目前任務',
                         '需要留下詢問，可輸入「需要協助：」加上內容。'),
    'already_confirmed': ('已記錄原確認', '仍需核對結果',
                          '這個取消動作沒有撤銷原確認。請先查詢結果，避免另建一份。'),
    'version_changed': ('採用資料已有更新', '需要重新確認內容',
                        '這張卡使用的資料版本已不同；請用「新需求：」重新整理內容。'),
    'content_changed': ('確認內容已有變動', '需要重新確認內容',
                        '原卡與目前內容不一致；請重新核對內容後再提出確認。'),
    'explicit_confirmation_required': ('請選擇要確認的卡片', '尚未取得這次同意',
                                       '單獨的一句「好」沒有指定確認內容，請回到原卡操作。'),
    'view_unavailable': ('目前無法整理這張卡', '顯示結果待核對',
                         '取得的欄位不足或格式不符。本次不顯示成功狀態，請稍後查詢目前任務。'),
}


def status_view(result: Mapping[str, Any], confirmation_id: str | None = None) -> View:
    state = result.get('status')
    title, badge, note = NOTICES.get(state, NOTICES['view_unavailable'])
    cid = checked_cid(confirmation_id) if confirmation_id else None
    if state not in ('pending_verification', 'already_confirmed'):
        cid = None
    return View(str(state), title, badge, (), note, _read_actions(cid),
                f'【{badge}】{note} 可查詢目前狀態或取得文字版。')


def _text(text: str, *, size: str = 'md', color: str = INK, weight: str = 'regular') -> dict:
    return {'type': 'text', 'text': text, 'size': size, 'color': color,
            'weight': weight, 'wrap': True, 'scaling': True}


def _flex(view: View) -> dict:
    body = [{'type': 'box', 'layout': 'vertical', 'backgroundColor': AMBER_BG,
             'cornerRadius': 'md', 'paddingAll': 'md',
             'contents': [_text(view.badge, color=AMBER, weight='bold')]}]
    for label, value in view.fields:
        body.append({'type': 'box', 'layout': 'vertical', 'spacing': 'xs',
                     'contents': [_text(label, size='sm', color=MUTED), _text(value)]})
    body.append({'type': 'separator', 'margin': 'md'})
    body.append(_text(view.note, size='sm', color=MUTED))
    buttons = []
    for index, action in enumerate(view.actions):
        buttons.append({'type': 'button', 'style': 'primary' if index == 0 else 'secondary',
                        'height': 'md', 'scaling': True, 'action': action.as_dict(),
                        **({'color': HEADER} if index == 0 else {})})
    message = {'type': 'flex', 'altText': _clip(view.alt, ALT_BUDGET), 'contents': {
        'type': 'bubble', 'size': 'mega',
        'header': {'type': 'box', 'layout': 'vertical', 'backgroundColor': HEADER,
                   'paddingAll': 'lg', 'contents': [_text('LOCAL · 地方詢問', size='xs', color='#FFFFFF'),
                                                  _text(view.title, size='lg', color='#FFFFFF', weight='bold')]},
        'body': {'type': 'box', 'layout': 'vertical', 'paddingAll': 'lg', 'spacing': 'md', 'contents': body},
        'footer': {'type': 'box', 'layout': 'vertical', 'paddingAll': 'lg', 'spacing': 'sm', 'contents': buttons}}}
    validate_local_message(message)
    return message


def _plain(view: View) -> dict:
    text = '\n'.join([f'【{view.badge}】{view.title}'] +
                     [f'{label}：{value}' for label, value in view.fields] + [view.note])
    if units(text) > TEXT_BUDGET:
        raise InvalidView('plain text budget')
    message = {'type': 'text', 'text': text, 'quickReply': {'items': [
        {'type': 'action', 'action': a.as_dict()} for a in view.actions
        if not a.data.startswith('text')]}}
    validate_local_message(message)
    return message


def build_confirmation_flex(result: Mapping[str, Any]) -> dict:
    return _flex(confirmation_view(result))


def build_receipt_flex(result: Mapping[str, Any]) -> dict:
    return _flex(receipt_view(result))


def build_status_flex(result: Mapping[str, Any], confirmation_id: str | None = None) -> dict:
    return _flex(status_view(result, confirmation_id))


def render_result(result: Mapping[str, Any], *, text_only: bool = False,
                  confirmation_id: str | None = None, cancelled_after_creation: bool = False) -> dict:
    """Call only with an authorized backend result, never raw model output."""
    try:
        result = _mapping(result, 'result')
        state = result.get('status')
        if state == 'awaiting_confirmation':
            view = confirmation_view(result)
        elif state in ('request_created', 'already_created', 'existing_request'):
            view = receipt_view(result, cancelled_after_creation=cancelled_after_creation)
        else:
            view = status_view(result, confirmation_id)
        return _plain(view) if text_only else _flex(view)
    except (InvalidView, TypeError):
        # Reject bad selected fields; do not echo secrets or model-authored success text.
        view = status_view({'status': 'view_unavailable'})
        return _plain(view) if text_only else _flex(view)


def validate_local_message(message: Mapping[str, Any]) -> None:
    """Validate this project's output subset. Not LINE server acceptance or a11y proof."""
    if not isinstance(message, dict):
        raise InvalidView('message object')
    actions = []
    if message.get('type') == 'flex':
        if set(message) != {'type', 'altText', 'contents'}:
            raise InvalidView('flex envelope')
        alt = _string(message['altText'], 'altText', 1000)
        if units(alt) > ALT_BUDGET:
            raise InvalidView('altText budget')
        bubble = message['contents']
        if not isinstance(bubble, dict) or bubble.get('type') != 'bubble':
            raise InvalidView('bubble')
        if len(json.dumps(bubble, ensure_ascii=False).encode()) > BUBBLE_BYTE_BUDGET:
            raise InvalidView('bubble budget')
        permitted = {
            'bubble': {'type', 'size', 'header', 'body', 'footer'},
            'box': {'type', 'layout', 'contents', 'backgroundColor', 'cornerRadius', 'paddingAll', 'spacing'},
            'text': {'type', 'text', 'size', 'color', 'weight', 'wrap', 'scaling'},
            'button': {'type', 'style', 'height', 'color', 'scaling', 'action'},
            'separator': {'type', 'margin'},
        }
        def walk(node):
            if not isinstance(node, dict) or node.get('type') not in permitted:
                raise InvalidView('component')
            if set(node) - permitted[node['type']]:
                raise InvalidView('extra component field')
            if node['type'] == 'text':
                _string(node.get('text'), 'text', 3000)
                if node.get('wrap') is not True:
                    raise InvalidView('text must wrap')
            if node['type'] == 'button':
                actions.append(node.get('action'))
            for name in ('header', 'body', 'footer'):
                if name in node:
                    walk(node[name])
            if node['type'] == 'box':
                if node.get('layout') != 'vertical' or not isinstance(node.get('contents'), list):
                    raise InvalidView('box contents')
                for child in node['contents']:
                    walk(child)
        walk(bubble)
    elif message.get('type') == 'text':
        if set(message) - {'type', 'text', 'quickReply'} or units(_string(message.get('text'), 'text', 4500)) > TEXT_BUDGET:
            raise InvalidView('text envelope')
        for item in message.get('quickReply', {}).get('items', []):
            if item.get('type') != 'action':
                raise InvalidView('quick reply')
            actions.append(item.get('action'))
    else:
        raise InvalidView('unsupported message type')
    for action in actions:
        if not isinstance(action, dict) or set(action) != {'type', 'label', 'data', 'displayText'}:
            raise InvalidView('action fields')
        if action['type'] != 'postback':
            raise InvalidView('action type')
        if units(_string(action['label'], 'label', 40)) > 20:
            raise InvalidView('label budget')
        data = _string(action['data'], 'data', 200)
        if data not in ('status', 'text'):
            verb, sep, cid = data.partition(':')
            if not sep or verb not in ('confirm', 'cancel', 'status', 'text'):
                raise InvalidView('action route')
            checked_cid(cid)
        _string(action['displayText'], 'displayText', 200)
