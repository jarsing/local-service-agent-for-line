"""Day 6：從海報擷取的欄位、原文依據與待核對狀態。"""
from __future__ import annotations

from datetime import date as Date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FIELDS = ("name", "date", "area", "time", "venue", "meeting_time", "meeting_point", "accessibility")
LABELS = {"name": "活動名稱", "date": "活動日期", "area": "鄉鎮市區", "time": "活動時間",
          "venue": "活動場地", "meeting_time": "集合時間", "meeting_point": "集合地點",
          "accessibility": "全程輪椅通行"}

class TextField(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str | None = Field(description="欄位內容；缺字、沒寫或不能確定時用 null。")
    quote: str | None = Field(description="圖片上支持本欄位的短句原文；沒有對應文字時用 null。")
    status: Literal["stated", "not_shown", "unclear"]

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "stated":
            if not self.value or not self.value.strip() or not self.quote or not self.quote.strip():
                raise ValueError("已讀到的文字欄位需要值與原文。")
        elif self.value is not None:
            raise ValueError("缺漏或不清楚的欄位應保留 null。")
        if self.status == "not_shown" and self.quote is not None:
            raise ValueError("圖片未顯示的欄位沒有引句。")
        if self.value is not None and len(self.value) > 500:
            raise ValueError("欄位過長。")
        if self.quote is not None and len(self.quote) > 500:
            raise ValueError("引句過長。")
        return self

class BooleanField(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: bool | None = Field(description="只有明確談到全程輪椅通行才填 true 或 false，其餘為 null。")
    quote: str | None = Field(description="支持全程可通行或不適合通行的圖片原文。")
    status: Literal["stated", "not_shown", "unclear"]

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "stated":
            if self.value is None or not self.quote or not self.quote.strip():
                raise ValueError("通行判斷需要布林值與原文。")
        elif self.value is not None:
            raise ValueError("待確認的通行條件使用 null。")
        if self.status == "not_shown" and self.quote is not None:
            raise ValueError("圖片未顯示的欄位沒有引句。")
        return self

class PosterEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: TextField
    date: TextField = Field(description="活動日期 YYYY-MM-DD。只有月日而沒有年份，保留原文並標 unclear。")
    area: TextField = Field(description="圖片明寫的鄉鎮市區；只看見場館名時留待核對。")
    time: TextField = Field(description="活動開始時間或時段，保留圖片語意；與集合時間分開。")
    venue: TextField = Field(description="活動進行的場地。")
    meeting_time: TextField = Field(description="圖片明寫的集合或報到時間。")
    meeting_point: TextField = Field(description="圖片明寫的集合或報到位置；與活動場地分開。")
    accessibility: BooleanField

    @model_validator(mode="after")
    def valid_date(self):
        value = self.date.value
        if value is not None:
            if Date.fromisoformat(value).isoformat() != value:
                raise ValueError("活動日期須為 YYYY-MM-DD。")
        return self

class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    events: list[PosterEvent] = Field(description="按圖片閱讀順序列出活動／場次，最多十筆。")
    notes: list[str] = Field(max_length=8, description="圖片辨識上的疑點，例如年份未顯示或多個地點。")

    @field_validator("events")
    @classmethod
    def event_limit(cls, v: list[PosterEvent]) -> list[PosterEvent]:
        if len(v) > 10:
            raise ValueError("活動場次最多十筆。")
        return v


def as_catalog(extraction: Extraction, source: dict, reviewed_at: str, reviewer: str) -> dict:
    """把已核對的值整理成 Day 5 搜尋函式可讀的資料；來源由程式附上。"""
    events = []
    for index, event in enumerate(extraction.events, 1):
        fields = event.model_dump()
        if not fields["name"]["value"]:
            raise ValueError("先核對活動名稱，才能加入搜尋目錄。")
        values = {key: fields[key]["value"] for key in FIELDS}
        events.append({"id": f'poster-{source["sha256"][:12]}-{index:02}', **values,
                       "source": source["source_ref"],
                       "updated_at": source.get("source_updated_at"),
                       "source_image_sha256": source["sha256"],
                       "field_evidence": fields})
    if not events:
        raise ValueError("核對資料至少需要一筆活動。")
    return {"kind": "reviewed_poster_data", "version": "day06-" + reviewed_at,
            "events": events, "review": {"reviewer": reviewer, "reviewed_at": reviewed_at},
            "source": source}
