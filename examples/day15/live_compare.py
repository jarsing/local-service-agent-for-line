"""Explicitly approved, two-call Gemini development comparison.

Same synthetic input, safe source history, model and tools; only context policy
differs. Not a benchmark, blind evaluation, LINE test or Cloud Run deployment.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time

from examples.day12.inherit import Actor, SQLiteTestStore, grant_key
from examples.day14.memory import PreferenceMemory
from examples.day14.engine import TurnTools
from .context_store import ContextJournal, COLLECTION
from .fixtures import QUESTIONS, PROJECTIONS
from .session_budget import MODEL_ID, ContextWindow, canonical_bytes


def require_sdk():
    pins = {"google-genai": "2.23.0", "google-adk": "2.9.1"}
    found = {k: importlib.metadata.version(k) for k in pins}
    if found != pins:
        raise RuntimeError("SDK_PIN_MISMATCH_DO_NOT_UPGRADE_AUTOMATICALLY")
    return found


async def run(out: Path):
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "origin": "author_local", "scope": "synthetic_two_call_development_comparison",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL_ID, "thinking": "LOW", "cases": [], "passed": False,
        "status": "starting", "max_generation_attempts": 2,
        "model_quality_benchmark": False,
    }
    try:
        report["packages"] = require_sdk()
        from .adk_budget_router import BudgetAdkInterpreter
        from .token_counter import GeminiTokenCounter
        for strategy in ("full_comparison", "budget"):
            store = SQLiteTestStore(out / (strategy + ".sqlite3"))
            actor = Actor("synthetic-day15-live", "synthetic-user", "source-session")
            store.atomic(lambda tx: tx.put("grants", grant_key(actor), {
                "allowed": True,
                "actor": {"tenant_id": actor.tenant_id, "user_id": actor.user_id}
            }))
            memory = PreferenceMemory(store, "synthetic-only-" + "s" * 40)
            p = memory.propose(actor, "vegetarian", "synthetic-seed")
            memory.approve(actor, p["token"])  # TEST PROGRAM, not a human click
            journal = ContextJournal(memory)
            # Both groups start with identical safe synthetic source history.
            # Production append() only persists the two-turn window + summary.
            store.atomic(lambda tx: tx.put(COLLECTION, journal.ident(actor), {
                "schema": 1, "generation": 1, "preference_revision": 1,
                "expires_at": memory.clock().timestamp() + 900,
                "window": ContextWindow(tuple(PROJECTIONS[:-1])).as_dict(),
            }))
            counter = GeminiTokenCounter(
                os.getenv("GOOGLE_API_KEY") or os.environ["GEMINI_API_KEY"],
                approve_external=True
            )
            router = BudgetAdkInterpreter(MODEL_ID, counter=counter, strategy=strategy)
            case = {"strategy": strategy, "input": QUESTIONS[-1], "actual": None,
                    "passed": False, "error_type": None}
            report["cases"].append(case)
            start = time.perf_counter()
            try:
                actual = await router.ask(
                    QUESTIONS[-1], actor, "synthetic-final-turn",
                    TurnTools(memory, actor)
                )
                case["actual"] = actual
                requested = next(e["args"] for e in actual["adk_events"]
                                 if e["kind"] == "TOOL_REQUESTED")
                effective = actual["tool_events"][0]["effective_arguments"]
                case["passed"] = (
                    actual["mode"] == "ADK_GEMINI_DAY15"
                    and actual["tool_events"][0]["tool"] == "search_local_places"
                    and requested.get("dietary_type", "") == ""
                    and effective["dietary_type"] == "vegetarian"
                    and effective["area"] == "花壇鄉"
                    and actual["trace_linkage"]["trace_linked"]
                )
            except Exception as exc:
                case["error_type"] = type(exc).__name__
                case["actual"] = getattr(exc, "report", None)
            finally:
                case["whole_turn_seconds"] = round(time.perf_counter() - start, 6)
                (out / (strategy + ".rows.json")).write_text(
                    json.dumps(store.inspect(), ensure_ascii=False, indent=2),
                    encoding="utf-8")
            if not case["passed"]:
                report["status"] = "failed_stop_without_retry"
                break
        else:
            report["status"] = "completed"
            report["passed"] = True
    except Exception as exc:
        report["status"] = "dependency_or_startup_failure"
        report["error_type"] = type(exc).__name__
    finally:
        # Synthetic inputs can be reviewed privately. Never point this CLI at
        # production logs or a real user database.
        (out / "comparison.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in out.iterdir() if p.is_file()}
        (out / "MANIFEST.sha256.json").write_text(json.dumps(hashes, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--approve-live", action="store_true")
    args = parser.parse_args()
    if not args.approve_live:
        parser.error("需 --approve-live：至多兩次生成與最多八次計數；使用私人合成測試。")
    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
        parser.error("請先設定私人金鑰；不要把值貼在命令。")
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() not in ("", "false", "0"):
        parser.error("固定沿用 Gemini Developer API。")
    result = asyncio.run(run(args.out))
    print(json.dumps({"passed": result["passed"], "status": result["status"],
                      "output": str(args.out)}, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)
