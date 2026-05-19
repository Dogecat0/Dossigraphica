import asyncio
import time
import logging

logger = logging.getLogger(__name__)


class MinuteRateLimiter:
    """
    Sliding-window rate limiter keyed to a 60-second rolling window.

    Callers may burst freely up to `limit` units within the window.
    Once the budget is exhausted, acquire() blocks until the window
    resets — no artificial per-request stagger.

    Thread/async safety: all state mutations are serialised through an
    asyncio.Lock so concurrent coroutines observe a consistent budget.

    Usage:
        limiter = MinuteRateLimiter(limit=30)
        await limiter.acquire()        # costs 1 unit
        await limiter.acquire(count=10)  # costs 10 units (e.g. a URL batch)
    """

    def __init__(self, limit: int):
        self.limit = limit
        self._used: int = 0
        self._window_start: float = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, count: int = 1) -> None:
        async with self._lock:
            now = time.monotonic()
            # Roll the window forward if 60 s have elapsed since it started
            if now - self._window_start >= 60.0:
                self._window_start = now
                self._used = 0

            # Budget exhausted — wait until the current window expires
            if self._used + count > self.limit:
                wait = 60.0 - (time.monotonic() - self._window_start)
                if wait > 0:
                    logger.debug(
                        f"Rate limit reached ({self._used}/{self.limit}). "
                        f"Waiting {wait:.1f}s for window reset."
                    )
                    await asyncio.sleep(wait)
                self._window_start = time.monotonic()
                self._used = 0

            self._used += count
