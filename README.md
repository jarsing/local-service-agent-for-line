# LOCAL Agent Kit for LINE

[![LOCAL offline CI](https://github.com/jarsing/local-service-agent-for-line/actions/workflows/ci.yml/badge.svg)](https://github.com/jarsing/local-service-agent-for-line/actions/workflows/ci.yml)

> Ask through LINE. Let Gemini use tools to find local-service information and explain the result.

[繁體中文](README.zh-TW.md) · [iThome series](https://ithelp.ithome.com.tw/users/20120682/ironman/9872) · [Day 12 setup guide](examples/day12/README.md)

**Author:** Jia-Sin Chen（陳佳新／佳新哥）, ChiBuApp（奇步應用） · GitHub: `jarsing`  
**Series:** LOCAL：30 天打造 LINE × Google AI 地方服務 Agent

Before joining a community walking tour, people ask practical questions: What time should we meet? Where? Can someone using a wheelchair follow the entire route? LOCAL starts with these questions and progressively connects LINE, Gemini, lookup tools, and backend workflows.

This project is for developers with Web, HTTP API, or LINE Bot experience who want to build with Google AI. Each example combines something to try with a design choice to understand.

## What can I try today?

**Code index updated through Day 12, September 26, 2026.** The repository contains the Day 1 acceptance specification and the Day 2–12 examples. The latest example adds **the first cloud-ready release deployed on Google Cloud Run with Firestore state persistence, Gemini 3.8 Flash activity lookup, two-phase confirmation, and cross-revision zero-amnesia request restoration**. Reference code snapshot: [examples/day12/](examples/day12/).


| Start with a goal | Entry point | What to explore |
|---|---|---|
| Deploy to Cloud Run & survive restarts | [Day 12: Cloud Run deployment](examples/day12/README.md) | FastAPI webhook, two-phase confirmation with postback action, Secret Manager integration, and cross-revision request recovery |
| Persist state & survive restarts | [Day 11: Firestore persistence](examples/day11/README.md) | Dual-backend storage adapter (SQLite/Firestore emulator verified), cross-process restart recovery, lease-based job coordination, and offline test suite |
| Reconcile timeouts & offline CI | [Day 10: reconciliation & CI](examples/day10/README.md) | Read-only SQLite lookup, synthetic transport timeouts, bounded recovery controller, and GitHub Actions offline CI |
| Build idempotent service requests | [Day 9: request creation & idempotency](examples/day09/README.md) | Google ADK `create_handoff_request`, SQLite transactional deduplication, returning the original request for retries, and rejecting conflicting reuse |
| Bind user confirmation to operations & versions | [Day 8: operation confirmation](examples/day08/README.md) | Google ADK Tool Confirmation, operation fingerprints, version-change interception, and confirmation receipts |
| Handle poster updates and field review | [Day 7: poster versioning](examples/day07/README.md) | Stable event matching, triplet diffs, human review, and three-phase query states |
| Extract event data from a poster | [Day 6: poster extraction](examples/day06/README.md) | Structured fields, quotation verification, human review export, and Day 5 search tool reuse |
| See an agent look up local events | [Day 5: ADK event search](examples/day05/README.md) | Four sample events, four questions, two conditions, and observable tool-call traces |
| Connect Gemini replies to LINE | [Day 4: LINE webhook](examples/day04/README.md) | A fixed `LOCAL ping` reply, followed by `LOCAL 測試` for a model-generated explanation |
| Make a first Gemini call | [Day 3: model experiment](examples/day03/README.md) | Fixed input, original model text, configuration, and usage metadata |
| Begin with a Python-only experiment | [Day 2: SQLite and timeouts](examples/day02/README.md) | A timeout after a committed write, reconciliation, and same-key retries |

This index tracks available code; follow the [iThome series](https://ithelp.ithome.com.tw/users/20120682/ironman/9872) for published articles. Day 2–5 use synthetic sample data; Day 6 experiments with operator-provided and attributed event posters. Most chapter documentation is currently in Traditional Chinese; the commands below provide an English starting point.

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

The articles are written in Traditional Chinese. English topic labels below summarize the published titles.

| Day | Article / topic | Code or specification | Reproduction notes |
|---|---|---|---|
| 1 | [Turn local-service needs into an engineering specification](https://ithelp.ithome.com.tw/articles/10411219) | [First acceptance specification](docs/day01/handoff-timeout-001.json) | Design and acceptance JSON |
| 2 | [Does “done” mean the backend task is complete?](https://ithelp.ithome.com.tw/articles/10412065) | [examples/day02](examples/day02/) | [docs/day02](docs/day02/README.md) |
| 3 | [From AI Studio to a reproducible Gemini API experiment](https://ithelp.ithome.com.tw/articles/10412603) | [examples/day03](examples/day03/) | [docs/day03](docs/day03/README.md) |
| 4 | [Bring Gemini into LINE: verify, then reply](https://ithelp.ithome.com.tw/articles/10413146) | [examples/day04](examples/day04/) | [docs/day04](docs/day04/README.md) |
| 5 | [ADK, controlled lookup, and the first agent orchestration](https://ithelp.ithome.com.tw/articles/10413779) | [examples/day05](examples/day05/) | [docs/day05](docs/day05/README.md) |
| 6 | [Turn an event poster into searchable service data](https://ithelp.ithome.com.tw/articles/10414133) | [examples/day06](examples/day06/) | [docs/day06](docs/day06/README.md) |
| 7 | [Readable does not mean reliable: sources, versions, and the unknown](https://ithelp.ithome.com.tw/articles/10414804) | [examples/day07](examples/day07/) | [docs/day07](docs/day07/README.md) |
| 8 | [A conversational “yes” is not enough: bind confirmation to a specific operation](https://ithelp.ithome.com.tw/articles/10415219) | [examples/day08](examples/day08/) | [docs/day08](docs/day08/README.md) |
| 9 | [Will a second submission create an extra record? Controlled request creation and idempotency](https://ithelp.ithome.com.tw/articles/10415923) | [examples/day09](examples/day09/) | [docs/day09](docs/day09/README.md) |
| 10 | [Did it go through after a timeout? Reconciliation and offline CI](https://ithelp.ithome.com.tw/articles/10416095) | [examples/day10](examples/day10/) | [docs/day10](docs/day10/README.md) |
| 11 | [Service restarted — is what I asked for still there? Resends, background jobs, and restart recovery](https://ithelp.ithome.com.tw/articles/10416397) | [examples/day11](examples/day11/) | [docs/day11](docs/day11/README.md) |
| 12 | [First cloud-ready release: Cloud Run in action with Baguashan Grand Hike](https://ithelp.ithome.com.tw/articles/10417489) | [examples/day12](examples/day12/) | [docs/day12](docs/day12/README.md) |

Find Day 13 and later articles through the [series page](https://ithelp.ithome.com.tw/users/20120682/ironman/9872). Day 1 delivers a design specification, so executable examples begin at `examples/day02/`.

LOCAL grows as one project, with chapter folders preserving each lesson's focus. Local service requests, idempotent retries, timeout reconciliation, task state persistence / process restart recovery, and the first cloud-ready Cloud Run deployment with Firestore are complete through Day 12; upcoming work will add evaluation, multi-source catalog integration, and subsequent state management. This index will expand as the examples are published.


## How LINE, Gemini, and ADK work together

The Day 5 phone demonstration follows this path:

**Fixed LINE command → webhook → Gemini requests a lookup → Python searches events → ADK returns the result → Gemini composes an answer → LINE reply.**

LINE supplies the messaging interface. Gemini interprets the question and requests a tool call. ADK coordinates the model, tools, and events. The Python tool performs the actual lookup. Google AI Studio is the entry point for obtaining and managing Gemini API keys, while Google Antigravity supports the development workflow.

Google Cloud deployment, consented long-term memory, and human-service handoff are future work in the series. The current messaging entry point, database experiment, and event search have their own examples; the broader capabilities will be integrated progressively.

## The five LOCAL design dimensions

| Letter | Dimension | Design question |
|---|---|---|
| L | LINE-native Interface | How do users ask, understand results, and continue? |
| O | Orchestration & Tools | How do the model, tools, and backend share the work? |
| C | Context & Consented Memory | What context is needed, and which preferences are stored with consent? |
| A | Assurance & Accountability | What evidence supports the result, and who owns the next step? |
| L | Launch & Learning Loop | How do we deploy, observe problems, and improve the next version? |

These dimensions work together throughout the same evolving service.

![LOCAL project overview: five design dimensions — Day 1 concept diagram](LOCAL_GitHub_1x1.png)

## Try an example and share what you find

Start with one example and note where the instructions or behavior are unclear. Leave a comment on the relevant article or open a repository issue with the chapter, code version, and error message. Redact API keys and user data before sharing.

**Which local-service lookup would you give to a tool first?**

## Data and licensing

Use synthetic or explicitly authorized data. Never publish client code, real LINE user IDs, credentials, or private operational data.

The source code is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

