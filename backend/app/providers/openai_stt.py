"""``STTProvider`` için OpenAI gerçek zamanlı transkripsiyon adaptörü (Türkçe test bekliyor, §15).

Güncel dokümana göre (2026-10-16; developers.openai.com, Realtime transcription):

- Model ``gpt-live-transcribe``: canlı ara metin verir ama kendi tur tespiti (VAD) yoktur;
  ``turn_detection`` boş bırakılır ve kullanıcı susunca biz ``input_audio_buffer.commit``
  göndeririz. Tur sonunu zaten LiveKit tarafında biz tespit ediyoruz (§4.3), bu uyumlu.
- Ses: 16 bit PCM, mono, **yalnızca 24 kHz** (``input_format``); çeviriyi gerçek zamanlı
  katman yapar.
- Adres: ``wss://api.openai.com/v1/realtime?intent=transcription``. Resmî sayfalarda açıkça
  yazmıyor (topluluk ve OpenAI'nin kendi örnek kodları bunu kullanıyor); anahtar gelince ilk
  denenecek şey bu.
- Farklı turların "completed" olayları sırasız gelebilir: ``item_id`` ile eşlenir, commit
  sırasıyla verilir.

Anahtar ``OPENAI_API_KEY`` ortam değişkeninden okunur; asla loglanmaz.
"""

import asyncio
import base64
import contextlib
import json
import os
from collections.abc import AsyncIterable, AsyncIterator, Callable
from typing import Any

from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import WebSocketException

from app.providers.base import (
    AudioFormat,
    FinalTranscript,
    PartialTranscript,
    ProviderError,
    SpeechBoundary,
    STTInput,
    TranscriptEvent,
)

DEFAULT_URL = "wss://api.openai.com/v1/realtime?intent=transcription"


class OpenAISTTProvider:
    name = "openai"
    input_format = AudioFormat(sample_rate=24_000)

    def __init__(
        self,
        *,
        model: str = "gpt-live-transcribe",
        url: str = DEFAULT_URL,
        noise_reduction: str = "near_field",
        connect: Callable[..., Any] = ws_connect,
    ) -> None:
        self._model = model
        self._url = url
        self._noise_reduction = noise_reduction
        self._connect = connect

    def _session_update(self, language: str) -> dict[str, Any]:
        return {
            "type": "session.update",
            "session": {
                "type": "transcription",
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": self.input_format.sample_rate},
                        "noise_reduction": {"type": self._noise_reduction},
                        "transcription": {"model": self._model, "languages": [language]},
                        "turn_detection": None,
                    }
                },
            },
        }

    async def transcribe(
        self, audio: AsyncIterable[STTInput], *, language: str
    ) -> AsyncIterator[TranscriptEvent]:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderError("OPENAI_API_KEY is not set", retryable=False)
        out: asyncio.Queue[TranscriptEvent | BaseException | None] = asyncio.Queue()
        try:
            async with self._connect(
                self._url, additional_headers={"Authorization": f"Bearer {key}"}
            ) as ws:
                await ws.send(json.dumps(self._session_update(language)))
                state = _TurnState()
                writer = asyncio.create_task(_write(ws, audio, state, out))
                reader = asyncio.create_task(_read(ws, state, out))
                try:
                    while True:
                        item = await out.get()
                        if item is None:
                            break
                        if isinstance(item, BaseException):
                            raise item
                        yield item
                finally:
                    for task in (writer, reader):
                        task.cancel()
                    for task in (writer, reader):
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            await task
        except (OSError, WebSocketException) as exc:
            raise ProviderError("stt connection error", retryable=True) from exc


class _TurnState:
    """Commit sırası ve henüz cevabı gelmemiş turlar (yazıcı ile okuyucu arasında paylaşılır)."""

    def __init__(self) -> None:
        self.audio_since_commit = False
        self.pending_commits = 0
        self.input_done = False
        self.order: list[str] = []  # commit sırasıyla item_id'ler
        self.done: dict[str, str] = {}  # item_id -> kesin metin
        self.partial: dict[str, str] = {}
        self.all_settled = asyncio.Event()

    def check_settled(self) -> None:
        if self.input_done and self.pending_commits == 0:
            self.all_settled.set()


async def _write(
    ws: Any,
    audio: AsyncIterable[STTInput],
    state: _TurnState,
    out: "asyncio.Queue[TranscriptEvent | BaseException | None]",
) -> None:
    async def commit() -> None:
        if state.audio_since_commit:
            state.pending_commits += 1
            state.audio_since_commit = False
            await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

    try:
        async for item in audio:
            if isinstance(item, SpeechBoundary):
                await commit()
                continue
            if item.format.sample_rate != OpenAISTTProvider.input_format.sample_rate:
                raise ProviderError("openai stt needs 24 kHz pcm", retryable=False)
            state.audio_since_commit = True
            await ws.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(item.data).decode("ascii"),
                    }
                )
            )
        await commit()
        state.input_done = True
        state.check_settled()
        await state.all_settled.wait()
        await out.put(None)
    except BaseException as exc:
        await out.put(exc)
        raise


async def _read(
    ws: Any, state: _TurnState, out: "asyncio.Queue[TranscriptEvent | BaseException | None]"
) -> None:
    try:
        async for raw in ws:
            event = json.loads(raw)
            kind = event.get("type", "")
            if kind == "input_audio_buffer.committed":
                state.order.append(str(event.get("item_id")))
            elif kind == "conversation.item.input_audio_transcription.delta":
                item_id = str(event.get("item_id"))
                state.partial[item_id] = state.partial.get(item_id, "") + str(
                    event.get("delta", "")
                )
                await out.put(PartialTranscript(state.partial[item_id]))
            elif kind == "conversation.item.input_audio_transcription.completed":
                state.done[str(event.get("item_id"))] = str(event.get("transcript", "")).strip()
                # Commit sırasına göre, cevabı gelmiş olanları sırayla ver.
                while state.order and state.order[0] in state.done:
                    item_id = state.order.pop(0)
                    state.partial.pop(item_id, None)
                    await out.put(FinalTranscript(state.done.pop(item_id), end_of_turn=True))
                    state.pending_commits -= 1
                state.check_settled()
            elif kind in ("error", "conversation.item.input_audio_transcription.failed"):
                raise ProviderError("stt error event", retryable=False)
    except BaseException as exc:
        await out.put(exc)
        raise
