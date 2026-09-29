"""Named test doubles and synthetic seed data. No Gemini or LINE API calls."""
from datetime import datetime, timezone
from contextlib import closing
import json
import sqlite3
from types import SimpleNamespace

from examples.day12.inherit import Actor, SQLiteTestStore, grant_key
from examples.day14.memory import PreferenceMemory
from examples.day15.context_store import ContextJournal
from examples.day15.session_budget import SafeTurn
from .policy import SAFE_FIELDS, check_declarations, PermissionDenied
from .read_tools import DocumentTools


class FixedClock:
    def __init__(self):
        self.value = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value


def seed(path):
    store = SQLiteTestStore(path)
    actor = Actor("synthetic-day16", "synthetic-owner", "session-A")
    store.atomic(lambda tx: tx.put("grants", grant_key(actor), {
        "allowed": True, "actor": {"tenant_id": actor.tenant_id, "user_id": actor.user_id}
    }))
    memory = PreferenceMemory(store, "synthetic-d16-" + "s" * 40, clock=FixedClock())
    # The test harness explicitly gives consent BEFORE the observation interval.
    proposal = memory.propose(actor, "vegetarian", "synthetic-prior-consent")
    memory.approve(actor, proposal["token"])
    store.atomic(lambda tx: tx.put("requests", "req-synthetic-day16-existing", {
        "request_id": "req-synthetic-day16-existing", "status": "pending_human_review",
        "note": "synthetic pre-existing row; not a claim of a real human handoff"
    }))
    journal = ContextJournal(memory)
    journal.append(actor, journal.read(actor), "synthetic-prior-turn", SafeTurn("places", "花壇鄉"))
    return store, memory, actor


def offline_schema():
    """A contract fixture, NOT evidence of the real SDK's outgoing schema."""
    return {"tools": [{"functionDeclarations": [
        {"name": name, "parameters": {"type": "OBJECT", "properties": {
            field: {"type": "STRING"} for field in fields
        }}} for name, fields in SAFE_FIELDS.items()
    ]}]}


def fake_context(tools, call_id="scripted-call"):
    bound = tools.policy.bound
    return SimpleNamespace(
        session=SimpleNamespace(id=bound.session_id, user_id=bound.user_id),
        state={"day16_mode": bound.mode, "day16_tenant": bound.tenant_id,
               "day16_preference_revision": bound.preference_revision},
        function_call_id=call_id,
        actions=SimpleNamespace(skip_summarization=False),
    )


class ScriptedDocumentReader:
    """Explicitly chosen call, not NLU: the flyer text does not drive this script."""
    mode = "SCRIPTED_DOCUMENT_NOT_GEMINI_NOT_ADK"

    def __init__(self, name="search_local_places", args=None):
        self.name, self.args = name, args if args is not None else {
            "area": "花壇鄉", "dietary_type": "", "keyword": ""
        }
        self.reports = []

    async def ask(self, document, question, actor, event_id, memory, *, events=None):
        tools = DocumentTools(memory, actor, "scripted-" + event_id, events=events)
        ctx = fake_context(tools)
        body = document.content(question)
        schema = offline_schema()
        names = check_declarations(schema)
        before = tools.before_tool(SimpleNamespace(name=self.name), dict(self.args), ctx)
        result = before or tools.execute(self.name, dict(self.args), tools.policy.bound,
                                         call_id=ctx.function_call_id)
        report = {"mode": self.mode, "document_sha256": document.sha256,
                  "document_text_in_request": document.text in body,
                  "schema_evidence_layer": "OFFLINE_CONTRACT_NOT_SDK",
                  "observed_schema_names": list(names), "model_calls": 0,
                  "request_content": body, "schema_fixture": schema,
                  "tool_events": tools.events, "result": result, "completed": True}
        self.reports.append(report)
        return report


def install_write_probe(path):
    """SQLite trigger audit, test database only. Captures write-then-restore too."""
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE audit_writes (op TEXT, kind TEXT, ident TEXT)")
        for operation in ("INSERT", "UPDATE", "DELETE"):
            source = "OLD" if operation == "DELETE" else "NEW"
            conn.execute(f"CREATE TRIGGER d16_{operation.lower()} AFTER {operation} ON docs "
                         f"BEGIN INSERT INTO audit_writes VALUES ('{operation}', {source}.kind, {source}.ident); END")
        conn.commit()


def observed_writes(path):
    with closing(sqlite3.connect(path)) as conn:
        return [dict(zip(("op", "kind", "ident"), row))
                for row in conn.execute("SELECT op,kind,ident FROM audit_writes")]


def backup_db(path, target):
    with closing(sqlite3.connect(path)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)


def changed_keys(before, after):
    changes = []
    for kind in sorted(set(before) | set(after)):
        a, b = before.get(kind, {}), after.get(kind, {})
        for ident in sorted(set(a) | set(b)):
            if a.get(ident) != b.get(ident):
                changes.append({"kind": kind, "ident": ident})
    return changes
