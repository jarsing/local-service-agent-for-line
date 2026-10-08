"""候選本機資料庫；未接線至 Day 14 服務或任何 LINE 帳號。"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from .schema import (SourceDocument, ReviewReceipt, validate_candidate,
                     require_review, candidate_digest)

DDL = """
CREATE TABLE IF NOT EXISTS places (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    area TEXT NOT NULL,
    specialties TEXT NOT NULL,
    dietary_tags TEXT NOT NULL,
    verified_hours TEXT,
    accessibility_notes TEXT,
    source_ref TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    candidate_sha256 TEXT NOT NULL,
    reviewer TEXT NOT NULL
);
"""


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(DDL)
    return db


def admit(db: sqlite3.Connection, raw: str, source: SourceDocument,
          receipt: ReviewReceipt) -> str:
    item = validate_candidate(raw, source)
    require_review(item, source, receipt)
    digest = candidate_digest(item, source)
    values = (digest, item.place_name, source.area,
              json.dumps(item.specialty_dishes, ensure_ascii=False),
              json.dumps(item.dietary_tags, ensure_ascii=False),
              item.opening_hours_text, item.accessibility_notes,
              source.source_ref, source.sha256, digest, receipt.reviewer)
    with db:
        db.execute("INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                   "ON CONFLICT(id) DO NOTHING", values)
    return digest


def search_reviewed_places(db: sqlite3.Connection, *, area: str = "",
                           dietary_type: str = "", keyword: str = "") -> dict:
    """候選讀取器：目前只支援不限飲食條件，不放寬舊蔬食工具。"""
    if not all(isinstance(s, str) and len(s) <= 80 for s in (area, dietary_type, keyword)):
        raise ValueError("INVALID_QUERY")
    if dietary_type not in ("", "any", "不限"):
        return {"status": "unsupported_filter", "places": [], "total": 0,
                "message": "此來源尚未建立素別映射；請保留既有蔬食查詢。"}
    if area in ("附近", "這附近"):
        return {"status": "needs_area", "places": [], "total": 0}
    rows = db.execute("SELECT * FROM places ORDER BY id").fetchall()
    matches = []
    for row in rows:
        record = dict(row)
        dishes = json.loads(record.pop("specialties"))
        tags = json.loads(record.pop("dietary_tags"))
        if area and record["area"] != area:
            continue
        if keyword.casefold() not in (record["name"] + " " + " ".join(dishes)).casefold():
            continue
        matches.append({**record, "specialties": dishes, "dietary_tags": tags,
                        "open_now": None, "coordinates": None,
                        "walking_distance_m": None})
    return {"status": "ok" if matches else "not_found", "places": matches[:5],
            "total": len(matches), "scope": "DAY25_LOCAL_CANDIDATE_READER",
            "production_tool_integrated": False}
