"""Retry with exponential backoff. Every portal step goes through this."""
from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from meridian.portal.errors import HumanNeeded, LoginFailed, PortalError, RateLimited, SessionExpired

log = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass
class RetryPolicy:
    attempts: int = 5
    base_delay: float = 1.0
    max_delay: float = 30.0
    rate_limit_delay: float = 20.0

    def delay(self, attempt: int) -> float:
        d = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        return d * (0.8 + 0.4 * random.random())


@dataclass
class RetryStats:
    retries: int = 0


async def with_retry(
    step: str,
    fn: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    stats: RetryStats | None = None,
    on_session_expired: Callable[[], Awaitable[None]] | None = None,
    on_rate_limited: Callable[[float], None] | None = None,
    sleep=asyncio.sleep,
) -> T:
    """Run ``fn``; retry transient portal failures. Never retries HumanNeeded or LoginFailed."""
    policy = policy or RetryPolicy()
    last: Exception | None = None
    for attempt in range(1, policy.attempts + 1):
        try:
            return await fn()
        except (HumanNeeded, LoginFailed):
            raise
        except SessionExpired as exc:
            last = exc
            log.info("step=%s attempt=%d session expired, logging in again", step, attempt)
            if on_session_expired is not None:
                await on_session_expired()
        except RateLimited as exc:
            last = exc
            wait = policy.rate_limit_delay * attempt
            log.info("step=%s attempt=%d rate limited, backing off %.1fs", step, attempt, wait)
            if on_rate_limited is not None:
                on_rate_limited(wait)
            await sleep(wait)
        except (PortalError, TimeoutError, asyncio.TimeoutError) as exc:
            last = exc
            wait = policy.delay(attempt)
            log.info("step=%s attempt=%d failed (%s), retrying in %.1fs", step, attempt, type(exc).__name__, wait)
            await sleep(wait)
        except Exception as exc:  # Playwright timeouts / navigation errors arrive as their own types
            if type(exc).__name__ not in {"TimeoutError", "Error"}:
                raise
            last = exc
            wait = policy.delay(attempt)
            log.info("step=%s attempt=%d playwright %s, retrying in %.1fs", step, attempt, type(exc).__name__, wait)
            await sleep(wait)
        if stats is not None:
            stats.retries += 1
    raise PortalError(f"step {step!r} failed after {policy.attempts} attempts: {last}")
