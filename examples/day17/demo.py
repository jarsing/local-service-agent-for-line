"""離線執行三種查詢結果，保留合成資料的業務寫入稽核。"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from .adapters import (
    QueryPhase, READ_TOOL_FIELDS, ScriptedInterpreter, ScriptedStep,
    ScriptedTools, TrustedQueryResult,
)
from .main import QueryService
from .outcomes import UpstreamHTTPError


ACTOR = "offline-fixture-actor"
BUSINESS_TABLES = ("preferences", "service_requests")


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def message_event(text: str, case_id: str = "fixture-event") -> dict[str, object]:
    """識別值僅供合成案例使用，不代表 LINE 或真實服務單。"""
    return {
        "type": "message", "webhookEventId": f"offline:{case_id}",
        "message": {"type": "text", "text": text},
    }


class OfflineStore:
    """僅供離線示範的 SQLite 資料來源；不是 Firestore 替代實作。"""

    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            CREATE TABLE preferences (
                actor_id TEXT PRIMARY KEY, dietary_type TEXT NOT NULL,
                revision INTEGER NOT NULL
            );
            CREATE TABLE service_requests (
                request_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL,
                subject TEXT NOT NULL, state TEXT NOT NULL
            );
            CREATE TABLE local_places (
                name TEXT PRIMARY KEY, area TEXT NOT NULL, dietary_type TEXT NOT NULL
            );
            CREATE TABLE local_events (
                name TEXT PRIMARY KEY, area TEXT NOT NULL, event_date TEXT NOT NULL
            );
            CREATE TABLE ledger (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL, result_status TEXT NOT NULL
            );
            CREATE TABLE business_write_audit (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL, operation TEXT NOT NULL, row_key TEXT NOT NULL
            );
        """)
        self.connection.execute(
            "INSERT INTO preferences VALUES (?, ?, ?)", (ACTOR, "vegetarian", 0),
        )
        self.connection.execute(
            "INSERT INTO service_requests VALUES (?, ?, ?, ?)",
            ("offline-fixture-request", ACTOR, "離線示範服務詢問", "submitted"),
        )
        self.connection.execute(
            "INSERT INTO local_places VALUES (?, ?, ?)",
            ("離線示範蔬食店", "彰化市", "vegetarian"),
        )
        self.connection.execute(
            "INSERT INTO local_events VALUES (?, ?, ?)",
            ("離線示範活動", "花壇鄉", "2099-01-01"),
        )
        # 稽核從種子資料建好後開始；INSERT／UPDATE／DELETE 都留下紀錄。
        for table, key in (("preferences", "actor_id"), ("service_requests", "request_id")):
            for operation in ("INSERT", "UPDATE", "DELETE"):
                row_alias = "OLD" if operation == "DELETE" else "NEW"
                self.connection.execute(f"""
                    CREATE TRIGGER audit_{table}_{operation.lower()}
                    AFTER {operation} ON {table}
                    BEGIN
                      INSERT INTO business_write_audit (table_name, operation, row_key)
                      VALUES ('{table}', '{operation}', {row_alias}.{key});
                    END
                """)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return {
            table: [dict(row) for row in self.connection.execute(f"SELECT * FROM {table} ORDER BY 1")]
            for table in BUSINESS_TABLES
        }

    def snapshot_sql(self) -> str:
        statements = ["-- 僅含離線合成的偏好與服務詢問，不含 ledger 或查詢目錄。"]
        for table in BUSINESS_TABLES:
            definition = self.connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,),
            ).fetchone()[0]
            statements.append(definition + ";")
            for row in self.connection.execute(f"SELECT * FROM {table} ORDER BY 1"):
                values = ", ".join(
                    self.connection.execute("SELECT quote(?)", (value,)).fetchone()[0]
                    for value in row
                )
                statements.append(f"INSERT INTO {table} VALUES ({values});")
        return "\n".join(statements) + "\n"

    def business_audit(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM business_write_audit ORDER BY sequence",
        )]

    def record_ledger(self, case_id: str, status: str) -> None:
        """由示範器寫入處理紀錄；與偏好、服務詢問的業務寫入分開計算。"""
        self.connection.execute(
            "INSERT INTO ledger (case_id, result_status) VALUES (?, ?)", (case_id, status),
        )
        self.connection.commit()

    def revision(self, actor: object) -> int:
        row = self.connection.execute(
            "SELECT revision FROM preferences WHERE actor_id = ?", (str(actor),),
        ).fetchone()
        if row is None:
            raise PermissionError("UNKNOWN_FIXTURE_ACTOR")
        return row[0]

    def query(self, tool_name: str, arguments: dict[str, str]) -> TrustedQueryResult:
        """可信結果由實際 SELECT 建立，模型不能供應空結果旗標。"""
        area = arguments.get("area", "")
        keyword = arguments.get("keyword", "")
        areas = ("彰化市", "花壇鄉")
        revision = self.revision(ACTOR)
        if tool_name == "search_local_places":
            if area not in areas:
                return TrustedQueryResult(
                    tool_name, QueryPhase.NEEDS_AREA, False,
                    available_areas=areas, memory_revision=revision,
                )
            dietary_type = arguments.get("dietary_type", "")
            rows = self.connection.execute(
                "SELECT name, area FROM local_places WHERE area = ? "
                "AND instr(name, ?) > 0 AND (? IN ('', 'any') OR dietary_type = ?) ORDER BY name",
                (area, keyword, dietary_type, dietary_type),
            ).fetchall()
        elif tool_name == "search_local_events":
            date = arguments.get("date", "")
            rows = self.connection.execute(
                "SELECT name, area FROM local_events WHERE (? = '' OR area = ?) "
                "AND (? = '' OR event_date = ?) AND instr(name, ?) > 0 ORDER BY name",
                (area, area, date, date, keyword),
            ).fetchall()
        else:
            raise PermissionError("FIXTURE_QUERY_TOOL_REQUIRED")
        return TrustedQueryResult(
            tool_name, rows=tuple(f"{row['name']}（{row['area']}）" for row in rows),
            available_areas=areas, memory_revision=revision,
        )

    def save_database(self, path: Path) -> None:
        with sqlite3.connect(path) as destination:
            self.connection.backup(destination)


class SQLiteFixtureTools(ScriptedTools):
    """查詢讀取 SQLite；能力清單仍只有兩個查詢與說明工具。"""

    def __init__(self, store: OfflineStore, *, results: dict[str, object] | None = None):
        super().__init__(results, revision=store.revision(ACTOR))
        self.store = store

    def execute(self, name: str, args: dict[str, str]) -> object:
        if name in ("search_local_events", "search_local_places") and name not in self.results:
            if not isinstance(args, dict) or set(args) - set(READ_TOOL_FIELDS[name]):
                raise PermissionError("UNEXPECTED_ARGUMENTS")
            if any(not isinstance(value, str) or len(value) > 100 for value in args.values()):
                raise PermissionError("INVALID_ARGUMENT_VALUE")
            if name == "search_local_places" and args.get("dietary_type", "") not in (
                "", "any", "vegetarian", "vegan", "ovo_lacto",
            ):
                raise PermissionError("INVALID_DIETARY_VALUE")
            self.results[name] = self.store.query(name, args)
        return super().execute(name, args)


def new_output_directory(raw_path: str | Path) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError("輸出資料夾必須尚未建立或保持空白，請改用新的執行目錄。")
    path.mkdir(parents=True, exist_ok=True)
    return path


async def run_demo(out: Path) -> dict[str, object]:
    store = OfflineStore()
    try:
        before = store.snapshot()
        before_sql = store.snapshot_sql()
        interpreter = ScriptedInterpreter({
            "查花壇的未收錄示範店": ScriptedStep(
                "search_local_places", {"area": "花壇鄉", "keyword": "未收錄示範店"},
            ),
            "示範查詢暫不可用": ScriptedStep(failure=UpstreamHTTPError(503)),
            "附近有停車場嗎": ScriptedStep("show_local_help", {"reason": "unsupported"}),
            "我想找蔬食": ScriptedStep("search_local_places"),
            "查彰化市示範蔬食": ScriptedStep("search_local_places", {"area": "彰化市"}),
        })
        tools_created: list[SQLiteFixtureTools] = []
        logs: list[dict[str, object]] = []

        async def factory(actor: object) -> SQLiteFixtureTools:
            store.revision(actor)
            instance = SQLiteFixtureTools(store)
            tools_created.append(instance)
            return instance

        def emit(event: str, **fields: object) -> None:
            logs.append({"event": event, **fields})

        async def assert_revision(actor: object, revision: int) -> None:
            from .outcomes import PreferenceChanged
            if store.revision(actor) != revision:
                raise PreferenceChanged()

        service = QueryService(
            interpreter, factory, catalog_is_current=lambda actor: True,
            assert_revision=assert_revision, emit=emit,
        )
        cases = (
            ("fixed_booking", "我要預約"),
            ("no_data", "查花壇的未收錄示範店"),
            ("unavailable", "示範查詢暫不可用"),
            ("unsupported", "附近有停車場嗎"),
            ("needs_area", "我想找蔬食"),
            ("success", "查彰化市示範蔬食"),
        )
        results: list[dict[str, object]] = []
        for case_id, text in cases:
            count_before = interpreter.ask_count
            tools_before = len(tools_created)
            plan = await service.route(ACTOR, message_event(text, case_id))
            calls = [call for instance in tools_created[tools_before:] for call in instance.calls]
            store.record_ledger(case_id, str(plan["result"]["status"]))
            results.append({
                "case_id": case_id, "synthetic_input": text,
                "plan": plan, "executed_tools": calls,
                "scripted_interpreter_calls": interpreter.ask_count - count_before,
                "model_api_calls": 0,
            })
        after = store.snapshot()
        after_sql = store.snapshot_sql()
        write_audit = {
            "scope": "offline_sqlite_business_tables_only",
            "business_tables": list(BUSINESS_TABLES),
            "business_snapshot_unchanged": before == after,
            "business_write_count": len(store.business_audit()),
            "business_writes": store.business_audit(),
            "ledger_origin": "offline_demo_harness",
            "ledger_write_count": store.connection.execute("SELECT count(*) FROM ledger").fetchone()[0],
            "before_sha256": hashlib.sha256(before_sql.encode()).hexdigest(),
            "after_sha256": hashlib.sha256(after_sql.encode()).hexdigest(),
            "does_not_prove": ["Firestore 寫入行為", "Gemini 意圖準確率", "LINE 手機顯示", "雲端部署狀態"],
        }
        report: dict[str, object] = {
            "mode": ScriptedInterpreter.mode, "data_origin": "synthetic_sqlite_fixture",
            "real_api_calls": 0, "model_timeout_policy_seconds": service.timeout_seconds,
            "cases": results, "logs": logs, "write_audit": write_audit,
        }
        (out / "demo_results.json").write_text(json_text(report), encoding="utf-8")
        (out / "write_audit.json").write_text(json_text(write_audit), encoding="utf-8")
        (out / "business_before.json").write_text(json_text(before), encoding="utf-8")
        (out / "business_after.json").write_text(json_text(after), encoding="utf-8")
        (out / "before.sql").write_text(before_sql, encoding="utf-8")
        (out / "after.sql").write_text(after_sql, encoding="utf-8")
        store.save_database(out / "fixture.sqlite3")
        if before != after or store.business_audit():
            raise AssertionError("BUSINESS_WRITE_DETECTED")
        return report
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="離線示範型別狀態、固定選單與業務寫入稽核。")
    parser.add_argument("--out", required=True, help="新建且保持空白的輸出資料夾。")
    args = parser.parse_args()
    try:
        out = new_output_directory(args.out)
        report = asyncio.run(run_demo(out))
    except ValueError as exc:
        parser.error(str(exc))
    for case in report["cases"]:
        result = case["plan"]["result"]
        print(f"{case['case_id']}: {result['status']} / {result['reason']}")
    print("業務資料快照一致；實際數量請查 write_audit.json。")
    print(f"輸出：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
