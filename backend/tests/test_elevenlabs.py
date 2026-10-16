"""ElevenLabs adaptörleri: ağa çıkmadan, sahte WebSocket ve sahte HTTP ile."""

import asyncio
import base64
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import pytest

from app.providers.base import (
    AudioFormat,
    EnrollmentSample,
    ProviderError,
    TTSRequest,
)
from app.providers.elevenlabs import ElevenLabsTTSProvider, ElevenLabsVoiceEnrollmentProvider

FMT = AudioFormat(sample_rate=24_000)
REQUEST = TTSRequest(voice_id="voice123", language="tr", output=FMT)


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")


class FakeSocket:
    """Gönderilen her metne bir ses parçasıyla cevap verir; "" gelince isFinal yollar."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.inbox: asyncio.Queue[str] = asyncio.Queue()
        self.url = ""
        self.headers: dict[str, str] = {}

    async def send(self, raw: str) -> None:
        message = json.loads(raw)
        self.sent.append(message)
        if message["text"] == "":
            await self.inbox.put(json.dumps({"isFinal": True}))
        elif message["text"].strip():
            audio = base64.b64encode(b"\x01\x00" * 10).decode()
            await self.inbox.put(json.dumps({"audio": audio, "isFinal": False}))

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[str]:
        while True:
            yield await self.inbox.get()


class FakeConnect:
    def __init__(self) -> None:
        self.socket = FakeSocket()

    def __call__(self, url: str, *, additional_headers: dict[str, str]) -> "FakeConnect":
        self.socket.url = url
        self.socket.headers = additional_headers
        return self

    async def __aenter__(self) -> FakeSocket:
        return self.socket

    async def __aexit__(self, *exc: object) -> None:
        return None


async def _text(parts: Sequence[str]) -> AsyncIterator[str]:
    for p in parts:
        yield p


async def test_tts_streams_pcm_in_requested_format() -> None:
    connect = FakeConnect()
    tts = ElevenLabsTTSProvider(connect=connect)
    chunks = [c async for c in tts.synthesize(_text(["Merhaba.", "Nasılsın? "]), REQUEST)]
    assert len(chunks) == 2
    assert all(c.format == FMT and c.data == b"\x01\x00" * 10 for c in chunks)

    socket = connect.socket
    assert "voice123/stream-input" in socket.url
    assert "model_id=eleven_flash_v2_5" in socket.url
    assert "output_format=pcm_24000" in socket.url
    assert "language_code=tr" in socket.url
    assert socket.headers == {"xi-api-key": "test-key"}, "key goes in a header, never the URL"
    assert socket.sent[0]["text"] == " ", "first message is a single space + settings"
    assert [m["text"] for m in socket.sent[1:]] == ["Merhaba. ", "Nasılsın? ", ""]


async def test_tts_cancellation_stops_sending_text() -> None:
    connect = FakeConnect()
    tts = ElevenLabsTTSProvider(connect=connect)
    pulled = 0

    async def endless() -> AsyncIterator[str]:
        nonlocal pulled
        while True:
            pulled += 1
            yield "cümle. "
            await asyncio.sleep(0)

    async def consume() -> None:
        async for _ in tts.synthesize(endless(), REQUEST):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    at_cancel = pulled
    await asyncio.sleep(0.01)
    assert pulled == at_cancel


async def test_tts_without_key_is_not_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    tts = ElevenLabsTTSProvider(connect=FakeConnect())
    with pytest.raises(ProviderError) as info:
        [c async for c in tts.synthesize(_text(["a"]), REQUEST)]
    assert info.value.retryable is False


# --- ses klonu -------------------------------------------------------------------


def _voices(handler: Any) -> ElevenLabsVoiceEnrollmentProvider:
    return ElevenLabsVoiceEnrollmentProvider(transport=httpx.MockTransport(handler))


async def test_create_voice_uploads_every_sample() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"voice_id": "v_1", "requires_verification": False})

    samples = [EnrollmentSample(b"a", "audio/webm"), EnrollmentSample(b"b", "audio/webm")]
    ref = await _voices(handler).create_voice(samples, label="eva-user-1")
    assert (ref.provider, ref.asset_id) == ("elevenlabs", "v_1")
    request = seen[0]
    assert request.url.path == "/v1/voices/add"
    assert request.headers["xi-api-key"] == "test-key"
    body = request.content
    assert body.count(b'name="files"') == 2
    assert b"eva-user-1" in body


async def test_voice_needing_verification_is_deleted_and_refused() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "POST":
            return httpx.Response(200, json={"voice_id": "v_2", "requires_verification": True})
        return httpx.Response(200, json={"status": "ok"})

    with pytest.raises(ProviderError):
        await _voices(handler).create_voice([EnrollmentSample(b"a", "audio/webm")], label="x")
    assert calls == ["POST", "DELETE"], "no half-created clone is left at the provider"


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, {"status": "ok"}),
        (404, {"detail": {"code": "voice_not_found"}}),
        (400, {"detail": {"status": "voice_does_not_exist"}}),
    ],
)
async def test_delete_voice_is_idempotent(status: int, body: dict[str, Any]) -> None:
    await _voices(lambda r: httpx.Response(status, json=body)).delete_voice("v_1")


async def test_delete_voice_server_error_is_retryable() -> None:
    provider = _voices(lambda r: httpx.Response(503, json={"detail": {"code": "maintenance"}}))
    with pytest.raises(ProviderError) as info:
        await provider.delete_voice("v_1")
    assert info.value.retryable is True


async def test_create_voice_requires_samples() -> None:
    with pytest.raises(ValueError):
        await _voices(lambda r: httpx.Response(500)).create_voice([], label="x")
