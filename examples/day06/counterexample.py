"""合成反例：欄位格式合法，仍可能把活動時間放進集合時間。"""
from __future__ import annotations
from copy import deepcopy
from schema import Extraction, FIELDS


def fixture():
    missing={"value":None,"quote":None,"status":"not_shown"}
    event={key:deepcopy(missing) for key in FIELDS}
    def stated(value,quote):
        return {"value":value,"quote":quote,"status":"stated"}
    event.update(name=stated("測試用社區走讀","測試用社區走讀"),
                 date=stated("2026-09-26","2026 年 9 月 26 日"),
                 area=stated("彰化市","彰化市"),
                 time=stated("09:30","活動時間 09:30"),
                 venue=stated("社區活動中心","活動地點：社區活動中心"),
                 meeting_time=stated("09:00","集合時間 09:00"),
                 meeting_point=stated("車站前廣場","集合地點：車站前廣場"))
    return {"events":[event],"notes":[]}


def demonstrate():
    expected=fixture()
    changed=deepcopy(expected)
    changed["events"][0]["meeting_time"]={"value":"09:30","quote":"活動時間 09:30","status":"stated"}
    Extraction.model_validate(changed)
    return {"kind":"SYNTHETIC_VALIDATOR_COUNTEREXAMPLE","source":"手工建立的離線反例，不是 Gemini 回覆",
            "schema_valid":True,"expected_meeting_time":"09:00","candidate_meeting_time":"09:30",
            "matches_expected":changed["events"][0]["meeting_time"]["value"]==expected["events"][0]["meeting_time"]["value"],
            "lesson":"型別與欄位結構通過後，還要核對這段時間屬於哪個標籤。"}
