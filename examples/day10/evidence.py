"""來源、附加式證據與合成案例報告。只保存可見事件，不保存模型思考。"""
from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import socket
import sqlite3
import subprocess
import sys
from threading import RLock
import uuid
from typing import Any, Iterator

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def create_run(root: Path, prefix: str) -> Path:
    result = Path(root) / f"{prefix}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    result.mkdir(parents=True, exist_ok=False)
    return result


def execution_info(origin: str) -> dict[str, Any]:
    is_ci = os.getenv('GITHUB_ACTIONS') == 'true'
    # 不從日期、所在資料夾或 requirements 推定執行者與已安裝版本。
    packages = {}
    for name in ('google-adk', 'google-genai', 'httpx', 'pydantic'):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    try:
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO,
                                text=True, capture_output=True, timeout=5, check=False)
        commit = result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        commit = None
    run_id = os.getenv('GITHUB_RUN_ID') if is_ci else None
    repository = os.getenv('GITHUB_REPOSITORY') if is_ci else None
    return {
        'origin': 'github_actions' if is_ci else origin,
        'execution_environment': 'github_actions' if is_ci else origin,
        'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
        'platform': platform.platform(), 'packages': packages,
        'source_commit': os.getenv('GITHUB_SHA') if is_ci else commit,
        'workflow_run_id': run_id,
        'workflow_run_attempt': os.getenv('GITHUB_RUN_ATTEMPT') if is_ci else None,
        'workflow_job': os.getenv('GITHUB_JOB') if is_ci else None,
        'workflow_url': f'https://github.com/{repository}/actions/runs/{run_id}' if repository and run_id else None,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
    }


def sources() -> dict[str, str]:
    paths = []
    for day in ('day02', 'day08', 'day09', 'day10'):
        folder = REPO / 'examples' / day
        paths.extend(p for p in folder.glob('*') if p.is_file() and p.suffix in ('.py', '.json', '.txt', '.md'))
    paths += [REPO/'docs/day01/handoff-timeout-001.json', REPO/'.github/workflows/ci.yml']
    return {str(p.relative_to(REPO)): sha256(p) for p in sorted(set(paths)) if p.is_file()}


class Trace:
    def __init__(self):
        self.events: list[dict[str, Any]] = []
        self._lock = RLock()
        self.turn = 0

    def emit(self, kind: str, **values: Any) -> None:
        with self._lock:
            if len(self.events) >= 500:
                raise RuntimeError('TRACE_EVENT_LIMIT')
            self.events.append({'sequence': len(self.events)+1, 'turn': self.turn,
                                'kind': kind, **deepcopy(values)})

    def save(self, path: Path) -> None:
        with path.open('x', encoding='utf-8') as f:
            for event in self.events:
                f.write(json.dumps(event, ensure_ascii=False, allow_nan=False)+'\n')


@contextmanager
def no_network() -> Iterator[None]:
    """在測試行程封鎖 Python socket/DNS；不是作業系統層網路沙箱。"""
    os.environ['OTEL_SDK_DISABLED'] = 'true'
    targets = [(socket.socket, 'connect'), (socket.socket, 'connect_ex'),
               (socket, 'create_connection'), (socket, 'getaddrinfo')]
    old = [(owner, name, getattr(owner, name)) for owner, name in targets]
    def blocked(*args: Any, **kwargs: Any):
        raise RuntimeError('OFFLINE_NETWORK_BLOCKED')
    try:
        for owner, name, _ in old:
            setattr(owner, name, blocked)
        yield
    finally:
        for owner, name, value in old:
            setattr(owner, name, value)
