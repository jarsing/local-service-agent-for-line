"""Separated verification layers; missing SDKs are an error, never a skipped pass."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import unittest

GROUPS = {
    "core": ["examples.day16.test_policy", "examples.day16.test_evidence", "examples.day16.test_packaging"],
    "flow": ["examples.day16.test_flow"],
    "adk": ["examples.day16.test_adk"],
    "emulator": ["examples.day16.test_emulator"],
    "previous": [
        "examples.day15.test_session_budget", "examples.day15.test_context_store",
        "examples.day15.test_packaging", "examples.day15.test_http_counter", "examples.day15.test_flow",
        "examples.day14.test_places", "examples.day14.test_memory", "examples.day14.test_engine",
        "examples.day14.test_messages", "examples.day14.test_packaging", "examples.day14.test_model_contract",
        "examples.day14.test_trace_contract", "examples.day14.test_flow", "examples.day12.test_core",
        "examples.day13.test_flex", "examples.day13.test_flow", "examples.day13.test_packaging",
    ],
}


def run(group, out, origin):
    out.mkdir(parents=True, exist_ok=False)
    results = []
    for name in ("core", "flow") if group == "all" else (group,):
        stream = io.StringIO()
        suite = unittest.defaultTestLoader.loadTestsFromNames(GROUPS[name])
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        (out / f"{name}.log").write_text(stream.getvalue(), encoding="utf-8")
        results.append({"group": name, "run": result.testsRun,
                        "failures": len(result.failures), "errors": len(result.errors),
                        "skipped": len(result.skipped),
                        "passed": result.wasSuccessful() and len(result.skipped) == 0})
    packages = {}
    for name in ("google-adk", "google-genai", "google-cloud-firestore", "fastapi", "httpx"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    report = {"origin": origin, "executed_at": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "packages": packages, "groups": results,
              "passed": all(row["passed"] for row in results),
              "scope": {"core": "stdlib_SQLite", "flow": "FastAPI_scripted_model_mock_LINE",
                        "adk": "real_Runner_scripted_BaseLlm_not_Gemini",
                        "emulator": "real_Firestore_Emulator_not_cloud"}}
    (out / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--group", choices=("all", *GROUPS), default="all")
    p.add_argument("--origin", choices=("author_local", "assistant_check", "ci"), default="author_local")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    raise SystemExit(0 if run(args.group, args.out, args.origin)["passed"] else 1)
