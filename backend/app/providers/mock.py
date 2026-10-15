"""Zero-cost, network-free LLM adapter used by tests and offline development."""

import asyncio
from collections.abc import AsyncIterator

from app.providers.base import LLMEvent, LLMRequest, StreamEnd, TextDelta


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
