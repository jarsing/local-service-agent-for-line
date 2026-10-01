"""Shared request pacing for explicit live samples; no silent retry-to-success."""
import asyncio
import math


class RequestGate:
    def __init__(self, concurrency=1, interval=1.0):
        if type(concurrency) is not int or concurrency < 1:
            raise ValueError('POSITIVE_CONCURRENCY_REQUIRED')
        if not isinstance(interval, (int, float)) or isinstance(interval, bool) or not math.isfinite(interval) or interval < 0:
            raise ValueError('NONNEGATIVE_FINITE_INTERVAL_REQUIRED')
        self.slots = asyncio.Semaphore(concurrency)
        self.lock = asyncio.Lock()
        self.next_start = 0.0
        self.interval = interval

    async def run(self, operation):
        async with self.slots:
            async with self.lock:
                loop = asyncio.get_running_loop()
                await asyncio.sleep(max(0.0, self.next_start - loop.time()))
                self.next_start = loop.time() + self.interval
            return await operation()


class RequestBudget:
    def __init__(self, generation_limit: int, count_limit: int):
        if type(generation_limit) is not int or generation_limit < 1 or type(count_limit) is not int or count_limit < 1:
            raise ValueError('EXPLICIT_POSITIVE_LIVE_LIMITS_REQUIRED')
        self.limits = {'generation': generation_limit, 'count_tokens': count_limit}
        self.attempted = {'generation': 0, 'count_tokens': 0}

    def claim(self, kind: str) -> None:
        if self.attempted[kind] >= self.limits[kind]:
            raise RuntimeError('EXTERNAL_REQUEST_BUDGET_EXHAUSTED')
        # Charged before sending: a failed HTTP request still consumes its attempt.
        self.attempted[kind] += 1
