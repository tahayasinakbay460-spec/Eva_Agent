"""FastAPI application factory.

Run locally:  uv run uvicorn app.main:app --reload --port 8000
"""

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
from app.persona.compiler import PersonaCompiler
from app.providers.registry import ProviderRegistry, load_provider_config
from app.routers import auth, chat, health, personas
from app.services import persona_service
from app.services.chat_service import ChatService

log = logging.getLogger("eva")


async def seed_defaults(app: FastAPI) -> None:
    async with app.state.session_factory() as db:
        await persona_service.ensure_default_eva(db)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO if settings.is_dev else logging.WARNING)
    setup_telemetry(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await seed_defaults(app)
        log.info("eva api ready", extra={"env": settings.env, "version": __version__})
        yield
        await app.state.engine.dispose()

    app = FastAPI(
        title="EVA API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.is_dev else None,
        redoc_url=None,
    )

    engine = create_engine(settings.database_url)
    registry = ProviderRegistry(
        load_provider_config(settings.providers_config),
        llm_override=settings.llm_provider_override,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.rate_limiter = MemoryRateLimiter()
    app.state.registry = registry
    app.state.chat_service = ChatService(
        registry=registry, compiler=PersonaCompiler(), settings=settings
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(RequestContextMiddleware, hsts=not settings.is_dev)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(personas.router)
    app.include_router(chat.router)
    return app


app = create_app()
