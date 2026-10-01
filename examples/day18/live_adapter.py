"""Opt-in real Gemini via the existing ADK interpreter, never a second classifier.

Candidate integration: no Live execution is claimed until verified in the user's
pinned environment. All test storage and output remain local. The production
LINE service is neither called nor redeployed.
"""
from __future__ import annotations
import os
from importlib.metadata import version
from .gate import RequestBudget, RequestGate


def factory(gate: RequestGate, budget: RequestBudget):
    if version('google-adk') != '2.9.1' or version('google-genai') != '2.23.0':
        raise RuntimeError('PINNED_ADK_GENAI_VERSIONS_REQUIRED')
    if os.getenv('GOOGLE_GENAI_USE_VERTEXAI', '').lower() not in ('', 'false', '0'):
        raise ValueError('DEVELOPER_API_ONLY')
    key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
    if not key:
        raise ValueError('EXPLICIT_PRIVATE_GEMINI_KEY_REQUIRED')
    from google.adk.models.google_llm import Gemini
    from google.genai import types
    from examples.day15.token_counter import GeminiTokenCounter
    from examples.day15.adk_budget_router import BudgetAdkInterpreter
    from examples.day15.session_budget import MODEL_ID

    class LimitedGemini(Gemini):
        async def generate_content_async(self, llm_request, stream=False):
            if stream:
                raise ValueError('EVALUATION_EXPECTS_EXISTING_NONSTREAMING_MODE')
            async def operation():
                budget.claim('generation')
                return [r async for r in super(LimitedGemini, self).generate_content_async(llm_request, stream=False)]
            for response in await gate.run(operation):
                yield response

    class CountWrapper:
        unit = 'tokens'
        def __init__(self, original):
            self.original = original
        @property
        def records(self):
            return self.original.records
        def fork(self):
            return type(self)(self.original.fork())
        async def __call__(self, request):
            async def operation():
                budget.claim('count_tokens')
                return await self.original(request)
            return await gate.run(operation)

    class RecordedLive(BudgetAdkInterpreter):
        async def ask(self, *args, **kwargs):
            # Base adapter labels ANY model_override ADK_SCRIPTED. Here the override
            # really calls Gemini; preserve that original label instead of hiding it.
            try:
                report = await super().ask(*args, **kwargs)
            except Exception as exc:
                report = getattr(exc, 'report', None)
                if isinstance(report, dict):
                    report['base_mode'] = report.get('mode')
                    report['mode'] = 'LIVE_GEMINI_WITH_REQUEST_GATE'
                    report['external_transport'] = 'LimitedGemini.super.generate_content_async'
                raise
            report['base_mode'] = report.get('mode')
            report['mode'] = 'LIVE_GEMINI_WITH_REQUEST_GATE'
            report['external_transport'] = 'LimitedGemini.super.generate_content_async'
            return report

    def create():
        model = LimitedGemini(model=MODEL_ID, retry_options=types.HttpRetryOptions(attempts=1))
        counter = CountWrapper(GeminiTokenCounter(key, approve_external=True))
        return RecordedLive(MODEL_ID, counter=counter, model_override=model)
    return create
