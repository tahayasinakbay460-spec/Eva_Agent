"""``LLMProvider`` için OpenAI (GPT) adaptörü — Responses API, akışlı (ADR 0004).

``OPENAI_API_KEY``'i SDK ortamdan kendisi okur. Önemli ayrıntılar (güncel dokümana göre,
2026-10-16):

- ``store=False`` her zaman gönderilir; gönderilmezse OpenAI cevabı en az 30 gün saklar.
- Sistem blokları tek bir ``instructions`` metnine birleştirilir: sabit baş kısım önde
  durduğu için OpenAI'nin otomatik prompt cache'i onu tekrar kullanabilir (§4.3).
- Kullanıcı kimliği OpenAI'ye gitmez; istenirse yalnızca tek yönlü özeti
  (``safety_identifier``) gönderilir.
- Hatalar akışın ortasında olay olarak da gelebilir (``response.failed`` / ``error``).
"""

from collections.abc import AsyncIterator
from typing import Any

import openai

from app.providers.base import (
    LLMEvent,
    LLMRequest,
    ProviderError,
    StopReason,
    StreamEnd,
    TextDelta,
)

# 429 gelse bile tekrar denemenin anlamsız olduğu durumlar: kota / bütçe bitti.
_NON_RETRYABLE_429 = frozenset(
    {
        "insufficient_quota",
        "credit_balance_exhausted",
        "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
    }
)


class OpenAILLMProvider:
    name = "openai"

    def __init__(self, *, timeout_s: float = 60.0, client: Any | None = None) -> None:
        self._timeout_s = timeout_s
        self._client = client

    def _get_client(self) -> Any:
        # İstemci ilk kullanımda kurulur: anahtar yokken (mock ile çalışırken) uygulama açılabilsin.
        if self._client is None:
            self._client = openai.AsyncOpenAI(timeout=self._timeout_s, max_retries=1)
        return self._client

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        instructions = "\n\n".join(block.text for block in request.system)
        params: dict[str, Any] = {
            "model": request.model,
            "instructions": instructions,
            "input": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_output_tokens": request.max_tokens,
            "store": False,
            "stream": True,
        }
        if request.effort:
            params["reasoning"] = {"effort": request.effort}

        stop: StopReason = "end_turn"
        refused = False
        usage: Any = None
        try:
            stream = await self._get_client().responses.create(**params)
            async for event in stream:
                kind = getattr(event, "type", "")
                if kind == "response.output_text.delta":
                    if event.delta:
                        yield TextDelta(event.delta)
                elif kind == "response.refusal.delta":
                    refused = True
                elif kind == "response.completed":
                    usage = event.response.usage
                elif kind == "response.incomplete":
                    usage = event.response.usage
                    details = event.response.incomplete_details
                    reason = getattr(details, "reason", None)
                    stop = "refusal" if reason == "content_filter" else "max_tokens"
                elif kind == "response.failed":
                    raise ProviderError("response failed", retryable=True)
                elif kind == "error":
                    raise ProviderError("stream error", retryable=False)
        except openai.RateLimitError as exc:
            code = _error_code(exc)
            raise ProviderError("rate limited", retryable=code not in _NON_RETRYABLE_429) from exc
        except openai.APIConnectionError as exc:  # zaman aşımı da bunun alt türü
            raise ProviderError("connection error", retryable=True) from exc
        except openai.APIStatusError as exc:
            raise ProviderError(
                f"upstream status {exc.status_code}", retryable=exc.status_code >= 500
            ) from exc

        if refused:
            stop = "refusal"
        details_in = getattr(usage, "input_tokens_details", None)
        yield StreamEnd(
            stop_reason=stop,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_tokens=int(getattr(details_in, "cached_tokens", 0) or 0),
        )


def _error_code(exc: openai.APIStatusError) -> str:
    """429 gövdesindeki hata kodu (``code`` ya da ``type``); bulunamazsa boş metin."""
    for attr in ("code", "type"):
        value = getattr(exc, attr, None)
        if isinstance(value, str) and value:
            if value in _NON_RETRYABLE_429:
                return value
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            for key in ("code", "type"):
                value = error.get(key)
                if isinstance(value, str) and value in _NON_RETRYABLE_429:
                    return value
    return ""
