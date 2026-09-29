"""Reuse Day 14 queries through an always-read-only transaction view.

This is a capability boundary in trusted application code, NOT an OS sandbox.
No eval/exec, shell, arbitrary SQL, arbitrary HTTP or file access is exposed.
"""
from examples.day14.engine import TurnTools
from examples.day14.memory import PURPOSE, PreferenceChanged
from .policy import PermissionDenied, ReadPolicy


class ReadTransaction:
    def __init__(self, transaction):
        self.__transaction = transaction

    def get(self, kind, ident):
        return self.__transaction.get(kind, ident)

    def put(self, *args, **kwargs):
        raise PermissionDenied("READ_ONLY_TRANSACTION")

    create = put


class ReadStore:
    def __init__(self, store):
        self.__store = store

    def atomic(self, function, *, read_only=False):
        if not read_only:
            raise PermissionDenied("READ_ONLY_STORE")
        return self.__store.atomic(
            lambda tx: function(ReadTransaction(tx)), read_only=True
        )


class PreferenceReader:
    """No signing key or approve/forget/propose method is exposed on this view."""
    def __init__(self, memory):
        self.store = ReadStore(memory.store)
        self.clock, self.__row = memory.clock, memory._row

    def inspect(self, actor):
        def read(tx):
            row = self.__row(tx, actor)
            return {"revision": row["revision"], "dietary_type": row.get("dietary_type"),
                    "status": "saved" if row.get("dietary_type") else "empty",
                    "purpose": PURPOSE, "consented_at": row.get("consented_at")}
        return self.store.atomic(read, read_only=True)

    def assert_revision(self, actor, revision):
        current = self.inspect(actor)
        if current["revision"] != revision:
            raise PreferenceChanged("PREFERENCE_CHANGED")
        return current


class DocumentTools:
    def __init__(self, memory, actor, session_id, *, places=None, events=None):
        reader = PreferenceReader(memory)
        self.policy = ReadPolicy(reader, actor, session_id)
        self.__tools = TurnTools(reader, actor, places=places, events=events)
        self.events = []
        self.last = None

    def execute(self, name, args, context, *, call_id="direct"):
        # Never assume the ADK callback ran: direct calls take the same gate.
        try:
            normalized = self.policy.authorize(name, args, context)
            result = self.__tools.execute(name, normalized)
            self.policy.authorize(name, normalized, context)
        except (PermissionError, PreferenceChanged) as exc:
            self.events.append({"kind": "EXECUTION_DENIED", "call_id": call_id,
                                "name": name, "reason": str(exc)})
            raise PermissionDenied(str(exc)) from exc
        self.events.append({"kind": "TOOL_EXECUTED", "call_id": call_id,
                            "name": name, "args": dict(args),
                            "effective": self.__tools.calls[-1].get("effective_arguments"),
                            "result": result})
        self.last = result
        return result

    def before_tool(self, tool, args, tool_context):
        # ADK passes these exact names as keyword arguments.
        name = tool.name
        try:
            context = self.policy.context_from_tool(tool_context)
            self.policy.authorize(name, args, context)
        except PermissionError as exc:
            self.events.append({"kind": "CALLBACK_DENIED", "name": name,
                                "call_id": tool_context.function_call_id,
                                "reason": str(exc)})
            tool_context.actions.skip_summarization = True
            return {"status": "document_action_denied", "reason": "TOOL_NOT_ALLOWED"}
        self.events.append({"kind": "CALLBACK_ALLOWED", "name": name,
                            "call_id": tool_context.function_call_id})
        return None
