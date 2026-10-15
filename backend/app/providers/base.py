"""Provider-neutral interfaces and value types.

Every adapter (mock, anthropic, self-hosted, ...) speaks only these types.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
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
