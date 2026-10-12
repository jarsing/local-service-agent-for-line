# Observation contract and collection boundary

## Three independent records

1. Fixture: proposed inputs, setup, steps and expected assertions.
2. Raw observation: values actually produced by a reviewed collector while running the selected source.
3. Grade: deterministic comparison of an observation to the fixture.

The fixture is new work. No collector implementation is included. The current report therefore contains 100 NOT_RUN cases, not successful LOCAL execution.

## Index shape

`index.json` is a JSON object with exactly the key `records`. Each record contains a known, unique `case_id` and a `raw` reference with a relative path and SHA-256. This fragment describes the shape only; placeholders are not executable observations:

```json
{
  "records": [
    {"case_id": "L29-001", "raw": {"path": "L29-001.json", "sha256": "<SHA-256 of actual raw-file bytes>"}}
  ]
}
```

## Raw-observation required bindings

| Field | Contract |
|---|---|
| `case_id` | Exact fixture ID |
| `case_sha256` | `digest(case)` over canonical JSON |
| `fixture_sha256` | SHA-256 over the actual fixture file bytes |
| `source_commit` | Full 40-character tested source commit, matching CLI |
| `input_sha256` | `digest(stimulus_for(case))`; input excludes `assertions` |
| `collector_sha256` | Actual collector implementation fingerprint |
| `config_sha256` | Canonical nonsecret configuration fingerprint; same within an aggregate batch |
| `mode` | `offline_contract` or `live_model`, matching CLI |
| `origin` | `captured_execution`; a declaration, not an authentication mechanism |
| `execution` | `COMPLETED`, `NOT_RUN`, or `BLOCKED` |
| `data` | Actual observed JSON object when completed |
| `elapsed_ms` | Nonnegative finite number or null; measures a declared operation, not automatically model latency |
| `reason` | Explanation for NOT_RUN/BLOCKED, when applicable |

Canonical JSON uses sorted keys, UTF-8, compact separators, and `allow_nan=False`. Fixture byte hash is intentionally distinct from semantic/canonical object hashes. Update references after an authorized fixture change; do not edit old evidence to match a new file.

The reader rejects duplicate JSON keys, nonfinite JSON constants, unknown/duplicate case IDs, absolute or escaping raw paths, digest mismatches and mixed configurations. Test files deliberately generate synthetic envelopes for parser testing. Those fixtures must never be presented as service observations.

## How to implement the missing collectors

A collector needs to consume the **stimulus only**, call real existing code or a clearly named simulator, observe effects, and write an append-only batch. It must not select a value from `case['assertions']` and call that an observation.

| Family | Proposed collection basis | Required caution |
|---|---|---|
| events/access | Actual lookup tool result and rendered result from the fixed catalog | Unknown accessibility is different from verified false; a synthetic catalog must be labeled |
| places | Lookup/admission output and fixed clock | Do not use fictional hours as real-store facts |
| memory | Actual preference store and consent-card operations | Revoke/cancel/forget are different; retain only minimal nonsecret evidence |
| requests | Original operation bindings, transactional snapshots, counts and versions | Preserve `operation_id` document key vs display `request_id`; `L29-079` needs two actual connections and a concurrency barrier |
| untrusted | Proposed/executed tool calls, backend side effects and visible response | A refusal sentence alone cannot prove no unauthorized write; `L29-091` is text only |

Day 18 already has an observed-record format and a three-part scorer. This new fixture is **not** that format. Map actual outputs explicitly, test each mapping, and keep both the original output and the mapped record. Do not pretend existing Day 18 adapters can already accept all 100 new operations.

For a real-model batch, additionally preserve sanitized SDK request/response data, call IDs, tool events, model version, tool schema, prompt/config fingerprints and full usage metadata. The present grader does not audit these additional model records or compute accuracy/cost from them.

For phone acceptance, preserve A-confirm/B-delivery/B-claim/A-readback as one complete script with authoritative IDs and deployment revision. Do not infer the full script from a subset of screenshots.

## Meaning of metrics

`tested` counts PASS+FAIL records; `planned` stays 100. Publish both coverage and observed pass rate. BLOCKED/NOT_RUN are not automatically failed answers, but do block complete acceptance. A 1/1 observed success must appear beside coverage 1/100, not as a total100 success.

The replay subset has 16 specifications; the adversarial subset has 26. They overlap and are contained in the 100-case denominator. These labels are coverage categories, not independently achieved safety guarantees.

## Security and privacy

Use only approved data and identities; keep secrets and personal conversations out of public logs. Hashing a low-entropy personal value is not anonymization. Operator authorization is required before sending model calls, LINE messages, changing Firestore or deploying infrastructure. This package does none of those actions.
