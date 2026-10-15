"""Fixed-window rate limiting.

In-process for now; the Redis-backed implementation will replace ``MemoryRateLimiter``
behind the same ``RateLimiter`` protocol once docker-compose is in place.
"""

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Protocol

from fastapi import HTTPException, Request, status


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_s: float) -> bool:
        """Record a hit; return False when ``key`` exceeded ``limit`` within the window."""


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def hit(self, key: str, limit: int, window_s: float) -> bool:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] >= window_s:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


def _client_key(request: Request) -> str:
    user = getattr(request.state, "user_id", None)
    if user is not None:
        return f"user:{user}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


def rate_limited(scope: str, setting: str) -> Callable[[Request], Awaitable[None]]:
    """Dependency factory. ``setting`` names the per-minute limit on ``Settings``."""

    async def dependency(request: Request) -> None:
        settings = request.app.state.settings
        limiter: RateLimiter = request.app.state.rate_limiter
        limit: int = getattr(settings, setting)
        key = f"{scope}:{_client_key(request)}"
        if not await limiter.hit(key, limit, 60.0):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
                headers={"Retry-After": "60"},
            )

    return dependency
