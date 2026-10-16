"""Latency metrics and spans are recorded per chat turn, and never carry content (§2.6, §4.4)."""

from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import Counter, Histogram, MeterProvider
from opentelemetry.sdk.metrics.export import AggregationTemporality, InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.telemetry import scrub_sentry_event
from app.providers.base import LLMEvent, LLMRequest, ProviderError, TextDelta
from tests.conftest import parse_sse

SECRET_TEXT = "annemin kızlık soyadı Yıldız"

# The global OTel providers can be installed once per process; the app's instruments
# were created against the API proxies and bind to these on installation.
# Delta temporality: each collect() returns only what was recorded since the last one.
_metric_reader = InMemoryMetricReader(
    preferred_temporality={
        Counter: AggregationTemporality.DELTA,
        Histogram: AggregationTemporality.DELTA,
    }
)
_span_exporter = InMemorySpanExporter()
_tracer_provider = TracerProvider()
_tracer_provider.add_span_processor(SimpleSpanProcessor(_span_exporter))
trace.set_tracer_provider(_tracer_provider)
metrics.set_meter_provider(MeterProvider(metric_readers=[_metric_reader]))


@pytest.fixture(autouse=True)
def _reset_exporters() -> Iterator[None]:
    _span_exporter.clear()
    _collect()  # drain anything recorded by earlier tests
    yield


def _collect() -> dict[str, list[Any]]:
    """Data points recorded since the previous collect, keyed by metric name."""
    points: dict[str, list[Any]] = {}
    data = _metric_reader.get_metrics_data()
    if data is None:
        return points
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                points.setdefault(metric.name, []).extend(metric.data.data_points)
    return points


def _turn_spans() -> list[ReadableSpan]:
    return [s for s in _span_exporter.get_finished_spans() if s.name == "chat.turn"]


async def _chat(client: httpx.AsyncClient, headers: dict[str, str], key: str) -> list[Any]:
    conv = await client.post("/chat/conversations", json={}, headers=headers)
    r = await client.post(
        f"/chat/conversations/{conv.json()['id']}/messages",
        json={"content": SECRET_TEXT, "idempotency_key": key},
        headers=headers,
    )
    return parse_sse(r.text)


async def test_successful_turn_records_latency_and_span(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    events = await _chat(client, auth_headers, "telemetry-ok-1")
    assert events[-1][0] == "done"

    points = _collect()
    turns = points["eva.chat.turns"]
    assert [dict(p.attributes) for p in turns] == [
        {"llm.provider": "mock", "llm.model": "claude-sonnet-5-5", "outcome": "ok"}
    ]
    assert turns[0].value == 1
    for name in ("eva.chat.llm_ttft", "eva.chat.e2e"):
        (point,) = points[name]
        assert point.count == 1 and point.sum >= 0

    (span,) = _turn_spans()
    assert span.attributes is not None
    assert span.attributes["outcome"] == "ok"
    assert span.attributes["llm.stop_reason"] == "end_turn"
    assert [e.name for e in span.events] == ["first_token"]


class _FailingProvider:
    name = "failing"

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        yield TextDelta("yarım ")
        raise ProviderError("boom", retryable=True)


async def test_provider_error_is_counted_and_marks_span(
    app: FastAPI, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    app.state.registry.register_llm("mock", _FailingProvider())
    events = await _chat(client, auth_headers, "telemetry-err-1")
    assert events[-1][0] == "error"

    points = _collect()
    (turn,) = points["eva.chat.turns"]
    assert turn.attributes["outcome"] == "provider_error"
    assert "eva.chat.e2e" not in points, "failed turns must not skew the e2e budget"
    (span,) = _turn_spans()
    assert not span.status.is_ok


async def test_no_content_in_metrics_or_spans(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _chat(client, auth_headers, "telemetry-pii-1")
    exported = repr(_collect()) + repr(
        [(s.attributes, s.events) for s in _span_exporter.get_finished_spans()]
    )
    assert "Yıldız" not in exported
    assert "Taha" not in exported


def test_sentry_scrubber_drops_pii_and_content() -> None:
    event: dict[str, Any] = {
        "message": "boom",
        "user": {"email": "x@example.com"},
        "request": {
            "url": "https://api/chat",
            "method": "POST",
            "data": {"content": SECRET_TEXT},
            "headers": {"Authorization": "Bearer abc"},
            "cookies": {"s": "1"},
            "query_string": "q=1",
        },
        "breadcrumbs": {"values": [{"message": SECRET_TEXT}]},
        "extra": {"prompt": SECRET_TEXT},
        "exception": {
            "values": [{"stacktrace": {"frames": [{"function": "f", "vars": {"x": SECRET_TEXT}}]}}]
        },
    }
    scrubbed = scrub_sentry_event(event)
    assert scrubbed["request"] == {"url": "https://api/chat", "method": "POST"}
    assert SECRET_TEXT not in repr(scrubbed)
    assert "Bearer" not in repr(scrubbed)
    assert "user" not in scrubbed
    assert scrubbed["exception"]["values"][0]["stacktrace"]["frames"] == [{"function": "f"}]
