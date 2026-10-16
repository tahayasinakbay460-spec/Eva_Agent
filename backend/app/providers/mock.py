"""Testlerde ve internetsiz geliştirmede kullanılan, bedava ve ağsız sahte adaptörler (§4.2).

Deterministiktirler (aynı girdiye hep aynı çıktı), böylece testler çıktılarını kontrol
edebilir. Hiçbiri gerçek bir güvenlik ya da kalite uygulaması değildir; özellikle sahte
moderasyondaki anahtar kelime listesi yalnızca testlerde kriz/dolandırıcılık kod yollarını
çalıştırmak için var.
"""

import asyncio
import hashlib
import itertools
import math
from collections.abc import AsyncIterable, AsyncIterator, Sequence

from app.providers.base import (
    AudioChunk,
    AudioFormat,
    AvatarSessionRequest,
    EmbeddingPurpose,
    EnrollmentSample,
    FinalTranscript,
    LLMEvent,
    LLMRequest,
    MessageReceipt,
    ModerationCategory,
    ModerationDirection,
    ModerationResult,
    OutboundMessage,
    PartialTranscript,
    ProviderAssetRef,
    SpeechBoundary,
    StreamEnd,
    STTInput,
    TextDelta,
    TranscriptEvent,
    TTSRequest,
)


class MockLLMProvider:
    name = "mock"

    def __init__(self, reply: str | None = None, chunk_delay_s: float = 0.0) -> None:
        self._reply = reply
        self._chunk_delay_s = chunk_delay_s

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        last_user = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
        text = self._reply or f"Buradayım. Şunu dedin: «{last_user}». (mock sağlayıcı)"
        words = text.split(" ")
        for i, word in enumerate(words):
            if self._chunk_delay_s:
                await asyncio.sleep(self._chunk_delay_s)
            yield TextDelta(word if i == len(words) - 1 else word + " ")
        yield StreamEnd(
            stop_reason="end_turn",
            input_tokens=sum(len(m.content) for m in request.messages) // 4,
            output_tokens=len(words),
        )


# Gerçek mikrofon sesi metne çevrilemeyince sahte STT'nin "duyduğu" cümle; böylece
# anahtarsız geliştirmede de sesli görüşmenin bütün hattı uçtan uca çalışır.
MOCK_HEARD_TEXT = "(mock) Sesini duydum."


class MockSTTProvider:
    """Ses parçası UTF-8 metinse onu "duyar" (testler için); gerçek ses (mikrofon) gelirse
    sabit bir cümle duymuş sayılır. Her ``SpeechBoundary`` ve akışın bitişi bölümü kapatır."""

    name = "mock"
    input_format = AudioFormat()

    async def transcribe(
        self, audio: AsyncIterable[STTInput], *, language: str
    ) -> AsyncIterator[TranscriptEvent]:
        words: list[str] = []
        heard_audio = False
        async for item in audio:
            if isinstance(item, SpeechBoundary):
                if words or heard_audio:
                    yield FinalTranscript(" ".join(words) or MOCK_HEARD_TEXT, end_of_turn=True)
                words, heard_audio = [], False
                continue
            try:
                words.extend(item.data.decode("utf-8").split())
                yield PartialTranscript(" ".join(words))
            except UnicodeDecodeError:
                heard_audio = True
        yield FinalTranscript(" ".join(words) or (MOCK_HEARD_TEXT if heard_audio else ""), True)


class MockTTSProvider:
    """Her metin parçası için kısık bir "bip" sesi üretir (varsayılan karakter başına 10 ms,
    parça başına en fazla 1,5 sn). Anahtarsız geliştirmede EVA'nın konuştuğu kulakla duyulsun
    diye sessizlik değil. ``ms_per_char`` büyütülürse konuşma uzar (söz kesme denemeleri için)."""

    name = "mock"

    def __init__(self, ms_per_char: int = 10) -> None:
        self._ms_per_char = ms_per_char

    async def synthesize(
        self, text: AsyncIterable[str], request: TTSRequest
    ) -> AsyncIterator[AudioChunk]:
        fmt = request.output
        async for fragment in text:
            if fragment:
                duration = min(len(fragment) * self._ms_per_char, 1500)
                yield AudioChunk(_beep(fmt, duration), fmt)


def _beep(fmt: AudioFormat, duration_ms: int) -> bytes:
    """440 Hz, düşük sesli bir sinüs dalgası (pcm_s16le)."""
    frames = fmt.sample_rate * duration_ms // 1000
    mono = b"".join(
        int(2000 * math.sin(2 * math.pi * 440 * i / fmt.sample_rate)).to_bytes(
            2, "little", signed=True
        )
        for i in range(frames)
    )
    if fmt.channels == 1:
        return mono
    return b"".join(mono[i : i + 2] * fmt.channels for i in range(0, len(mono), 2))


class _MockEnrollmentStore:
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._ids = itertools.count(1)
        self.assets: dict[str, str] = {}

    def create(self, samples: Sequence[EnrollmentSample], label: str) -> ProviderAssetRef:
        if not samples:
            raise ValueError("at least one sample is required")
        asset_id = f"{self._prefix}_{next(self._ids)}"
        self.assets[asset_id] = label
        return ProviderAssetRef(provider="mock", asset_id=asset_id)

    def delete(self, asset_id: str) -> None:
        self.assets.pop(asset_id, None)


class MockVoiceEnrollmentProvider:
    name = "mock"

    def __init__(self) -> None:
        self._store = _MockEnrollmentStore("voice")

    @property
    def assets(self) -> dict[str, str]:
        return self._store.assets

    async def create_voice(
        self, samples: Sequence[EnrollmentSample], *, label: str
    ) -> ProviderAssetRef:
        return self._store.create(samples, label)

    async def delete_voice(self, asset_id: str) -> None:
        self._store.delete(asset_id)


class MockAvatarEnrollmentProvider:
    name = "mock"

    def __init__(self) -> None:
        self._store = _MockEnrollmentStore("avatar")

    @property
    def assets(self) -> dict[str, str]:
        return self._store.assets

    async def create_avatar(
        self, samples: Sequence[EnrollmentSample], *, label: str
    ) -> ProviderAssetRef:
        return self._store.create(samples, label)

    async def delete_avatar(self, asset_id: str) -> None:
        self._store.delete(asset_id)


class MockAvatarSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.audio_bytes = 0
        self.interrupts = 0
        self.closed = False

    async def send_audio(self, chunk: AudioChunk) -> None:
        if self.closed:
            raise RuntimeError("avatar session is closed")
        self.audio_bytes += len(chunk.data)

    async def interrupt(self) -> None:
        self.interrupts += 1

    async def close(self) -> None:
        self.closed = True


class MockAvatarProvider:
    name = "mock"

    def __init__(self) -> None:
        self._ids = itertools.count(1)

    async def start_session(self, request: AvatarSessionRequest) -> MockAvatarSession:
        return MockAvatarSession(f"avatar_session_{next(self._ids)}")


class MockEmbeddingProvider:
    """Hash'ten türetilen, uzunluğu 1 olan sabit vektörler; aynı metin hep aynı vektörü verir."""

    name = "mock"

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: Sequence[str], *, purpose: EmbeddingPurpose) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        digest = b""
        counter = 0
        while len(digest) < self.dimensions:
            digest += hashlib.sha256(f"{counter}:{text}".encode()).digest()
            counter += 1
        raw = [b / 255.0 - 0.5 for b in digest[: self.dimensions]]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]


_MOCK_MODERATION_KEYWORDS: dict[ModerationCategory, tuple[str, ...]] = {
    "self_harm": ("intihar", "kendimi öldür", "suicide", "kill myself"),
    "fraud": ("şifreni", "doğrulama kodu", "kart numaran", "iban", "password"),
}


class MockModerationProvider:
    name = "mock"

    async def classify(
        self, text: str, *, direction: ModerationDirection, language: str
    ) -> ModerationResult:
        lowered = text.casefold()
        flagged = frozenset(
            category
            for category, words in _MOCK_MODERATION_KEYWORDS.items()
            if any(w in lowered for w in words)
        )
        return ModerationResult(flagged=flagged)


class MockMessagingProvider:
    """Gönderilen mesajları testler için bellekte (``outbox``) tutar; dışarı hiçbir şey çıkmaz."""

    name = "mock"

    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self.outbox: list[OutboundMessage] = []

    async def send(self, message: OutboundMessage) -> MessageReceipt:
        if not message.to:
            raise ValueError("recipient is required")
        self.outbox.append(message)
        return MessageReceipt(provider="mock", message_id=f"msg_{next(self._ids)}")
