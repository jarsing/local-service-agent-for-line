"""LOCAL 的活動目錄與唯讀搜尋。只用 Python 標準函式庫。"""
from __future__ import annotations

from copy import deepcopy
from datetime import date as Date
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL_NAME = "search_local_events"
FILTERS = ("date", "area", "keyword")
EVENT_FIELDS = ("id", "name", "date", "area", "time", "meeting_point", "accessibility", "source", "updated_at")


def load_catalog(path: Path = HERE / "catalog.json") -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("kind") != "synthetic_teaching_data" or not isinstance(data.get("events"), list):
        raise ValueError("活動目錄格式不符。")
    if not data["events"] or len({e["id"] for e in data["events"]}) != len(data["events"]):
        raise ValueError("活動編號需唯一，目錄至少要有一筆資料。")
    for event in data["events"]:
        for field in EVENT_FIELDS:
            if field != "accessibility" and (not isinstance(event.get(field), str) or not event[field]):
                raise ValueError("活動必要欄位不完整。")
        Date.fromisoformat(event["date"])
        if event.get("accessibility") is not None and type(event["accessibility"]) is not bool:
            raise ValueError("accessibility 使用 true、false 或 null。")
    return data


def load_cases() -> list[dict]:
    return json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]


def normalize_query(args: dict) -> dict[str, str]:
    if not isinstance(args, dict) or set(args) - set(FILTERS):
        raise ValueError("搜尋只接受 date、area、keyword。")
    query = {}
    for key in FILTERS:
        value = args.get(key, "")
        if not isinstance(value, str) or len(value) > 80:
            raise ValueError("搜尋條件應為 80 字以內的文字。")
        query[key] = value.strip()
    if not any(query.values()):
        raise ValueError("請至少提供一項搜尋條件。")
    if query["date"] and Date.fromisoformat(query["date"]).isoformat() != query["date"]:
        raise ValueError("日期請用 YYYY-MM-DD。")
    return query


def search_catalog(data: dict, args: dict) -> dict:
    """條件以 AND 組合；缺少的無障礙欄位在回傳時明示為 null。"""
    query = normalize_query(args)
    found = []
    unknown = []
    for original in data["events"]:
        if query["date"] and original["date"] != query["date"]:
            continue
        if query["area"] and query["area"] not in original["area"]:
            continue
        if query["keyword"] and query["keyword"].casefold() not in original["name"].casefold():
            continue
        event = deepcopy(original)
        event.setdefault("accessibility", None)
        if event["accessibility"] is None:
            unknown.append(event["id"] + ".accessibility")
        found.append(event)
    return {"status": "ok" if found else "not_found", "query": query,
            "catalog_version": data["version"], "events": found,
            "unknown_fields": unknown}


def make_search_tool(data: dict, emit, *, max_calls: int = 2):
    """建立具明確函式名稱的工具；每個 Agent 回合獨立計數。"""
    count = 0

    def search_local_events(date: str = "", area: str = "", keyword: str = "") -> dict:
        """依日期、地區或活動名稱，搜尋 LOCAL 的示範活動目錄。

        Args:
            date: 活動日期 YYYY-MM-DD，空字串代表不限日期。
            area: 鄉鎮市名稱，例如彰化市或鹿港鎮，空字串代表不限地區。
            keyword: 活動名稱關鍵字，例如社區走讀，空字串代表不限名稱。

        Returns:
            status 為 ok、not_found 或 error；events 含活動資訊、source 及
            updated_at；unknown_fields 列出待確認欄位。accessibility 為 null
            表示資料未確認，false 表示已知路線有不適合輪椅通行的條件。
        """
        nonlocal count
        if count >= max_calls:
            result = {"status": "error", "code": "TOOL_LIMIT", "events": [], "unknown_fields": []}
            emit("TOOL_REJECTED", result=result)
            return result
        count += 1
        args = {"date": date, "area": area, "keyword": keyword}
        try:
            result = search_catalog(data, args)
        except (ValueError, TypeError):
            result = {"status": "error", "code": "INVALID_ARGUMENTS", "events": [], "unknown_fields": []}
        emit("TOOL_EXECUTED", name=TOOL_NAME, args=args, result=result)
        return result

    return search_local_events
