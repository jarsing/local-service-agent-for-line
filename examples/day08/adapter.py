"""Day 8 資料匯入 Adapter。

讀取 Day 7 歸檔活動資料（卦山大縱走・花壇場次），
提供 Day 8 演練狀態下的快照切換（更新前 v1 與採用後 v2）。
不修改 Day 7 的 active.json 或原始 evidence。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# 預設活動：花壇場次
DEFAULT_EVENT_ID = "evt-60d76a55472c503faa4c"

# 內建唯讀資料快照（源自 Day 7 真正發布與歸檔紀錄）
SNAPSHOT_V1 = {
    "catalog_version": "v-0337e2296139",
    "status": "adopted",
    "source_kind": "reviewed_base",
    "event": {
        "id": DEFAULT_EVENT_ID,
        "name": "卦山大縱走 彰化兜兜圈",
        "area": "花壇",
        "venue": "大嶺巷步道",
        "date": "2026-09-19",
        "time": "07:30~11:00",
        "meeting_point": "尚未公布",
        "meeting_time": "尚未公布",
    }
}

SNAPSHOT_V2 = {
    "catalog_version": "v-62ccd0ef3ca44e6ca8b7ef2d3302ab28",
    "status": "adopted",
    "source_kind": "reviewed_teaching_revision",
    "event": {
        "id": DEFAULT_EVENT_ID,
        "name": "卦山大縱走 彰化兜兜圈",
        "area": "花壇",
        "venue": "大嶺巷步道",
        "date": "2026-09-19",
        "time": "08:00~11:00",
        "meeting_point": "尚未公布",
        "meeting_time": "尚未公布",
    }
}


class CatalogCatalogState:
    """Day 8 獨立的演練狀態管理。不更動外部 Day 7 檔案。"""

    def __init__(self, initial_version: str = "v1") -> None:
        self._current_version_label = initial_version
        self._custom_snapshots: dict[str, dict[str, Any]] = {
            "v1": SNAPSHOT_V1,
            "v2": SNAPSHOT_V2,
        }

    @property
    def version_label(self) -> str:
        return self._current_version_label

    @property
    def current_snapshot(self) -> dict[str, Any]:
        return self._custom_snapshots[self._current_version_label]

    @property
    def catalog_version(self) -> str:
        return self.current_snapshot["catalog_version"]

    @property
    def data_status(self) -> str:
        return self.current_snapshot["status"]

    def get_event(self, event_id: str) -> dict[str, Any]:
        event = self.current_snapshot["event"]
        if event["id"] != event_id:
            raise KeyError(f"Event {event_id} not found in current catalog snapshot.")
        return dict(event)

    def switch_to(self, version_label: str) -> None:
        if version_label not in self._custom_snapshots:
            raise ValueError(f"Unknown version label: {version_label}. Must be 'v1' or 'v2'.")
        self._current_version_label = version_label


def load_from_day07_evidence(evidence_dir: Path | str) -> tuple[dict[str, Any], dict[str, Any]]:
    """嘗試從 Day 7 evidence run 目錄讀取真實快照；失敗時回退至內建快照。"""
    p = Path(evidence_dir)
    base_file = p / "base.enriched.json"
    after_file = p / "catalog.after.json"
    if not base_file.exists() or not after_file.exists():
        return SNAPSHOT_V1, SNAPSHOT_V2

    try:
        with open(base_file, "r", encoding="utf-8") as f:
            base_data = json.load(f)
        with open(after_file, "r", encoding="utf-8") as f:
            after_data = json.load(f)

        def extract_event(catalog_data: dict[str, Any]) -> dict[str, Any]:
            for ev in catalog_data.get("events", []):
                if ev.get("id") == DEFAULT_EVENT_ID:
                    fields = ev.get("fields", {})
                    enrichments = ev.get("enrichments", {})
                    date_val = enrichments.get("date", {}).get("value") or fields.get("date", {}).get("value")
                    return {
                        "id": DEFAULT_EVENT_ID,
                        "name": fields.get("name", {}).get("value", "卦山大縱走 彰化兜兜圈"),
                        "area": fields.get("area", {}).get("value", "花壇"),
                        "venue": fields.get("venue", {}).get("value", "大嶺巷步道"),
                        "date": date_val or "2026-09-19",
                        "time": fields.get("time", {}).get("value", ""),
                        "meeting_point": fields.get("meeting_point", {}).get("value") or "尚未公布",
                        "meeting_time": fields.get("meeting_time", {}).get("value") or "尚未公布",
                    }
            return SNAPSHOT_V1["event"]

        v1 = {
            "catalog_version": "v-0337e2296139",
            "status": "adopted",
            "source_kind": "reviewed_base_enriched",
            "event": extract_event(base_data),
        }
        v2 = {
            "catalog_version": "v-62ccd0ef3ca44e6ca8b7ef2d3302ab28",
            "status": "adopted",
            "source_kind": "reviewed_teaching_revision",
            "event": extract_event(after_data),
        }
        return v1, v2
    except Exception:
        return SNAPSHOT_V1, SNAPSHOT_V2
