"""LiveAvatar LITE adaptörü: sahte HTTP API'si ve sahte WebSocket ile, ağsız."""

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app.providers.base import (
    AudioChunk,
    AudioFormat,
    AvatarPlaybackFinished,
    AvatarPlaybackStarted,
    AvatarSessionRequest,
    MediaRoom,
    ProviderError,
)
from app.providers.liveavatar import LiveAvatarProvider

PCM24 = AudioFormat(sample_rate=24_000)
REQUEST = AvatarSessionRequest(
    avatar_id="avatar-1",
    room_name="eva-room",
    max_duration_s=600,
    idle_timeout_s=60,
    room=MediaRoom(url="wss://lk.example", token="avatar-jwt"),
)


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVEAVATAR_API_KEY", "la-key")


class FakeApi:
    def __init__(self, *, fail_start: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any], dict[str, str]]] = []
        self.fail_start = fail_start

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        self.calls.append((request.url.path, body, dict(request.headers)))
        if request.url.path == "/v1/sessions/token":
            data = {"session_id": "s1", "session_token": "st"}
        elif request.url.path == "/v1/sessions/start":
            if self.fail_start:
                return httpx.Response(500, json={"code": 500})
            data = {"session_id": "s1", "ws_url": "wss://avatar.example/ws"}
        else:
            return httpx.Response(200, json={"code": 100, "data": None})
        return httpx.Response(201, json={"code": 100, "data": data})

    def paths(self) -> list[str]:
        return [c[0] for c in self.calls]


class FakeSocket:
    """LiveAvatar'ı taklit eder: açılınca "connected"; speak gelince konuşmaya başlar,
    speak_end gelince bitirir, interrupt gelince keser."""

    def __init__(self, *, connect: bool = True) -> None:
        self.sent: list[dict[str, Any]] = []
        self.inbox: asyncio.Queue[str] = asyncio.Queue()
        self.kwargs: dict[str, Any] = {}
        if connect:
            self.inbox.put_nowait(
                json.dumps({"type": "session.state_updated", "state": "connected"})
            )

    def __call__(self, url: str, **kwargs: Any) -> "FakeSocket":
        self.url, self.kwargs = url, kwargs
        return self

    async def __aenter__(self) -> "FakeSocket":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def send(self, raw: str) -> None:
        message = json.loads(raw)
        self.sent.append(message)
        reply = {
            "agent.speak": "agent.speak_started",
            "agent.speak_end": "agent.speak_ended",
            "agent.interrupt": "agent.speak_interrupted",
        }.get(message["type"])
        if reply:
            await self.inbox.put(json.dumps({"type": reply}))

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[str]:
        while True:
            yield await self.inbox.get()

    def types(self) -> list[str]:
        return [m["type"] for m in self.sent]


def _provider(api: FakeApi, socket: FakeSocket) -> LiveAvatarProvider:
    return LiveAvatarProvider(transport=httpx.MockTransport(api), connect=socket)


async def test_lite_session_joins_our_room() -> None:
    api, socket = FakeApi(), FakeSocket()
    session = await _provider(api, socket).start_session(REQUEST)
    path, body, headers = api.calls[0]
    assert path == "/v1/sessions/token"
    assert headers["x-api-key"] == "la-key"
    assert body["mode"] == "LITE", "never FULL: STT/LLM/TTS stay ours"
    assert body["livekit_config"] == {
        "livekit_url": "wss://lk.example",
        "livekit_room": "eva-room",
        "livekit_client_token": "avatar-jwt",
    }
    assert body["max_session_duration"] == 600
    assert api.calls[1][2]["authorization"] == "Bearer st"
    assert socket.kwargs == {"ping_interval": None}
    await session.close()
    assert api.paths()[-1] == "/v1/sessions/stop"


async def test_audio_is_chunked_and_utterances_are_sealed() -> None:
    api, socket = FakeApi(), FakeSocket()
    session = await _provider(api, socket).start_session(REQUEST)
    events = session.events()
    second = b"\x00\x00" * 24_000  # 1 sn
    await session.send_audio(AudioChunk(second, PCM24))
    await session.send_audio(AudioChunk(b"\x00\x00" * 4_800, PCM24))  # 0,2 sn, tamponda kalır
    await session.end_of_speech()
    assert socket.types() == [
        "agent.speak",
        "agent.speak",
        "agent.speak_end",
        "agent.start_listening",
    ]
    assert len(base64.b64decode(socket.sent[1]["audio"])) == 9_600
    assert isinstance(await anext(events), AvatarPlaybackStarted)
    finished = await anext(events)
    assert isinstance(finished, AvatarPlaybackFinished) and not finished.interrupted
    await session.close()


async def test_interrupt_clears_and_reports_cut() -> None:
    api, socket = FakeApi(), FakeSocket()
    session = await _provider(api, socket).start_session(REQUEST)
    events = session.events()
    await session.send_audio(AudioChunk(b"\x00\x00" * 24_000, PCM24))
    await session.send_audio(AudioChunk(b"\x00\x00" * 100, PCM24))
    await session.interrupt()
    assert socket.types()[-1] == "agent.interrupt"
    assert isinstance(await anext(events), AvatarPlaybackStarted)
    cut = await anext(events)
    assert isinstance(cut, AvatarPlaybackFinished) and cut.interrupted
    await session.end_of_speech()
    assert socket.types()[-2:] == ["agent.speak_end", "agent.start_listening"], "buffer was dropped"
    await session.close()


async def test_wrong_sample_rate_is_rejected() -> None:
    session = await _provider(FakeApi(), FakeSocket()).start_session(REQUEST)
    with pytest.raises(ProviderError):
        await session.send_audio(AudioChunk(b"\x00\x00" * 100, AudioFormat(sample_rate=16_000)))
    await session.close()


async def test_failed_start_still_stops_the_billing_session() -> None:
    api = FakeApi(fail_start=True)
    with pytest.raises(ProviderError):
        await _provider(api, FakeSocket()).start_session(REQUEST)
    assert api.paths() == ["/v1/sessions/token", "/v1/sessions/start", "/v1/sessions/stop"]


async def test_never_connected_websocket_stops_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.providers.liveavatar.CONNECT_TIMEOUT_S", 0.05)
    api = FakeApi()
    with pytest.raises(ProviderError):
        await _provider(api, FakeSocket(connect=False)).start_session(REQUEST)
    assert api.paths()[-1] == "/v1/sessions/stop"


async def test_room_is_required_and_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(FakeApi(), FakeSocket())
    no_room = AvatarSessionRequest(avatar_id="a", room_name="r", max_duration_s=1, idle_timeout_s=1)
    with pytest.raises(ProviderError):
        await provider.start_session(no_room)
    monkeypatch.delenv("LIVEAVATAR_API_KEY")
    with pytest.raises(ProviderError) as info:
        await provider.start_session(REQUEST)
    assert info.value.retryable is False
