"""型別、來源核對與人工審閱收據，各自承擔不同責任。"""
from __future__ import annotations
import hashlib
import json
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class PlaceExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    place_name: str = Field(min_length=1, max_length=100)
    specialty_dishes: list[str] = Field(max_length=12)
    dietary_tags: list[str] = Field(max_length=12)
    hours_status: Literal["explicitly_stated", "unverified"]
    opening_hours_text: str | None = None
    accessibility_notes: str | None = None
    source_quote: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def check_hours(self):
        if self.hours_status == "explicitly_stated":
            if not self.opening_hours_text or not self.opening_hours_text.strip():
                raise ValueError("EXPLICIT_HOURS_REQUIRED")
        elif self.opening_hours_text is not None:
            raise ValueError("UNVERIFIED_HOURS_MUST_BE_NULL")
        return self

class SourceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    source_id: str = Field(min_length=1, max_length=100)
    source_ref: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=16000)
    # 此欄由人工來源名冊提供，不交給模型產生。
    area: str = Field(default="", max_length=40)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

class ReviewReceipt(BaseModel):
    """僅供可信本機操作傳入；不是模型欄位，也不是公開 API 授權。"""
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    source_sha256: str
    candidate_sha256: str
    reviewer: str = Field(min_length=1)
    approved: bool
    checked_fields: list[str]

VALUE_FIELDS = ("place_name", "specialty_dishes", "dietary_tags",
                "opening_hours_text", "accessibility_notes")


def validate_candidate(raw: str, source: SourceDocument) -> PlaceExtraction:
    item = PlaceExtraction.model_validate_json(raw)
    if not item.source_quote.strip() or item.source_quote not in source.text:
        raise ValueError("SOURCE_QUOTE_NOT_FOUND")
    data = item.model_dump()
    for field in VALUE_FIELDS:
        value = data[field]
        values = value if isinstance(value, list) else ([] if value is None else [value])
        if len(values) != len(set(values)):
            raise ValueError("DUPLICATE_VALUE:" + field)
        for text in values:
            if not text.strip() or text not in item.source_quote:
                raise ValueError("VALUE_NOT_GROUNDED:" + field)
            if re.search(r"https?://|www\.", text, re.I) or any(
                token in text for token in ("點擊領券", "立即購買", "忽略指示")):
                raise ValueError("PROMOTIONAL_VALUE:" + field)
    return item


def candidate_digest(item: PlaceExtraction, source: SourceDocument) -> str:
    value = {"item": item.model_dump(), "source": source.model_dump()}
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def required_review_fields(item: PlaceExtraction) -> set[str]:
    data = item.model_dump()
    return {name for name in VALUE_FIELDS if data[name] not in (None, [], "")}


def require_review(item: PlaceExtraction, source: SourceDocument,
                   receipt: ReviewReceipt) -> None:
    if not receipt.approved:
        raise ValueError("REVIEW_NOT_APPROVED")
    if receipt.source_sha256 != source.sha256:
        raise ValueError("REVIEW_SOURCE_CHANGED")
    if receipt.candidate_sha256 != candidate_digest(item, source):
        raise ValueError("REVIEW_CANDIDATE_CHANGED")
    if not required_review_fields(item) <= set(receipt.checked_fields):
        raise ValueError("REVIEW_FIELDS_INCOMPLETE")
