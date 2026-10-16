"""Provider-neutral interfaces and value types.

Every adapter (mock, anthropic, self-hosted, ...) speaks only these types.
"""

from collections.abc import AsyncIterable, AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

Effort = Literal["low", "medium", "high", "xhigh", "max"]
StopReason = Literal["end_turn", "max_tokens", "refusal"]


@dataclass(frozen=True, slots=True)
class SystemBlock:
    """One segment of the system prompt. ``cacheable`` marks a stable prefix boundary."""

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
    """Raised by adapters for upstream failures. ``retryable`` guides the caller."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(Protocol):
    name: str

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        """Yield ``TextDelta`` items as they are produced, then exactly one ``StreamEnd``."""
        ...


# --- audio ----------------------------------------------------------------------

AudioEncoding = Literal["pcm_s16le"]


@dataclass(frozen=True, slots=True)
class AudioFormat:
    """Raw audio shape on the realtime path (docs/contracts will pin the defaults)."""

    encoding: AudioEncoding = "pcm_s16le"
    sample_rate: int = 16_000
    channels: int = 1


@dataclass(frozen=True, slots=True)
class AudioChunk:
    data: bytes
    format: AudioFormat = AudioFormat()


# --- speech to text -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PartialTranscript:
    """Interim hypothesis; may be revised by later events."""

    text: str


@dataclass(frozen=True, slots=True)
class FinalTranscript:
    """Stable text for a segment. ``end_of_turn`` means the user finished speaking."""

    text: str
    end_of_turn: bool


TranscriptEvent = PartialTranscript | FinalTranscript


class STTProvider(Protocol):
    name: str

    def transcribe(
        self, audio: AsyncIterable[AudioChunk], *, language: str
    ) -> AsyncIterator[TranscriptEvent]:
        """Consume audio as it arrives; yield partials, then finals as segments settle."""
        ...


# --- text to speech -------------------------------------------------------------


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
        """Consume text fragments (sentence chunks) and yield audio as soon as it exists.

        Cancelling the consuming task must stop synthesis (barge-in, §4.3).
        """
        ...


# --- enrollment (consented voice / face clones) -----------------------------------


@dataclass(frozen=True, slots=True)
class EnrollmentSample:
    """One consented raw sample, read from our own storage (§4.2 "assets are ours")."""

    data: bytes
    media_type: str


@dataclass(frozen=True, slots=True)
class ProviderAssetRef:
    """The provider-side id of a clone; stored only as a mapping in ``provider_assets``."""

    provider: str
    asset_id: str


class VoiceEnrollmentProvider(Protocol):
    name: str

    async def create_voice(
        self, samples: Sequence[EnrollmentSample], *, label: str
    ) -> ProviderAssetRef: ...

    async def delete_voice(self, asset_id: str) -> None:
        """Idempotent: deleting an unknown or already-deleted voice is not an error."""
        ...


class AvatarEnrollmentProvider(Protocol):
    name: str

    async def create_avatar(
        self, samples: Sequence[EnrollmentSample], *, label: str
    ) -> ProviderAssetRef: ...

    async def delete_avatar(self, asset_id: str) -> None:
        """Idempotent, like ``delete_voice``."""
        ...


# --- realtime avatar --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AvatarSessionRequest:
    avatar_id: str
    room_name: str
    max_duration_s: int
    idle_timeout_s: int


class AvatarSession(Protocol):
    session_id: str

    async def send_audio(self, chunk: AudioChunk) -> None:
        """Feed TTS audio; the provider renders lip-synced video into the room."""
        ...

    async def interrupt(self) -> None:
        """Drop queued audio immediately (barge-in)."""
        ...

    async def close(self) -> None:
        """Idempotent; ends billing for the session."""
        ...


class AvatarProvider(Protocol):
    name: str

    async def start_session(self, request: AvatarSessionRequest) -> AvatarSession: ...


# --- embeddings -----------------------------------------------------------------

EmbeddingPurpose = Literal["document", "query"]


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    async def embed(self, texts: Sequence[str], *, purpose: EmbeddingPurpose) -> list[list[float]]:
        """One vector of length ``dimensions`` per input text, in input order."""
        ...


# --- moderation -----------------------------------------------------------------

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


# --- messaging (email / SMS) ----------------------------------------------------

MessageChannel = Literal["email", "sms"]
# Fixed, recognisable templates only (§8.3); free-form bodies are not allowed.
MessageTemplate = Literal[
    "signup_code",
    "login_code",
    "password_reset_code",
    "account_exists",
    "password_changed",
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
