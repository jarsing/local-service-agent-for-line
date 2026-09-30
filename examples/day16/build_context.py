"""Extend the reviewed Day 15 build allowlist; never walk/copy a whole repo."""
import argparse
import hashlib
import json
from pathlib import Path
from examples.day15.build_context import export as export_day15
from examples.day17.build_context import copy_runtime as copy_day17_runtime

HERE = Path(__file__).resolve().parent
RUNTIME = ("__init__.py", "documents.py", "policy.py", "read_tools.py", "adk_guard.py",
           "messages.py", "main.py", "data/untrusted_flyer.txt")


def export(out: Path):
    for name in (*RUNTIME, "Dockerfile"):
        source = HERE / name
        if not source.is_file() or source.is_symlink():
            raise ValueError("MISSING_OR_LINKED_SOURCE")
    report = export_day15(out)
    copy_day17_runtime(out, report)
    for name in RUNTIME:
        target = out / "examples/day16" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((HERE / name).read_bytes())
        report["files"]["examples/day16/" + name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (out / "Dockerfile").write_bytes((HERE / "Dockerfile").read_bytes())
    report["files"]["Dockerfile"] = hashlib.sha256((out / "Dockerfile").read_bytes()).hexdigest()
    report["day16_entrypoint"] = "examples.day16.main:app"
    report["day16_boundary"] = "Explicit document route; no write tool declarations or context append"
    (out / "SOURCE_MANIFEST.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    print(json.dumps(export(parser.parse_args().out), ensure_ascii=False, indent=2))
