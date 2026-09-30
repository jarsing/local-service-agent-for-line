"""結果型別對應固定 LINE 訊息；模型不控制文案、URL 或按鈕資料。"""
from __future__ import annotations

from .outcomes import FailureReason, QueryOutcome, QueryState


MENU = (
    ("查活動", "d14:events", "查詢地方活動"),
    ("查蔬食", "d14:places", "尋找蔬食店家"),
    ("留下服務詢問", "d14:enquiry", "留下服務詢問"),
)
RETRY_TEXT = "重新輸入查詢條件"


def _units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def text(value: str) -> dict[str, object]:
    if not isinstance(value, str) or not value or _units(value) > 4500:
        raise ValueError("TEXT_BUDGET")
    return {"type": "text", "text": value}


def action(label: str, data: str, display: str) -> dict[str, str]:
    if not label or _units(label) > 20 or len(data) > 300 or _units(display) > 300:
        raise ValueError("ACTION_BUDGET")
    return {"type": "postback", "label": label, "data": data, "displayText": display}


def retry_action() -> dict[str, str]:
    # 新的一次使用者操作先顯示條件提示，不保存或重播上次查詢文字。
    return {"type": "message", "label": "稍後重新查詢", "text": RETRY_TEXT}


def card(title: str, body: str, actions: list[dict[str, str]]) -> dict[str, object]:
    return {
        "type": "flex", "altText": (title + "。" + body).replace("\n", " ")[:340],
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "spacing": "md",
                "contents": [
                    {"type": "text", "text": title, "weight": "bold", "size": "lg", "wrap": True, "scaling": True},
                    {"type": "text", "text": body, "size": "sm", "wrap": True, "scaling": True},
                ],
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {"type": "button", "height": "sm", "style": "secondary", "action": item}
                    for item in actions
                ],
            },
        },
    }


def help_card(*, unsupported: bool = False) -> dict[str, object]:
    lead = "這項需求超出 LOCAL 目前的服務範圍。\n" if unsupported else ""
    return card(
        "先選這次要做什麼",
        lead + "LOCAL 目前能查活動、找店家及留下詢問，沒有停車查詢或預約功能。\n"
        "查詢與留下詢問都不會自動保存飲食偏好。",
        [action(*item) for item in MENU],
    )


def retry_guide() -> dict[str, object]:
    return card(
        "請重新告訴我查詢條件",
        "可以輸入鄉鎮、日期或想找的店家。這次會重新查詢；也可先選下方入口。",
        [action(*item) for item in MENU[:2]],
    )


def _unavailable_card(reason: str) -> dict[str, object]:
    if reason == FailureReason.CATALOG_CHANGED.value:
        body = "活動資料的版本正在核對，這次結果先不採用。請等資料更新後再查，也可查看原本的服務單。"
    elif reason == FailureReason.RATE_LIMITED.value:
        body = "這次查詢遇到使用額度或流量限制，暫時無法完成。可以稍後再查，或查看原本的服務單。"
    else:
        body = "這次查詢暫時無法完成。可以稍後重新輸入條件，或查看原本的服務單。"
    return card(
        "這次暫時查不了", body,
        [retry_action(), action("查原本單據", "status", "查看原本服務單")],
    )


def present_query_outcome(outcome: QueryOutcome) -> list[dict[str, object]]:
    if outcome.state is QueryState.UNAVAILABLE:
        return [_unavailable_card(outcome.reason)]
    if outcome.state is QueryState.UNSUPPORTED:
        return [help_card(unsupported=True)]
    if outcome.state is QueryState.HELP:
        return [help_card()]
    if outcome.state is QueryState.PREFERENCE_CHANGED:
        return [text("偏好剛被修改或忘記，這次結果先不套用。請再查一次。")]
    if outcome.state is QueryState.NEEDS_AREA:
        return [card(
            "想找哪個鄉鎮？",
            "目前只有部分公開店家快照；請選區域。距離與步行路線尚未提供。",
            [action(area, "d14:area:" + area, "查" + area + "店家") for area in outcome.available_areas[:5]],
        )]
    if outcome.state is QueryState.NO_DATA:
        actions = [{"type": "message", "label": "重新輸入條件", "text": RETRY_TEXT}]
        if outcome.tool_name == "search_local_places":
            actions.insert(0, action("換個鄉鎮查詢", "d14:places", "重新選擇店家查詢鄉鎮"))
        body = (
            "這次已完成查詢，這份歷史教學快照中沒有符合條件的項目。可以調整條件再查；這不是即時活動或預約名單。"
            if outcome.tool_name == "search_local_events" else
            "這次已完成查詢，這份精選公開店家快照中沒有符合條件的項目。可以調整條件再查；快照沒有收錄，不代表現場一定沒有。"
        )
        return [card(
            "這份快照沒有符合資料",
            body,
            actions,
        )]
    if outcome.state is QueryState.SUCCESS:
        return [
            text("\n\n".join(outcome.rows)),
            card("接下來", "查詢結果不等於預約或已存偏好。", [action(*item) for item in MENU]),
        ]
    raise ValueError("UNKNOWN_QUERY_STATE")
