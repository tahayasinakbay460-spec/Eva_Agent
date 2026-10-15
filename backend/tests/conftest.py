"""Shared fixtures: an app on a temp SQLite file with the mock LLM provider."""

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.database import Base
from app.main import create_app, seed_defaults

AppFactory = Callable[..., "AsyncIterator[FastAPI]"]


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "env": "test",
        "database_url": f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        "llm_provider_override": "mock",
        "cors_origins": ["http://localhost:3000"],
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


async def build_app(settings: Settings) -> FastAPI:
    app = create_app(settings)
    async with app.state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_defaults(app)
    return app


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    application = await build_app(make_settings(tmp_path))
    yield application
    await application.state.engine.dispose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def login(client: httpx.AsyncClient, handle: str = "taha") -> dict[str, str]:
    r = await client.post(
        "/auth/dev-login", json={"handle": handle, "display_name": handle.title()}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    return await login(client)


def parse_sse(raw: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for chunk in raw.strip().split("\n\n"):
        name, data = "", "{}"
        for line in chunk.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
        events.append((name, json.loads(data)))
    return events
