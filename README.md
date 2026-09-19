# LOCAL Agent Kit for LINE

> Ask through LINE. Let Gemini use tools to find local-service information and explain the result.

[繁體中文](README.zh-TW.md) · [iThome series](https://ithelp.ithome.com.tw/users/20120682/ironman/9872) · [Day 5 setup guide](examples/day05/README.md)

**Author:** Jia-Sin Chen（陳佳新／佳新哥）, ChiBuApp（奇步應用） · GitHub: `jarsing`  
**Series:** LOCAL：30 天打造 LINE × Google AI 地方服務 Agent

Before joining a community walking tour, people ask practical questions: What time should we meet? Where? Can someone using a wheelchair follow the entire route? LOCAL starts with these questions and progressively connects LINE, Gemini, lookup tools, and backend workflows.

This project is for developers with Web, HTTP API, or LINE Bot experience who want to build with Google AI. Each example combines something to try with a design choice to understand.

## What can I try today?

**Code index updated through Day 5, September 19, 2026.** The repository contains the Day 1 acceptance specification and the Day 2–5 examples. The latest example adds **ADK event search and a four-question comparison with and without a tool**. Reference code snapshot: [`59265ab`](https://github.com/jarsing/local-service-agent-for-line/tree/59265ab4212512f72260700c7cda931e837025e6).

| Start with a goal | Entry point | What to explore |
|---|---|---|
| See an agent look up local events | [Day 5: ADK event search](examples/day05/README.md) | Four sample events, four questions, two conditions, and observable tool-call traces |
| Connect Gemini replies to LINE | [Day 4: LINE webhook](examples/day04/README.md) | A fixed `LOCAL ping` reply, followed by `LOCAL 測試` for a model-generated explanation |
| Make a first Gemini call | [Day 3: model experiment](examples/day03/README.md) | Fixed input, original model text, configuration, and usage metadata |
| Begin with a Python-only experiment | [Day 2: SQLite and timeouts](examples/day02/README.md) | A timeout after a committed write, reconciliation, and same-key retries |

This index tracks available code; follow the [iThome series](https://ithelp.ithome.com.tw/users/20120682/ironman/9872) for published articles. Examples use synthetic data, and the articles describe their actual service calls and observed results. Most chapter documentation is currently in Traditional Chinese; the commands below provide an English starting point.

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

Find Day 6 and later articles through the [series page](https://ithelp.ithome.com.tw/users/20120682/ironman/9872). Day 1 delivers a design specification, so executable examples begin at `examples/day02/`.

LOCAL grows as one project, with chapter folders preserving each lesson's focus. Upcoming work will extract event data from posters, add service requests and conversational state, and explore evaluation and cloud deployment. This index will expand as the examples are published.

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

An open-source release is planned. No license has yet been selected for this design snapshot; public visibility alone is not an open-source license. Code, articles, illustrations, and data will have their licensing scope clarified before reuse is offered.
