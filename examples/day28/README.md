# Developer handoff examples

This candidate includes a local FastAPI routing experiment and a proposed request-claim adapter. It has not been integrated into the live LOCAL deployment. No Cloud Run, Firestore, Gemini or LINE call is made by its tests.

## Run locally after integration

From the repository root, prepare an isolated environment with `requirements-dev.txt`, then run:

```bash
python3 -m unittest discover -s examples/day28 -p test_contracts.py -v
python3 -O -m unittest discover -s examples/day28 -p test_contracts.py -v
python3 examples/day28/health_example.py
```

21 tests = 17 claim contracts + 4 FastAPI checks. Running them in two interpreter modes does not create 42 distinct test cases. `MemoryTx` tests value contracts and read-before-write order; it does not emulate Firestore contention, retries or isolation.

## Route experiment

Registering `/healthz` on one app but exporting another produces 404. Using the configured app produces 200. Mounting it under `/api` exposes `/api/healthz`, not the parent's `/healthz`. This is a controlled example, not the established cause of the historic deployed 404.

## Claim candidate

`claim_in_tx` is compatible with the method shape of the existing Day 11 `get/put/atomic` adapter. The storage key remains the original 64-character `operation_id`; `request_id` is the value displayed to the user and must be checked, not substituted for the document path.

`claim_version`, `claimed_by`, `volunteer_grants` and `service_controls` are proposed additions. Missing versions raise `SCHEMA_MIGRATION_REQUIRED`. The current production schema must be migrated explicitly; missing values are not converted to 1.

`VerifiedVolunteer` is a trusted-entry value, not an authentication mechanism. A real integration must verify LINE signature, the current event identity, role assignment and service scope before obtaining it, and must create grant/control records through an authorized administration route. Do not populate it from untrusted request-body role flags.

The adapter reads request, binding, current grant and control within a transaction, then makes at most one write. It keeps request content and owner bindings. A serving-mode retry by the same claimant reads current state without another write. The candidate does not yet update Day 11 lookup validators, Day 13 cards or notification outbox delivery.

## Remaining acceptance

Use the real adapter and a dedicated test namespace for Firestore integration tests, including simultaneous claims, transaction retries, paused mode, revoked grants, old cards, owner-only readback and schema migration. Real phone screenshots and server records must share the same authoritative request ID. None of those results are supplied by this local mock test suite.

Source baseline: `b8d62771abc9353933b6cb1e69ae237b27546381`. See the article's separate runtime observations and the release checklist for publication conditions.
