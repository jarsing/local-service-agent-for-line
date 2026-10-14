# LOCAL Agent Kit for LINE

[![LOCAL offline CI](https://github.com/jarsing/local-service-agent-for-line/actions/workflows/ci.yml/badge.svg)](https://github.com/jarsing/local-service-agent-for-line/actions/workflows/ci.yml)

> Ask through LINE. Let Gemini use tools to find local-service information and explain the result.

[繁體中文](README.zh-TW.md) · [iThome series](https://ithelp.ithome.com.tw/users/20120682/ironman/9872)

**Author:** Jia-Sin Chen（陳佳新／佳新哥）, ChiBuApp（奇步應用） · GitHub: `jarsing`  
**Series:** LOCAL：30 天打造 LINE × Google AI 地方服務 Agent

![LOCAL project overview: five design dimensions — Day 1 concept diagram](LOCAL_GitHub_1x1.png)

Before joining a community walking tour, people ask practical questions: What time should we meet? Where? Can someone using a wheelchair follow the entire route? LOCAL starts with these questions and progressively connects LINE, Gemini, lookup tools, and backend workflows.

This project is for developers with Web, HTTP API, or LINE Bot experience who want to build with Google AI. Each example combines something to try with a design choice to understand.

## Product Card

> Understand local-service questions; keep decisions auditable.

- **Start here (3-Minute Quickstart):** Run the offline SQLite example with Python 3.10+. No API key is needed; no LINE message is sent.
  ```bash
  python3 -m unittest test_day27_replay -v && python3 replay_day27.py --out out/day28/quickstart-01
  ```
- **Observe:** One request, a blocked claim while paused, and one accepted claim (`out/day28/quickstart-01/report.json`).
- **Then explore:** Gemini + ADK lookup, consent, persistence, and UI recovery. Cloud integration has separate credentials, costs, and acceptance checks.
- **License & Governance:** MIT License (`LICENSE`). Contribution guide: [`CONTRIBUTING.md`](CONTRIBUTING.md). Release checklist: [`docs/day28/RELEASE_CHECKLIST.md`](docs/day28/RELEASE_CHECKLIST.md).

## Where should I start? (30-Day Complete Guide)

**30-day iThome Ironman series completed (October 14, 2026 · Series snapshot tag: [`ironman-2026-final`](https://github.com/jarsing/local-service-agent-for-line/releases/tag/ironman-2026-final)).** If you are visiting LOCAL for the first time, we recommend starting from **[Day 1: First Acceptance Specification](docs/day01/handoff-timeout-001.json)** and **[Day 2: SQLite & Timeout Reconciliation](examples/day02/README.md)**, then following the four progressive engineering phases below—or jumping to the full chronological [Day 1–30 Articles and Code Map](#articles-and-code-map).

| Learning phase | Recommended starting points | What you will build & verify |
|---|---|---|
| **Phase 1: Problem, Specs & Grounded Sources (Day 1–7)**<br>Start from Day 1 | **[Day 1: Acceptance spec](docs/day01/handoff-timeout-001.json)**<br>**[Day 2: SQLite & timeouts](examples/day02/README.md)**<br>**[Day 5: ADK event search](examples/day05/README.md)** | Why “the model said done” does not mean the backend finished: pure-Python timeout reconciliation, first reproducible Gemini API call, LINE webhook signature check, ADK tool orchestration, and event poster extraction with human review. |
| **Phase 2: Confirmation, Idempotent Records & Memory (Day 8–15)**<br>Stateful cloud persistence | **[Day 8: Operation confirmation](examples/day08/README.md)**<br>**[Day 12: Cloud Run deployment](examples/day12/README.md)**<br>**[Day 14: Consented memory](examples/day14/README.md)** | Bind user confirmation to `operation_id` and versions, transactional request creation, offline CI, Firestore persistence across Cloud Run revisions, LINE Flex stale-card defense, consented dietary memory, and 5-layer context budgeting. |
| **Phase 3: Defense, Evaluation & Trade-offs (Day 16–23)**<br>Guardrails & observability | **[Day 16: Untrusted documents](examples/day16/README.md)**<br>**[Day 18: 20-case contract eval](examples/day18/README.md)**<br>**[Day 22: Stop gates & permissions](examples/day22/README.md)** | Read-only tool allowlists against prompt injection, typed degradation outcomes, 20-case 3-layer deterministic evaluation, volunteer CAS inbox claim, Decimal cost ledger, Cloud Logging trace audit, standalone circuit breaker, and Google AI stack matrix. |
| **Phase 4: Observation, Reproducibility & Handover (Day 24–30)**<br>Audit, clean-room & finale | **[Day 24: Evaluation wall](examples/day24/README.md)**<br>**[Day 27: Demo & offline replay](examples/day27/README.md)**<br>**[Day 29: 100-case specs & overview](examples/day29/README.md)**<br>**[Day 30: Series retrospective](docs/day30/README.md)** | Three-denominator evaluation wall & A/B cost audit, Gemini structured extraction with quote verification, 155-test clean-room container reproducibility, 3-minute demo runbook & SQLite replay, open-source product card, 100-case contract grader, and the Day 30 final handover ledger. |

This guide tracks all published code and specifications across the 30-day series; read the full narrative on the [iThome series page](https://ithelp.ithome.com.tw/users/20120682/ironman/9872). Day 2–5 use synthetic sample data; Day 6 experiments with operator-provided and attributed event posters. Most chapter documentation is in Traditional Chinese; the commands below provide an English starting point.

## Quickstart: ask for a meeting time and place

Clone the repository with GitHub Desktop, or download and extract the source. Open a terminal in the **repository root**. These commands target macOS/Linux with Python 3.10 or later. On Windows, the virtual-environment interpreter path is `examples/day05/.venv/Scripts/python.exe`.

### 1. Prepare the Day 5 environment and check the interface

```bash
python3 -m venv examples/day05/.venv
examples/day05/.venv/bin/python -m pip install -r examples/day05/requirements.txt
examples/day05/.venv/bin/python -m pip check
examples/day05/.venv/bin/python examples/day05/verify.py --sdk
```

`verify.py` checks event search, reporting, and LINE routing. The `--sdk` option also exercises a real ADK Runner with a scripted model to check the tool round trip. These are offline checks; the next step calls the Gemini API.

Day 5 uses its own virtual environment so that chapter dependencies stay separate. Reuse an existing matching environment when one is already available.

### 2. Run a real event lookup

Set `GEMINI_API_KEY` in your own environment, or follow the [Day 5 guide](examples/day05/README.md) to load a private key file outside the repository. Check your account's usage and billing settings before running:

```bash
examples/day05/.venv/bin/python examples/day05/run.py --live \
  --case meeting --condition with_tool
```

This entry point sends a predefined meeting-information question. The model requests `search_local_events(date, area, keyword)`, Python reads the event data, and ADK returns the result to the model for a final answer.

To run the complete small comparison:

```bash
examples/day05/.venv/bin/python examples/day05/run.py --live
```

The complete batch contains four questions under two conditions: eight agent turns, with a maximum of sixteen model requests. The preceding single-question lookup is a separate turn. Both conditions use the same model and main generation settings; access to event data through the tool is the difference being explored. Answers, events, elapsed time, and available usage metadata are recorded.

### 3. Open the report and follow the lookup

Each run prints its report location, under `output/day05/run-.../` by default:

| File | Purpose |
|---|---|
| `REPORT.html` | Compare answers in a browser and expand the tool request, execution, and response |
| `COMPARISON.md` | Read the original answers for each question and condition |
| `verification.json` | Inspect versions, inputs, original text, events, and usage |

Start with the search arguments, then compare the returned time and meeting point with the answer. When accessibility information is missing, inspect how the model explains that specific gap. The report displays the output from your own run.

For the phone demonstration, continue with the LINE integration section in the [Day 5 guide](examples/day05/README.md). It reuses the Day 4 webhook and additionally requires a LINE test channel, private credentials, and an HTTPS endpoint. The `LOCAL 測試` command currently starts a fixed accessibility question.

## Articles and code map

The 30 articles are written in Traditional Chinese. English topic labels and exploration summaries below map the complete chronological progression from Day 1 to Day 30.

| Day | Article / topic | Code or specification | Reproduction notes | What to explore |
|---|---|---|---|---|
| 1 | [Turn local-service needs into an engineering specification](https://ithelp.ithome.com.tw/articles/10411219) | [First acceptance specification](docs/day01/handoff-timeout-001.json) | Design and acceptance JSON | Local-service problem framing, five LOCAL dimensions, and `handoff-timeout-001` contract |
| 2 | [Does “done” mean the backend task is complete?](https://ithelp.ithome.com.tw/articles/10412065) | [examples/day02](examples/day02/) | [docs/day02](docs/day02/README.md) | A timeout after a committed write, reconciliation, and same-key retries |
| 3 | [From AI Studio to a reproducible Gemini API experiment](https://ithelp.ithome.com.tw/articles/10412603) | [examples/day03](examples/day03/) | [docs/day03](docs/day03/README.md) | Fixed input, original model text, configuration, and usage metadata |
| 4 | [Bring Gemini into LINE: verify, then reply](https://ithelp.ithome.com.tw/articles/10413146) | [examples/day04](examples/day04/) | [docs/day04](docs/day04/README.md) | A fixed `LOCAL ping` reply, followed by `LOCAL 測試` for a model-generated explanation |
| 5 | [ADK, controlled lookup, and the first agent orchestration](https://ithelp.ithome.com.tw/articles/10413779) | [examples/day05](examples/day05/) | [docs/day05](docs/day05/README.md) | Four sample events, four questions, two conditions, and observable tool-call traces |
| 6 | [Turn an event poster into searchable service data](https://ithelp.ithome.com.tw/articles/10414133) | [examples/day06](examples/day06/) | [docs/day06](docs/day06/README.md) | Structured fields, quotation verification, human review export, and Day 5 search tool reuse |
| 7 | [Readable does not mean reliable: sources, versions, and the unknown](https://ithelp.ithome.com.tw/articles/10414804) | [examples/day07](examples/day07/) | [docs/day07](docs/day07/README.md) | Stable event matching, triplet diffs, human review, and three-phase query states |
| 8 | [A conversational “yes” is not enough: bind confirmation to a specific operation](https://ithelp.ithome.com.tw/articles/10415219) | [examples/day08](examples/day08/) | [docs/day08](docs/day08/README.md) | Google ADK Tool Confirmation, operation fingerprints, version-change interception, and confirmation receipts |
| 9 | [Will a second submission create an extra record? Controlled request creation and idempotency](https://ithelp.ithome.com.tw/articles/10415923) | [examples/day09](examples/day09/) | [docs/day09](docs/day09/README.md) | Google ADK `create_handoff_request`, SQLite transactional deduplication, returning the original request for retries, and rejecting conflicting reuse |
| 10 | [Did it go through after a timeout? Reconciliation and offline CI](https://ithelp.ithome.com.tw/articles/10416095) | [examples/day10](examples/day10/) | [docs/day10](docs/day10/README.md) | Read-only SQLite lookup, synthetic transport timeouts, bounded recovery controller, and GitHub Actions offline CI |
| 11 | [Service restarted — is what I asked for still there? Resends, background jobs, and restart recovery](https://ithelp.ithome.com.tw/articles/10416397) | [examples/day11](examples/day11/) | [docs/day11](docs/day11/README.md) | Dual-backend storage adapter (SQLite/Firestore emulator verified), cross-process restart recovery, lease-based job coordination, and offline test suite |
| 12 | [When cloud processes change, is what I asked for still there? First Cloud Run release](https://ithelp.ithome.com.tw/articles/10417489) | [examples/day12](examples/day12/) | [docs/day12](docs/day12/README.md) | FastAPI webhook, two-phase confirmation with postback action, Secret Manager integration, and cross-revision request recovery |
| 13 | [Is a visible button still a valid one? LINE Flex state and safe actions](https://ithelp.ithome.com.tw/articles/10417809) | [examples/day13](examples/day13/) | [docs/day13](docs/day13/README.md) | Fixed Flex bubble templates, postback action binding, stale-card cancel defense, and plain-text accessibility fallback |
| 14 | [“I feel like eating vegetarian today” does not mean forever! Consented memory and place lookup](https://ithelp.ithome.com.tw/articles/10418240) | [examples/day14](examples/day14/) | [docs/day14](docs/day14/README.md) | Third tool `search_local_places`, Changhua Vegfest place data, consented memory lifecycle, and intent routing |
| 15 | [As conversations grow longer: Session, summary, and context budget](https://ithelp.ithome.com.tw/articles/10418768) | [examples/day15](examples/day15/) | [docs/day15](docs/day15/README.md) | 5-layer context engineering, sliding window trimming, structured summaries, and consent-revision invalidation |
| 16 | [Hidden instructions in a flyer: will the system obey? Untrusted documents and least privilege](https://ithelp.ithome.com.tw/articles/10419112) | [examples/day16](examples/day16/) | [docs/day16](docs/day16/README.md) | Read-only tool allowlist, ADK `before_tool_callback`, independent backend gate, and offline four zeros |
| 17 | [Empty result or temporary failure? Typed outcomes and service degradation](https://ithelp.ithome.com.tw/articles/10419526) | [examples/day17](examples/day17/) | [docs/day17](docs/day17/README.md) | Typed outcomes (`no_data` / `query_unavailable` / `unsupported`), intent routing, fixed recovery buttons, and offline fault injection |
| 18 | [20 local contract evaluation benchmarks: From queries and tools to replies, preserving failures](https://ithelp.ithome.com.tw/articles/10419979) | [examples/day18](examples/day18/) | [eval/local20.json](eval/local20.json) | 20-case benchmark (`eval/local20.json`), 3-layer deterministic scoring, dual-track execution, request rate gate, and counterexample audit |
| 19 | [Volunteer inbox closed-loop: Minimal human notification and atomic claim](https://ithelp.ithome.com.tw/articles/10420229) | [examples/day19](examples/day19/) | [docs/day19](docs/day19/README.md) | Volunteer inbox contract, CAS atomic claim, inbox loop, and timeout reconciliation (dual-window acceptance specification in Day 26) |
| 20 | [Model configuration, latency, and per-task cost: Quality before speed and savings](https://ithelp.ithome.com.tw/articles/10420729) | [examples/day20](examples/day20/) | [docs/day20](docs/day20/README.md) | Provenance cost ledger (`cost_ledger.py`), Decimal pricing arithmetic, thinking token billing, 2-second webhook timing gate, and comparable condition verification |
| 21 | [One trace to find the defect: Follow from model tool call to backend result](https://ithelp.ithome.com.tw/articles/10421328) | [examples/day21](examples/day21/) | [docs/day21](docs/day21/README.md) | Inspectable causality chain (`trace_audit.py`), Google Cloud Logging / Cloud Trace structured event mapping, multi-tier defect diagnosis, and PII-safe ID validation |
| 22 | [Permissions, Secrets, and Stop Gates: Least Privilege and Circuit Breaking](https://ithelp.ithome.com.tw/articles/10421645) | [examples/day22](examples/day22/) | [docs/day22](docs/day22/README.md) | Standalone stop gate (`circuit_breaker.py`), epoch invalidation control, atomic request and outbox commit, target three-tier identity architecture, and dedicated CI suite |
| 23 | [Stack decision matrix: Choosing Google AI tools for local service agents](https://ithelp.ithome.com.tw/articles/10421985) | [examples/day23](examples/day23/) | [docs/day23](docs/day23/README.md) | Offline design evaluation (`stack_matrix.py`), four declared architectures (AI Studio, Vertex AI, Cloud Run, Firestore), fresh-process import probe, and dedicated CI suite |
| 24 | [Did Changing One Line Break the 20 Cases? Evaluation Wall and A/B Cost Measurement](https://ithelp.ithome.com.tw/articles/10422261) | [examples/day24](examples/day24/) | [docs/day24](docs/day24/README.md) | Direct SDK routing capture (`capture.py`), evidence auditor (`audit.py`), 20-case contract regression runner (`offline.py`), backend replay (`replay.py`), and dedicated CI suite |
| 25 | [Extracting Local Data with Gemini Structured Outputs: From Public Text to Service Database](https://ithelp.ithome.com.tw/articles/10422718) | [examples/day25](examples/day25/) | [docs/day25](docs/day25/README.md) | Structured outputs with `response_json_schema` (`capture.py`), deterministic quote verifier (`schema.py`), review admission store (`store.py`), live evaluation runner (`run_live.py`), and dedicated CI suite |
| 26 | [Acceptance Specification for Clean Environments and Dual LINE Windows](https://ithelp.ithome.com.tw/articles/10423179) | [examples/day26](examples/day26/) | [docs/day26](docs/day26/README.md) | Clean-room reproducibility script (`cleanroom.sh`), Dockerfile for Google Cloud Shell, 155-test verification suite, dual LINE window lifecycle specification, and SQLite CAS atomic claim |
| 27 | [What to freeze for product demo: Demo version freeze, 3-minute storyboard, and offline fallback](https://ithelp.ithome.com.tw/articles/10423364) | [examples/day27](examples/day27/) | [docs/day27](docs/day27/README.md) | Version-pinned 3-minute storyboard runbook (`DEMO.md`), Google Cloud Shell clean-room script (`cleanroom.sh`), local SQLite fallback replay (`replay_day27.py`), and 5 independent unit tests |
| 28 | [Handing LOCAL to Developers: Product Card, Quickstart, and Open Source Delivery Specs](https://ithelp.ithome.com.tw/articles/10423648) | [examples/day28](examples/day28/) | [docs/day28](docs/day28/README.md) | Bilingual product card, 3-minute Quickstart one-liner, Cloud Run 404 routing investigation example, Firestore CAS claim contract, MIT license, and CONTRIBUTING guide |
| 29 | [100-Case Local Contract Acceptance and Complete Service Architecture Overview](https://ithelp.ithome.com.tw/articles/10423875) | [examples/day29](examples/day29/) | [docs/day29](docs/day29/README.md) | 100 synthetic development contracts across 5 families, offline 4-state grader (42 tests PASS), complete service journey architecture overview, and dual-track model gateway |
| 30 | [From specification to a handover-ready LOCAL: 30-day review, engineering trade-offs, and next steps](https://ithelp.ithome.com.tw/articles/10424210) | [eval/local100.json](eval/local100.json) · [ARCHITECTURE.md](ARCHITECTURE.md) | [docs/day30](docs/day30/README.md) | 30-day four-tier architectural synthesis, commitment-to-evidence ledger, three-denominator metric audit, Sub-Agent expansion blueprint, and [`ironman-2026-final`](https://github.com/jarsing/local-service-agent-for-line/releases/tag/ironman-2026-final) handover |

Day 1 delivers the initial design specification, so executable Python examples begin at `examples/day02/`.

LOCAL grows as one cohesive project across 30 chapters, with chapter folders preserving each lesson's focus: local service requests, idempotent retries, timeout reconciliation, task state persistence / process restart recovery, Cloud Run deployment with Firestore, LINE Flex state presentation with defensive postbacks, consented dietary memory lifecycle with local place lookup, multi-tier context engineering with session budgeting, untrusted document defense with read-only capability allowlists, typed outcome service degradation with conversational intent routing, 20-case local contract evaluation benchmarks with deterministic triple-layer scoring, volunteer inbox contract with CAS optimistic locking, model configuration / latency / cost analysis ledger, structured trace defect audit with Cloud Logging mapping, standalone stop gate with control epoch invalidation and least-privilege identity separation, architecture decision matrix, three-denominator evaluation wall with A/B cost audit, unstructured text ingestion pipeline with Pydantic quote verification and SQLite review store, clean-room container reproducibility and dual LINE window lifecycle specifications, version-pinned demo freeze runbook and offline SQLite replay, open-source product card and delivery specs, 100-case synthetic contract specifications with offline 4-state grader and full architecture overview, and the Day 30 series retrospective and handover ledger.

## How LINE, Gemini, and ADK work together

The Day 5 phone demonstration follows this path:

**Fixed LINE command → webhook → Gemini requests a lookup → Python searches events → ADK returns the result → Gemini composes an answer → LINE reply.**

LINE supplies the messaging interface. Gemini interprets the question and requests a tool call. ADK coordinates the model, tools, and events. The Python tool performs the actual lookup. Google AI Studio is the entry point for obtaining and managing Gemini API keys, while Google Antigravity supports the development workflow.

Across the 30-day series: Day 12 adds the LINE teaching service on Cloud Run; Day 14 lands consented dietary memory and place search; Day 17 introduces typed outcomes and service degradation; Day 18 establishes the 20-case contract evaluation harness; Day 19 adds the volunteer inbox contract; Day 20 implements the provenance cost ledger; Day 21 introduces structured trace validation and Cloud Logging mapping; Day 22 delivers the controlled stop gate and least-privilege architecture; Day 23 establishes the stack decision matrix; Day 24 delivers the three-denominator evaluation wall and verifier; Day 25 delivers structured extraction from public text and SQLite review admission storage; Day 26–27 deliver clean-room reproducibility, dual LINE window lifecycle specs, and offline replay; Day 28–30 complete the open-source product card, 100-case contract grader, full architecture overview, and final handover ledger.

## The five LOCAL design dimensions

| Letter | Dimension | Design question |
|---|---|---|
| L | LINE-native Interface | How do users ask, understand results, and continue? |
| O | Orchestration & Tools | How do the model, tools, and backend share the work? |
| C | Context & Consented Memory | What context is needed, and which preferences are stored with consent? |
| A | Assurance & Accountability | What evidence supports the result, and who owns the next step? |
| L | Launch & Learning Loop | How do we deploy, observe problems, and improve the next version? |

These dimensions work together throughout the same evolving service.

## Try an example and share what you find

Start with one example and note where the instructions or behavior are unclear. Leave a comment on the relevant article or open a repository issue with the chapter, code version, and error message. Redact API keys and user data before sharing.

**Which local-service lookup would you give to a tool first?**

## Data and licensing

Use synthetic or explicitly authorized data. Never publish client code, real LINE user IDs, credentials, or private operational data.

The source code is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

