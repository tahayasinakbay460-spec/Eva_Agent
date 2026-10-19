"""Vefat sonrası Miras (ADR 0011, tehdit modeli §7): kurulum, hareketsizlik, uyarı süreci,
otomatik anahtar, vefat bildirimi + inceleme, e-posta onaylı silme ve geri getirme."""

import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from app.database import utcnow
from app.models.biometric import AuditLog
from app.models.conversation import Conversation
from app.models.job import Job
from app.models.legacy import LegacyAccess, LegacyGrant, LegacyHeir, LegacyPosthumous
from app.models.persona import Persona
from app.models.user import User
from app.services import legacy_posthumous_service, password_auth_service
from app.services.legacy_posthumous_service import CONSENT_VERSION
from app.worker.jobs import LEGACY_POSTHUMOUS_SWEEP
from app.worker.runner import drain
from tests.conftest import login
from tests.test_biometrics import _make_admin
from tests.test_legacy_grants import _last, _outbox, _owner_ready
from tests.test_legacy_persona import _session, _step_up

OWNER_EMAIL = "ahmet@ornek.com"
HEIRS = ["elif@ornek.com", "murat@ornek.com"]
PDF = b"%PDF-1.4\n% vefat belgesi\n"


async def _user_id(app: FastAPI, headers: dict[str, str]) -> uuid.UUID:
    return (await _session(app, headers)).user_id


async def _verify_email(app: FastAPI, headers: dict[str, str], email: str) -> None:
    async with app.state.session_factory() as db:
        user = await db.get(User, await _user_id(app, headers))
        assert user is not None
        user.email = email
        user.email_verified_at = utcnow()
        await db.commit()


def _body(emails: list[str] = HEIRS, **extra: Any) -> dict[str, Any]:
    return {
        "emails": emails,
        "consent_accepted": True,
        "consent_text_version": CONSENT_VERSION,
        **extra,
    }


async def _armed_owner(app: FastAPI, client: httpx.AsyncClient) -> dict[str, str]:
    owner = await _owner_ready(app, client)
    await _verify_email(app, owner, OWNER_EMAIL)
    r = await client.put("/legacy/posthumous", headers=owner, json=_body())
    assert r.status_code == 200, r.text
    return owner


async def _set_last_active(app: FastAPI, headers: dict[str, str], when: datetime) -> None:
    async with app.state.session_factory() as db:
        user = await db.get(User, await _user_id(app, headers))
        assert user is not None
        user.last_active_at = when
        await db.commit()


async def _sweep(app: FastAPI, now: datetime) -> None:
    deps = password_auth_service.Deps(
        messaging=app.state.registry.messaging(), limiter=app.state.rate_limiter
    )
    async with app.state.session_factory() as db:
        await legacy_posthumous_service.sweep(
            db, app.state.settings, deps, app.state.legacy_pepper, now=now
        )


async def _row(app: FastAPI) -> LegacyPosthumous:
    async with app.state.session_factory() as db:
        row: LegacyPosthumous = (await db.scalars(select(LegacyPosthumous))).one()
        return row


def _sent(app: FastAPI, template: str) -> list[str]:
    return [m.to for m in _outbox(app).outbox if m.template == template]


async def _activate(app: FastAPI, client: httpx.AsyncClient) -> tuple[dict[str, str], datetime]:
    owner = await _armed_owner(app, client)
    t0 = utcnow()
    await _set_last_active(app, owner, t0 - timedelta(days=181))
    for day in (0, 7, 13, 14):
        await _sweep(app, t0 + timedelta(days=day))
    assert (await _row(app)).state == "activated"
    return owner, t0


# --- kurulum ---------------------------------------------------------------------------


async def test_posthumous_endpoints_require_login(client: httpx.AsyncClient) -> None:
    assert (await client.get("/legacy/posthumous")).status_code == 401
    assert (await client.put("/legacy/posthumous", json=_body())).status_code == 401
    assert (await client.get("/legacy/heir-of")).status_code == 401


async def test_heirs_need_step_up_email_and_a_ready_legacy(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    headers = await login(client, "ahmet")
    r = await client.put("/legacy/posthumous", headers=headers, json=_body())
    assert r.status_code == 403 and r.json()["detail"] == "step_up_required"
    await _step_up(app, headers)
    r = await client.put("/legacy/posthumous", headers=headers, json=_body())
    assert r.status_code == 409 and r.json()["detail"] == "legacy_email_required"
    await _verify_email(app, headers, OWNER_EMAIL)
    r = await client.put("/legacy/posthumous", headers=headers, json=_body())
    assert r.status_code == 409 and r.json()["detail"] == "legacy_not_published"
    r = await client.put(
        "/legacy/posthumous", headers=headers, json=_body(consent_text_version="old")
    )
    assert r.status_code == 409 and r.json()["detail"] == "consent_text_outdated"


async def test_heir_list_rules(app: FastAPI, client: httpx.AsyncClient) -> None:
    owner = await _owner_ready(app, client)
    await _verify_email(app, owner, OWNER_EMAIL)
    six = [f"kisi{i}@ornek.com" for i in range(6)]
    assert (
        await client.put("/legacy/posthumous", headers=owner, json=_body(six))
    ).status_code == 422
    assert (
        await client.put("/legacy/posthumous", headers=owner, json=_body([]))
    ).status_code == 422
    r = await client.put(
        "/legacy/posthumous", headers=owner, json=_body(["Ahmet@Ornek.com", "elif@ornek.com"])
    )
    assert r.status_code == 422 and r.json()["detail"] == "recipient_is_owner"


async def test_configure_arms_without_sending_any_key(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    owner = await _armed_owner(app, client)
    body = (await client.get("/legacy/posthumous", headers=owner)).json()
    assert body["state"] == "armed" and body["inactivity_days"] == 180
    assert body["warning_days"] == 14 and "6 ay" in body["consent_text"]
    assert [(h["email"], h["sent"]) for h in body["heirs"]] == [(e, False) for e in HEIRS]
    async with app.state.session_factory() as db:
        assert (await db.scalars(select(LegacyGrant))).all() == []
    assert _sent(app, "legacy_posthumous_delivery") == []

    # Liste değiştirilebilir; kapatmak da adım-yukarı ister.
    r = await client.put("/legacy/posthumous", headers=owner, json=_body(["yeni@ornek.com"]))
    assert [h["email"] for h in r.json()["heirs"]] == ["yeni@ornek.com"]
    fresh = await login(client, "ahmet")
    assert (await client.delete("/legacy/posthumous", headers=fresh)).status_code == 403
    r = await client.delete("/legacy/posthumous", headers=owner)
    assert r.status_code == 200 and r.json()["state"] == "off" and r.json()["heirs"] == []


# --- hareketsizlik ve uyarı süreci ---------------------------------------------------------


async def test_inactivity_runs_full_warning_cycle_then_sends_keys_once(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    owner = await _armed_owner(app, client)
    t0 = utcnow()
    # 179 gün: henüz bir şey olmaz.
    await _set_last_active(app, owner, t0 - timedelta(days=179))
    await _sweep(app, t0)
    assert (await _row(app)).state == "armed"

    await _set_last_active(app, owner, t0 - timedelta(days=181))
    await _sweep(app, t0)
    row = await _row(app)
    assert (row.state, row.trigger, row.warnings_sent) == ("warning", "inactivity", 1)
    assert _sent(app, "legacy_posthumous_warning") == [OWNER_EMAIL]
    await _sweep(app, t0 + timedelta(hours=1))  # tekrar: aynı uyarı ikinci kez gitmez
    assert len(_sent(app, "legacy_posthumous_warning")) == 1

    await _sweep(app, t0 + timedelta(days=7))
    await _sweep(app, t0 + timedelta(days=13))
    assert len(_sent(app, "legacy_posthumous_warning")) == 3
    assert (await _row(app)).state == "warning", "not before 14 days"
    async with app.state.session_factory() as db:
        assert (await db.scalars(select(LegacyGrant))).all() == []

    await _sweep(app, t0 + timedelta(days=14))
    assert (await _row(app)).state == "activated"
    assert sorted(_sent(app, "legacy_posthumous_delivery")) == sorted(HEIRS)
    mail = _last(app, "legacy_posthumous_delivery")
    assert mail["key"].startswith("EVA-") and mail["owner_name"]
    async with app.state.session_factory() as db:
        grants = (await db.scalars(select(LegacyGrant))).all()
        assert {g.mode for g in grants} == {"posthumous"}
        assert all(g.expires_at - g.created_at == timedelta(days=365) for g in grants)
        assert all(h.grant_id for h in (await db.scalars(select(LegacyHeir))).all())

    owner_grants = (await client.get("/legacy/grants", headers=owner)).json()
    assert {g["mode"] for g in owner_grants} == {"posthumous"}
    # Tekrar taramak aynı kişilere ikinci anahtar göndermez.
    await _sweep(app, t0 + timedelta(days=15))
    assert len(_sent(app, "legacy_posthumous_delivery")) == len(HEIRS)
    async with app.state.session_factory() as db:
        actions = (await db.scalars(select(AuditLog.action))).all()
    for action in ("legacy.warning_started", "legacy.warning_sent", "legacy.activated"):
        assert action in actions
    # Etkinleşmiş kurulum değiştirilemez.
    await _step_up(app, owner)
    r = await client.put("/legacy/posthumous", headers=owner, json=_body())
    assert r.status_code == 409 and r.json()["detail"] == "legacy_already_activated"


async def test_owner_login_cancels_warning(app: FastAPI, client: httpx.AsyncClient) -> None:
    owner = await _armed_owner(app, client)
    t0 = utcnow()
    await _set_last_active(app, owner, t0 - timedelta(days=181))
    await _sweep(app, t0)
    assert (await _row(app)).state == "warning"

    # Sahip herhangi bir şekilde giriş yapar (kimlik doğrulamalı tek bir istek yeter).
    assert (await client.get("/legacy/posthumous", headers=owner)).status_code == 200
    row = await _row(app)
    assert (row.state, row.warnings_sent, row.trigger) == ("armed", 0, None)
    await _sweep(app, t0 + timedelta(days=14))
    assert (await _row(app)).state == "armed"
    async with app.state.session_factory() as db:
        actions = (await db.scalars(select(AuditLog.action))).all()
    assert "legacy.warning_cancelled" in actions


async def test_activity_is_written_at_most_hourly(app: FastAPI, client: httpx.AsyncClient) -> None:
    headers = await login(client, "ahmet")
    recent = utcnow() - timedelta(minutes=30)
    await _set_last_active(app, headers, recent)
    await client.get("/legacy/posthumous", headers=headers)
    async with app.state.session_factory() as db:
        user = await db.get(User, await _user_id(app, headers))
        assert user is not None and user.last_active_at == recent
    await _set_last_active(app, headers, utcnow() - timedelta(hours=2))
    await client.get("/legacy/posthumous", headers=headers)
    async with app.state.session_factory() as db:
        user = await db.get(User, await _user_id(app, headers))
        assert user is not None and user.last_active_at is not None
        assert utcnow() - user.last_active_at < timedelta(minutes=1)


async def test_sweep_job_reschedules_itself(app: FastAPI) -> None:
    from app.worker import queue

    async with app.state.session_factory() as db:
        await queue.enqueue(db, LEGACY_POSTHUMOUS_SWEEP, {}, dedupe_key=LEGACY_POSTHUMOUS_SWEEP)
        await db.commit()
    await drain(app.state.worker_context)
    async with app.state.session_factory() as db:
        pending = (
            await db.scalars(
                select(Job).where(Job.kind == LEGACY_POSTHUMOUS_SWEEP, Job.status == "pending")
            )
        ).all()
    assert len(pending) == 1 and pending[0].run_at > utcnow() + timedelta(minutes=50)


# --- vefat bildirimi ve inceleme -----------------------------------------------------------


async def test_death_report_only_by_heir_and_review_starts_warning(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    owner = await _armed_owner(app, client)
    owner_id = await _user_id(app, owner)
    stranger = await login(client, "yabanci")
    await _verify_email(app, stranger, "yabanci@ornek.com")
    assert (await client.get("/legacy/heir-of", headers=stranger)).json() == []
    r = await client.post(
        f"/legacy/heir-of/{owner_id}/report",
        headers={**stranger, "Content-Type": "application/pdf"},
        content=PDF,
    )
    assert r.status_code == 404

    elif_ = await login(client, "elif")
    # Doğrulanmamış e-posta sayılmaz.
    assert (await client.get("/legacy/heir-of", headers=elif_)).json() == []
    await _verify_email(app, elif_, "elif@ornek.com")
    heir_of = (await client.get("/legacy/heir-of", headers=elif_)).json()
    assert [h["owner_id"] for h in heir_of] == [str(owner_id)]
    r = await client.post(
        f"/legacy/heir-of/{owner_id}/report",
        headers={**elif_, "Content-Type": "application/pdf"},
        content=b"not a pdf",
    )
    assert r.status_code == 415
    r = await client.post(
        f"/legacy/heir-of/{owner_id}/report",
        headers={**elif_, "Content-Type": "application/pdf"},
        content=PDF,
    )
    assert r.status_code == 201
    r = await client.post(
        f"/legacy/heir-of/{owner_id}/report",
        headers={**elif_, "Content-Type": "application/pdf"},
        content=PDF,
    )
    assert r.status_code == 409 and r.json()["detail"] == "report_already_open"
    assert (await client.get("/legacy/heir-of", headers=elif_)).json()[0]["open_report"] is True

    # Admin olmayan için inceleme uçları "yok".
    assert (await client.get("/admin/legacy/death-reports", headers=elif_)).status_code == 404
    admin = await login(client, "admin")
    await _make_admin(app, "admin")
    [report] = (await client.get("/admin/legacy/death-reports", headers=admin)).json()
    assert report["reporter_name"] and report["media_type"] == "application/pdf"
    doc_url = f"/admin/legacy/death-reports/{report['id']}/document"
    assert (await client.get(doc_url, headers=admin)).status_code == 403
    await _step_up(app, admin)
    doc = await client.get(doc_url, headers=admin)
    assert doc.status_code == 200 and doc.content == PDF
    assert doc.headers["cache-control"] == "no-store"

    r = await client.post(f"/admin/legacy/death-reports/{report['id']}/approve", headers=admin)
    assert r.status_code == 204
    row = await _row(app)
    # Onay bile hemen açmaz: uyarı süreci başlar; sahip girerse durur.
    assert (row.state, row.trigger) == ("warning", "death_report")
    async with app.state.session_factory() as db:
        assert (await db.scalars(select(LegacyGrant))).all() == []
        actions = (await db.scalars(select(AuditLog.action))).all()
    assert {"legacy.death_reported", "legacy.death_report_viewed"} <= set(actions)
    await _set_last_active(app, owner, utcnow() - timedelta(days=1))
    await client.get("/legacy/posthumous", headers=owner)
    assert (await _row(app)).state == "armed"


async def test_rejected_report_changes_nothing(app: FastAPI, client: httpx.AsyncClient) -> None:
    owner = await _armed_owner(app, client)
    owner_id = await _user_id(app, owner)
    elif_ = await login(client, "elif")
    await _verify_email(app, elif_, "elif@ornek.com")
    await client.post(
        f"/legacy/heir-of/{owner_id}/report",
        headers={**elif_, "Content-Type": "application/pdf"},
        content=PDF,
    )
    admin = await login(client, "admin")
    await _make_admin(app, "admin")
    await _step_up(app, admin)
    [report] = (await client.get("/admin/legacy/death-reports", headers=admin)).json()
    r = await client.post(f"/admin/legacy/death-reports/{report['id']}/reject", headers=admin)
    assert r.status_code == 204
    assert (await _row(app)).state == "armed"
    assert (await client.get("/admin/legacy/death-reports", headers=admin)).json() == []


# --- alıcı: vefat sonrası Miras'ı açma, silme (e-posta onayı), geri getirme ----------------


async def _open_as_heir(
    app: FastAPI, client: httpx.AsyncClient, handle: str, email: str
) -> tuple[dict[str, str], str, str]:
    key = next(
        m.params["key"]
        for m in _outbox(app).outbox
        if m.template == "legacy_posthumous_delivery" and m.to == email
    )
    heir = await login(client, handle)
    r = await client.post("/legacy/redeem", headers=heir, json={"key": key})
    assert r.status_code == 200, r.text
    code = _last(app, "legacy_redeem_code", email)["code"]
    r = await client.post(
        "/legacy/redeem/verify",
        headers=heir,
        json={"flow_id": r.json()["flow_id"], "code": code},
    )
    assert r.status_code == 200, r.text
    pid = r.json()["persona_id"]
    access_id = (await client.get("/legacy/shared", headers=heir)).json()[0]["access_id"]
    return heir, pid, access_id


async def test_posthumous_delete_needs_code_and_keeps_persona(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    await _activate(app, client)
    # Bu test kısa sürede çok sayıda anahtar/kod isteği yapar; dakikalık sınır konu dışı.
    app.state.settings.rate_limit_call_per_minute = 100
    elif_, pid, access_id = await _open_as_heir(app, client, "elif", "elif@ornek.com")
    murat, _, _ = await _open_as_heir(app, client, "murat", "murat@ornek.com")
    shared = (await client.get("/legacy/shared", headers=elif_)).json()
    assert shared[0]["mode"] == "posthumous" and shared[0]["status"] == "active"
    conv = (
        await client.post("/chat/conversations", headers=elif_, json={"persona_id": pid})
    ).json()["id"]

    # Doğrudan silme yok: e-posta onayı gerekir.
    r = await client.delete(f"/legacy/shared/{access_id}", headers=elif_)
    assert r.status_code == 409 and r.json()["detail"] == "confirmation_required"
    # Başkası başlatamaz.
    r = await client.post(f"/legacy/shared/{access_id}/delete/start", headers=murat)
    assert r.status_code == 404

    r = await client.post(f"/legacy/shared/{access_id}/delete/start", headers=elif_)
    assert r.status_code == 200 and r.json()["email_hint"] == "e***@ornek.com"
    flow_id = r.json()["flow_id"]
    code = _last(app, "legacy_delete_code", "elif@ornek.com")["code"]
    bad = await client.post(
        f"/legacy/shared/{access_id}/delete/verify",
        headers=elif_,
        json={"flow_id": flow_id, "code": "000000" if code != "000000" else "111111"},
    )
    assert bad.status_code == 400
    # Kod başka hesapla kullanılamaz.
    r = await client.post(
        f"/legacy/shared/{access_id}/delete/verify",
        headers=murat,
        json={"flow_id": flow_id, "code": code},
    )
    assert r.status_code == 400
    r = await client.post(f"/legacy/shared/{access_id}/delete/start", headers=elif_)
    flow_id = r.json()["flow_id"]
    code = _last(app, "legacy_delete_code", "elif@ornek.com")["code"]
    r = await client.post(
        f"/legacy/shared/{access_id}/delete/verify",
        headers=elif_,
        json={"flow_id": flow_id, "code": code},
    )
    assert r.status_code == 204

    assert (await client.get("/legacy/shared", headers=elif_)).json() == []
    assert (
        await client.post("/chat/conversations", headers=elif_, json={"persona_id": pid})
    ).status_code == 404
    async with app.state.session_factory() as db:
        # Karakter sistemde yaşamaya devam eder; Elif'in geçmişi de silinmez.
        assert await db.get(Persona, uuid.UUID(pid)) is not None
        assert await db.get(Conversation, uuid.UUID(conv)) is not None
        access = await db.get(LegacyAccess, uuid.UUID(access_id))
        assert access is not None and access.status == "deleted"
    # Diğer alıcı etkilenmez.
    assert (await client.get("/legacy/shared", headers=murat)).json()[0]["status"] == "active"

    # Geri getirme yalnızca destek (admin + adım-yukarı).
    restore = f"/admin/legacy/access/{access_id}/restore"
    assert (await client.post(restore, headers=elif_)).status_code == 404
    admin = await login(client, "admin")
    await _make_admin(app, "admin")
    assert (await client.post(restore, headers=admin)).status_code == 403
    await _step_up(app, admin)
    assert (await client.post(restore, headers=admin)).status_code == 204
    shared = (await client.get("/legacy/shared", headers=elif_)).json()
    assert shared[0]["status"] == "active"
    r = await client.post(
        f"/chat/conversations/{conv}/messages",
        headers=elif_,
        json={"content": "Baba yine buradayım", "idempotency_key": uuid.uuid4().hex},
    )
    assert r.status_code == 200
