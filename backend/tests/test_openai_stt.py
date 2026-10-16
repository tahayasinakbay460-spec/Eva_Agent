"""OpenAI transkripsiyon adaptörü: sahte bir Realtime sunucusuyla, ağsız."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.providers.base import (
    AudioChunk,
    AudioFormat,
    FinalTranscript,
    PartialTranscript,
    ProviderError,
    SpeechBoundary,
    STTInput,
)
from app.providers.openai_stt import OpenAISTTProvider

PCM24 = AudioFormat(sample_rate=24_000)


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


class FakeRealtime:
    """Her commit'e bir item verir; transkripti, eklenen seslerin sayısından üretir.

    ``reverse=True`` iken son iki turun "completed" olayları ters sırada gelir.
    """

    def __init__(self, *, reverse: bool = False, fail: bool = False) -> None:
        self.sent: list[dict[str, Any]] = []
        self.inbox: asyncio.Queue[str] = asyncio.Queue()
        self.headers: dict[str, str] = {}
        self.url = ""
        self._appends = 0
        self._items = 0
        self._held: list[str] = []
        self._reverse = reverse
        self._fail = fail

    def __call__(self, url: str, *, additional_headers: dict[str, str]) -> "FakeRealtime":
        self.url, self.headers = url, additional_headers
        return self

    async def __aenter__(self) -> "FakeRealtime":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def send(self, raw: str) -> None:
        event = json.loads(raw)
        self.sent.append(event)
        if event["type"] == "input_audio_buffer.append":
            self._appends += 1
            if self._fail:
                await self.inbox.put(json.dumps({"type": "error", "error": {"code": "x"}}))
        elif event["type"] == "input_audio_buffer.commit":
            self._items += 1
            item = f"item_{self._items}"
            await self.inbox.put(
                json.dumps({"type": "input_audio_buffer.committed", "item_id": item})
            )
            await self.inbox.put(
                json.dumps(
                    {
                        "type": "conversation.item.input_audio_transcription.delta",
                        "item_id": item,
                        "delta": "par",
                    }
                )
            )
            done = json.dumps(
                {
                    "type": "conversation.item.input_audio_transcription.completed",
                    "item_id": item,
                    "transcript": f" tur {self._items} ({self._appends} parça) ",
                }
            )
            self._appends = 0
            if self._reverse and self._items == 1:
                self._held.append(done)
            else:
                await self.inbox.put(done)
                for held in self._held:
                    await self.inbox.put(held)
                self._held.clear()

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[str]:
        while True:
            yield await self.inbox.get()


async def _audio(*items: STTInput) -> AsyncIterator[STTInput]:
    for item in items:
        yield item


def _pcm() -> AudioChunk:
    return AudioChunk(b"\x00\x00" * 240, PCM24)


async def test_session_is_configured_for_turkish_manual_commit() -> None:
    fake = FakeRealtime()
    stt = OpenAISTTProvider(connect=fake)
    events = [e async for e in stt.transcribe(_audio(_pcm(), SpeechBoundary()), language="tr")]
    first = fake.sent[0]
    assert first["type"] == "session.update"
    audio_in = first["session"]["audio"]["input"]
    assert audio_in["format"] == {"type": "audio/pcm", "rate": 24_000}
    assert audio_in["transcription"] == {"model": "gpt-live-transcribe", "languages": ["tr"]}
    assert audio_in["turn_detection"] is None, "end of turn is decided by our VAD"
    assert fake.headers == {"Authorization": "Bearer test-key"}
    assert "test-key" not in fake.url
    assert any(isinstance(e, PartialTranscript) for e in events)
    assert events[-1] == FinalTranscript("tur 1 (1 parça)", end_of_turn=True)


async def test_finals_follow_commit_order_even_if_completions_arrive_reversed() -> None:
    stt = OpenAISTTProvider(connect=FakeRealtime(reverse=True))
    events = [
        e
        async for e in stt.transcribe(
            _audio(_pcm(), SpeechBoundary(), _pcm(), _pcm(), SpeechBoundary()), language="tr"
        )
    ]
    finals = [e.text for e in events if isinstance(e, FinalTranscript)]
    assert finals == ["tur 1 (1 parça)", "tur 2 (2 parça)"]


async def test_empty_boundary_does_not_commit() -> None:
    fake = FakeRealtime()
    stt = OpenAISTTProvider(connect=fake)
    events = [e async for e in stt.transcribe(_audio(SpeechBoundary()), language="tr")]
    assert events == []
    assert not [e for e in fake.sent if e["type"] == "input_audio_buffer.commit"]


async def test_trailing_audio_is_committed_at_end_of_stream() -> None:
    stt = OpenAISTTProvider(connect=FakeRealtime())
    events = [e async for e in stt.transcribe(_audio(_pcm()), language="tr")]
    assert isinstance(events[-1], FinalTranscript) and events[-1].end_of_turn


async def test_error_event_raises() -> None:
    stt = OpenAISTTProvider(connect=FakeRealtime(fail=True))
    with pytest.raises(ProviderError):
        [e async for e in stt.transcribe(_audio(_pcm(), SpeechBoundary()), language="tr")]


async def test_wrong_sample_rate_is_rejected() -> None:
    stt = OpenAISTTProvider(connect=FakeRealtime())
    with pytest.raises(ProviderError):
        [e async for e in stt.transcribe(_audio(AudioChunk(b"\x00\x00")), language="tr")]


async def test_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY")
    stt = OpenAISTTProvider(connect=FakeRealtime())
    with pytest.raises(ProviderError) as info:
        [e async for e in stt.transcribe(_audio(_pcm()), language="tr")]
    assert info.value.retryable is False
