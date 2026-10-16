"""Passkey sign-up and sign-in, including every threat in docs/threat-model.md §1."""

from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.conftest import build_app, make_settings
from tests.soft_authenticator import SoftAuthenticator, b64url

SIGN_UP = {
    "display_name": "Taha Yasin",
    "age_confirmed": True,
    "ai_disclosure_accepted": True,
}
FAILED = {"detail": "Verification failed"}


async def _register_options(client: httpx.AsyncClient) -> dict[str, Any]:
    r = await client.post("/auth/passkey/register/options", json=SIGN_UP)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


async def _sign_up(client: httpx.AsyncClient, device: SoftAuthenticator) -> httpx.Response:
    flow = await _register_options(client)
    return await client.post(
        "/auth/passkey/register/verify",
        json={"flow_id": flow["flow_id"], "credential": device.create(flow["options"])},
    )


async def _login(
    client: httpx.AsyncClient, device: SoftAuthenticator, **get_kwargs: Any
) -> httpx.Response:
    r = await client.post("/auth/passkey/login/options")
    assert r.status_code == 200, r.text
    flow = r.json()
    return await client.post(
        "/auth/passkey/login/verify",
        json={"flow_id": flow["flow_id"], "credential": device.get(flow["options"], **get_kwargs)},
    )


def _bearer(r: httpx.Response) -> dict[str, str]:
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --- happy paths ------------------------------------------------------------------


async def test_sign_up_creates_account_and_session(client: httpx.AsyncClient) -> None:
    r = await _sign_up(client, SoftAuthenticator())
    assert r.status_code == 200, r.text
    me = await client.get("/auth/me", headers=_bearer(r))
    assert me.status_code == 200
    assert me.json()["display_name"] == "Taha Yasin"
    assert me.json()["handle"].startswith("u_"), "internal handle, not the display name"


async def test_registration_options_demand_resident_key_and_uv(
    client: httpx.AsyncClient,
) -> None:
    options = (await _register_options(client))["options"]
    assert options["rp"]["id"] == "localhost"
    selection = options["authenticatorSelection"]
    assert selection["residentKey"] == "required"
    assert selection["userVerification"] == "required"
    assert len(options["user"]["id"]) >= 40, "random 32-byte user handle"


async def test_login_with_registered_passkey(client: httpx.AsyncClient) -> None:
    device = SoftAuthenticator()
    signed_up = await _sign_up(client, device)
    r = await _login(client, device)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == signed_up.json()["user"]["id"]
    assert r.json()["access_token"] != signed_up.json()["access_token"]
    assert (await client.get("/auth/me", headers=_bearer(r))).status_code == 200


async def test_login_options_do_not_ask_for_username(client: httpx.AsyncClient) -> None:
    options = (await client.post("/auth/passkey/login/options")).json()["options"]
    assert options.get("allowCredentials", []) == []
    assert options["userVerification"] == "required"


# --- sign-up form (§7, §12) -------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"age_confirmed": False},
        {"ai_disclosure_accepted": False},
        {"age_confirmed": None},
        {"display_name": ""},
        {"display_name": "x" * 81},
        {"locale": "de"},
    ],
)
async def test_sign_up_requires_declarations_and_valid_form(
    client: httpx.AsyncClient, override: dict[str, Any]
) -> None:
    body = {**SIGN_UP, **override}
    body = {k: v for k, v in body.items() if v is not None}
    r = await client.post("/auth/passkey/register/options", json=body)
    assert r.status_code == 422


# --- threat model: spoofing / replay ----------------------------------------------


async def test_flow_cannot_be_reused(client: httpx.AsyncClient) -> None:
    device = SoftAuthenticator()
    flow = await _register_options(client)
    payload = {"flow_id": flow["flow_id"], "credential": device.create(flow["options"])}
    assert (await client.post("/auth/passkey/register/verify", json=payload)).status_code == 200
    r = await client.post("/auth/passkey/register/verify", json=payload)
    assert r.status_code == 400 and r.json() == FAILED


async def test_expired_flow_is_rejected(tmp_path: Path) -> None:
    app = await build_app(make_settings(tmp_path, auth_challenge_ttl_s=0))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await _sign_up(c, SoftAuthenticator())
            assert r.status_code == 400 and r.json() == FAILED
    finally:
        await app.state.engine.dispose()


async def test_phishing_origin_is_rejected(client: httpx.AsyncClient) -> None:
    r = await _sign_up(client, SoftAuthenticator(origin="https://eva-login.example"))
    assert r.status_code == 400 and r.json() == FAILED

    device = SoftAuthenticator()
    assert (await _sign_up(client, device)).status_code == 200
    device.origin = "https://eva-login.example"
    r = await _login(client, device)
    assert r.status_code == 400 and r.json() == FAILED


async def test_wrong_rp_id_is_rejected(client: httpx.AsyncClient) -> None:
    r = await _sign_up(client, SoftAuthenticator(rp_id="evil.example"))
    assert r.status_code == 400 and r.json() == FAILED


async def test_user_verification_is_required(client: httpx.AsyncClient) -> None:
    r = await _sign_up(client, SoftAuthenticator(user_verified=False))
    assert r.status_code == 400 and r.json() == FAILED

    device = SoftAuthenticator()
    assert (await _sign_up(client, device)).status_code == 200
    device.user_verified = False
    r = await _login(client, device)
    assert r.status_code == 400 and r.json() == FAILED


async def test_login_flow_cannot_finish_a_registration(client: httpx.AsyncClient) -> None:
    flow = (await client.post("/auth/passkey/login/options")).json()
    fake_create_options = {"challenge": flow["options"]["challenge"], "user": {"id": b64url(b"x")}}
    r = await client.post(
        "/auth/passkey/register/verify",
        json={
            "flow_id": flow["flow_id"],
            "credential": SoftAuthenticator().create(fake_create_options),
        },
    )
    assert r.status_code == 400 and r.json() == FAILED


async def test_unknown_passkey_gets_the_same_error(client: httpx.AsyncClient) -> None:
    stranger = SoftAuthenticator()
    stranger.user_handle = b"\x01" * 32
    r = await _login(client, stranger)
    assert r.status_code == 400 and r.json() == FAILED


async def test_cloned_authenticator_is_rejected(client: httpx.AsyncClient) -> None:
    device = SoftAuthenticator()
    assert (await _sign_up(client, device)).status_code == 200
    assert (await _login(client, device)).status_code == 200  # counter 1
    assert (await _login(client, device)).status_code == 200  # counter 2
    r = await _login(client, device, advance_counter=False)  # counter stays 2: a clone
    assert r.status_code == 400 and r.json() == FAILED


async def test_tampered_signature_is_rejected(client: httpx.AsyncClient) -> None:
    device = SoftAuthenticator()
    assert (await _sign_up(client, device)).status_code == 200
    flow = (await client.post("/auth/passkey/login/options")).json()
    credential = device.get(flow["options"])
    credential["response"]["signature"] = b64url(b"\x30\x06\x02\x01\x01\x02\x01\x01")
    r = await client.post(
        "/auth/passkey/login/verify", json={"flow_id": flow["flow_id"], "credential": credential}
    )
    assert r.status_code == 400 and r.json() == FAILED


async def test_passkey_of_another_user_cannot_claim_a_handle(client: httpx.AsyncClient) -> None:
    alice, bob = SoftAuthenticator(), SoftAuthenticator()
    assert (await _sign_up(client, alice)).status_code == 200
    assert (await _sign_up(client, bob)).status_code == 200
    bob.user_handle = alice.user_handle  # bob's key presenting alice's user handle
    r = await _login(client, bob)
    assert r.status_code == 400 and r.json() == FAILED


async def test_same_credential_cannot_register_twice(client: httpx.AsyncClient) -> None:
    device = SoftAuthenticator()
    assert (await _sign_up(client, device)).status_code == 200
    r = await _sign_up(client, device)
    assert r.status_code == 400 and r.json() == FAILED


# --- denial of service ------------------------------------------------------------


async def test_passkey_endpoints_are_rate_limited(tmp_path: Path) -> None:
    app = await build_app(make_settings(tmp_path, rate_limit_auth_per_minute=2))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as c:
            assert (await c.post("/auth/passkey/login/options")).status_code == 200
            assert (await c.post("/auth/passkey/login/options")).status_code == 200
            assert (await c.post("/auth/passkey/login/options")).status_code == 429
    finally:
        await app.state.engine.dispose()
