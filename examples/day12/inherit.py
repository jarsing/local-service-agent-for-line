"""明確載入前篇；保持 Day 5、8、9、11 原檔不變。"""
from pathlib import Path
import importlib.util
import sys

REPO = Path(__file__).resolve().parents[2]
DAY11 = REPO / 'examples/day11'
for name in ('domain', 'service', 'store', 'upstream', 'confirmation_gate'):
    loaded = sys.modules.get(name)
    if loaded and Path(getattr(loaded, '__file__', '')).parent != DAY11:
        raise ImportError(f'{name} 已由其他範例載入；請用獨立的 Python 行程。')
if str(DAY11) not in sys.path:
    sys.path.insert(0, str(DAY11))
from domain import (SendArgs, key, clone, operation_id, confirmation_key, session_key,
                    grant_key, catalog_key, draft_key, iso, time_of, utcnow,
                    pending, rejected, ContractError)
from upstream import Actor, Operation, ConfirmationStore, operation_fingerprint
from service import HandoffService, authorized, check_binding
from confirmation_gate import validate_first_write
from store import SQLiteTestStore, StoreUnavailable
from jobs import RecoveryWorker

spec = importlib.util.spec_from_file_location('_local_day05_catalog', REPO / 'examples/day05/catalog.py')
if spec is None or spec.loader is None:
    raise ImportError('缺少 Day 5 catalog.py，請使用完整的指定版本 Repo。')
catalog_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog_module)
search_catalog = catalog_module.search_catalog
