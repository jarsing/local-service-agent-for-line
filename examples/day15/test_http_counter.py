"""Mock HTTP transport, not a request to Google."""
import unittest
import httpx
from .token_counter import GeminiTokenCounter, CounterUnavailable
from .session_budget import MODEL_ID

REQ = {"model": "models/" + MODEL_ID,
       "systemInstruction": {"parts": [{"text": "rules"}]},
       "tools": [{"functionDeclarations": [{"name": "example"}]}],
       "contents": [{"role": "user", "parts": [{"text": "花壇"}]}]}


class CounterTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_request_shape(self):
        import json
        seen = []
        def handler(request):
            seen.append(json.loads(request.content))
            self.assertNotIn("key=", str(request.url))
            return httpx.Response(200, json={"totalTokens": 123})
        counter = GeminiTokenCounter("synthetic-key", approve_external=True,
                                     transport=httpx.MockTransport(handler))
        self.assertEqual(await counter(REQ), 123)
        self.assertEqual(seen, [{"generateContentRequest": REQ}])
        self.assertNotIn("synthetic-key", repr(counter.records))

    async def test_failure_not_success(self):
        counter = GeminiTokenCounter("synthetic-key", approve_external=True,
            transport=httpx.MockTransport(lambda r: httpx.Response(503)))
        with self.assertRaises(CounterUnavailable):
            await counter(REQ)
        self.assertIsNone(counter.records[0]["total_tokens"])

    async def test_bad_payload(self):
        for value in (None, True, -1):
            with self.subTest(value=value):
                counter = GeminiTokenCounter("synthetic-key", approve_external=True,
                    transport=httpx.MockTransport(lambda r: httpx.Response(
                        200, json={"totalTokens": value})))
                with self.assertRaises(CounterUnavailable):
                    await counter(REQ)

    async def test_explicit_approval(self):
        with self.assertRaises(ValueError):
            GeminiTokenCounter("synthetic-key")

    async def test_count_calls_are_bounded(self):
        counter = GeminiTokenCounter("synthetic-key", approve_external=True,
            transport=httpx.MockTransport(lambda r: httpx.Response(
                200, json={"totalTokens": 123})))
        for _ in range(4):
            await counter(REQ)
        with self.assertRaises(CounterUnavailable):
            await counter(REQ)
        self.assertEqual(len(counter.records), 4)
