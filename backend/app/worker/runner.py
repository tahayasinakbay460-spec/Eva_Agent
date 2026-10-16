"""İşçi döngüsü: sıradan iş al, ilgili fonksiyonu çalıştır, sonucu yaz (ADR 0003).

Her iş kendi veritabanı oturumunda çalışır; biri patlarsa diğerlerini etkilemez.
Loglara sadece iş türü, sonuç ve süre yazılır; içerik yazılmaz (§2.6).
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.providers.registry import ProviderRegistry
from app.worker import queue

log = logging.getLogger("eva.worker")


@dataclass(frozen=True, slots=True)
class WorkerContext:
    session_factory: async_sessionmaker[AsyncSession]
    registry: ProviderRegistry
    settings: Settings


Handler = Callable[[WorkerContext, dict[str, Any]], Awaitable[None]]
_HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    """``@handler("embed_memory")`` ile bir fonksiyonu o iş türünün işleyicisi yapar."""

    def register(fn: Handler) -> Handler:
        _HANDLERS[kind] = fn
        return fn

    return register


async def run_once(ctx: WorkerContext) -> bool:
    """Sıradan tek bir iş yapar. İş yoksa ``False`` döner."""
    async with ctx.session_factory() as db:
        job = await queue.claim(db)
    if job is None:
        return False

    started = time.perf_counter()
    fn = _HANDLERS.get(job.kind)
    try:
        if fn is None:
            raise LookupError(f"no handler for job kind {job.kind!r}")
        await fn(ctx, job.payload)
    except Exception as exc:  # her hata yakalanıp kuyruğa yazılır, işçi durmaz
        async with ctx.session_factory() as db:
            await queue.fail(db, job, exc)
        log.warning(
            "job_failed",
            extra={"job_kind": job.kind, "attempt": job.attempts, "error": type(exc).__name__},
        )
        return True
    async with ctx.session_factory() as db:
        await queue.complete(db, job.id)
    log.info(
        "job_done",
        extra={"job_kind": job.kind, "ms": round((time.perf_counter() - started) * 1000, 1)},
    )
    return True


async def drain(ctx: WorkerContext, *, limit: int = 1000) -> int:
    """Zamanı gelmiş bütün işleri bitirir (testler ve tek seferlik çalıştırma için)."""
    done = 0
    while done < limit and await run_once(ctx):
        done += 1
    return done


async def run_forever(ctx: WorkerContext, stop: asyncio.Event, *, poll_s: float = 1.0) -> None:
    """İş varsa hemen yapar, yoksa ``poll_s`` saniye bekleyip tekrar bakar."""
    log.info("worker started")
    while not stop.is_set():
        try:
            busy = await run_once(ctx)
        except Exception:  # kuyruğa ulaşılamadı: bekle ve tekrar dene
            log.exception("worker loop error")
            busy = False
        if not busy:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=poll_s)
    log.info("worker stopped")
