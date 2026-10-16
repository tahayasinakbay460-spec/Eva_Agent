"""``LLMProvider`` için Anthropic Claude adaptörü.

``ANTHROPIC_API_KEY``'i SDK ortamdan kendisi okur. Sabit sistem bloklarına ``cache_control``
eklenir; böylece persona'nın baş kısmı prompt cache'ten (önbellekten) gelir (§4.3).
Sunucu tarafı yedek model (fallback) açıktır: model güvenlik nedeniyle cevap vermeyi
reddederse, boş cevap dönmek yerine aynı istek içinde yedek bir modelle tekrar denenir.
"""

from collections.abc import AsyncIterator

import anthropic
from anthropic.types.beta import BetaMessageParam, BetaTextBlockParam

from app.providers.base import (
    LLMEvent,
    LLMRequest,
    ProviderError,
    StopReason,
    StreamEnd,
    TextDelta,
)

_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicLLMProvider:
    name = "anthropic"

    def __init__(self, *, timeout_s: float = 60.0, fallbacks: bool = True) -> None:
        self._client = anthropic.AsyncAnthropic(timeout=timeout_s, max_retries=1)
        self._fallbacks = fallbacks

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        system: list[BetaTextBlockParam] = []
        for block in request.system:
            param: BetaTextBlockParam = {"type": "text", "text": block.text}
            if block.cacheable:
                param["cache_control"] = {"type": "ephemeral"}
            system.append(param)
        messages: list[BetaMessageParam] = [
            {"role": m.role, "content": m.content} for m in request.messages
        ]

        try:
            async with self._client.beta.messages.stream(
                model=request.model,
                max_tokens=request.max_tokens,
                system=system,
                messages=messages,
                output_config={"effort": request.effort} if request.effort else anthropic.omit,
                betas=[_FALLBACK_BETA] if self._fallbacks else anthropic.omit,
                fallbacks="default" if self._fallbacks else anthropic.omit,
            ) as stream:
                async for text in stream.text_stream:
                    yield TextDelta(text)
                final = await stream.get_final_message()
        except anthropic.RateLimitError as exc:
            raise ProviderError("rate limited", retryable=True) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("connection error", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                f"upstream status {exc.status_code}", retryable=exc.status_code >= 500
            ) from exc

        stop: StopReason = "end_turn"
        if final.stop_reason == "max_tokens":
            stop = "max_tokens"
        elif final.stop_reason == "refusal":
            stop = "refusal"
        yield StreamEnd(
            stop_reason=stop,
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
            cache_read_tokens=final.usage.cache_read_input_tokens or 0,
        )
