"""Rızalı ses/yüz kaydı (Faz 3); docs/threat-model.md §5'teki her tehdit burada denenir.

Faz 3 çıkış şartı: "rıza doğrulaması, iptal ve sağlayıcıdan silme test edildi".
"""

import hashlib
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.core.security import hash_token
from app.database import utcnow
from app.models.biometric import (
    AppendOnlyError,
    AuditLog,
    BiometricEnrollment,
    ConsentRecord,
    EnrollmentSample,
    ProviderAsset,
)
from app.models.session import AuthSession
from app.models.user import User
from app.providers.base import ProviderError
from app.providers.mock import MockVoiceEnrollmentProvider
from app.services import biometric_service, consent_texts
from app.worker.runner import drain
from tests.conftest import login, make_settings

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 2048
OGG = b"OggS" + b"\x00" * 2048
VERSION = consent_texts.VERSION


# --- yardımcılar ------------------------------------------------------------------


async def _step_up(app: FastAPI, headers: dict[str, str]) -> None:
    """Testlerde adım-yukarı doğrulamanın kendisi değil sonucu lazım (akışlar
    test_step_up.py'de ayrıca deneniyor): oturuma damgayı doğrudan basarız."""
    token = headers["Authorization"].split(" ", 1)[1]
    async with app.state.session_factory() as db:
        session = (
            await db.execute(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
        ).scalar_one()
        session.step_up_at = utcnow()
        await db.commit()


async def _user(client: httpx.AsyncClient, app: FastAPI, handle: str) -> dict[str, str]:
    headers = await login(client, handle)
    await _step_up(app, headers)
    return headers


async def _make_admin(app: FastAPI, handle: str) -> None:
    async with app.state.session_factory() as db:
        user = (await db.execute(select(User).where(User.handle == handle))).scalar_one()
        user.role = "admin"
        await db.commit()


async def _start(
    client: httpx.AsyncClient, headers: dict[str, str], kind: str = "voice"
) -> dict[str, Any]:
    r = await client.post(
        "/biometrics/enrollments",
        headers=headers,
        json={"kind": kind, "consent_text_version": VERSION, "consent_accepted": True},
    )
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


async def _upload(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    enrollment_id: str,
    data: bytes,
    content_type: str,
    role: str = "sample",
) -> httpx.Response:
    return await client.post(
        f"/biometrics/enrollments/{enrollment_id}/files",
        params={"role": role, "duration_s": 60},
        headers={**headers, "Content-Type": content_type},
        content=data,
    )


async def _ready(
    client: httpx.AsyncClient, headers: dict[str, str], kind: str = "voice"
) -> dict[str, Any]:
    """Örneği ve rıza videosu yüklenmiş, gönderilmiş bir kayıt."""
    enrollment = await _start(client, headers, kind)
    sample_type = "audio/webm" if kind == "voice" else "video/webm"
    assert (await _upload(client, headers, enrollment["id"], WEBM, sample_type)).status_code == 201
    r = await _upload(
        client, headers, enrollment["id"], WEBM + b"consent", "video/webm", "consent_recording"
    )
    assert r.status_code == 201, r.text
    r = await client.post(f"/biometrics/enrollments/{enrollment['id']}/submit", headers=headers)
    assert r.status_code == 200, r.text
    return enrollment


async def _admin(client: httpx.AsyncClient, app: FastAPI) -> dict[str, str]:
    headers = await _user(client, app, "reviewer")
    await _make_admin(app, "reviewer")
    return headers


APPROVE = {"adult": True, "same_person": True, "code_matches": True, "consent_is_clear": True}


async def _approve(client: httpx.AsyncClient, admin: dict[str, str], enrollment_id: str) -> None:
    r = await client.post(
        f"/admin/biometrics/enrollments/{enrollment_id}/approve", headers=admin, json=APPROVE
    )
    assert r.status_code == 200, r.text


def _voices(app: FastAPI) -> MockVoiceEnrollmentProvider:
    provider = app.state.registry.voice_enrollment()
    assert isinstance(provider, MockVoiceEnrollmentProvider)
    return provider


async def _status(client: httpx.AsyncClient, headers: dict[str, str], enrollment_id: str) -> str:
    r = await client.get(f"/biometrics/enrollments/{enrollment_id}", headers=headers)
    status: str = r.json()["status"]
    return status


async def _preview(client: httpx.AsyncClient, headers: dict[str, str]) -> httpx.Response:
    return await client.post("/biometrics/voice/preview", headers=headers, json={"sentence": 0})


def _stored_files(tmp_path: Path) -> list[Path]:
    root = tmp_path / "storage"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


# --- rıza metni ve başlatma ---------------------------------------------------------


async def test_consent_text(client: httpx.AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.get("/biometrics/consent-text?kind=voice", headers=auth_headers)
    body = r.json()
    assert body["version"] == VERSION
    assert "geri" in body["summary"], "withdrawal right is stated"
    assert body["reading_passage"]
    face = (await client.get("/biometrics/consent-text?kind=face", headers=auth_headers)).json()
    assert face["reading_passage"] is None


async def test_sensitive_steps_require_step_up(app: FastAPI, client: httpx.AsyncClient) -> None:
    headers = await login(client)
    body = {"kind": "voice", "consent_text_version": VERSION, "consent_accepted": True}
    r = await client.post("/biometrics/enrollments", headers=headers, json=body)
    assert r.status_code == 403 and r.json() == {"detail": "step_up_required"}

    await _step_up(app, headers)
    enrollment = await _start(client, headers)
    async with app.state.session_factory() as db:
        session = (await db.execute(select(AuthSession))).scalar_one()
        session.step_up_at = None
        await db.commit()
    for action in ("submit", "revoke"):
        r = await client.post(
            f"/biometrics/enrollments/{enrollment['id']}/{action}", headers=headers
        )
        assert r.status_code == 403, action


async def test_consent_must_be_accepted_and_current(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    headers = await _user(client, app, "ayse")
    r = await client.post(
        "/biometrics/enrollments",
        headers=headers,
        json={"kind": "voice", "consent_text_version": VERSION, "consent_accepted": False},
    )
    assert r.status_code == 422
    r = await client.post(
        "/biometrics/enrollments",
        headers=headers,
        json={"kind": "voice", "consent_text_version": "2020-01-01", "consent_accepted": True},
    )
    assert r.status_code == 409 and r.json() == {"detail": "consent_text_outdated"}


async def test_each_enrollment_gets_a_fresh_code(app: FastAPI, client: httpx.AsyncClient) -> None:
    headers = await _user(client, app, "ayse")
    codes = set()
    for _ in range(3):
        enrollment = await _start(client, headers)
        code = enrollment["challenge_code"]
        assert len(code) == 6 and code.isdigit()
        assert " ".join(code) in enrollment["consent_sentence"], "code is read digit by digit"
        assert "Ayse" in enrollment["consent_sentence"]
        codes.add(code)
        await client.post(f"/biometrics/enrollments/{enrollment['id']}/revoke", headers=headers)
    assert len(codes) == 3


async def test_one_open_enrollment_per_kind(app: FastAPI, client: httpx.AsyncClient) -> None:
    headers = await _user(client, app, "ayse")
    await _start(client, headers, "voice")
    r = await client.post(
        "/biometrics/enrollments",
        headers=headers,
        json={"kind": "voice", "consent_text_version": VERSION, "consent_accepted": True},
    )
    assert r.status_code == 409 and r.json() == {"detail": "enrollment_exists"}
    await _start(client, headers, "face")  # yüz ayrı bir amaç: ayrıca başlatılabilir


# --- yükleme -------------------------------------------------------------------------


async def test_upload_rejects_wrong_magic_bytes_and_types(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    headers = await _user(client, app, "ayse")
    eid = (await _start(client, headers))["id"]
    r = await _upload(client, headers, eid, b"<html>evil</html>" * 10, "audio/webm")
    assert r.status_code == 415 and r.json() == {"detail": "media_type_mismatch"}
    r = await _upload(client, headers, eid, OGG, "audio/webm")
    assert r.status_code == 415, "declared webm, actually ogg"
    r = await _upload(client, headers, eid, WEBM, "image/png")
    assert r.status_code == 415 and r.json() == {"detail": "unsupported_media_type"}
    r = await _upload(client, headers, eid, WEBM, "audio/webm", role="consent_recording")
    assert r.status_code == 415, "consent must be a video (face + voice)"
    r = await _upload(client, headers, eid, OGG, "audio/ogg;codecs=opus")
    assert r.status_code == 201, "codec parameters are ignored"


async def test_upload_size_limit(
    app: FastAPI, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _user(client, app, "ayse")
    eid = (await _start(client, headers))["id"]
    monkeypatch.setitem(biometric_service.SIZE_LIMITS, ("voice", "sample"), 1024)
    r = await _upload(client, headers, eid, WEBM, "audio/webm")
    assert r.status_code == 413


async def test_sample_count_limit(app: FastAPI, client: httpx.AsyncClient) -> None:
    headers = await _user(client, app, "ayse")
    eid = (await _start(client, headers))["id"]
    for _ in range(biometric_service.MAX_SAMPLES):
        assert (await _upload(client, headers, eid, WEBM, "audio/webm")).status_code == 201
    r = await _upload(client, headers, eid, WEBM, "audio/webm")
    assert r.status_code == 409 and r.json() == {"detail": "too_many_samples"}


async def test_consent_recording_can_be_retaken(app: FastAPI, client: httpx.AsyncClient) -> None:
    headers = await _user(client, app, "ayse")
    eid = (await _start(client, headers))["id"]
    for _ in range(2):
        r = await _upload(client, headers, eid, WEBM, "video/webm", "consent_recording")
        assert r.status_code == 201
    files = (await client.get(f"/biometrics/enrollments/{eid}", headers=headers)).json()["files"]
    assert [f["role"] for f in files] == ["consent_recording"]


async def test_files_are_stored_encrypted(
    app: FastAPI, client: httpx.AsyncClient, tmp_path: Path
) -> None:
    headers = await _user(client, app, "ayse")
    eid = (await _start(client, headers))["id"]
    marker = WEBM + b"BENIM-SESIM" * 20
    await _upload(client, headers, eid, marker, "audio/webm")
    (stored,) = _stored_files(tmp_path)
    assert b"BENIM-SESIM" not in stored.read_bytes()
    assert "biometric" in stored.parts


async def test_submit_requires_samples_and_consent_recording(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    headers = await _user(client, app, "ayse")
    eid = (await _start(client, headers))["id"]
    r = await client.post(f"/biometrics/enrollments/{eid}/submit", headers=headers)
    assert r.status_code == 422 and r.json() == {"detail": "samples_missing"}
    await _upload(client, headers, eid, WEBM, "audio/webm")
    r = await client.post(f"/biometrics/enrollments/{eid}/submit", headers=headers)
    assert r.status_code == 422 and r.json() == {"detail": "consent_recording_missing"}


async def test_submit_writes_consent_record(app: FastAPI, client: httpx.AsyncClient) -> None:
    headers = await _user(client, app, "ayse")
    enrollment = await _ready(client, headers)
    assert await _status(client, headers, enrollment["id"]) == "pending_review"
    r = await _upload(client, headers, enrollment["id"], WEBM, "audio/webm")
    assert r.status_code == 409, "no more uploads after submitting"

    async with app.state.session_factory() as db:
        (record,) = (await db.execute(select(ConsentRecord))).scalars().all()
        assert record.event == "granted"
        assert record.text_version == VERSION
        assert record.evidence_sha256 == hashlib.sha256(WEBM + b"consent").hexdigest()
        user = (await db.execute(select(User).where(User.handle == "ayse"))).scalar_one()
        assert record.text_sha256 == consent_texts.text_digest(
            "voice", user.locale, name=user.display_name, code=enrollment["challenge_code"]
        )
        actions = {a.action for a in (await db.execute(select(AuditLog))).scalars()}
        assert {"biometric.enrollment_started", "biometric.submitted"} <= actions


async def test_consent_records_are_append_only(app: FastAPI, client: httpx.AsyncClient) -> None:
    headers = await _user(client, app, "ayse")
    await _ready(client, headers)
    async with app.state.session_factory() as db:
        record = (await db.execute(select(ConsentRecord))).scalar_one()
        record.event = "approved"
        with pytest.raises(AppendOnlyError):
            await db.commit()
    async with app.state.session_factory() as db:
        record = (await db.execute(select(ConsentRecord))).scalar_one()
        await db.delete(record)
        with pytest.raises(AppendOnlyError):
            await db.commit()
    async with app.state.session_factory() as db:
        log = (await db.execute(select(AuditLog))).scalars().first()
        assert log is not None
        log.action = "nothing"
        with pytest.raises(AppendOnlyError):
            await db.commit()


async def test_users_cannot_touch_each_others_enrollments(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    alice = await _user(client, app, "alice")
    bob = await _user(client, app, "bob")
    enrollment = await _start(client, alice)
    eid = enrollment["id"]
    file_id = (await _upload(client, alice, eid, WEBM, "audio/webm")).json()["id"]

    assert (await client.get(f"/biometrics/enrollments/{eid}", headers=bob)).status_code == 404
    assert (await _upload(client, bob, eid, WEBM, "audio/webm")).status_code == 404
    r = await client.delete(f"/biometrics/enrollments/{eid}/files/{file_id}", headers=bob)
    assert r.status_code == 404
    for action in ("submit", "revoke"):
        r = await client.post(f"/biometrics/enrollments/{eid}/{action}", headers=bob)
        assert r.status_code == 404
    assert (await client.get("/biometrics/enrollments", headers=bob)).json() == []
    assert await _status(client, alice, eid) == "collecting"


# --- inceleme ve klon -----------------------------------------------------------------


async def test_no_clone_without_approval(app: FastAPI, client: httpx.AsyncClient) -> None:
    headers = await _user(client, app, "ayse")
    await _ready(client, headers)
    await drain(app.state.worker_context)
    assert _voices(app).assets == {}
    r = await _preview(client, headers)
    assert r.status_code == 409 and r.json() == {"detail": "no_active_voice"}


async def test_admin_endpoints_are_hidden_from_users(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    headers = await _user(client, app, "ayse")
    enrollment = await _ready(client, headers)
    assert (await client.get("/admin/biometrics/pending", headers=headers)).status_code == 404
    r = await client.post(
        f"/admin/biometrics/enrollments/{enrollment['id']}/approve", headers=headers, json=APPROVE
    )
    assert r.status_code == 404, "users cannot approve their own clone"


async def test_admin_needs_step_up_for_files_and_decisions(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    user = await _user(client, app, "ayse")
    enrollment = await _ready(client, user)
    admin = await login(client, "reviewer")
    await _make_admin(app, "reviewer")
    pending = (await client.get("/admin/biometrics/pending", headers=admin)).json()
    assert [p["id"] for p in pending] == [enrollment["id"]]
    file_id = pending[0]["files"][0]["id"]
    r = await client.get(
        f"/admin/biometrics/enrollments/{enrollment['id']}/files/{file_id}", headers=admin
    )
    assert r.status_code == 403
    r = await client.post(
        f"/admin/biometrics/enrollments/{enrollment['id']}/approve", headers=admin, json=APPROVE
    )
    assert r.status_code == 403


async def test_admin_sample_access_is_audited(app: FastAPI, client: httpx.AsyncClient) -> None:
    user = await _user(client, app, "ayse")
    enrollment = await _ready(client, user)
    admin = await _admin(client, app)
    detail = (
        await client.get(f"/admin/biometrics/enrollments/{enrollment['id']}", headers=admin)
    ).json()
    consent_file = next(f for f in detail["files"] if f["role"] == "consent_recording")
    assert detail["consent_sentence"] == enrollment["consent_sentence"], "reviewer compares it"
    r = await client.get(
        f"/admin/biometrics/enrollments/{enrollment['id']}/files/{consent_file['id']}",
        headers=admin,
    )
    assert r.status_code == 200
    assert r.content == WEBM + b"consent"
    assert r.headers["cache-control"] == "no-store"
    async with app.state.session_factory() as db:
        viewed = (
            await db.execute(select(AuditLog).where(AuditLog.action == "biometric.file_viewed"))
        ).scalar_one()
        assert viewed.meta == {"role": "consent_recording"}


async def test_approval_requires_all_checks(app: FastAPI, client: httpx.AsyncClient) -> None:
    user = await _user(client, app, "ayse")
    enrollment = await _ready(client, user)
    admin = await _admin(client, app)
    for missing in APPROVE:
        body = {k: v for k, v in APPROVE.items() if k != missing}
        r = await client.post(
            f"/admin/biometrics/enrollments/{enrollment['id']}/approve", headers=admin, json=body
        )
        assert r.status_code == 422, missing


async def test_approved_enrollment_becomes_active_and_previews(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    user = await _user(client, app, "ayse")
    enrollment = await _ready(client, user)
    admin = await _admin(client, app)
    await _approve(client, admin, enrollment["id"])
    assert await _status(client, user, enrollment["id"]) == "processing"
    await drain(app.state.worker_context)
    assert await _status(client, user, enrollment["id"]) == "active"
    assert list(_voices(app).assets.values()) == [f"eva-{enrollment['id']}"], "no personal data"

    r = await _preview(client, user)
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF"
    assert r.headers["cache-control"] == "no-store"
    async with app.state.session_factory() as db:
        events = [r.event for r in (await db.execute(select(ConsentRecord))).scalars()]
        assert events == ["granted", "approved"]


async def test_preview_only_fixed_sentences(app: FastAPI, client: httpx.AsyncClient) -> None:
    """Klon sesle keyfi metin üretilemez (sahte arama dolandırıcılığına karşı)."""
    user = await _user(client, app, "ayse")
    enrollment = await _ready(client, user)
    await _approve(client, await _admin(client, app), enrollment["id"])
    await drain(app.state.worker_context)
    r = await client.post(
        "/biometrics/voice/preview", headers=user, json={"text": "Annene para gönder"}
    )
    assert r.status_code == 422
    r = await client.post("/biometrics/voice/preview", headers=user, json={"sentence": 9})
    assert r.status_code == 422 and r.json() == {"detail": "unknown_sentence"}
    sentences = (await client.get("/biometrics/voice/preview-sentences", headers=user)).json()
    assert sentences == list(consent_texts.PREVIEW_SENTENCES["tr"])


async def test_revoke_stops_use_immediately(app: FastAPI, client: httpx.AsyncClient) -> None:
    user = await _user(client, app, "ayse")
    enrollment = await _ready(client, user)
    await _approve(client, await _admin(client, app), enrollment["id"])
    await drain(app.state.worker_context)
    assert (await _preview(client, user)).status_code == 200

    r = await client.post(f"/biometrics/enrollments/{enrollment['id']}/revoke", headers=user)
    assert r.status_code == 200 and r.json()["status"] == "revoked"
    # İşçi henüz çalışmadı; klon sağlayıcıda duruyor ama artık kullanılamaz.
    assert _voices(app).assets
    assert (await _preview(client, user)).status_code == 409


async def test_revoke_deletes_provider_asset_and_files(
    app: FastAPI, client: httpx.AsyncClient, tmp_path: Path
) -> None:
    user = await _user(client, app, "ayse")
    enrollment = await _ready(client, user)
    await _approve(client, await _admin(client, app), enrollment["id"])
    await drain(app.state.worker_context)
    assert _voices(app).assets and _stored_files(tmp_path)

    await client.post(f"/biometrics/enrollments/{enrollment['id']}/revoke", headers=user)
    await client.post(f"/biometrics/enrollments/{enrollment['id']}/revoke", headers=user)
    await drain(app.state.worker_context)

    assert _voices(app).assets == {}, "clone deleted at the provider"
    assert _stored_files(tmp_path) == [], "raw samples destroyed"
    async with app.state.session_factory() as db:
        (asset,) = (await db.execute(select(ProviderAsset))).scalars().all()
        assert asset.status == "deleted" and asset.deleted_at is not None
        assert (await db.execute(select(EnrollmentSample))).scalars().all() == []
        events = [r.event for r in (await db.execute(select(ConsentRecord))).scalars()]
        assert events == ["granted", "approved", "revoked"], "evidence stays, files go"
        actions = [a.action for a in (await db.execute(select(AuditLog))).scalars()]
        assert actions.count("biometric.revoked") == 1, "second revoke is a no-op"
        assert "biometric.purged" in actions


async def test_rejection_purges_everything(
    app: FastAPI, client: httpx.AsyncClient, tmp_path: Path
) -> None:
    user = await _user(client, app, "ayse")
    enrollment = await _ready(client, user)
    admin = await _admin(client, app)
    r = await client.post(
        f"/admin/biometrics/enrollments/{enrollment['id']}/reject",
        headers=admin,
        json={"reason": "not_adult"},
    )
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    await drain(app.state.worker_context)
    assert _stored_files(tmp_path) == []
    assert _voices(app).assets == {}
    body = (await client.get(f"/biometrics/enrollments/{enrollment['id']}", headers=user)).json()
    assert body["reject_reason"] == "not_adult"
    # Reddedilen kişi baştan tekrar başvurabilir.
    await _start(client, user)


async def test_revoked_during_clone_creation_is_cleaned_up(
    app: FastAPI, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await _user(client, app, "ayse")
    enrollment = await _ready(client, user)
    await _approve(client, await _admin(client, app), enrollment["id"])
    provider = _voices(app)
    original = provider.create_voice

    async def create_then_user_revokes(*args: Any, **kwargs: Any) -> Any:
        ref = await original(*args, **kwargs)
        r = await client.post(f"/biometrics/enrollments/{enrollment['id']}/revoke", headers=user)
        assert r.status_code == 200
        return ref

    monkeypatch.setattr(provider, "create_voice", create_then_user_revokes)
    await drain(app.state.worker_context)
    assert provider.assets == {}, "clone created during revoke was deleted right away"
    assert await _status(client, user, enrollment["id"]) == "revoked"


async def test_permanent_provider_failure_marks_failed_and_purges(
    app: FastAPI, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user = await _user(client, app, "ayse")
    enrollment = await _ready(client, user)
    await _approve(client, await _admin(client, app), enrollment["id"])

    async def refuse(*args: Any, **kwargs: Any) -> Any:
        raise ProviderError("sample rejected", retryable=False)

    monkeypatch.setattr(_voices(app), "create_voice", refuse)
    await drain(app.state.worker_context)
    assert await _status(client, user, enrollment["id"]) == "failed"
    assert _stored_files(tmp_path) == []


async def test_face_enrollment_flow_uses_the_avatar_provider(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    user = await _user(client, app, "ayse")
    enrollment = await _ready(client, user, "face")
    await _approve(client, await _admin(client, app), enrollment["id"])
    await drain(app.state.worker_context)
    assert await _status(client, user, enrollment["id"]) == "active"
    async with app.state.session_factory() as db:
        asset = (await db.execute(select(ProviderAsset))).scalar_one()
        assert asset.kind == "avatar"


# --- ayar kuralları ----------------------------------------------------------------


def _enrollment_of(user_id: uuid.UUID) -> BiometricEnrollment:
    return BiometricEnrollment(
        user_id=user_id, kind="voice", challenge_code="123456", consent_text_version=VERSION
    )


def test_self_approval_forbidden_outside_dev(tmp_path: Path) -> None:
    reviewer = User(id=uuid.uuid4(), handle="admin", display_name="Admin", role="admin")
    prod = make_settings(tmp_path, env="prod")
    with pytest.raises(biometric_service.BiometricError) as info:
        biometric_service._check_reviewer(prod, reviewer, _enrollment_of(reviewer.id))
    assert info.value.code == "self_review_forbidden"
    dev = make_settings(tmp_path, env="dev")
    assert biometric_service._check_reviewer(dev, reviewer, _enrollment_of(reviewer.id)) is True
    assert biometric_service._check_reviewer(prod, reviewer, _enrollment_of(uuid.uuid4())) is False


def test_mock_enrollment_providers_are_unavailable_outside_dev(
    app: FastAPI, tmp_path: Path
) -> None:
    prod = make_settings(tmp_path, env="prod")
    registry = app.state.registry
    assert not biometric_service.provider_available(prod, registry, "voice")
    assert not biometric_service.provider_available(prod, registry, "face")
    assert biometric_service.provider_available(app.state.settings, registry, "voice")


@pytest.mark.parametrize(
    ("data", "container"),
    [
        (WEBM, "webm"),
        (OGG, "ogg"),
        (b"RIFF\x00\x00\x00\x00WAVEfmt ", "wav"),
        (b"\x00\x00\x00\x20ftypisom", "mp4"),
        (b"ID3\x03", "mpeg"),
        (b"\x89PNG\r\n", None),
    ],
)
def test_sniff_container(data: bytes, container: str | None) -> None:
    assert biometric_service.sniff_container(data) == container
