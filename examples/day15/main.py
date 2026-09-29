"""Day 15 runtime entry: reuse Day 14 webhook, consent and fixed controls."""
from __future__ import annotations

from contextlib import asynccontextmanager
import os
from starlette.concurrency import run_in_threadpool

from examples.day12.main import open_store
from examples.day12.delivery import LineReply
from examples.day12.settings import Settings
from examples.day14.main import MemoryApplication, create_app as create_previous
from examples.day14.engine import ScriptedInterpreter
from .context_store import ContextJournal, project_result
from .session_budget import MODEL_ID


class BudgetApplication(MemoryApplication):
    async def _finalize(self, actor, event, result):
        data = event.get("postback", {}).get("data", "")
        is_lookup_button = data == "d14:events" or data.startswith("d14:area:")
        journal = ContextJournal(self.memory)
        snapshot = await run_in_threadpool(journal.read, actor) if is_lookup_button else None
        plan = await super()._finalize(actor, event, result)
        if snapshot is not None:
            await run_in_threadpool(
                journal.append, actor, snapshot, event["webhookEventId"],
                project_result(result)
            )
        return plan

    async def route(self, actor, event):
        before = await run_in_threadpool(self.memory.inspect, actor)
        plan = await super().route(actor, event)
        after = await run_in_threadpool(self.memory.inspect, actor)
        # Any consent revision change invalidates the entire short context.
        # This is separate cleanup after the authoritative memory transaction.
        # On cleanup failure, journal.read rejects mismatched revisions anyway.
        if before["revision"] != after["revision"]:
            await run_in_threadpool(ContextJournal(self.memory).clear, actor)
        return plan


def build_runtime():
    settings = Settings.from_env()
    if settings.model_mode == "gemini":
        if settings.model_id != MODEL_ID:
            raise ValueError("FIXED_SERIES_MODEL_REQUIRED")
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() not in ("", "0", "false"):
            raise ValueError("EXISTING_DEVELOPER_API_ROUTE_ONLY")
        if os.getenv("LOCAL_APPROVE_COUNT_TOKENS") != "yes":
            raise ValueError("EXPLICIT_COUNT_API_APPROVAL_REQUIRED")
        from .adk_budget_router import BudgetAdkInterpreter
        from .token_counter import GeminiTokenCounter
        key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
        interpreter = BudgetAdkInterpreter(
            MODEL_ID, counter=GeminiTokenCounter(key, approve_external=True)
        )
    else:
        interpreter = ScriptedInterpreter()  # explicit original test mode only
    return BudgetApplication(settings, open_store(settings),
                             interpreter, LineReply(settings.channel_token))


def create_app(runtime=None):
    app = create_previous(runtime)
    @asynccontextmanager
    async def lifespan(app):
        engine = runtime or build_runtime()
        app.state.runtime = engine
        try:
            yield
        finally:
            close = getattr(engine.store, "close", None)
            if close:
                close()
    app.router.lifespan_context = lifespan
    return app


app = create_app()
