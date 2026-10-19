"""FastAPI uygulamasını kuran fabrika (create_app).

Lokalde çalıştırmak için:  uv run uvicorn app.main:app --reload --port 8000
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.config import Settings, get_settings
from app.core.middleware import RequestContextMiddleware
from app.core.ratelimit import MemoryRateLimiter
from app.core.telemetry import setup_telemetry
from app.database import create_engine, create_session_factory
from app.legacy.keys import LegacyConfigError, load_pepper
from app.persona.compiler import PersonaCompiler
from app.providers.registry import ProviderRegistry, build_registry
from app.routers import (
    admin,
    auth,
    biometrics,
    characters,
    chat,
    health,
    media,
    memories,
    personas,
    voice,
)
from app.services import persona_service
from app.services.chat_service import ChatService
from app.storage.factory import build_encrypted_store, check_storage
from app.worker import handlers  # noqa: F401 - iş işleyicilerini kaydeder
from app.worker.runner import WorkerContext, run_forever

log = logging.getLogger("eva")

# Gerçekte hiç e-posta/SMS göndermeyen adaptörler; staging/prod'da kabul edilmez.
DEV_ONLY_MESSAGING = frozenset({"mock", "dev_mailbox"})


async def seed_defaults(app: FastAPI) -> None:
    async with app.state.session_factory() as db:
        await persona_service.ensure_default_eva(db)


def check_production_providers(app: FastAPI) -> None:
    """Staging/prod, hiçbir şey teslim etmeyen sahte adaptörlerle açılmasın diye durdurur."""
    settings: Settings = app.state.settings
    registry: ProviderRegistry = app.state.registry
    if not settings.is_dev and registry.provider_name("messaging", "default") in DEV_ONLY_MESSAGING:
        raise RuntimeError("a real messaging provider is required outside dev/test")
    check_storage(app.state.store)
    if app.state.legacy_pepper is None:
        raise LegacyConfigError("EVA_LEGACY_KEY_PEPPER is required outside dev/test")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO if settings.is_dev else logging.WARNING)
    setup_telemetry(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        check_production_providers(app)
        await seed_defaults(app)
        stop = asyncio.Event()
        worker: asyncio.Task[None] | None = None
        if settings.run_worker_inprocess:
            # Geliştirmede ayrı terminal açmamak için işçi API'nin içinde de döner (ADR 0003).
            worker = asyncio.create_task(run_forever(app.state.worker_context, stop))
        log.info("eva api ready", extra={"env": settings.env, "version": __version__})
        yield
        stop.set()
        if worker is not None:
            await worker
        await app.state.engine.dispose()

    app = FastAPI(
        title="EVA API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.is_dev else None,
        redoc_url=None,
    )

    engine = create_engine(settings.database_url)
    registry = build_registry(settings)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.rate_limiter = MemoryRateLimiter()
    app.state.registry = registry
    app.state.store = build_encrypted_store(settings)
    # Miras anahtar özetlerinin biberi; gerçek ortamda yoksa uygulama açılışta durur (ADR 0010).
    try:
        app.state.legacy_pepper = load_pepper(
            configured=(
                settings.legacy_key_pepper.get_secret_value()
                if settings.legacy_key_pepper
                else None
            ),
            dev_file=settings.dev_legacy_pepper_file,
            is_dev=settings.is_dev,
        )
    except LegacyConfigError:
        app.state.legacy_pepper = None
    app.state.worker_context = WorkerContext(
        session_factory=app.state.session_factory,
        registry=registry,
        settings=settings,
        store=app.state.store,
    )
    app.state.chat_service = ChatService(
        registry=registry, compiler=PersonaCompiler(), settings=settings
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(RequestContextMiddleware, hsts=not settings.is_dev)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(personas.router)
    app.include_router(characters.router)
    app.include_router(chat.router)
    app.include_router(memories.router)
    app.include_router(voice.router)
    app.include_router(media.router)
    app.include_router(biometrics.router)
    app.include_router(admin.router)
    return app


app = create_app()
