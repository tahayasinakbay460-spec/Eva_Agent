"""OpenAI adaptörü: ağa çıkmadan, sahte bir istemciyle (SDK'nın olay şekilleri taklit edilir)."""

from collections.abc import AsyncIterator
from types import SimpleNamespace as Ns
from typing import Any

import httpx
import openai
import pytest

from app.providers.base import ProviderError, StreamEnd, TextDelta
from app.providers.openai_llm import OpenAILLMProvider
from tests.test_providers import _request, assert_llm_contract


def _usage(inp: int = 10, out: int = 3, cached: int = 4) -> Ns:
    return Ns(
        input_tokens=inp,
        output_tokens=out,
        input_tokens_details=Ns(cached_tokens=cached),
    )


class FakeResponses:
    def __init__(self, events: list[Any] | Exception) -> None:
        self.events = events
        self.calls: list[dict[str, Any]] = []

    async def create(self, **params: Any) -> AsyncIterator[Any]:
        self.calls.append(params)
        if isinstance(self.events, Exception):
            raise self.events
        events = self.events

        async def gen() -> AsyncIterator[Any]:
            for e in events:
                yield e

        return gen()


def _provider(events: list[Any] | Exception) -> tuple[OpenAILLMProvider, FakeResponses]:
    responses = FakeResponses(events)
    return OpenAILLMProvider(client=Ns(responses=responses)), responses


def _delta(text: str) -> Ns:
    return Ns(type="response.output_text.delta", delta=text)


async def test_streams_text_and_usage() -> None:
    provider, _ = _provider(
        [
            Ns(type="response.created"),
            _delta("Mer"),
            _delta("haba"),
            Ns(type="response.completed", response=Ns(usage=_usage())),
        ]
    )
    text = await assert_llm_contract(provider)
    assert text == "Merhaba"
    events = [e async for e in provider.stream(_request())]
    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert (end.stop_reason, end.input_tokens, end.output_tokens, end.cache_read_tokens) == (
        "end_turn",
        10,
        3,
        4,
    )


async def test_request_never_stores_and_keeps_static_prefix_first() -> None:
    provider, responses = _provider([Ns(type="response.completed", response=Ns(usage=_usage()))])
    [e async for e in provider.stream(_request())]
    params = responses.calls[0]
    assert params["store"] is False, "OpenAI keeps responses for 30 days unless store=False"
    assert params["instructions"].startswith("rules"), "cacheable block comes first"
    assert params["input"] == [{"role": "user", "content": "merhaba"}]
    assert params["stream"] is True
    assert "reasoning" not in params
    assert "user" not in params, "no raw user identifiers go to the provider"


async def test_max_tokens_and_content_filter() -> None:
    incomplete = Ns(
        type="response.incomplete",
        response=Ns(usage=_usage(), incomplete_details=Ns(reason="max_output_tokens")),
    )
    provider, _ = _provider([_delta("a"), incomplete])
    events = [e async for e in provider.stream(_request())]
    assert isinstance(events[-1], StreamEnd) and events[-1].stop_reason == "max_tokens"

    filtered = Ns(
        type="response.incomplete",
        response=Ns(usage=_usage(), incomplete_details=Ns(reason="content_filter")),
    )
    provider, _ = _provider([filtered])
    events = [e async for e in provider.stream(_request())]
    assert isinstance(events[-1], StreamEnd) and events[-1].stop_reason == "refusal"


async def test_refusal() -> None:
    provider, _ = _provider(
        [
            Ns(type="response.refusal.delta", delta="Bunu yapamam"),
            Ns(type="response.completed", response=Ns(usage=_usage())),
        ]
    )
    events = [e async for e in provider.stream(_request())]
    assert not any(isinstance(e, TextDelta) for e in events), "refusal text is not shown as reply"
    assert isinstance(events[-1], StreamEnd) and events[-1].stop_reason == "refusal"


async def test_mid_stream_failure_raises() -> None:
    provider, _ = _provider([_delta("a"), Ns(type="response.failed", response=Ns())])
    with pytest.raises(ProviderError):
        [e async for e in provider.stream(_request())]


def _status_error(cls: type[openai.APIStatusError], status: int, code: str) -> Exception:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status, request=request)
    body = {"error": {"code": code, "type": code, "message": "x"}}
    return cls("x", response=response, body=body)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (_status_error(openai.RateLimitError, 429, "rate_limit_exceeded"), True),
        (_status_error(openai.RateLimitError, 429, "insufficient_quota"), False),
        (_status_error(openai.InternalServerError, 503, "server_is_overloaded"), True),
        (_status_error(openai.AuthenticationError, 401, "invalid_api_key"), False),
        (_status_error(openai.BadRequestError, 400, "invalid_value"), False),
    ],
)
async def test_error_retry_policy(error: Exception, retryable: bool) -> None:
    provider, _ = _provider(error)
    with pytest.raises(ProviderError) as info:
        [e async for e in provider.stream(_request())]
    assert info.value.retryable is retryable
