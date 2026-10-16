"""Gecikme bütçesi ölçümü ve hata raporlama (CLAUDE.md §3, §4.4).

Süreçten dışarı yalnızca sayılar ve kimlikler çıkar; prompt, mesaj ya da anı içeriği
asla çıkmaz (§2.6).

- Metrikler ve trace'ler (bir isteğin adım adım zaman çizelgesi) OpenTelemetry API'sinden
  geçer. Ölçüm araçları import anında oluşturulur ve kurulu olan sağlayıcıya bağlanır;
  hiçbiri kurulu değilse hiçbir şey yapmazlar. ``EVA_OTEL_ENABLED`` açıksa
  ``setup_telemetry`` OTLP dışa aktarıcılarını kurar; adres, başlıklar ve protokol
  standart ``OTEL_*`` ortam değişkenlerinden gelir.
- Sentry yalnızca ``EVA_SENTRY_DSN`` ayarlıysa açılır ve kişisel veri (PII) temizlenir.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from opentelemetry import metrics, trace
from opentelemetry.trace import Span, Status, StatusCode

from app import __version__
from app.core.config import Settings

log = logging.getLogger("eva.telemetry")

_meter = metrics.get_meter("eva.api", __version__)
_tracer = trace.get_tracer("eva.api", __version__)

LLM_TTFT = _meter.create_histogram(
    "eva.chat.llm_ttft", unit="ms", description="Send to first LLM token (text chat)"
)
E2E = _meter.create_histogram(
    "eva.chat.e2e", unit="ms", description="Send to last LLM token (text chat)"
)
TURNS = _meter.create_counter("eva.chat.turns", description="Text chat turns by outcome")
MEMORY_RETRIEVAL = _meter.create_histogram(
    "eva.memory.retrieval", unit="ms", description="Hot-path memory lookup per chat turn"
)


def record_memory_retrieval(elapsed_ms: float, *, candidates: int) -> None:
    """Sohbet sırasında anı aramanın süresi (§4.4 hedef: p50 < 20 ms). İçerik kaydedilmez."""
    MEMORY_RETRIEVAL.record(elapsed_ms, {"candidates_bucket": _bucket(candidates)})


def _bucket(n: int) -> str:
    # Tam sayı yerine aralık: metrik etiketleri az sayıda farklı değer almalı.
    for limit in (0, 10, 100, 1000):
        if n <= limit:
            return f"<={limit}"
    return ">1000"


TurnOutcome = Literal["ok", "interrupted", "provider_error"]


@dataclass
class TurnTimer:
    """Tek bir sohbet turunu ölçer: ilk token'a kadar geçen süre ve baştan sona süre.

    Turun span'ini (trace içindeki tek bir zaman dilimi) de o tutar. Span "geçerli span"
    yapılmadan başlatılır, çünkü tur, farklı bağlamlarda kaldığı yerden devam eden bir
    async generator içinde çalışır.
    """

    provider: str
    model: str
    started: float = field(default_factory=time.perf_counter)
    first_token_at: float | None = None
    span: Span = field(init=False)

    def __post_init__(self) -> None:
        self.span = _tracer.start_span(
            "chat.turn", attributes={"llm.provider": self.provider, "llm.model": self.model}
        )

    def mark_first_token(self) -> None:
        if self.first_token_at is None:
            self.first_token_at = time.perf_counter()
            self.span.add_event("first_token")

    @property
    def ttft_ms(self) -> float | None:
        if self.first_token_at is None:
            return None
        return (self.first_token_at - self.started) * 1000

    @property
    def e2e_ms(self) -> float:
        return (time.perf_counter() - self.started) * 1000


def record_turn(
    timer: TurnTimer,
    *,
    outcome: TurnOutcome,
    stop_reason: str | None = None,
    output_tokens: int = 0,
) -> None:
    attrs: dict[str, str] = {
        "llm.provider": timer.provider,
        "llm.model": timer.model,
        "outcome": outcome,
    }
    ttft = timer.ttft_ms
    e2e = timer.e2e_ms
    if ttft is not None:
        LLM_TTFT.record(ttft, attrs)
    if outcome == "ok":
        E2E.record(e2e, attrs)
    TURNS.add(1, attrs)

    span = timer.span
    span.set_attribute("outcome", outcome)
    span.set_attribute("llm.output_tokens", output_tokens)
    if stop_reason is not None:
        span.set_attribute("llm.stop_reason", stop_reason)
    if outcome == "provider_error":
        span.set_status(Status(StatusCode.ERROR, "provider_error"))
    span.end()

    log.info(
        "chat_turn",
        extra={
            "llm_provider": timer.provider,
            "llm_model": timer.model,
            "llm_ttft_ms": round(ttft, 1) if ttft is not None else None,
            "e2e_ms": round(e2e, 1),
            "outcome": outcome,
            "stop_reason": stop_reason,
            "output_tokens": output_tokens,
        },
    )


# --- kurulum --------------------------------------------------------------------


def setup_telemetry(settings: Settings) -> None:
    if settings.otel_enabled:
        _setup_otel(settings)
    if settings.sentry_dsn:
        _setup_sentry(settings)


def _setup_otel(settings: Settings) -> None:
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.name": "eva-api",
            "service.version": __version__,
            "deployment.environment": settings.env,
        }
    )
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(
        MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
        )
    )
    log.info("opentelemetry export enabled")


# İsteğin kişisel veri, token ya da mesaj içeriği taşıyabilecek kısımları.
_SCRUBBED_REQUEST_KEYS = ("data", "cookies", "query_string", "headers", "env")


def scrub_sentry_event(event: Any, hint: Any = None) -> Any:
    """``before_send`` kancası: kişisel veri ya da içerik taşıyabilecek her şeyi atar (§2.6)."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in _SCRUBBED_REQUEST_KEYS:
            request.pop(key, None)
    event.pop("user", None)
    event.pop("breadcrumbs", None)
    event.pop("extra", None)
    for exc in (event.get("exception") or {}).get("values", []):
        for frame in (exc.get("stacktrace") or {}).get("frames", []):
            frame.pop("vars", None)
    return event


def _setup_sentry(settings: Settings) -> None:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        release=f"eva-api@{__version__}",
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,  # trace'ler OpenTelemetry'den gider
        before_send=scrub_sentry_event,
        before_breadcrumb=lambda crumb, hint: None,
    )
    log.info("sentry enabled")
