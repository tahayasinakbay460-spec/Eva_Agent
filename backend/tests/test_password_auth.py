"""Email + password sign-up/sign-in/reset with emailed codes (docs/threat-model.md §2)."""

import logging
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.models.user import User
from app.providers.mock import MockMessagingProvider
from app.services import password_auth_service
from tests.conftest import build_app, make_settings

EMAIL = "taha@example.com"
PASSWORD = "uzun-ve-guclu-sifre"
SIGN_UP = {
    "email": EMAIL,
    "password": PASSWORD,
    "display_name": "Taha",
    "age_confirmed": True,
    "ai_disclosure_accepted": True,
}
FAILED = {"detail": "Verification failed"}


def _outbox(app: FastAPI) -> MockMessagingProvider:
    provider = app.state.registry.messaging()
    assert isinstance(provider, MockMessagingProvider)
    return provider


def _last_code(app: FastAPI, email: str = EMAIL) -> str:
    for message in reversed(_outbox(app).outbox):
        if message.to == email and "code" in message.params:
            return message.params["code"]
    raise AssertionError(f"no code sent to {email}")


def _templates(app: FastAPI, email: str = EMAIL) -> list[str]:
    return [m.template for m in _outbox(app).outbox if m.to == email]


async def _user_count(app: FastAPI) -> int:
    async with app.state.session_factory() as db:
        return int((await db.execute(select(func.count()).select_from(User))).scalar_one())


async def _sign_up(app: FastAPI, client: httpx.AsyncClient, **override: Any) -> httpx.Response:
    body = {**SIGN_UP, **override}
    r = await client.post("/auth/password/register", json=body)
    assert r.status_code == 202, r.text
    return await client.post(
        "/auth/password/register/verify",
        json={"flow_id": r.json()["flow_id"], "code": _last_code(app, body["email"].lower())},
    )


async def _login(
    app: FastAPI, client: httpx.AsyncClient, email: str = EMAIL, password: str = PASSWORD
) -> httpx.Response:
    r = await client.post("/auth/password/login", json={"email": email, "password": password})
    if r.status_code != 200:
        return r
    return await client.post(
        "/auth/password/login/verify",
        json={"flow_id": r.json()["flow_id"], "code": _last_code(app, email.lower())},
    )


def _bearer(r: httpx.Response) -> dict[str, str]:
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --- happy paths ------------------------------------------------------------------


async def test_sign_up_creates_account_only_after_code(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    before = await _user_count(app)
    r = await client.post("/auth/password/register", json=SIGN_UP)
    assert r.status_code == 202
    assert r.json()["method"] == "email_code"
    assert await _user_count(app) == before, "no account before the email is proven"
    assert _templates(app) == ["signup_code"]

    r = await client.post(
        "/auth/password/register/verify",
        json={"flow_id": r.json()["flow_id"], "code": _last_code(app)},
    )
    assert r.status_code == 200, r.text
    me = (await client.get("/auth/me", headers=_bearer(r))).json()
    assert me["email"] == EMAIL and me["display_name"] == "Taha"


async def test_password_is_stored_as_argon2id(app: FastAPI, client: httpx.AsyncClient) -> None:
    assert (await _sign_up(app, client)).status_code == 200
    async with app.state.session_factory() as db:
        user = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one()
    assert user.password_hash is not None
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


async def test_login_needs_password_and_code(app: FastAPI, client: httpx.AsyncClient) -> None:
    assert (await _sign_up(app, client)).status_code == 200
    r = await client.post("/auth/password/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200
    assert "access_token" not in r.json(), "the password alone must not open a session"
    assert _templates(app)[-1] == "login_code"

    r = await client.post(
        "/auth/password/login/verify",
        json={"flow_id": r.json()["flow_id"], "code": _last_code(app)},
    )
    assert r.status_code == 200
    assert (await client.get("/auth/me", headers=_bearer(r))).status_code == 200


async def test_email_is_case_insensitive(app: FastAPI, client: httpx.AsyncClient) -> None:
    assert (await _sign_up(app, client, email="Taha@Example.COM")).status_code == 200
    assert (await _login(app, client, email="TAHA@example.com")).status_code == 200


# --- enumeration ------------------------------------------------------------------


async def test_wrong_password_and_unknown_email_look_the_same(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    assert (await _sign_up(app, client)).status_code == 200
    wrong = await client.post("/auth/password/login", json={"email": EMAIL, "password": "x" * 12})
    unknown = await client.post(
        "/auth/password/login", json={"email": "kimse@example.com", "password": PASSWORD}
    )
    assert wrong.status_code == unknown.status_code == 400
    assert wrong.json() == unknown.json() == FAILED


async def test_sign_up_with_taken_email_looks_successful(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    assert (await _sign_up(app, client)).status_code == 200
    users = await _user_count(app)
    r = await client.post("/auth/password/register", json={**SIGN_UP, "display_name": "Saldırgan"})
    assert r.status_code == 202 and set(r.json()) == {"flow_id", "method"}
    assert _templates(app)[-1] == "account_exists", "the owner is told, no code is sent"
    for guess in ("000000", "123456"):
        v = await client.post(
            "/auth/password/register/verify", json={"flow_id": r.json()["flow_id"], "code": guess}
        )
        assert v.json() == FAILED
    assert await _user_count(app) == users


async def test_reset_for_unknown_email_looks_successful(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    r = await client.post("/auth/password/reset", json={"email": "kimse@example.com"})
    assert r.status_code == 202 and set(r.json()) == {"flow_id", "method"}
    assert _templates(app, "kimse@example.com") == []


# --- code guessing / replay -------------------------------------------------------


async def test_code_attempts_are_capped(app: FastAPI, client: httpx.AsyncClient) -> None:
    assert (await _sign_up(app, client)).status_code == 200
    r = await client.post("/auth/password/login", json={"email": EMAIL, "password": PASSWORD})
    flow_id, code = r.json()["flow_id"], _last_code(app)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(password_auth_service.MAX_ATTEMPTS):
        v = await client.post(
            "/auth/password/login/verify", json={"flow_id": flow_id, "code": wrong}
        )
        assert v.json() == FAILED
    v = await client.post("/auth/password/login/verify", json={"flow_id": flow_id, "code": code})
    assert v.status_code == 400, "the right code must not work after the cap"


async def test_code_is_single_use(app: FastAPI, client: httpx.AsyncClient) -> None:
    assert (await _sign_up(app, client)).status_code == 200
    r = await client.post("/auth/password/login", json={"email": EMAIL, "password": PASSWORD})
    body = {"flow_id": r.json()["flow_id"], "code": _last_code(app)}
    assert (await client.post("/auth/password/login/verify", json=body)).status_code == 200
    assert (await client.post("/auth/password/login/verify", json=body)).json() == FAILED


async def test_new_code_invalidates_the_old_one(app: FastAPI, client: httpx.AsyncClient) -> None:
    assert (await _sign_up(app, client)).status_code == 200
    login = {"email": EMAIL, "password": PASSWORD}
    first = (await client.post("/auth/password/login", json=login)).json()["flow_id"]
    first_code = _last_code(app)
    assert (await client.post("/auth/password/login", json=login)).status_code == 200
    v = await client.post(
        "/auth/password/login/verify", json={"flow_id": first, "code": first_code}
    )
    assert v.json() == FAILED


async def test_expired_code_is_rejected(
    app: FastAPI, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(password_auth_service, "CODE_TTL", timedelta(0))
    r = await client.post("/auth/password/register", json=SIGN_UP)
    v = await client.post(
        "/auth/password/register/verify",
        json={"flow_id": r.json()["flow_id"], "code": _last_code(app)},
    )
    assert v.json() == FAILED


async def test_code_cannot_cross_flows(app: FastAPI, client: httpx.AsyncClient) -> None:
    assert (await _sign_up(app, client)).status_code == 200
    r = await client.post("/auth/password/login", json={"email": EMAIL, "password": PASSWORD})
    v = await client.post(
        "/auth/password/reset/verify",
        json={"flow_id": r.json()["flow_id"], "code": _last_code(app), "new_password": "y" * 12},
    )
    assert v.json() == FAILED


# --- password policy --------------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"password": "kisa"},
        {"password": "x" * 129},
        {"email": "not-an-email"},
        {"age_confirmed": False},
        {"ai_disclosure_accepted": False},
    ],
)
async def test_sign_up_validation(client: httpx.AsyncClient, override: dict[str, Any]) -> None:
    r = await client.post("/auth/password/register", json={**SIGN_UP, **override})
    assert r.status_code == 422


async def test_password_equal_to_email_is_weak(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/auth/password/register",
        json={**SIGN_UP, "email": "uzunadres@example.com", "password": "UzunAdres@example.com"},
    )
    assert r.status_code == 422 and r.json() == {"detail": "Weak password"}


# --- reset ------------------------------------------------------------------------


async def test_reset_changes_password_and_signs_out_everywhere(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    session = await _sign_up(app, client)
    old_headers = _bearer(session)
    r = await client.post("/auth/password/reset", json={"email": EMAIL})
    flow_id, code = r.json()["flow_id"], _last_code(app)

    weak = await client.post(
        "/auth/password/reset/verify",
        json={"flow_id": flow_id, "code": code, "new_password": EMAIL},
    )
    assert weak.json() == {"detail": "Weak password"}, "policy runs before the code is spent"

    new_password = "yepyeni-guclu-sifre"
    done = await client.post(
        "/auth/password/reset/verify",
        json={"flow_id": flow_id, "code": code, "new_password": new_password},
    )
    assert done.status_code == 204
    assert (await client.get("/auth/me", headers=old_headers)).status_code == 401
    assert _templates(app)[-1] == "password_changed"
    assert (await _login(app, client)).status_code == 400, "old password is dead"
    assert (await _login(app, client, password=new_password)).status_code == 200


# --- abuse ------------------------------------------------------------------------


async def test_mail_bombing_is_capped_per_email(app: FastAPI, client: httpx.AsyncClient) -> None:
    for _ in range(password_auth_service.MAIL_LIMIT + 2):
        r = await client.post("/auth/password/reset", json={"email": "kurban@example.com"})
        assert r.status_code == 202
    await client.post("/auth/password/register", json={**SIGN_UP, "email": "kurban@example.com"})
    assert len(_templates(app, "kurban@example.com")) <= password_auth_service.MAIL_LIMIT


async def test_password_and_code_never_reach_logs(
    app: FastAPI, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    assert (await _sign_up(app, client)).status_code == 200
    r = await client.post("/auth/password/login", json={"email": EMAIL, "password": PASSWORD})
    code = _last_code(app)
    await client.post(
        "/auth/password/login/verify", json={"flow_id": r.json()["flow_id"], "code": code}
    )
    assert PASSWORD not in caplog.text
    assert not re.search(rf"\b{code}\b", caplog.text)


async def test_production_refuses_dev_mailbox(tmp_path: Path) -> None:
    app = await build_app(make_settings(tmp_path, env="prod", messaging_provider_override=None))
    try:
        with pytest.raises(RuntimeError, match="real messaging provider"):
            async with app.router.lifespan_context(app):
                pass
    finally:
        await app.state.engine.dispose()
