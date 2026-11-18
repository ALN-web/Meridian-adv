"""Shared rate limiter: at most N portal requests per second across all browser contexts."""
from __future__ import annotations

import asyncio
import time


class RateLimiter:
    def __init__(self, per_second: float = 2.0, clock=time.monotonic, sleep=asyncio.sleep):
        self.min_interval = 1.0 / per_second
        self._clock = clock
        self._sleep = sleep
        self._next_slot = 0.0
        self._lock = asyncio.Lock()
        self._penalty_until = 0.0
        self.count = 0  # requests let through, for reporting the achieved rate

    async def wait(self) -> None:
        async with self._lock:
            now = self._clock()
            slot = max(now, self._next_slot, self._penalty_until)
            self._next_slot = slot + self.min_interval
            self.count += 1
        delay = slot - now
        if delay > 0:
            await self._sleep(delay)

    def back_off(self, seconds: float) -> None:
        """Called when the portal says we're going too fast: everyone pauses."""
        self._penalty_until = max(self._penalty_until, self._clock() + seconds)
