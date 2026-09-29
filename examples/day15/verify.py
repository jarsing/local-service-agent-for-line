"""Never skip a missing dependency and relabel it as a successful test."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import unittest

GROUPS = {
    "core": ["examples.day15.test_session_budget", "examples.day15.test_context_store",
             "examples.day15.test_packaging"],
    "flow": ["examples.day15.test_http_counter", "examples.day15.test_flow"],
    "adk": ["examples.day15.test_adk"],
    "emulator": ["examples.day15.test_emulator"],
    "previous": [
        "examples.day14.test_places", "examples.day14.test_memory",
        "examples.day14.test_engine", "examples.day14.test_messages",
        "examples.day14.test_packaging", "examples.day14.test_model_contract",
        "examples.day14.test_trace_contract", "examples.day14.test_flow",
        "examples.day12.test_core", "examples.day13.test_flex",
        "examples.day13.test_flow", "examples.day13.test_packaging",
    ],
}


def run(group, out, origin):
    out.mkdir(parents=True, exist_ok=False)
    results = []
    for name in (("core", "flow") if group == "all" else (group,)):
        stream = io.StringIO()
        suite = unittest.defaultTestLoader.loadTestsFromNames(GROUPS[name])
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        (out / (name + ".log")).write_text(stream.getvalue(), encoding="utf-8")
        results.append({"group": name, "run": result.testsRun,
                        "failures": len(result.failures), "errors": len(result.errors),
                        "skipped": len(result.skipped),
                        "passed": result.wasSuccessful() and not result.skipped})
    packages = {}
    for name in ("google-adk", "google-genai", "google-cloud-firestore", "fastapi", "httpx"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    report = {"origin": origin, "executed_at": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "packages": packages,
              "groups": results, "passed": all(r["passed"] for r in results),
              "scope": "offline; ADK group uses real Runner + scripted model; no paid API"}
    (out / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--group", choices=("all", *GROUPS), default="all")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--origin", choices=("assistant_check", "author_local", "ci"),
                   default="author_local")
    a = p.parse_args()
    raise SystemExit(0 if run(a.group, a.out, a.origin)["passed"] else 1)
