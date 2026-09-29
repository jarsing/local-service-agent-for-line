"""Full-request Gemini countTokens, with no silent byte/token substitution."""
from __future__ import annotations

import hashlib
import time
from .session_budget import MODEL_ID, canonical_bytes


class CounterUnavailable(RuntimeError):
    pass


def countable_envelope(model: str, config: dict) -> dict:
    """Map the documented GenAI JSON config to GenerateContentRequest fields.

    Only supported text/function tools are allowed; no cache, files or retrieval
    config is silently left uncounted.
    """
    if model != MODEL_ID:
        raise ValueError("FIXED_SERIES_MODEL_REQUIRED")
    def pick(camel, snake):
        return config.get(camel, config.get(snake))
    for camel, snake in (
        ("cachedContent", "cached_content"), ("responseSchema", "response_schema"),
    ):
        if pick(camel, snake):
            raise ValueError("UNSUPPORTED_COUNT_CONFIGURATION")
    envelope = {"model": "models/" + model}
    for camel, snake in (
        ("systemInstruction", "system_instruction"),
        ("tools", "tools"), ("toolConfig", "tool_config"),
    ):
        value = pick(camel, snake)
        if value is not None:
            if camel == "systemInstruction" and isinstance(value, str):
                value = {"parts": [{"text": value}]}
            envelope[camel] = value
    return envelope


class GeminiTokenCounter:
    unit = "tokens"

    def __init__(self, api_key: str, *, model: str = MODEL_ID,
                 approve_external: bool = False, transport=None):
        if not approve_external or not api_key or model != MODEL_ID:
            raise ValueError("EXPLICIT_COUNT_API_APPROVAL_REQUIRED")
        self.api_key, self.model, self.transport = api_key, model, transport
        self.records = []

    def fork(self):
        return type(self)(self.api_key, model=self.model, approve_external=True,
                          transport=self.transport)

    async def __call__(self, request: dict) -> int:
        import httpx
        if request.get("model") != "models/" + self.model:
            raise ValueError("COUNTER_MODEL_MISMATCH")
        if len(self.records) >= 4:
            raise CounterUnavailable("COUNT_REQUEST_LIMIT")
        start = time.perf_counter()
        row = {"request_sha256": hashlib.sha256(canonical_bytes(request)).hexdigest(),
               "total_tokens": None, "elapsed_seconds": None, "status": "failed"}
        self.records.append(row)
        try:
            async with httpx.AsyncClient(
                timeout=8, transport=self.transport, trust_env=False
            ) as client:
                response = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    + self.model + ":countTokens",
                    headers={"x-goog-api-key": self.api_key},
                    json={"generateContentRequest": request},
                )
                response.raise_for_status()
                count = response.json().get("totalTokens")
                if type(count) is not int or count < 0:
                    raise ValueError("INVALID_COUNT_RESPONSE")
                row.update(status="ok", total_tokens=count)
                return count
        except Exception as exc:
            row["error_type"] = type(exc).__name__
            # Never persist response bodies, private request contents or API keys.
            raise CounterUnavailable("COUNT_UNAVAILABLE_NO_GENERATION") from None
        finally:
            row["elapsed_seconds"] = round(time.perf_counter() - start, 6)
