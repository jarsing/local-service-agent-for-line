"""使用既有 Day 5 搜尋與 Day 6 欄位型別；不複製或修改前篇程式。"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
DAY05 = HERE.parent / 'day05' / 'catalog.py'
DAY06 = HERE.parent / 'day06'


def load_module(path: Path, name: str):
    if not path.is_file():
        raise FileNotFoundError(f'請在同一 Repo 保留前篇檔案：{path}')
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f'無法載入：{path.name}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def schema():
    return load_module(DAY06 / 'schema.py', 'local_day07_previous_schema')


def search_tool():
    return load_module(DAY05, 'local_day07_previous_catalog')


def hashes() -> dict:
    paths = list(HERE.glob('*.py')) + [DAY05, DAY06 / 'schema.py', DAY06 / 'run.py', DAY06 / 'prompts.py']
    return {str(p.relative_to(HERE.parent.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths if p.is_file()}
