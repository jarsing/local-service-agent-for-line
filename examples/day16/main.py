"""Explicit document route on the original Day 15 LINE service.

Delivery/idempotency metadata may still be written by the inherited process().
Document data is never replayed as a normal command or appended to context.
"""
import os
from contextlib import asynccontextmanager
from starlette.concurrency import run_in_threadpool

from examples.day12.main import open_store
from examples.day12.delivery import LineReply
from examples.day12.settings import Settings
from examples.day15.main import BudgetApplication, create_app as create_previous
from examples.day15.session_budget import MODEL_ID
from examples.day14.engine import ScriptedInterpreter
from .documents import DOCUMENT_COMMAND, DOCUMENT_PREFIX, Document, sample_document
from .messages import document_messages


class DocumentApplication(BudgetApplication):
    def __init__(self, *args, document_reader, **kwargs):
        super().__init__(*args, **kwargs)
        self.document_reader = document_reader

    async def route(self, actor, event):
        text = event.get("message", {}).get("text", "")
        is_document = (event.get("type") == "message" and
                       (text == DOCUMENT_COMMAND or text.startswith(DOCUMENT_PREFIX)))
        if not is_document:
            return await super().route(actor, event)
        # Explicit route chosen by the application, not a model-supplied mode flag.
        snapshot = await run_in_threadpool(self.memory.inspect, actor)
        try:
            document = sample_document() if text == DOCUMENT_COMMAND else Document(text[len(DOCUMENT_PREFIX):])
            allowed = await run_in_threadpool(
                self.ledger.model_budget, actor, self.settings.model_daily_limit)
            if not allowed:
                return self._plan(document_messages({"status": "document_unavailable"}),
                                  {"status": "model_budget_exhausted"}, snapshot["revision"])
            report = await self.document_reader.ask(
                document, "請查文件提及鄉鎮的公開店家或活動資訊。", actor,
                event["webhookEventId"], self.memory, events=self.catalog)
            result = report["result"]
            if result.get("status") == "events_result":
                # Original activity renderer still checks authoritative catalog state.
                plan = await super()._finalize(actor, event, result)
                await run_in_threadpool(self.memory.assert_revision, actor, snapshot["revision"])
                return plan
        except PermissionError:
            # Do not retry this document through the privileged normal router.
            result = {"status": "document_action_denied"}
        except Exception as exc:
            self.emit("DAY16_DOCUMENT_UNAVAILABLE", error_type=type(exc).__name__)
            result = {"status": "document_unavailable"}
        await run_in_threadpool(self.memory.assert_revision, actor, snapshot["revision"])
        return self._plan(document_messages(result), result, snapshot["revision"])


def build_runtime():
    settings = Settings.from_env()
    if settings.model_mode == "gemini":
        if settings.model_id != MODEL_ID:
            raise ValueError("FIXED_SERIES_MODEL_REQUIRED")
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() not in ("", "0", "false"):
            raise ValueError("EXISTING_DEVELOPER_API_ROUTE_ONLY")
        if os.getenv("LOCAL_APPROVE_COUNT_TOKENS") != "yes":
            raise ValueError("EXPLICIT_COUNT_API_APPROVAL_REQUIRED")
        from examples.day15.adk_budget_router import BudgetAdkInterpreter
        from examples.day15.token_counter import GeminiTokenCounter
        from .adk_guard import AdkDocumentReader
        key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
        counter = GeminiTokenCounter(key, approve_external=True)
        interpreter = BudgetAdkInterpreter(MODEL_ID, counter=counter)
        reader = AdkDocumentReader(counter)
    else:
        from .testing import ScriptedDocumentReader
        interpreter, reader = ScriptedInterpreter(), ScriptedDocumentReader()
    return DocumentApplication(settings, open_store(settings), interpreter,
                               LineReply(settings.channel_token), document_reader=reader)


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
