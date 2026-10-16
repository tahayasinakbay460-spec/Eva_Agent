"""Sabit pencereli istek sınırı (rate limit): "dakikada en fazla N istek".

Şimdilik sayaçlar süreç belleğinde tutuluyor; docker-compose kurulunca Redis'li sürüm,
aynı ``RateLimiter`` arayüzünün arkasında ``MemoryRateLimiter``'ın yerini alacak.
"""

import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Protocol

from fastapi import HTTPException, Request, status


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_s: float) -> bool:
        """Bir isteği say; ``key`` pencere içinde ``limit``'i aştıysa False döndür."""


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
    """Bağımlılık üretir. ``setting``, ``Settings`` içindeki dakikalık limit alanının adıdır."""

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
