"""Day 27 本機備援示範：合成身分、真實 SQLite，無外部服務呼叫。

從固定 LOCAL Repo 根目錄執行；輸出目錄必須不存在。
本程式是本日教學候選，並非已推送至公開 Repo 的檔案。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from examples.day22.circuit_breaker import SecurityStore, Paused, demo_policy
import examples.day22.circuit_breaker as core

EXPECTED_CORE_SHA256 = "f0ff3a99d082a7777fe1f019936087404844e46fb19d433b4501ee589a8548f1"
REFERENCE_COMMIT = "f8267a84fc7456783b2229e42b580d705164fd8d"


def require(condition: bool, reason: str) -> None:
    if condition is not True:
        raise RuntimeError(reason)


def exercise(store: SecurityStore) -> dict:
    store.set_mode("sample-operator", "SERVING", "demo")
    epoch = store.admit("sample-user")
    first = store.confirm("sample-user", "demo-confirm", "meal_inquiry", epoch)
    rid, version = first["request_id"], first["claim_version"]
    events = [{"step": "confirmed", "request_id": rid, "state": first["state"]}]
    store.set_mode("sample-operator", "PAUSED", "incident")
    try:
        store.claim("sample-volunteer", rid, version)
    except Paused as exc:
        require(str(exc) == "SERVICE_PAUSED", "WRONG_PAUSE_REASON")
    else:
        raise RuntimeError("PAUSED_CLAIM_ACCEPTED")
    require(store.read("sample-user", rid) == first, "PAUSED_ROW_CHANGED")
    events.append({"step": "paused_claim", "request_id": rid, "blocked": True})
    store.set_mode("sample-operator", "SERVING", "recovered")
    claimed = store.claim("sample-volunteer", rid, version)
    require(claimed is True, "CLAIM_FAILED")
    second = store.claim("sample-second-volunteer", rid, version)
    require(second is False, "SECOND_CLAIM_ACCEPTED")
    after = store.read("sample-user", rid)
    require(after["state"] == "human_claimed", "WRONG_STATE")
    require(after["claimed_by"] == "sample-volunteer", "WRONG_CLAIMANT")
    require(after["claim_version"] == version + 1, "WRONG_VERSION")
    again = store.confirm("sample-user", "demo-confirm", "meal_inquiry", epoch)
    require(again == after, "REPEATED_CONFIRM_CHANGED_REQUEST")
    require(len(store.request_snapshot()) == 1, "DUPLICATE_REQUEST")
    events.append({"step": "claimed_and_read", "request_id": rid,
                   "state": after["state"], "claim_version": after["claim_version"]})
    events.append({"step": "same_operation_again", "request_id": again["request_id"],
                   "same_request": again["request_id"] == rid})
    return {"status": "PASS", "request_id": rid, "events": events,
            "request_count": 1, "claim_version_before": version,
            "claim_version_after": after["claim_version"],
            "final_state": after["state"], "second_claim_succeeded": second}


def run(out: Path) -> dict:
    core_path = Path(core.__file__)
    core_sha = hashlib.sha256(core_path.read_bytes()).hexdigest()
    require(core_sha == EXPECTED_CORE_SHA256, "CORE_VERSION_MISMATCH")
    out.mkdir(parents=True, exist_ok=False)
    metadata = {"scope": "SYNTHETIC_IDENTITIES_REAL_SQLITE",
                "execution_origin": "LOCAL_RUN", "reference_commit": REFERENCE_COMMIT,
                "core_sha256": core_sha,
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "python": platform.python_version(), "platform": platform.platform(),
                "external_model_calls": 0, "line_calls": 0,
                "network_isolation": "NOT_APPLIED", "live_handoff": "NOT_RUN"}
    try:
        result = exercise(SecurityStore(out / "demo.sqlite3", demo_policy()))
    except Exception as exc:
        report = {**metadata, "status": "FAIL", "error_type": type(exc).__name__,
                  "reason": str(exc)}
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise
    report = {**metadata, **result}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.out), ensure_ascii=False, indent=2))
