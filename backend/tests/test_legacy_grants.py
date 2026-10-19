"""Miras anahtarı: oluşturma, teslim ve iki faktörlü kullanma (tehdit modeli §6)."""

from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text

from app.database import utcnow
from app.models.biometric import AuditLog
from app.models.legacy import LegacyAccess, LegacyGrant
from app.models.user import User
from app.providers.mock import MockMessagingProvider
from app.services.legacy_grant_service import CONSENT_VERSION
from tests.conftest import login
from tests.test_legacy_persona import DRAFT, _activate_media, _memory, _session, _step_up

RECIPIENT = "elif@ornek.com"


def _outbox(app: FastAPI) -> MockMessagingProvider:
    provider = app.state.registry.messaging()
    assert isinstance(provider, MockMessagingProvider)
    return provider


def _last(app: FastAPI, template: str, to: str | None = None) -> dict[str, str]:
    for message in reversed(_outbox(app).outbox):
        if message.template == template and (to is None or message.to == to):
            return dict(message.params)
    raise AssertionError(f"no {template} message")


def _grant_body(email: str = RECIPIENT, **extra: Any) -> dict[str, Any]:
    return {
        "recipient_email": email,
        "consent_accepted": True,
        "consent_text_version": CONSENT_VERSION,
        **extra,
    }


async def _owner_ready(app: FastAPI, client: httpx.AsyncClient) -> dict[str, str]:
    """Miras'ı yayınlanmış, sesi ve yüzü onaylı, adım-yukarı doğrulaması taze bir sahip."""
    headers = await login(client, "ahmet")
    await _memory(client, headers, "Kızıma parkta bisiklet sürmeyi öğrettim.")
    await client.put("/legacy/persona", headers=headers, json=DRAFT)
    await _activate_media(app, headers, "voice")
    await _activate_media(app, headers, "face")
    await _step_up(app, headers)
    r = await client.post("/legacy/persona/publish", headers=headers)
    assert r.status_code == 201, r.text
    return headers


async def _send(
    client: httpx.AsyncClient, owner: dict[str, str], email: str = RECIPIENT
) -> dict[str, Any]:
    r = await client.post("/legacy/grants", headers=owner, json=_grant_body(email))
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


async def _redeem(
    app: FastAPI, client: httpx.AsyncClient, headers: dict[str, str], key: str
) -> httpx.Response:
    r = await client.post("/legacy/redeem", headers=headers, json={"key": key})
    assert r.status_code == 200, r.text
    code = _last(app, "legacy_redeem_code")["code"]
    return await client.post(
        "/legacy/redeem/verify",
        headers=headers,
        json={"flow_id": r.json()["flow_id"], "code": code},
    )


# --- oluşturma -------------------------------------------------------------------------


async def test_grant_endpoints_require_login(client: httpx.AsyncClient) -> None:
    assert (await client.get("/legacy/grants")).status_code == 401
    assert (await client.post("/legacy/grants", json=_grant_body())).status_code == 401
    assert (await client.post("/legacy/redeem", json={"key": "x" * 20})).status_code == 401
    assert (await client.get("/legacy/consent-text")).status_code == 401


async def test_create_grant_requires_step_up_consent_and_published_legacy(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    headers = await login(client, "ahmet")
    r = await client.post("/legacy/grants", headers=headers, json=_grant_body())
    assert r.status_code == 403 and r.json()["detail"] == "step_up_required"
    await _step_up(app, headers)
    r = await client.post("/legacy/grants", headers=headers, json=_grant_body())
    assert r.status_code == 409 and r.json()["detail"] == "legacy_not_published"
    r = await client.post(
        "/legacy/grants", headers=headers, json=_grant_body(consent_text_version="old")
    )
    assert r.status_code == 409 and r.json()["detail"] == "consent_text_outdated"
    r = await client.post(
        "/legacy/grants", headers=headers, json=_grant_body(consent_accepted=False)
    )
    assert r.status_code == 422
    text_body = (await client.get("/legacy/consent-text", headers=headers)).json()
    assert text_body["version"] == CONSENT_VERSION and "klon" in text_body["text"]


async def test_key_is_shown_once_emailed_and_only_its_digest_is_stored(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    owner = await _owner_ready(app, client)
    created = await _send(client, owner)
    key = created["key"]
    assert key.startswith("EVA-") and created["status"] == "pending"

    mail = _last(app, "legacy_key_delivery", RECIPIENT)
    assert mail["key"] == key and mail["owner_name"]
    assert mail["link"].startswith("http://localhost:3000/")
    # E-postada persona içeriği yok (oltalamaya karşı sabit şablon).
    assert set(mail) == {"owner_name", "key", "link", "expires_on"}

    listed = (await client.get("/legacy/grants", headers=owner)).json()
    assert [g["status"] for g in listed] == ["pending"] and "key" not in listed[0]

    async with app.state.session_factory() as db:
        normalized = key.replace("-", "").removeprefix("EVA")
        for table in ("legacy_grants", "audit_log", "auth_codes"):
            rows = (await db.execute(text(f"SELECT * FROM {table}"))).all()  # noqa: S608
            dump = repr(rows)
            assert key not in dump and normalized not in dump, table
        actions = (await db.scalars(select(AuditLog.action))).all()
    assert {"legacy.created", "legacy.sent"} <= set(actions)


async def test_grant_limit(app: FastAPI, client: httpx.AsyncClient) -> None:
    owner = await _owner_ready(app, client)
    # Dakikalık istek sınırını aç; burada ölçülen sahip başına 5 açık anahtar kuralı.
    app.state.settings.rate_limit_call_per_minute = 100
    for i in range(5):
        await _send(client, owner, f"kisi{i}@ornek.com")
    r = await client.post("/legacy/grants", headers=owner, json=_grant_body("altinci@ornek.com"))
    assert r.status_code == 409 and r.json()["detail"] == "legacy_grant_limit"


async def test_owner_cannot_send_to_own_email(app: FastAPI, client: httpx.AsyncClient) -> None:
    owner = await _owner_ready(app, client)
    user_id = (await _session(app, owner)).user_id
    async with app.state.session_factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        user.email = "ahmet@ornek.com"
        await db.commit()
    r = await client.post("/legacy/grants", headers=owner, json=_grant_body("Ahmet@Ornek.com "))
    assert r.status_code == 422 and r.json()["detail"] == "recipient_is_owner"


# --- kullanma --------------------------------------------------------------------------


async def test_redeem_with_key_and_emailed_code_opens_access_once(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    owner = await _owner_ready(app, client)
    key = (await _send(client, owner))["key"]
    elif_ = await login(client, "elif")

    # İnsanların yazdığı gibi: küçük harf, boşluklu.
    r = await client.post(
        "/legacy/redeem", headers=elif_, json={"key": key.lower().replace("-", " ")}
    )
    assert r.status_code == 200 and r.json()["email_hint"] == "e***@ornek.com"
    # Anahtar tek başına erişim vermez.
    async with app.state.session_factory() as db:
        assert (await db.scalars(select(LegacyAccess))).all() == []
    code = _last(app, "legacy_redeem_code", RECIPIENT)["code"]
    r = await client.post(
        "/legacy/redeem/verify",
        headers=elif_,
        json={"flow_id": r.json()["flow_id"], "code": code},
    )
    assert r.status_code == 200 and r.json()["owner_name"]

    async with app.state.session_factory() as db:
        [access] = (await db.scalars(select(LegacyAccess))).all()
        assert access.status == "active"
        [grant] = (await db.scalars(select(LegacyGrant))).all()
        assert grant.status == "redeemed" and grant.redeemed_by == access.recipient_id
        actions = (await db.scalars(select(AuditLog.action))).all()
    assert "legacy.redeemed" in actions
    listed = (await client.get("/legacy/grants", headers=owner)).json()
    assert listed[0]["status"] == "redeemed"

    # Anahtar tükendi: ikinci kez (başka hesapla da) kullanılamaz.
    other = await login(client, "murat")
    r = await client.post("/legacy/redeem", headers=other, json={"key": key})
    assert r.status_code == 400 and r.json()["detail"] == "invalid_or_expired"


async def test_owner_is_notified_when_the_key_is_used(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    owner = await _owner_ready(app, client)
    user_id = (await _session(app, owner)).user_id
    async with app.state.session_factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        user.email = "ahmet@ornek.com"
        await db.commit()
    key = (await _send(client, owner))["key"]
    r = await _redeem(app, client, await login(client, "elif"), key)
    assert r.status_code == 200
    assert _last(app, "legacy_key_used", "ahmet@ornek.com") == {"recipient_email": RECIPIENT}


@pytest.mark.parametrize("case", ["wrong", "format", "own", "expired", "revoked"])
async def test_redeem_errors_are_uniform(
    app: FastAPI, client: httpx.AsyncClient, case: str
) -> None:
    owner = await _owner_ready(app, client)
    key = (await _send(client, owner))["key"]
    who = owner if case == "own" else await login(client, "elif")
    if case == "wrong":
        key = (await _send(client, owner, "baska@ornek.com"))["key"]
        async with app.state.session_factory() as db:
            for grant in (await db.scalars(select(LegacyGrant))).all():
                grant.key_digest = (
                    "0" * 64 if grant.recipient_email == "baska@ornek.com" else (grant.key_digest)
                )
            await db.commit()
    elif case == "format":
        key = "EVA-0000-0000"
    elif case in ("expired", "revoked"):
        async with app.state.session_factory() as db:
            grant = (await db.scalars(select(LegacyGrant))).one()
            if case == "expired":
                grant.expires_at = utcnow() - timedelta(seconds=1)
            else:
                grant.status = "revoked"
            await db.commit()
    r = await client.post("/legacy/redeem", headers=who, json={"key": key})
    assert r.status_code == 400 and r.json() == {"detail": "invalid_or_expired"}


async def test_code_is_bound_to_the_account_that_entered_the_key(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    owner = await _owner_ready(app, client)
    key = (await _send(client, owner))["key"]
    elif_, murat = await login(client, "elif"), await login(client, "murat")
    r = await client.post("/legacy/redeem", headers=elif_, json={"key": key})
    flow_id = r.json()["flow_id"]
    code = _last(app, "legacy_redeem_code")["code"]
    r = await client.post(
        "/legacy/redeem/verify", headers=murat, json={"flow_id": flow_id, "code": code}
    )
    assert r.status_code == 400
    async with app.state.session_factory() as db:
        assert (await db.scalars(select(LegacyAccess))).all() == []


async def test_repeated_failures_lock_the_account(app: FastAPI, client: httpx.AsyncClient) -> None:
    owner = await _owner_ready(app, client)
    # Dakikalık istek sınırını aç; burada ölçülen hesap başına 24 saatlik kilit.
    app.state.settings.rate_limit_call_per_minute = 100
    key = (await _send(client, owner))["key"]
    elif_ = await login(client, "elif")
    for _ in range(5):
        r = await client.post("/legacy/redeem", headers=elif_, json={"key": "EVA-" + "1" * 33})
        assert r.status_code == 400
    # Doğru anahtar bile kilitliyken kabul edilmez.
    r = await client.post("/legacy/redeem", headers=elif_, json={"key": key})
    assert r.status_code == 429 and r.json()["detail"] == "too_many_attempts"
    # Kilit hesaba özel: başka hesap etkilenmez.
    r = await client.post("/legacy/redeem", headers=await login(client, "murat"), json={"key": key})
    assert r.status_code == 200


async def test_redeem_is_rate_limited_per_minute(app: FastAPI, client: httpx.AsyncClient) -> None:
    elif_ = await login(client, "elif")
    codes = [
        (
            await client.post("/legacy/redeem", headers=elif_, json={"key": "EVA-" + "1" * 33})
        ).status_code
        for _ in range(6)
    ]
    assert codes[-1] == 429
