"""建立不可覆寫的 run 目錄，記錄本次實際檔案雜湊與環境。"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
from pathlib import Path
import platform
import secrets
import sqlite3
from typing import Any
from dependencies import BASE_COMMIT, CORE_PATH

HERE = Path(__file__).resolve().parent

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_snapshot() -> dict[str, str]:
    paths = [p for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py','.json','.txt','.md')
             and '__pycache__' not in p.parts and 'output' not in p.parts]
    return {**{str(p.relative_to(HERE)):sha256(p) for p in sorted(paths)},
            '../day08/confirmation.py':sha256(CORE_PATH)}

def environment() -> dict[str, Any]:
    result: dict[str, Any] = {'python':platform.python_version(), 'os':platform.system(),
        'sqlite':sqlite3.sqlite_version, 'day08_dependency_commit':BASE_COMMIT,
        'day09_executed_commit':None}
    for pkg in ('google-adk','google-genai'):
        try:
            result[pkg] = version(pkg)
        except PackageNotFoundError:
            result[pkg] = None
    return result

def create_run(parent: Path, prefix: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    dest = parent / (prefix + '-' + stamp + '-' + secrets.token_hex(3))
    dest.mkdir(exist_ok=False)
    return dest

def write_json(path: Path, data: Any):
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
