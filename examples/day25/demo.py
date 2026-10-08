"""Mock 模擬資料與真實 SQLite 操作；不呼叫 Gemini 或 LINE。"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .fixtures import sample
from .schema import (validate_candidate, candidate_digest, required_review_fields,
                     ReviewReceipt)
from .store import open_db, admit, search_reviewed_places


def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    source, item, raw = sample("clear")
    validated = validate_candidate(raw, source)
    receipt = ReviewReceipt(source_sha256=source.sha256,
        candidate_sha256=candidate_digest(validated, source),
        reviewer="synthetic-local-test", approved=True,
        checked_fields=sorted(required_review_fields(validated)))
    db = open_db(out / "places.sqlite3")
    try:
        first = admit(db, raw, source, receipt)
        again = admit(db, raw, source, receipt)
        rows = search_reviewed_places(db, keyword="爌肉飯")
        result = {"origin": "MOCK_INPUT_REAL_LOCAL_SQLITE", "external_model_calls": 0,
                  "line_calls": 0, "inserted_rows": db.execute("SELECT count(*) FROM places").fetchone()[0],
                  "same_id_on_repeat": first == again,
                  "search_result": rows, "human_review_executed": False,
                  "review_receipt_origin": "SYNTHETIC_TEST_ONLY"}
        (out / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    a = parser.parse_args()
    print(json.dumps(run(a.out), ensure_ascii=False, indent=2))
