from pathlib import Path

import httpx

from tests.conftest import build_app, login, make_settings


async def test_health_is_public(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-request-id"]


async def test_protected_routes_require_token(client: httpx.AsyncClient) -> None:
    for path in ("/auth/me", "/personas", "/chat/conversations"):
        r = await client.get(path)
        assert r.status_code == 401, path
    r = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


async def test_dev_login_then_me(client: httpx.AsyncClient) -> None:
    headers = await login(client, "ayse")
    r = await client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["handle"] == "ayse"


async def test_logout_revokes_token(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.post("/auth/logout", headers=auth_headers)
    assert r.status_code == 204
    r = await client.get("/auth/me", headers=auth_headers)
    assert r.status_code == 401


async def test_dev_login_rejects_bad_handle(client: httpx.AsyncClient) -> None:
    r = await client.post("/auth/dev-login", json={"handle": "Bad Handle!", "display_name": "x"})
    assert r.status_code == 422


async def test_dev_login_disabled_outside_dev(tmp_path: Path) -> None:
    app = await build_app(make_settings(tmp_path, env="prod"))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post("/auth/dev-login", json={"handle": "x1", "display_name": "x"})
            assert r.status_code == 404
            r = await c.get("/docs")
            assert r.status_code == 404
    finally:
        await app.state.engine.dispose()


async def test_auth_rate_limit(tmp_path: Path) -> None:
    app = await build_app(make_settings(tmp_path, rate_limit_auth_per_minute=2))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            body = {"handle": "rl", "display_name": "RL"}
            assert (await c.post("/auth/dev-login", json=body)).status_code == 200
            assert (await c.post("/auth/dev-login", json=body)).status_code == 200
            r = await c.post("/auth/dev-login", json=body)
            assert r.status_code == 429
            assert r.headers["retry-after"] == "60"
    finally:
        await app.state.engine.dispose()
