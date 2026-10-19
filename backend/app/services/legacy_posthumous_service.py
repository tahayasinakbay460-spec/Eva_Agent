"""Vefat sonrası Miras (ADR 0011, tehdit modeli §7).

Sahip alıcılarını önceden belirler (``armed``). İki tetikleyici aynı uyarı sürecine girer:
  - hareketsizlik: 180 gündür hiç giriş yok,
  - vefat bildirimi: belirlenmiş bir alıcının belgesi admin tarafından onaylandı.
Uyarı süreci 14 gün sürer; sahibe 0., 7. ve 13. günlerde e-posta gider. Bu sürede sahip bir kez
giriş yaparsa süreç durur. Süre dolunca her alıcı için anahtar üretilir ve otomatik gönderilir.

Tarama işçide saatlik çalışır ve tekrar çalıştırılabilir: aynı uyarı ya da aynı alıcıya iki
anahtar iki kez gitmez (sayaçlar ve anahtar bağlantısı her adımda aynı commit'te yazılır).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.database import utcnow
from app.legacy import keys
from app.models.legacy import LegacyDeathReport, LegacyGrant, LegacyHeir, LegacyPosthumous
from app.models.user import User
from app.services import audit, legacy_service, password_auth_service
from app.services.biometric_service import sniff_container
from app.services.legacy_grant_service import normalize_email
from app.storage.encrypted import EncryptedStore

CONSENT_VERSION = "2026-10-19"
CONSENT_TEXT = {
    "tr": (
        "Vefatımdan sonra Miras'ımın bu kişilere ulaşmasını istiyorum. 6 ay giriş yapmazsam ya da "
        "bu kişilerden biri vefatımı belgeyle bildirir ve onaylanırsa bana 14 gün boyunca uyarı "
        "gönderilir; giriş yapmazsam anahtarlar otomatik gider. Bu kurulumu istediğim an "
        "değiştirebilir ya da kapatabilirim."
    ),
    "en": (
        "I want my Legacy to reach these people after my death. If I don't sign in for 6 months, "
        "or one of them reports my death with a document and it is approved, I will be warned "
        "for 14 days; if I don't sign in, the keys are sent automatically. I can change or turn "
        "off this setup at any time."
    ),
}

MAX_HEIRS = 5
DOCUMENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "application/pdf"})
DOCUMENT_SIZE_LIMIT = 10 * 1024 * 1024
# Saatte en çok bir kez "son etkinlik" yazılır (her istekte yazmak gereksiz yük).
ACTIVITY_WRITE_EVERY = timedelta(hours=1)


class PosthumousError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True, slots=True)
class Setup:
    state: str
    heirs: list[LegacyHeir]
    warning_started_at: datetime | None
    warnings_sent: int
    trigger: str | None


# --- sahip tarafı ----------------------------------------------------------------------


async def _row(db: AsyncSession, owner_id: uuid.UUID) -> LegacyPosthumous | None:
    return await db.scalar(select(LegacyPosthumous).where(LegacyPosthumous.owner_id == owner_id))


async def _heirs(db: AsyncSession, owner_id: uuid.UUID) -> list[LegacyHeir]:
    result = await db.scalars(
        select(LegacyHeir).where(LegacyHeir.owner_id == owner_id).order_by(LegacyHeir.created_at)
    )
    return list(result.all())


async def get_setup(db: AsyncSession, owner: User) -> Setup:
    row = await _row(db, owner.id)
    return Setup(
        state=row.state if row else "off",
        heirs=await _heirs(db, owner.id),
        warning_started_at=row.warning_started_at if row else None,
        warnings_sent=row.warnings_sent if row else 0,
        trigger=row.trigger if row else None,
    )


async def configure(
    db: AsyncSession,
    settings: Settings,
    owner: User,
    *,
    emails: list[str],
    consent_text_version: str,
) -> Setup:
    """Vefat sonrası alıcıları belirler (ya da günceller). Ön koşullar yaşarken paylaşmayla aynı:
    yayınlanmış sürüm, onaylı ses ve yüz, tanınma eşiği. Uyarılar e-postayla gideceği için
    sahibin doğrulanmış e-postası olmalı."""
    if consent_text_version != CONSENT_VERSION:
        raise PosthumousError("consent_text_outdated")
    if not owner.email or owner.email_verified_at is None:
        raise PosthumousError("legacy_email_required")
    persona = await legacy_service.get_persona(db, owner)
    if persona is None or await legacy_service.latest_version(db, persona.id) is None:
        raise PosthumousError("legacy_not_published")
    if not (await legacy_service.familiarity(db, settings, owner.id)).ready:
        raise PosthumousError("legacy_not_enough_data")
    media = await legacy_service.media_readiness(db, owner.id)
    if not (media.voice and media.face):
        raise PosthumousError("legacy_voice_missing" if not media.voice else "legacy_face_missing")
    wanted = list(dict.fromkeys(normalize_email(e) for e in emails if e.strip()))
    if not wanted:
        raise PosthumousError("legacy_heirs_required", status=422)
    if len(wanted) > MAX_HEIRS:
        raise PosthumousError("legacy_heir_limit", status=422)
    if normalize_email(owner.email) in wanted:
        raise PosthumousError("recipient_is_owner", status=422)

    row = await _row(db, owner.id)
    if row is not None and row.state == "activated":
        raise PosthumousError("legacy_already_activated")
    if row is None:
        row = LegacyPosthumous(owner_id=owner.id, warnings_sent=0)
        db.add(row)
    # Kurulumu değiştirmek de bir "buradayım" işaretidir: süren uyarı süreci durur.
    row.state = "armed"
    row.consent_text_version = consent_text_version
    row.trigger = None
    row.warning_started_at = None
    row.warnings_sent = 0

    current = {h.email: h for h in await _heirs(db, owner.id)}
    for email, heir in current.items():
        if email not in wanted:
            await db.delete(heir)
    for email in wanted:
        if email not in current:
            db.add(LegacyHeir(owner_id=owner.id, email=email))
    audit.record(
        db,
        action="legacy.posthumous_configured",
        target_type="legacy_posthumous",
        target_id=None,
        user_id=owner.id,
        actor_id=owner.id,
        meta={"heirs": len(wanted), "consent_text_version": consent_text_version},
    )
    await db.commit()
    return await get_setup(db, owner)


async def turn_off(db: AsyncSession, owner: User) -> Setup:
    row = await _row(db, owner.id)
    if row is not None and row.state == "activated":
        raise PosthumousError("legacy_already_activated")
    if row is not None:
        row.state = "off"
        row.trigger = None
        row.warning_started_at = None
        row.warnings_sent = 0
    await db.execute(delete(LegacyHeir).where(LegacyHeir.owner_id == owner.id))
    audit.record(
        db,
        action="legacy.posthumous_off",
        target_type="legacy_posthumous",
        target_id=None,
        user_id=owner.id,
        actor_id=owner.id,
    )
    await db.commit()
    return await get_setup(db, owner)


async def touch_activity(db: AsyncSession, user: User) -> None:
    """Kimlik doğrulamalı her istekte çağrılır; saatte en çok bir kez yazar. Sahip uyarı
    sürecindeyken giriş yaparsa süreç hemen durur (ADR 0011)."""
    now = utcnow()
    if user.last_active_at is not None and now - user.last_active_at < ACTIVITY_WRITE_EVERY:
        return
    user.last_active_at = now
    row = await _row(db, user.id)
    if row is not None and row.state == "warning":
        row.state = "armed"
        row.trigger = None
        row.warning_started_at = None
        row.warnings_sent = 0
        audit.record(
            db,
            action="legacy.warning_cancelled",
            target_type="legacy_posthumous",
            target_id=row.id,
            user_id=user.id,
            actor_id=user.id,
        )
    await db.commit()


# --- tarama (işçi) ----------------------------------------------------------------------


def _start_warning(row: LegacyPosthumous, trigger: str, now: datetime) -> None:
    row.state = "warning"
    row.trigger = trigger
    row.warning_started_at = now
    row.warnings_sent = 0


async def sweep(
    db: AsyncSession,
    settings: Settings,
    deps: password_auth_service.Deps,
    pepper: bytes,
    *,
    now: datetime | None = None,
) -> None:
    now = now or utcnow()
    inactive_before = now - timedelta(days=settings.legacy_inactivity_days)

    # 1) Hareketsizlik: kurulu ve 180 gündür giriş yok -> uyarı süreci.
    armed = await db.execute(
        select(LegacyPosthumous, User)
        .join(User, User.id == LegacyPosthumous.owner_id)
        .where(
            LegacyPosthumous.state == "armed",
            or_(
                User.last_active_at < inactive_before,
                User.last_active_at.is_(None) & (User.created_at < inactive_before),
            ),
        )
    )
    for row, owner in armed.all():
        _start_warning(row, "inactivity", now)
        audit.record(
            db,
            action="legacy.warning_started",
            target_type="legacy_posthumous",
            target_id=row.id,
            user_id=owner.id,
            actor_id=None,
            meta={"trigger": "inactivity"},
        )
    await db.commit()

    # 2) Uyarılar ve etkinleşme.
    warning = await db.execute(
        select(LegacyPosthumous, User)
        .join(User, User.id == LegacyPosthumous.owner_id)
        .where(LegacyPosthumous.state == "warning")
    )
    schedule = settings.legacy_warning_schedule_days
    for row, owner in warning.all():
        started = row.warning_started_at or now
        while row.warnings_sent < len(schedule) and now >= started + timedelta(
            days=schedule[row.warnings_sent]
        ):
            days_left = max(0, (started + timedelta(days=settings.legacy_warning_days) - now).days)
            row.warnings_sent += 1
            audit.record(
                db,
                action="legacy.warning_sent",
                target_type="legacy_posthumous",
                target_id=row.id,
                user_id=owner.id,
                actor_id=None,
                meta={"n": row.warnings_sent},
            )
            # Sayaç e-postadan önce yazılır: işçi çökerse aynı uyarı iki kez gitmez.
            await db.commit()
            if owner.email:
                await password_auth_service.send_message(
                    deps,
                    email=owner.email,
                    locale=owner.locale,
                    template="legacy_posthumous_warning",
                    params={"days_left": str(days_left), "link": settings.web_url},
                    limited=False,
                )
        if row.warnings_sent >= len(schedule) and now >= started + timedelta(
            days=settings.legacy_warning_days
        ):
            await _activate(db, settings, deps, pepper, row, owner, now)


async def _activate(
    db: AsyncSession,
    settings: Settings,
    deps: password_auth_service.Deps,
    pepper: bytes,
    row: LegacyPosthumous,
    owner: User,
    now: datetime,
) -> None:
    persona = await legacy_service.get_persona(db, owner)
    if persona is None or await legacy_service.latest_version(db, persona.id) is None:
        # Yayın yoksa gönderilecek bir şey yok; kurulum yine de kapanır, iz bırakılır.
        row.state = "off"
        audit.record(
            db,
            action="legacy.activation_skipped",
            target_type="legacy_posthumous",
            target_id=row.id,
            user_id=owner.id,
            actor_id=None,
            meta={"reason": "not_published"},
        )
        await db.commit()
        return
    row.state = "activated"
    row.activated_at = now
    audit.record(
        db,
        action="legacy.activated",
        target_type="legacy_posthumous",
        target_id=row.id,
        user_id=owner.id,
        actor_id=None,
        meta={"trigger": row.trigger or "unknown"},
    )
    await db.commit()
    for heir in await _heirs(db, owner.id):
        if heir.grant_id is not None:
            continue  # bu kişiye anahtar zaten gitti
        key = keys.generate_key()
        grant = LegacyGrant(
            owner_id=owner.id,
            persona_id=persona.id,
            recipient_email=heir.email,
            key_digest=keys.digest(pepper, key),
            status="pending",
            mode="posthumous",
            consent_text_version=row.consent_text_version or CONSENT_VERSION,
            created_at=now,
            expires_at=now + timedelta(days=settings.legacy_posthumous_key_ttl_days),
        )
        db.add(grant)
        await db.flush()
        heir.grant_id = grant.id
        audit.record(
            db,
            action="legacy.sent",
            target_type="legacy_grant",
            target_id=grant.id,
            user_id=owner.id,
            actor_id=None,
            meta={"channel": "email", "mode": "posthumous"},
        )
        # Bağlantı e-postadan önce yazılır: aynı kişiye ikinci anahtar üretilmez.
        await db.commit()
        await password_auth_service.send_message(
            deps,
            email=heir.email,
            locale=owner.locale,
            template="legacy_posthumous_delivery",
            params={
                "owner_name": owner.display_name,
                "key": key,
                "link": f"{settings.web_url.rstrip('/')}/miras/anahtar",
                "expires_on": grant.expires_at.date().isoformat(),
            },
            limited=False,
        )


# --- vefat bildirimi (alıcı) ve inceleme (admin) ------------------------------------------


@dataclass(frozen=True, slots=True)
class HeirOf:
    owner_id: uuid.UUID
    owner_name: str
    state: str
    open_report: bool


async def heir_of(db: AsyncSession, user: User) -> list[HeirOf]:
    """Bu kişiyi vefat sonrası alıcı olarak belirlemiş sahipler (doğrulanmış e-postayla)."""
    if not user.email or user.email_verified_at is None:
        return []
    rows = await db.execute(
        select(LegacyHeir, User, LegacyPosthumous)
        .join(User, User.id == LegacyHeir.owner_id)
        .join(LegacyPosthumous, LegacyPosthumous.owner_id == LegacyHeir.owner_id)
        .where(
            LegacyHeir.email == normalize_email(user.email),
            LegacyPosthumous.state.in_(("armed", "warning")),
        )
    )
    out = []
    for _heir, owner, row in rows.all():
        report = await _open_report(db, owner.id, user.id)
        out.append(HeirOf(owner.id, owner.display_name, row.state, report is not None))
    return out


async def _open_report(
    db: AsyncSession, owner_id: uuid.UUID, reporter_id: uuid.UUID
) -> LegacyDeathReport | None:
    return await db.scalar(
        select(LegacyDeathReport).where(
            LegacyDeathReport.owner_id == owner_id,
            LegacyDeathReport.reporter_id == reporter_id,
            LegacyDeathReport.status == "pending",
        )
    )


async def submit_report(
    db: AsyncSession,
    store: EncryptedStore,
    reporter: User,
    owner_id: uuid.UUID,
    *,
    media_type: str,
    data: bytes,
) -> LegacyDeathReport:
    if not any(h.owner_id == owner_id for h in await heir_of(db, reporter)):
        # Belirlenmiş alıcı değilse (ya da kurulum yoksa) "yok" sayılır.
        raise PosthumousError("not_found", status=404)
    if not data:
        raise PosthumousError("file_empty", status=422)
    if len(data) > DOCUMENT_SIZE_LIMIT:
        raise PosthumousError("file_too_large", status=413)
    if media_type not in DOCUMENT_TYPES:
        raise PosthumousError("unsupported_media_type", status=415)
    sniffed = "pdf" if data[:5] == b"%PDF-" else sniff_container(data)
    if sniffed != media_type.split("/", 1)[1]:
        raise PosthumousError("media_type_mismatch", status=415)
    if await _open_report(db, owner_id, reporter.id) is not None:
        raise PosthumousError("report_already_open")

    report_id = uuid.uuid4()
    blob_key = f"{reporter.id}/death-reports/{report_id}"
    await store.put(db, reporter.id, "media", blob_key, data)
    report = LegacyDeathReport(
        id=report_id,
        owner_id=owner_id,
        reporter_id=reporter.id,
        blob_key=blob_key,
        media_type=media_type,
        status="pending",
    )
    db.add(report)
    audit.record(
        db,
        action="legacy.death_reported",
        target_type="legacy_death_report",
        target_id=report_id,
        user_id=owner_id,
        actor_id=reporter.id,
    )
    await db.commit()
    return report


async def pending_reports(db: AsyncSession) -> list[tuple[LegacyDeathReport, str, str]]:
    rows = await db.execute(
        select(LegacyDeathReport, User.display_name)
        .join(User, User.id == LegacyDeathReport.owner_id)
        .where(LegacyDeathReport.status == "pending")
        .order_by(LegacyDeathReport.created_at)
    )
    out = []
    for report, owner_name in rows.all():
        reporter = await db.get(User, report.reporter_id)
        out.append((report, owner_name, reporter.display_name if reporter else ""))
    return out


async def report_document(
    db: AsyncSession, store: EncryptedStore, admin: User, report_id: uuid.UUID
) -> tuple[bytes, str]:
    report = await db.get(LegacyDeathReport, report_id)
    if report is None:
        raise PosthumousError("not_found", status=404)
    data = await store.get(db, report.reporter_id, "media", report.blob_key)
    audit.record(
        db,
        action="legacy.death_report_viewed",
        target_type="legacy_death_report",
        target_id=report.id,
        user_id=report.owner_id,
        actor_id=admin.id,
    )
    await db.commit()
    return data, report.media_type


async def decide_report(
    db: AsyncSession, admin: User, report_id: uuid.UUID, *, approve: bool
) -> LegacyDeathReport:
    report = await db.get(LegacyDeathReport, report_id)
    if report is None or report.status != "pending":
        raise PosthumousError("not_found", status=404)
    report.status = "approved" if approve else "rejected"
    report.reviewer_id = admin.id
    report.reviewed_at = utcnow()
    if approve:
        row = await _row(db, report.owner_id)
        if row is not None and row.state == "armed":
            # Onay bile Miras'ı hemen açmaz: sahibe 14 günlük uyarı süreci başlar.
            _start_warning(row, "death_report", utcnow())
    audit.record(
        db,
        action="legacy.death_report_approved" if approve else "legacy.death_report_rejected",
        target_type="legacy_death_report",
        target_id=report.id,
        user_id=report.owner_id,
        actor_id=admin.id,
    )
    await db.commit()
    return report
