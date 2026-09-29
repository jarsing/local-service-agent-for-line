"""Five-minute offline entry: contracts, a size comparison and intentional refusal.

Reports bytes only. True token counts and model latency stay null.
"""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import time
import unittest

from examples.day12.inherit import Actor, SQLiteTestStore, grant_key
from examples.day14.memory import PreferenceMemory
from examples.day14.engine import TurnTools
from .context_store import ContextJournal
from .fixtures import FIXTURE_ENVELOPE, QUESTIONS, PROJECTIONS
from .session_budget import (
    BudgetExceeded, BudgetSessionManager, ByteCounter, ContextWindow,
    canonical_bytes,
)


def backup(db: Path, target: Path):
    with sqlite3.connect(db) as source, sqlite3.connect(target) as dest:
        source.backup(dest)


async def run(out: Path, origin: str):
    out.mkdir(parents=True, exist_ok=False)
    log = io.StringIO()
    tests = unittest.defaultTestLoader.loadTestsFromNames([
        "examples.day15.test_session_budget", "examples.day15.test_context_store"
    ])
    started = time.perf_counter()
    result = await asyncio.to_thread(
        unittest.TextTestRunner(stream=log, verbosity=2).run, tests
    )
    (out / "contracts.log").write_text(log.getvalue(), encoding="utf-8")
    report = {
        "origin": origin, "executed_at": datetime.now(timezone.utc).isoformat(),
        "scope": "synthetic_fixture_stdlib_SQLite_no_Gemini_no_ADK_no_LINE",
        "test_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "input_tokens": None, "model_latency_seconds": None,
        "counter": "UTF8_BYTES_NOT_TOKENS", "rows": [],
    }
    if not result.wasSuccessful() or result.skipped:
        report["passed"] = False
        (out / "report.json").write_text(json.dumps(report, indent=2))
        return report

    full = ContextWindow()
    bounded = ContextWindow()
    for number, (question, turn) in enumerate(zip(QUESTIONS, PROJECTIONS), 1):
        a = await BudgetSessionManager(20, 30000, "utf8_bytes").prepare(
            full, question, FIXTURE_ENVELOPE, ByteCounter())
        b = await BudgetSessionManager(2, 30000, "utf8_bytes").prepare(
            bounded, question, FIXTURE_ENVELOPE, ByteCounter())
        (out / f"turn-{number}-full.json").write_bytes(canonical_bytes(a.request))
        (out / f"turn-{number}-budget.json").write_bytes(canonical_bytes(b.request))
        report["rows"].append({
            "turn": number, "full_input_bytes": a.measured_units,
            "budget_input_bytes": b.measured_units,
            "kept_pairs": len(b.window.turns),
            "summary": b.window.summary.__dict__,
            "tokens": None, "latency_seconds": None,
        })
        full = full.append(turn, max_turns=20)
        bounded = bounded.append(turn, max_turns=2)

    try:
        await BudgetSessionManager(2, 1, "utf8_bytes").prepare(
            bounded, QUESTIONS[-1], FIXTURE_ENVELOPE, ByteCounter())
    except BudgetExceeded as exc:
        report["intentional_refusal"] = str(exc)
    else:
        raise AssertionError("Oversize current request was not rejected")

    db = out / "synthetic.sqlite3"
    store = SQLiteTestStore(db)
    actor = Actor("synthetic-day15", "synthetic-user", "session-A")
    store.atomic(lambda tx: tx.put("grants", grant_key(actor), {
        "allowed": True,
        "actor": {"tenant_id": actor.tenant_id, "user_id": actor.user_id}
    }))
    memory = PreferenceMemory(store, "synthetic-demo-key-" + "s" * 40)
    proposal = memory.propose(actor, "vegetarian", "synthetic-consent")
    # Explicit synthetic test harness consent, NOT a person nor a model decision.
    memory.approve(actor, proposal["token"])
    journal = ContextJournal(memory)
    for i, turn in enumerate(PROJECTIONS[:-1]):
        journal.append(actor, journal.read(actor), f"synthetic-event-{i}", turn)
    previous_state = store.inspect()
    backup(db, out / "before-forget.sqlite3")
    tools = TurnTools(memory, actor)
    applied = tools.execute("search_local_places",
                            {"area": "花壇鄉", "dietary_type": ""})
    memory.forget(actor, "synthetic-forget")
    journal.clear(actor)
    after = TurnTools(memory, actor)
    forgotten = after.execute("search_local_places",
                               {"area": "花壇鄉", "dietary_type": ""})
    backup(db, out / "after-forget.sqlite3")
    (out / "before.rows.json").write_text(
        json.dumps(previous_state, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "after.rows.json").write_text(
        json.dumps(store.inspect(), ensure_ascii=False, indent=2), encoding="utf-8")
    report["tool_observations"] = [tools.calls[0], after.calls[0]]
    report["after_forget_window"] = journal.read(actor).window.as_dict()
    report["passed"] = (
        applied["query"]["dietary_type"] == "vegetarian"
        and forgotten["query"]["dietary_type"] == "any"
        and not journal.read(actor).window.turns
    )
    report["offline_wall_seconds"] = round(time.perf_counter() - started, 6)
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in out.iterdir() if p.is_file()}
    (out / "MANIFEST.sha256.json").write_text(json.dumps(manifest, indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--origin", choices=("author_local", "assistant_check", "ci"),
                   default="author_local")
    args = p.parse_args()
    report = asyncio.run(run(args.out, args.origin))
    print(json.dumps({
        "passed": report["passed"], "tests": report["test_run"],
        "last_turn": (report.get("rows") or [{}])[-1],
        "intentional_refusal": report.get("intentional_refusal"),
        "output": str(args.out),
    }, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
