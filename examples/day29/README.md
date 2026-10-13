# Day 29: fixture and evidence grader

**Status: integrated into repository; offline acceptance specifications and grader.**

This package contains 100 newly authored **synthetic development specifications**, a standard-library evidence grader and a model-client configuration boundary. It does not execute LOCAL scenarios. In particular, a successful `--plan` is not `100/100 PASS`.

## First execution

Use Python 3.10+ (verified here on Python 3.13.5). No additional packages or API keys are required. Open a terminal in the directory containing `eval/` and `examples/`—the extracted review-package root or the integrated repository root.

```bash
python3 -m unittest discover -s examples/day29 -p test_acceptance.py -v
python3 -O -m unittest discover -s examples/day29 -p test_acceptance.py -v
python3 examples/day29/acceptance.py --plan --out out/day29/plan-01
```

On Windows, use `py -3` in place of `python3` in a suitable terminal. These are the same 42 tests in two interpreter modes, not 84 independent cases. The tests use synthetic observations to test the grader; they do not supply actual model or service observations.

The plan command exits 0 on valid specifications and writes `status=NOT_RUN`, `planned=100`, `tested=0`, `pass_rate_observed=null`. An existing output directory is refused; use `plan-02` for a new experiment.

Without `--plan`, absence of service records produces a NOT_RUN report and exit code 3:

```bash
python3 examples/day29/acceptance.py --out out/day29/no-observations-01
```

## Grade observations collected independently

The following command assumes an operator has actually produced `observations/index.json` and raw observations. They are not supplied or synthesized by this delivery.

```bash
python3 examples/day29/acceptance.py --fixture eval/local100.json \
  --records observations/index.json --evidence-root observations \
  --source-commit a335fbc0b53e81a65d2a0f520c53b48cbc7055c3 \
  --mode offline_contract --out out/day29/acceptance-01
```

Use the full commit of the **actual implementation under test**, not this historical source automatically. Do not pass expected assertions to a model/collector. The `stimulus_for()` helper separates allowed inputs from expected results, but process separation and collector review remain operator responsibilities.

`PASS`: all 100 records have complete, matching provenance and pass their assertions.
`FAIL`: at least one complete record contradicts an assertion.
`INCOMPLETE`: at least one case lacks sufficient evidence.
`NOT_RUN`: no case has executed evidence.
`BLOCKED_MIXED_CONFIGURATION`: completed records have different collector/configuration fingerprints.

A partial list never reduces the planned denominator below 100. Invalid or missing observed facts are not replaced with zero. Expected `null` is different from a missing field. JSON booleans, integers and floats are compared by JSON type.

Exit codes: 0 = successful plan or complete pass; 2 = invalid input/output conflict; 3 = valid report without full acceptance. The JSON report is authoritative about scope. A plan's exit code 0 is not service approval.

## Files and limitations

- `acceptance.py`: fixture checks, raw-reference validation, grading and separate metric fields.
- `model_route.py`: injected client-factory configuration checks. No SDK/endpoint call occurs in its tests.
- `test_acceptance.py`: 42 tests for the grader and client boundary.
- `../../eval/local100.json`: 100 case specifications.
- `../../eval/local20.json`: unchanged handoff reference, not copied historical PASS results.
- `../../docs/day29/DATASET.md`: case inventory and definition changes.
- `../../docs/day29/OBSERVATIONS.md`: raw/record contract and collection requirements.
- `../../ARCHITECTURE.md`: architecture source and completion-state legend.

**Not implemented here:** production or emulator collectors, full 100-case LOCAL replay, real model trajectory validation, Firestore concurrency, phone delivery, OS network isolation, immutable source attestation, SDK endpoint compatibility tests, model cost/latency calculations.

A file hash and `origin=captured_execution` label cannot prove a record's author or source. The grader validates declared integrity/bindings, not the truthfulness of the producer. Preserve source logs and review the collector. The case format is not a drop-in replacement for Day 18's dataset or ADK EvalSet.

Model metrics stay `null`; recorded operation elapsed time is not model inference latency. The `live_model` label only separates batches and does not turn these backend assertions into model accuracy measurements. Do not publish a performance radar from missing observations.
