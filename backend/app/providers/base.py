"""Sağlayıcıdan bağımsız arayüzler ve veri tipleri.

Her adaptör (mock, anthropic, ileride kendi sunucumuz, ...) yalnızca bu tiplerle konuşur.
"""

from collections.abc import AsyncIterable, AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

# "none": akıl yürütme yok, en hızlı cevap (yalnızca destekleyen modellerde; ör. GPT-6 Luna).
Effort = Literal["none", "low", "medium", "high", "xhigh", "max"]
StopReason = Literal["end_turn", "max_tokens", "refusal"]


@dataclass(frozen=True, slots=True)
class SystemBlock:
    """Sistem prompt'unun bir parçası. ``cacheable``, sabit (önbelleğe alınabilir) baş kısmın
    bittiği yeri işaretler."""

    text: str
    cacheable: bool = False


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class LLMRequest:
    model: str
    system: tuple[SystemBlock, ...]
    messages: tuple[LLMMessage, ...]
    max_tokens: int = 1024
    effort: Effort | None = None


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class StreamEnd:
    stop_reason: StopReason
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


LLMEvent = TextDelta | StreamEnd


class ProviderError(Exception):
    """Sağlayıcı tarafında bir hata olunca adaptörler bunu fırlatır. ``retryable``, çağırana
    "tekrar denemeye değer mi" bilgisini verir."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(Protocol):
    name: str

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        """Üretildikçe ``TextDelta`` parçaları verir, en sonda tam bir tane ``StreamEnd``."""
        ...


# --- ses ------------------------------------------------------------------------

AudioEncoding = Literal["pcm_s16le"]


@dataclass(frozen=True, slots=True)
class AudioFormat:
    """Gerçek zamanlı yoldaki ham sesin biçimi (varsayılanları docs/contracts sabitleyecek)."""

    encoding: AudioEncoding = "pcm_s16le"
    sample_rate: int = 16_000
    channels: int = 1


@dataclass(frozen=True, slots=True)
class AudioChunk:
    data: bytes
    format: AudioFormat = AudioFormat()


# --- konuşmadan metne (STT) -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class PartialTranscript:
    """Ara tahmin; sonraki olaylarla değişebilir."""

    text: str


@dataclass(frozen=True, slots=True)
class FinalTranscript:
    """Bir bölümün kesinleşmiş metni. ``end_of_turn`` = kullanıcı konuşmasını bitirdi."""

    text: str
    end_of_turn: bool


TranscriptEvent = PartialTranscript | FinalTranscript


@dataclass(frozen=True, slots=True)
class SpeechBoundary:
    """Ses akışına konan işaret: "kullanıcı sustu, bu bölümü kesinleştir".

    Tur sonunu (VAD + tur sonu modeli) gerçek zamanlı katman tespit eder; STT kendi tur
    tespitini yapamıyorsa (ör. OpenAI gpt-live-transcribe) bu işaretle bölümü kapatır.
    """


STTInput = AudioChunk | SpeechBoundary


class STTProvider(Protocol):
    name: str
    # Sağlayıcının istediği ses biçimi; gerçek zamanlı katman sesi buna çevirip (resample) verir.
    input_format: AudioFormat

    def transcribe(
        self, audio: AsyncIterable[STTInput], *, language: str
    ) -> AsyncIterator[TranscriptEvent]:
        """Sesi geldikçe işler; önce ara tahminleri, bölümler kesinleşince son metinleri verir.

        Her ``SpeechBoundary``'den sonra o bölüm için ``end_of_turn=True`` olan bir son
        metin gelir; akışın bitişi de son bölümü kapatır.
        """
        ...


# --- metinden konuşmaya (TTS) ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class TTSRequest:
    voice_id: str
    language: str
    output: AudioFormat = AudioFormat()


class TTSProvider(Protocol):
    name: str

    def synthesize(
        self, text: AsyncIterable[str], request: TTSRequest
    ) -> AsyncIterator[AudioChunk]:
        """Metin parçalarını (cümle cümle) alır ve ses hazır olur olmaz verir.

        Tüketen görev iptal edilirse ses üretimi de durmalı (söz kesme / barge-in, §4.3).
        """
        ...


# --- kayıt (rızalı ses / yüz klonları) --------------------------------------------


@dataclass(frozen=True, slots=True)
class EnrollmentSample:
    """Rızası alınmış tek bir ham örnek; kendi depomuzdan okunur (§4.2 "varlıklar bizimdir")."""

    data: bytes
    media_type: str


@dataclass(frozen=True, slots=True)
class ProviderAssetRef:
    """Bir klonun sağlayıcıdaki id'si; ``provider_assets``'te yalnızca eşleme olarak tutulur."""

    provider: str
    asset_id: str


class VoiceEnrollmentProvider(Protocol):
    name: str

    async def create_voice(
        self, samples: Sequence[EnrollmentSample], *, label: str
    ) -> ProviderAssetRef: ...

    async def delete_voice(self, asset_id: str) -> None:
        """İdempotent (kaç kez çağrılırsa çağrılsın sonuç aynı): bilinmeyen ya da zaten
        silinmiş bir sesi silmek hata değildir."""
        ...


class AvatarEnrollmentProvider(Protocol):
    name: str

    async def create_avatar(
        self, samples: Sequence[EnrollmentSample], *, label: str
    ) -> ProviderAssetRef: ...

    async def delete_avatar(self, asset_id: str) -> None:
        """``delete_voice`` gibi idempotent."""
        ...


# --- gerçek zamanlı avatar --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AvatarSessionRequest:
    avatar_id: str
    room_name: str
    max_duration_s: int
    idle_timeout_s: int


class AvatarSession(Protocol):
    session_id: str

    async def send_audio(self, chunk: AudioChunk) -> None:
        """TTS sesini gönderir; sağlayıcı odaya dudak senkronlu video basar."""
        ...

    async def interrupt(self) -> None:
        """Sırada bekleyen sesi hemen atar (kullanıcı söz kesti / barge-in)."""
        ...

    async def close(self) -> None:
        """İdempotent; oturumun ücretlendirmesini bitirir."""
        ...


class AvatarProvider(Protocol):
    name: str

    async def start_session(self, request: AvatarSessionRequest) -> AvatarSession: ...


# --- embedding'ler (metni anlam vektörüne çevirme) ------------------------------

EmbeddingPurpose = Literal["document", "query"]


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    async def embed(self, texts: Sequence[str], *, purpose: EmbeddingPurpose) -> list[list[float]]:
        """Her girdi metni için ``dimensions`` uzunluğunda bir vektör, girdiyle aynı sırada."""
        ...


# --- moderasyon (güvenlik sınıflandırması) --------------------------------------

ModerationCategory = Literal[
    "self_harm",
    "abuse",
    "medical_emergency",
    "sexual_real_person",
    "minor",
    "hate_violence",
    "fraud",
]
ModerationDirection = Literal["input", "output"]
CRISIS_CATEGORIES: frozenset[ModerationCategory] = frozenset(
    {"self_harm", "abuse", "medical_emergency"}
)


@dataclass(frozen=True, slots=True)
class ModerationResult:
    flagged: frozenset[ModerationCategory] = frozenset()

    @property
    def is_crisis(self) -> bool:
        return bool(self.flagged & CRISIS_CATEGORIES)


class ModerationProvider(Protocol):
    name: str

    async def classify(
        self, text: str, *, direction: ModerationDirection, language: str
    ) -> ModerationResult: ...


# --- mesajlaşma (e-posta / SMS) -------------------------------------------------

MessageChannel = Literal["email", "sms"]
# Yalnızca sabit, tanınır şablonlar (§8.3; oltalamaya karşı); serbest metin gönderilemez.
MessageTemplate = Literal[
    "signup_code",
    "login_code",
    "password_reset_code",
    "account_exists",
    "password_changed",
    "step_up_code",
    "legacy_key_delivery",
    "legacy_key_used",
]


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    channel: MessageChannel
    to: str
    template: MessageTemplate
    locale: str
    params: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MessageReceipt:
    provider: str
    message_id: str


class MessagingProvider(Protocol):
    name: str

    async def send(self, message: OutboundMessage) -> MessageReceipt: ...
