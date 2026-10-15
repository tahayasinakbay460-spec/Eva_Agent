"""Latency-budget instrumentation (CLAUDE.md §4.4).

Only numbers and identifiers are logged, never prompt or message content (§2.6).
OpenTelemetry export will plug in here; call sites stay the same.
"""

import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger("eva.telemetry")


@dataclass
class TurnTimer:
    """Measures one chat turn: time to first token and end-to-end."""

    started: float = field(default_factory=time.perf_counter)
    first_token_at: float | None = None

    def mark_first_token(self) -> None:
        if self.first_token_at is None:
            self.first_token_at = time.perf_counter()

    @property
    def ttft_ms(self) -> float | None:
        if self.first_token_at is None:
            return None
        return (self.first_token_at - self.started) * 1000

    @property
    def e2e_ms(self) -> float:
        return (time.perf_counter() - self.started) * 1000


def log_turn(
    *,
    timer: TurnTimer,
    provider: str,
    model: str,
    stop_reason: str,
    output_tokens: int,
    interrupted: bool,
) -> None:
    log.info(
        "chat_turn",
        extra={
            "llm_provider": provider,
            "llm_model": model,
            "llm_ttft_ms": round(timer.ttft_ms, 1) if timer.ttft_ms is not None else None,
            "e2e_ms": round(timer.e2e_ms, 1),
            "stop_reason": stop_reason,
            "output_tokens": output_tokens,
            "interrupted": interrupted,
        },
    )
