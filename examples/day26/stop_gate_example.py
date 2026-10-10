import json
from pathlib import Path
from examples.day22.circuit_breaker import SecurityStore, Paused, demo_policy

root = Path("out/day26/claim-01")
root.mkdir(parents=True, exist_ok=False)
store = SecurityStore(root / "claims.sqlite3", demo_policy())
store.set_mode("sample-operator", "SERVING", "demo")
epoch = store.admit("sample-user")
request = store.confirm("sample-user", "sample-operation", "meal_inquiry", epoch)
rid, version = request["request_id"], request["claim_version"]
store.set_mode("sample-operator", "PAUSED", "incident")
try:
    store.claim("sample-volunteer", rid, version)
except Paused as exc:
    if str(exc) != "SERVICE_PAUSED":
        raise AssertionError(f"UNEXPECTED_EXCEPTION: {exc}")
else:
    raise AssertionError("PAUSED_CLAIM_ACCEPTED")
if store.read("sample-user", rid) != request:
    raise AssertionError("REQUEST_MUTATED_WHILE_PAUSED")
store.set_mode("sample-operator", "SERVING", "recovered")
if not store.claim("sample-volunteer", rid, version):
    raise AssertionError("FIRST_CLAIM_REJECTED")
if store.claim("sample-second-volunteer", rid, version):
    raise AssertionError("SECOND_CLAIM_ACCEPTED")
current = store.read("sample-user", rid)
if current["state"] != "human_claimed" or current["claimed_by"] != "sample-volunteer":
    raise AssertionError("CLAIM_STATE_MISMATCH")
if current["claim_version"] != version + 1:
    raise AssertionError("VERSION_NOT_INCREMENTED")
report = {
    "scope": "LOCAL_SQLITE_SYNTHETIC_IDENTITIES",
    "request_id": rid, "state": current["state"],
    "external_calls": 0, "line_device_test": "NOT_RUN",
}
(root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
