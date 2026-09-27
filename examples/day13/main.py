"""Day 13 entry point: same configuration, store and transport as Day 12."""
from contextlib import asynccontextmanager
from examples.day12.main import create_app as original_create_app, open_store
from examples.day12.settings import Settings
from examples.day12.delivery import LineReply
from .bridge import FlexApplication


def build_runtime():
    import os
    settings = Settings.from_env()
    if settings.model_mode == 'gemini':
        if os.environ.get('GOOGLE_GENAI_USE_VERTEXAI', 'false').lower() not in ('false', '0', ''):
            raise ValueError('沿用 Day 12 Gemini Developer API 路線。')
        if not (os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')):
            raise ValueError('請沿用 Day 12 已核准的私人 Gemini key。')
        from examples.day12.adk_query import AdkQuery
        query = AdkQuery(settings.model_id)
    else:
        from examples.day12.query import StubQuery
        query = StubQuery()
    return FlexApplication(settings, open_store(settings), query, LineReply(settings.channel_token))


def create_app(runtime=None):
    app = original_create_app(runtime)
    @asynccontextmanager
    async def lifespan(app):
        engine = runtime or build_runtime()
        app.state.runtime = engine
        try:
            yield
        finally:
            close = getattr(engine.store, 'close', None)
            if close:
                close()
    app.router.lifespan_context = lifespan
    return app


app = create_app()
