"""Adım-yukarı doğrulama (§11.2): hassas işlemden önce kimliği yeniden doğrulama."""

from datetime import timedelta
from typing import Any

import httpx
from fastapi import Depends, FastAPI
from sqlalchemy import select

from app.core.security import require_step_up
from app.models.session import AuthSession
from tests.soft_authenticator import SoftAuthenticator
from tests.test_passkey import _bearer
from tests.test_passkey import _sign_up as passkey_sign_up
from tests.test_password_auth import PASSWORD, _last_code
from tests.test_password_auth import _sign_up as password_sign_up

FAILED = {"detail": "Verification failed"}


def _protect(app: FastAPI) -> None:
    """Testler için adım-yukarı isteyen küçük bir uç nokta."""

    @app.get("/_test/sensitive", dependencies=[Depends(require_step_up)])
    async def sensitive() -> dict[str, bool]:
        return {"ok": True}


async def _passkey_step_up(
    client: httpx.AsyncClient, headers: dict[str, str], device: SoftAuthenticator
) -> httpx.Response:
    r = await client.post("/auth/step-up/passkey/options", headers=headers)
    assert r.status_code == 200, r.text
    flow: dict[str, Any] = r.json()
    return await client.post(
        "/auth/step-up/passkey/verify",
        headers=headers,
        json={"flow_id": flow["flow_id"], "credential": device.get(flow["options"])},
    )


async def test_sensitive_endpoint_requires_fresh_step_up(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    _protect(app)
    device = SoftAuthenticator()
    headers = _bearer(await passkey_sign_up(client, device))

    r = await client.get("/_test/sensitive", headers=headers)
    assert r.status_code == 403
    assert r.json() == {"detail": "step_up_required"}

    status = (await client.get("/auth/step-up", headers=headers)).json()
    assert status == {"valid_until": None, "methods": ["passkey"]}

    r = await _passkey_step_up(client, headers, device)
    assert r.status_code == 200, r.text
    assert r.json()["valid_until"] is not None
    assert (await client.get("/_test/sensitive", headers=headers)).status_code == 200


async def test_step_up_expires(app: FastAPI, client: httpx.AsyncClient) -> None:
    _protect(app)
    device = SoftAuthenticator()
    headers = _bearer(await passkey_sign_up(client, device))
    assert (await _passkey_step_up(client, headers, device)).status_code == 200

    async with app.state.session_factory() as db:
        row = (await db.execute(select(AuthSession))).scalar_one()
        assert row.step_up_at is not None
        row.step_up_at -= timedelta(seconds=app.state.settings.step_up_ttl_s + 1)
        await db.commit()

    assert (await client.get("/_test/sensitive", headers=headers)).status_code == 403


async def test_step_up_is_per_session(app: FastAPI, client: httpx.AsyncClient) -> None:
    """Bir cihazda onay vermek, başka bir oturuma (ör. çalınmış token) yetki kazandırmaz."""
    _protect(app)
    device = SoftAuthenticator()
    first = _bearer(await passkey_sign_up(client, device))
    flow = (await client.post("/auth/passkey/login/options")).json()
    second = _bearer(
        await client.post(
            "/auth/passkey/login/verify",
            json={"flow_id": flow["flow_id"], "credential": device.get(flow["options"])},
        )
    )
    assert (await _passkey_step_up(client, first, device)).status_code == 200
    assert (await client.get("/_test/sensitive", headers=first)).status_code == 200
    assert (await client.get("/_test/sensitive", headers=second)).status_code == 403


async def test_another_users_passkey_cannot_step_up(client: httpx.AsyncClient) -> None:
    mine, theirs = SoftAuthenticator(), SoftAuthenticator()
    headers = _bearer(await passkey_sign_up(client, mine))
    await passkey_sign_up(client, theirs)

    flow = (await client.post("/auth/step-up/passkey/options", headers=headers)).json()
    assert len(flow["options"]["allowCredentials"]) == 1, "only this user's passkeys"
    r = await client.post(
        "/auth/step-up/passkey/verify",
        headers=headers,
        json={"flow_id": flow["flow_id"], "credential": theirs.get(flow["options"])},
    )
    assert r.status_code == 400
    assert r.json() == FAILED


async def test_step_up_flow_cannot_be_used_by_another_user(client: httpx.AsyncClient) -> None:
    alice_device, bob_device = SoftAuthenticator(), SoftAuthenticator()
    alice = _bearer(await passkey_sign_up(client, alice_device))
    bob = _bearer(await passkey_sign_up(client, bob_device))

    flow = (await client.post("/auth/step-up/passkey/options", headers=alice)).json()
    r = await client.post(
        "/auth/step-up/passkey/verify",
        headers=bob,
        json={"flow_id": flow["flow_id"], "credential": bob_device.get(flow["options"])},
    )
    assert r.status_code == 400


async def test_step_up_flow_is_single_use(client: httpx.AsyncClient) -> None:
    device = SoftAuthenticator()
    headers = _bearer(await passkey_sign_up(client, device))
    flow = (await client.post("/auth/step-up/passkey/options", headers=headers)).json()
    body = {"flow_id": flow["flow_id"], "credential": device.get(flow["options"])}
    first = await client.post("/auth/step-up/passkey/verify", headers=headers, json=body)
    again = await client.post("/auth/step-up/passkey/verify", headers=headers, json=body)
    assert first.status_code == 200
    assert again.status_code == 400


async def test_login_flow_cannot_be_used_for_step_up(client: httpx.AsyncClient) -> None:
    device = SoftAuthenticator()
    headers = _bearer(await passkey_sign_up(client, device))
    flow = (await client.post("/auth/passkey/login/options")).json()
    r = await client.post(
        "/auth/step-up/passkey/verify",
        headers=headers,
        json={"flow_id": flow["flow_id"], "credential": device.get(flow["options"])},
    )
    assert r.status_code == 400


async def test_password_step_up(app: FastAPI, client: httpx.AsyncClient) -> None:
    _protect(app)
    headers = _bearer(await password_sign_up(app, client))
    status = (await client.get("/auth/step-up", headers=headers)).json()
    assert status["methods"] == ["password"]

    wrong = await client.post(
        "/auth/step-up/password", headers=headers, json={"password": "yanlis-sifre-123"}
    )
    assert wrong.status_code == 400

    r = await client.post("/auth/step-up/password", headers=headers, json={"password": PASSWORD})
    assert r.status_code == 200, r.text
    flow_id = r.json()["flow_id"]
    code = _last_code(app)
    bad = await client.post(
        "/auth/step-up/password/verify",
        headers=headers,
        json={"flow_id": flow_id, "code": "000000" if code != "000000" else "111111"},
    )
    assert bad.status_code == 400
    assert (await client.get("/_test/sensitive", headers=headers)).status_code == 403

    ok = await client.post(
        "/auth/step-up/password/verify", headers=headers, json={"flow_id": flow_id, "code": code}
    )
    assert ok.status_code == 200, ok.text
    assert (await client.get("/_test/sensitive", headers=headers)).status_code == 200


async def test_password_step_up_code_is_bound_to_the_user(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    alice = _bearer(await password_sign_up(app, client))
    bob = _bearer(await password_sign_up(app, client, email="bob@example.com"))
    r = await client.post("/auth/step-up/password", headers=alice, json={"password": PASSWORD})
    flow_id = r.json()["flow_id"]
    code = _last_code(app)
    stolen = await client.post(
        "/auth/step-up/password/verify", headers=bob, json={"flow_id": flow_id, "code": code}
    )
    assert stolen.status_code == 400
    # Bob'un denemesi Alice'in akışını harcamadı.
    ok = await client.post(
        "/auth/step-up/password/verify", headers=alice, json={"flow_id": flow_id, "code": code}
    )
    assert ok.status_code == 200


async def test_step_up_requires_login(client: httpx.AsyncClient) -> None:
    assert (await client.get("/auth/step-up")).status_code == 401
    assert (await client.post("/auth/step-up/passkey/options")).status_code == 401
    r = await client.post("/auth/step-up/password", json={"password": "x"})
    assert r.status_code == 401


async def test_user_without_passkey_gets_generic_error(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.post("/auth/step-up/passkey/options", headers=auth_headers)
    assert r.status_code == 400
    assert r.json() == FAILED
