"""Short-lived public conversation context over the original Day 11 store.

No nested transactions and no LLM/LINE side effects inside a transaction.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from examples.day12.inherit import key
from examples.day14.memory import PreferenceChanged
from .session_budget import ContextWindow, SafeTurn, canonical_bytes

COLLECTION = "conversation_context"


class ContextChanged(RuntimeError):
    pass


@dataclass(frozen=True)
class Snapshot:
    window: ContextWindow
    generation: int
    preference_revision: int


class ContextJournal:
    def __init__(self, memory, *, ttl_seconds: int = 900):
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
            raise ValueError("INVALID_CONTEXT_TTL")
        self.memory, self.store, self.ttl_seconds = memory, memory.store, ttl_seconds

    def ident(self, actor):
        return key("day15-context", actor.tenant_id, actor.user_id)

    def _read(self, tx, actor, now):
        pref = self.memory._row(tx, actor)  # existing permission + schema checks
        row = tx.get(COLLECTION, self.ident(actor)) or {}
        if row and row.get("schema") != 1:
            raise ValueError("INVALID_CONTEXT_SCHEMA")
        gen = row.get("generation", 0)
        if type(gen) is not int or gen < 0:
            raise ValueError("INVALID_CONTEXT_GENERATION")
        valid = (row.get("preference_revision") == pref["revision"]
                 and row.get("expires_at", 0) > now)
        window = ContextWindow.from_dict(row["window"]) if valid else ContextWindow()
        return pref, row, gen, window

    def read(self, actor):
        now = self.memory.clock().timestamp()
        def get(tx):
            pref, row, gen, window = self._read(tx, actor, now)
            return Snapshot(window, gen, pref["revision"])
        return self.store.atomic(get, read_only=True)

    def assert_current(self, actor, snapshot):
        current = self.read(actor)
        if current.preference_revision != snapshot.preference_revision:
            raise PreferenceChanged("PREFERENCE_CHANGED")
        if (current.generation != snapshot.generation
                or current.window != snapshot.window):
            raise ContextChanged("CONVERSATION_CHANGED")
        return current

    def append(self, actor, snapshot, event_id, turn: SafeTurn):
        # Compute time and opaque event identity outside retryable transaction.
        now = self.memory.clock().timestamp()
        event_hash = hmac.new(
            self.memory.secret, (self.ident(actor) + "\0" + event_id).encode(),
            hashlib.sha256).hexdigest()
        projection_hash = hashlib.sha256(canonical_bytes(
            {"topic": turn.topic, "area": turn.area}
        )).hexdigest()
        def put(tx):
            pref, row, gen, window = self._read(tx, actor, now)
            if pref["revision"] != snapshot.preference_revision:
                raise PreferenceChanged("PREFERENCE_CHANGED")
            if (row.get("last_event") == event_hash
                    and row.get("preference_revision") == pref["revision"]):
                if row.get("last_projection") != projection_hash:
                    raise ContextChanged("SAME_EVENT_DIFFERENT_PROJECTION")
                return False
            if gen != snapshot.generation or window != snapshot.window:
                raise ContextChanged("CONVERSATION_CHANGED")
            new = window.append(turn)
            tx.put(COLLECTION, self.ident(actor), {
                "schema": 1, "generation": gen + 1,
                "preference_revision": pref["revision"],
                "expires_at": now + self.ttl_seconds, "last_event": event_hash,
                "last_projection": projection_hash,
                "window": new.as_dict(),
            })
            return True
        return self.store.atomic(put)

    def clear(self, actor):
        now = self.memory.clock().timestamp()
        def put(tx):
            pref, row, gen, window = self._read(tx, actor, now)
            tx.put(COLLECTION, self.ident(actor), {
                "schema": 1, "generation": gen + 1,
                "preference_revision": pref["revision"],
                "expires_at": now, "window": ContextWindow().as_dict(),
            })
        self.store.atomic(put)


def project_result(result: dict) -> SafeTurn:
    """Generate public metadata from an executed tool, never from raw prose."""
    if result.get("tool") == "search_local_places":
        return SafeTurn("places", result.get("query", {}).get("area", "")
                        if result.get("query", {}).get("area", "") in ("花壇鄉", "彰化市") else "")
    # Event data remains independently verified by the original path.
    if result.get("status") == "events_result":
        return SafeTurn("events")
    return SafeTurn("help")
