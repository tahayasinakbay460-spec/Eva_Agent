"""Saf ASGI ara katmanı (middleware): her isteğe kimlik (request ID) ve güvenlik başlıkları.

``BaseHTTPMiddleware`` yerine ham ASGI ile yazıldı; böylece akışlı SSE cevapları
(sunucunun parça parça gönderdiği cevaplar) bozulmadan geçer.
"""

import uuid
from collections.abc import MutableMapping
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

SECURITY_HEADERS: dict[bytes, bytes] = {
    b"x-content-type-options": b"nosniff",
    b"referrer-policy": b"strict-origin-when-cross-origin",
    b"x-frame-options": b"DENY",
    b"cache-control": b"no-store",
}


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        state: MutableMapping[str, Any] = scope.setdefault("state", {})
        state["request_id"] = request_id

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                headers.extend(SECURITY_HEADERS.items())
                if self.hsts:
                    headers.append(
                        (b"strict-transport-security", b"max-age=63072000; includeSubDomains")
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
