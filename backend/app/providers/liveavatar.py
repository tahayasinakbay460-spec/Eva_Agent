"""``AvatarProvider`` için HeyGen LiveAvatar adaptörü — yalnızca LITE modu (CLAUDE.md §4.2).

LITE: konuşmayı (STT → LLM → TTS) biz yaparız, LiveAvatar sadece verdiğimiz sese göre dudak
senkronlu yüz videosunu üretir ve **bizim** LiveKit odamıza katılıp yayınlar. FULL modu
kullanılmaz (persona, hafıza ve sağlayıcı seçimini HeyGen'e kilitler).

Güncel dokümana göre (2026-10-16; docs.liveavatar.com + OpenAPI şeması):

1. ``POST /v1/sessions/token`` (``X-API-KEY``): ``mode=LITE``, ``avatar_id``, en uzun süre ve
   ``livekit_config`` (bizim oda adresimiz + avatar için ürettiğimiz token).
2. ``POST /v1/sessions/start`` (``Authorization: Bearer <session_token>``) → ``ws_url``.
3. ``ws_url``: "connected" durumunu bekle; ses 24 kHz/16 bit/mono PCM, base64, ~1 sn'lik
   parçalarla ``agent.speak``; söz bitince ``agent.speak_end``; söz kesilince
   ``agent.interrupt``; 60 sn'de bir ``session.keep_alive``.
4. Her durumda ``POST /v1/sessions/stop`` (yoksa oturum boşta kalma süresine kadar ücretlenir).

Anahtar ``LIVEAVATAR_API_KEY`` ortam değişkeninden okunur; asla loglanmaz.
"""

import asyncio
import base64
import contextlib
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any, Literal

import httpx
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import WebSocketException

from app.providers.base import (
    AudioChunk,
    AudioFormat,
    AvatarEvent,
    AvatarPlaybackFinished,
    AvatarPlaybackStarted,
    AvatarSessionRequest,
    ProviderError,
)

DEFAULT_API = "https://api.liveavatar.com"
PCM_24K = AudioFormat(sample_rate=24_000)
_BYTES_PER_SECOND = PCM_24K.sample_rate * 2
# İlk parça daha kısa: avatarın ilk karesi daha erken gelsin (resmî eklentiyle aynı).
FIRST_CHUNK_S = 0.6
NEXT_CHUNK_S = 1.0
KEEP_ALIVE_S = 60.0
CONNECT_TIMEOUT_S = 15.0


def _api_key() -> str:
    key = os.environ.get("LIVEAVATAR_API_KEY")
    if not key:
        raise ProviderError("LIVEAVATAR_API_KEY is not set", retryable=False)
    return key


class LiveAvatarProvider:
    name = "liveavatar"

    def __init__(
        self,
        *,
        api_base: str = DEFAULT_API,
        video_quality: str = "high",
        sandbox: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        connect: Callable[..., Any] = ws_connect,
    ) -> None:
        self._api_base = api_base
        self._video_quality = video_quality
        self._sandbox = sandbox
        self._transport = transport
        self._connect = connect

    def _client(self, headers: dict[str, str]) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._api_base, headers=headers, timeout=15.0, transport=self._transport
        )

    async def start_session(self, request: AvatarSessionRequest) -> "LiveAvatarSession":
        if request.room is None:
            raise ProviderError("liveavatar needs our media room", retryable=False)
        body: dict[str, Any] = {
            "mode": "LITE",
            "avatar_id": request.avatar_id,
            "is_sandbox": self._sandbox,
            "video_settings": {"quality": self._video_quality, "encoding": "H264"},
            "max_session_duration": request.max_duration_s,
            "livekit_config": {
                "livekit_url": request.room.url,
                "livekit_room": request.room_name,
                "livekit_client_token": request.room.token,
            },
        }
        key = _api_key()
        token_data = await self._post("/v1/sessions/token", body, {"X-API-KEY": key})
        session_id = str(token_data["session_id"])
        session_token = str(token_data["session_token"])
        try:
            start_data = await self._post(
                "/v1/sessions/start",
                {"session_id": session_id},
                {"Authorization": f"Bearer {session_token}"},
            )
            session = LiveAvatarSession(
                session_id=session_id,
                ws_url=str(start_data["ws_url"]),
                stop=lambda: self._stop(session_id, key),
                connect=self._connect,
            )
            await session.open()
        except BaseException:
            # Başlatamadıysak bile oturumu kapat: yoksa boşta kalma süresine kadar ücretlenir.
            await self._stop(session_id, key)
            raise
        return session

    async def _post(self, path: str, body: dict[str, Any], headers: dict[str, str]) -> Any:
        try:
            async with self._client(headers) as client:
                r = await client.post(path, json=body)
        except httpx.HTTPError as exc:
            raise ProviderError("liveavatar connection error", retryable=True) from exc
        if r.status_code >= 400:
            raise ProviderError(
                f"liveavatar {path} failed: {r.status_code}", retryable=r.status_code >= 500
            )
        envelope = r.json()
        if envelope.get("code") != 100 or not isinstance(envelope.get("data"), dict):
            raise ProviderError(f"liveavatar {path} refused", retryable=False)
        return envelope["data"]

    async def _stop(self, session_id: str, key: str) -> None:
        with contextlib.suppress(ProviderError):
            await self._post(
                "/v1/sessions/stop",
                {"session_id": session_id, "reason": "USER_CLOSED"},
                {"X-API-KEY": key},
            )


class LiveAvatarSession:
    audio_via_room: Literal[False] = False
    input_format = PCM_24K

    def __init__(
        self,
        *,
        session_id: str,
        ws_url: str,
        stop: Callable[[], Any],
        connect: Callable[..., Any],
    ) -> None:
        self.session_id = session_id
        self._ws_url = ws_url
        self._stop = stop
        self._connect = connect
        self._ws: Any = None
        self._ws_cm: Any = None
        self._buffer = bytearray()
        self._first_chunk = True
        self._speaking = False
        self._interrupted = False
        self._events: asyncio.Queue[AvatarEvent | None] = asyncio.Queue()
        self._tasks: list[asyncio.Task[None]] = []
        self._connected = asyncio.Event()
        self._closed = False

    async def open(self) -> None:
        try:
            self._ws_cm = self._connect(self._ws_url, ping_interval=None)
            self._ws = await self._ws_cm.__aenter__()
        except (OSError, WebSocketException) as exc:
            raise ProviderError("liveavatar websocket error", retryable=True) from exc
        self._tasks = [
            asyncio.create_task(self._read()),
            asyncio.create_task(self._keep_alive()),
        ]
        try:
            await asyncio.wait_for(self._connected.wait(), CONNECT_TIMEOUT_S)
        except TimeoutError as exc:
            await self.close()
            raise ProviderError("liveavatar did not connect", retryable=True) from exc

    async def _send(self, message: dict[str, Any]) -> None:
        if self._closed:
            return
        message.setdefault("event_id", str(uuid.uuid4()))
        try:
            await self._ws.send(json.dumps(message))
        except (OSError, WebSocketException) as exc:
            raise ProviderError("liveavatar send failed", retryable=False) from exc

    async def _flush(self) -> None:
        if self._buffer:
            audio = base64.b64encode(bytes(self._buffer)).decode("ascii")
            self._buffer.clear()
            self._first_chunk = False
            await self._send({"type": "agent.speak", "audio": audio})

    async def send_audio(self, chunk: AudioChunk) -> None:
        if chunk.format != self.input_format:
            # Yanlış örnekleme hızı LiveAvatar'da hatasız ama bozuk görüntü verir; erken yakala.
            raise ProviderError("liveavatar needs 24 kHz mono pcm", retryable=False)
        self._buffer.extend(chunk.data)
        threshold = FIRST_CHUNK_S if self._first_chunk else NEXT_CHUNK_S
        if len(self._buffer) >= threshold * _BYTES_PER_SECOND:
            await self._flush()

    async def end_of_speech(self) -> None:
        await self._flush()
        await self._send({"type": "agent.speak_end"})
        await self._send({"type": "agent.start_listening"})
        self._first_chunk = True

    async def interrupt(self) -> None:
        self._buffer.clear()
        self._first_chunk = True
        await self._send({"type": "agent.interrupt"})

    async def events(self) -> AsyncIterator[AvatarEvent]:
        while (event := await self._events.get()) is not None:
            yield event

    def _handle(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "session.state_updated" and event.get("state") == "connected":
            self._connected.set()
        elif kind == "agent.speak_started" or (
            kind == "agent.state_updated" and event.get("new_state") == "talking"
        ):
            if not self._speaking:
                self._speaking = True
                self._interrupted = False
                self._events.put_nowait(AvatarPlaybackStarted())
        elif kind in ("agent.speak_interrupted", "agent.audio_buffer_cleared"):
            if self._speaking:
                self._speaking = False
                self._interrupted = True
                self._events.put_nowait(AvatarPlaybackFinished(interrupted=True))
        elif kind == "agent.speak_ended" or (
            kind == "agent.state_updated" and event.get("new_state") in ("idle", "listening")
        ):
            if self._speaking:
                self._speaking = False
                self._events.put_nowait(AvatarPlaybackFinished(interrupted=False))

    async def _read(self) -> None:
        try:
            async for raw in self._ws:
                with contextlib.suppress(ValueError):
                    self._handle(json.loads(raw))
        except (OSError, WebSocketException):
            pass
        finally:
            self._events.put_nowait(None)

    async def _keep_alive(self) -> None:
        await self._connected.wait()
        while not self._closed:
            await asyncio.sleep(KEEP_ALIVE_S)
            with contextlib.suppress(ProviderError):
                await self._send({"type": "session.keep_alive"})

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self._ws_cm is not None:
            with contextlib.suppress(Exception):
                await self._ws_cm.__aexit__(None, None, None)
        self._events.put_nowait(None)
        await self._stop()
