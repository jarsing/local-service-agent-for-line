"""補齊既有映像需要的查詢模組；只複製明列檔案，不掃描整個目錄。"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
RUNTIME = (
    "__init__.py", "outcomes.py", "adapters.py", "messages.py", "main.py", "legacy_adapter.py",
)


def copy_runtime(out: Path, report: dict[str, Any]) -> dict[str, Any]:
    """接在既有 export 之後；沿用其新建輸出位置與 SOURCE_MANIFEST 格式。

    不複製測試、demo、建置腳本或文件，也不改既有 Webhook 進入點。
    SOURCE_MANIFEST.json 仍由呼叫端在全部模組複製完成後寫入。
    """
    out = Path(out)
    if not out.is_dir() or out.is_symlink():
        raise ValueError("EXISTING_BUILD_DIRECTORY_REQUIRED")
    if not isinstance(report, dict) or not isinstance(report.get("files"), dict):
        raise ValueError("SOURCE_MANIFEST_FILES_REQUIRED")
    examples = out / "examples"
    if not examples.is_dir() or examples.is_symlink():
        raise ValueError("EXISTING_EXAMPLES_DIRECTORY_REQUIRED")
    target_dir = examples / "day17"
    if target_dir.exists() or target_dir.is_symlink():
        raise FileExistsError("DAY17_BUILD_DIRECTORY_ALREADY_EXISTS")
    sources: dict[str, bytes] = {}
    for name in RUNTIME:
        source = HERE / name
        if not source.is_file() or source.is_symlink():
            raise ValueError("MISSING_OR_LINKED_SOURCE")
        sources[name] = source.read_bytes()
        if "examples/day17/" + name in report["files"]:
            raise ValueError("DAY17_MANIFEST_ENTRY_ALREADY_EXISTS")
    target_dir.mkdir()
    for name, content in sources.items():
        (target_dir / name).write_bytes(content)
        report["files"]["examples/day17/" + name] = hashlib.sha256(content).hexdigest()
    report["day17_runtime_files"] = ["examples/day17/" + name for name in RUNTIME]
    return report
