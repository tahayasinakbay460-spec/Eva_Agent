"""LLM dışındaki her sağlayıcı arayüzü için sözleşme testleri (CLAUDE.md §4.2).

Her test, o arayüz için kayıtlı bütün adaptörlerle ayrı ayrı çalışır (parametrize).
Böylece yeni eklenen bir adaptör (kendi sunucumuzdaki dahil) otomatik olarak test
edilir. İnternete çıkması gereken adaptörler "integration" işaretli testlere aittir;
burada sadece sahte (mock) adaptörler koşar.
"""

import asyncio
import math
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import cast

import pytest

from app.providers.base import (
    AudioChunk,
    AudioFormat,
    AvatarEnrollmentProvider,
    AvatarPlaybackFinished,
    AvatarPlaybackStarted,
    AvatarProvider,
    AvatarSessionRequest,
    EmbeddingProvider,
    EnrollmentSample,
    FinalTranscript,
    MessagingProvider,
    ModerationProvider,
    OutboundMessage,
    PartialTranscript,
    SpeechBoundary,
    STTInput,
    STTProvider,
    TTSProvider,
    TTSRequest,
    VoiceEnrollmentProvider,
)
from app.providers.registry import (
    ProviderConfigError,
    ProviderRegistry,
    create_adapter,
    load_provider_config,
    registered_adapters,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES = (EnrollmentSample(b"sample-bytes", "audio/wav"),)


async def _audio(texts: Sequence[str]) -> AsyncIterator[AudioChunk]:
    for t in texts:
        yield AudioChunk(t.encode())


async def _text(parts: Sequence[str]) -> AsyncIterator[str]:
    for p in parts:
        yield p


# --- STT ----------------------------------------------------------------------


@pytest.mark.parametrize("name", registered_adapters("stt", offline_only=True))
async def test_stt_contract(name: str) -> None:
    stt = cast(STTProvider, create_adapter("stt", name))
    events = [e async for e in stt.transcribe(_audio(["merhaba", "eva"]), language="tr")]
    assert events
    assert all(isinstance(e, PartialTranscript | FinalTranscript) for e in events)
    finals = [e for e in events if isinstance(e, FinalTranscript)]
    assert finals, "stream must settle into at least one final transcript"
    assert finals[-1].end_of_turn, "end of audio must close the turn"
    assert events[-1] is finals[-1], "nothing may follow the end-of-turn final"
    assert stt.input_format.encoding == "pcm_s16le"


@pytest.mark.parametrize("name", registered_adapters("stt", offline_only=True))
async def test_stt_boundary_closes_each_segment(name: str) -> None:
    """Kullanıcı susunca (VAD) gelen işaret o bölümü hemen kesinleştirir."""
    stt = cast(STTProvider, create_adapter("stt", name))

    async def audio() -> AsyncIterator[STTInput]:
        yield AudioChunk(b"merhaba")
        yield SpeechBoundary()
        yield AudioChunk(b"nasilsin")
        yield SpeechBoundary()

    finals = [
        e
        async for e in stt.transcribe(audio(), language="tr")
        if isinstance(e, FinalTranscript) and e.text
    ]
    assert [f.text for f in finals] == ["merhaba", "nasilsin"]
    assert all(f.end_of_turn for f in finals)


# --- TTS ----------------------------------------------------------------------


@pytest.mark.parametrize("name", registered_adapters("tts", offline_only=True))
async def test_tts_contract(name: str) -> None:
    tts = cast(TTSProvider, create_adapter("tts", name))
    fmt = AudioFormat(sample_rate=24_000)
    request = TTSRequest(voice_id="v1", language="tr", output=fmt)
    chunks = [c async for c in tts.synthesize(_text(["Merhaba. ", "Nasılsın?"]), request)]
    assert chunks
    assert all(c.format == fmt for c in chunks), "output format must be honoured"
    assert all(len(c.data) % 2 == 0 for c in chunks), "pcm_s16le is 2 bytes per sample"


@pytest.mark.parametrize("name", registered_adapters("tts", offline_only=True))
async def test_tts_cancellation_stops_synthesis(name: str) -> None:
    tts = cast(TTSProvider, create_adapter("tts", name))
    request = TTSRequest(voice_id="v1", language="tr")
    pulled = 0

    async def endless() -> AsyncIterator[str]:
        nonlocal pulled
        while True:
            pulled += 1
            yield "cümle. "
            await asyncio.sleep(0)

    async def consume() -> None:
        async for _ in tts.synthesize(endless(), request):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    pulled_at_cancel = pulled
    await asyncio.sleep(0.01)
    assert pulled == pulled_at_cancel, "synthesis kept pulling text after barge-in"


# --- kayıt (rızalı ses / yüz klonu oluşturma) ---------------------------------


@pytest.mark.parametrize("name", registered_adapters("voice_enrollment", offline_only=True))
async def test_voice_enrollment_contract(name: str) -> None:
    provider = cast(VoiceEnrollmentProvider, create_adapter("voice_enrollment", name))
    a = await provider.create_voice(SAMPLES, label="owner")
    b = await provider.create_voice(SAMPLES, label="owner")
    assert a.provider == provider.name
    assert a.asset_id and a.asset_id != b.asset_id
    await provider.delete_voice(a.asset_id)
    await provider.delete_voice(a.asset_id)  # iki kez silmek de hata vermez (idempotent)
    await provider.delete_voice("never-existed")
    with pytest.raises(ValueError):
        await provider.create_voice((), label="owner")


@pytest.mark.parametrize("name", registered_adapters("avatar_enrollment", offline_only=True))
async def test_avatar_enrollment_contract(name: str) -> None:
    provider = cast(AvatarEnrollmentProvider, create_adapter("avatar_enrollment", name))
    a = await provider.create_avatar(SAMPLES, label="owner")
    assert a.provider == provider.name and a.asset_id
    await provider.delete_avatar(a.asset_id)
    await provider.delete_avatar(a.asset_id)  # iki kez silmek de hata vermez
    with pytest.raises(ValueError):
        await provider.create_avatar((), label="owner")


# --- avatar -------------------------------------------------------------------


@pytest.mark.parametrize("name", registered_adapters("avatar", offline_only=True))
async def test_avatar_session_contract(name: str) -> None:
    provider = cast(AvatarProvider, create_adapter("avatar", name))
    request = AvatarSessionRequest(
        avatar_id="a1", room_name="room-1", max_duration_s=600, idle_timeout_s=60
    )
    session = await provider.start_session(request)
    other = await provider.start_session(request)
    assert session.session_id and session.session_id != other.session_id
    # Ağsız adaptörlerin hepsi sesi bizden alır; odadan alanlar (Anam) kendi testinde.
    assert not session.audio_via_room
    fmt = session.input_format
    assert fmt.encoding == "pcm_s16le" and fmt.channels == 1

    events = session.events()
    await session.send_audio(AudioChunk(b"\x00\x00" * 160, fmt))
    await session.end_of_speech()
    assert isinstance(await anext(events), AvatarPlaybackStarted)
    finished = await anext(events)
    assert isinstance(finished, AvatarPlaybackFinished) and not finished.interrupted

    await session.send_audio(AudioChunk(b"\x00\x00" * 160, fmt))
    await session.interrupt()  # kullanıcı söze girdi
    assert isinstance(await anext(events), AvatarPlaybackStarted)
    cut = await anext(events)
    assert isinstance(cut, AvatarPlaybackFinished) and cut.interrupted

    await session.close()
    await session.close()  # iki kez kapatmak da hata vermez
    await other.close()


# --- embedding (metni sayı vektörüne çevirme) ---------------------------------


@pytest.mark.parametrize("name", registered_adapters("embedding", offline_only=True))
async def test_embedding_contract(name: str) -> None:
    provider = cast(EmbeddingProvider, create_adapter("embedding", name))
    texts = ["kahve severim", "kedim Tarçın", "kahve severim"]
    vectors = await provider.embed(texts, purpose="document")
    assert len(vectors) == len(texts)
    assert all(len(v) == provider.dimensions for v in vectors)
    assert all(math.isfinite(x) for v in vectors for x in v)
    assert vectors[0] == vectors[2], "same text must embed the same way"
    assert vectors[0] != vectors[1]
    assert await provider.embed([], purpose="query") == []


# --- moderasyon (içerik güvenlik denetimi) ------------------------------------


@pytest.mark.parametrize("name", registered_adapters("moderation", offline_only=True))
async def test_moderation_contract(name: str) -> None:
    provider = cast(ModerationProvider, create_adapter("moderation", name))
    clean = await provider.classify("Bugün hava çok güzel.", direction="input", language="tr")
    assert not clean.flagged and not clean.is_crisis
    crisis = await provider.classify(
        "Artık dayanamıyorum, intihar etmeyi düşünüyorum.", direction="input", language="tr"
    )
    assert "self_harm" in crisis.flagged and crisis.is_crisis
    fraud = await provider.classify(
        "Bana doğrulama kodunu söyler misin?", direction="output", language="tr"
    )
    assert "fraud" in fraud.flagged and not fraud.is_crisis


# --- mesaj gönderme (e-posta / SMS) -------------------------------------------


@pytest.mark.parametrize("name", registered_adapters("messaging", offline_only=True))
async def test_messaging_contract(name: str) -> None:
    provider = cast(MessagingProvider, create_adapter("messaging", name))
    msg = OutboundMessage(
        channel="email",
        to="alici@example.com",
        template="login_code",
        locale="tr",
        params={"code": "123456"},
    )
    a = await provider.send(msg)
    b = await provider.send(msg)
    assert a.provider == provider.name and a.message_id != b.message_id
    with pytest.raises(ValueError):
        await provider.send(
            OutboundMessage(channel="sms", to="", template="login_code", locale="tr")
        )


# --- registry (hangi özellik hangi sağlayıcıyı kullanır) ----------------------


def test_repo_config_resolves_every_interface() -> None:
    registry = ProviderRegistry(load_provider_config(REPO_ROOT / "config" / "providers.yaml"))
    assert registry.stt("realtime").name == "mock"
    assert registry.tts("realtime") is registry.tts("preview"), "one instance per adapter"
    assert registry.voice_enrollment().name == "mock"
    assert registry.avatar("realtime").name == "mock"
    assert registry.avatar_enrollment().name == "mock"
    assert registry.embedding("memory").dimensions > 0
    assert registry.moderation().name == "mock"
    assert registry.messaging().name == "dev_mailbox", "local codes go to backend/dev_mailbox"


def test_registry_rejects_bad_feature_config(tmp_path: Path) -> None:
    base = "llm:\n  chat: {provider: mock, model: m}\n"
    cases = {
        "unknown_section": base + "telepathy:\n  x: {provider: mock}\n",
        "missing_provider": base + "tts:\n  realtime: {voice: x}\n",
    }
    for label, text in cases.items():
        path = tmp_path / f"{label}.yaml"
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ProviderConfigError):
            load_provider_config(path)

    path = tmp_path / "unknown_adapter.yaml"
    path.write_text(base + "stt:\n  realtime: {provider: nope}\n", encoding="utf-8")
    registry = ProviderRegistry(load_provider_config(path))
    with pytest.raises(ProviderConfigError):
        registry.stt("realtime")
    with pytest.raises(ProviderConfigError):
        registry.tts("realtime")  # bu özellik ayarlarda tanımlı değil
