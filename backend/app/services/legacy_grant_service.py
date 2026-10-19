"""Miras anahtarı: oluşturma, teslim ve kullanma (CLAUDE.md §8.3, ADR 0010, tehdit modeli §6).

Oluşturma (sahip): adım-yukarı + Miras rızası + yayınlanmış sürüm + onaylı ses ve yüz → anahtar
üretilir, yalnızca özeti saklanır, alıcıya sabit şablonlu e-postayla gider ve sahibe **bir kez**
gösterilir.

Kullanma (alıcı, iki faktör): kendi hesabıyla anahtarı yazar → anahtarın gönderildiği e-postaya
6 haneli kod gider → kodu girince erişim açılır, anahtar tükenir, sahibe bildirim gider.
Her hata dışarıya aynı görünür (``invalid_or_expired``); art arda hatalar hesabı kilitler.
"""

import hmac
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.database import utcnow
from app.legacy import keys
from app.models.legacy import LegacyAccess, LegacyGrant, LegacyRedeemFailure
from app.models.persona import Persona
from app.models.user import User
from app.services import audit, legacy_service, password_auth_service
from app.services.auth_service import AuthFailedError

# Sahibin onayladığı Miras rıza metni (amaç: legacy_share, §11.3). Metin değişirse sürüm değişir.
CONSENT_VERSION = "2026-10-19"
CONSENT_TEXT = {
    "tr": (
        "Miras'ımı bu kişiyle paylaşıyorum. Miras'a dahil ettiğim anılarım, kişiliğim, klon "
        "sesim ve yüz fotoğrafım, bu kişi anahtarı kullandığında onunla konuşan Miras "
        "personamda kullanılacak. Erişimi istediğim an kapatabilirim."
    ),
    "en": (
        "I am sharing my Legacy with this person. The memories I included, my personality, my "
        "cloned voice and my face photo will be used by my Legacy persona when this person "
        "uses the key. I can close their access at any time."
    ),
}

OPEN_STATUSES = ("pending", "redeemed")


class LegacyGrantError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class RedeemFailedError(Exception):
    """Dışarıya her zaman aynı: ``invalid_or_expired``. Sebep yalnızca içeride."""


class RedeemLockedError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CreatedGrant:
    grant: LegacyGrant
    key: str  # yalnızca bu cevapta; bir daha hiçbir yerde yok


@dataclass(frozen=True, slots=True)
class RedeemStarted:
    flow_id: uuid.UUID
    email_hint: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


def mask_email(email: str) -> str:
    """``ayse@ornek.com`` -> ``a***@ornek.com`` (kodun nereye gittiğini hatırlatmak için)."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


GrantStatus = Literal["pending", "redeemed", "revoked", "expired"]


def effective_status(grant: LegacyGrant) -> GrantStatus:
    if grant.status == "pending" and grant.expires_at <= utcnow():
        return "expired"
    if grant.status in ("pending", "redeemed", "revoked"):
        return grant.status  # type: ignore[return-value]
    return "revoked"


# --- sahip tarafı ----------------------------------------------------------------------


async def list_grants(db: AsyncSession, owner: User) -> list[LegacyGrant]:
    result = await db.execute(
        select(LegacyGrant)
        .where(LegacyGrant.owner_id == owner.id)
        .order_by(LegacyGrant.created_at.desc())
    )
    return list(result.scalars())


async def _open_grant_count(db: AsyncSession, owner_id: uuid.UUID) -> int:
    now = utcnow()
    count = await db.scalar(
        select(func.count())
        .select_from(LegacyGrant)
        .where(
            LegacyGrant.owner_id == owner_id,
            (
                (LegacyGrant.status == "redeemed")
                | ((LegacyGrant.status == "pending") & (LegacyGrant.expires_at > now))
            ),
        )
    )
    return int(count or 0)


async def create_grant(
    db: AsyncSession,
    settings: Settings,
    deps: password_auth_service.Deps,
    pepper: bytes,
    owner: User,
    *,
    recipient_email: str,
    consent_text_version: str,
) -> CreatedGrant:
    if consent_text_version != CONSENT_VERSION:
        raise LegacyGrantError("consent_text_outdated")
    persona = await legacy_service.get_persona(db, owner)
    if persona is None or await legacy_service.latest_version(db, persona.id) is None:
        raise LegacyGrantError("legacy_not_published")
    media = await legacy_service.media_readiness(db, owner.id)
    if not media.voice:
        raise LegacyGrantError("legacy_voice_missing")
    if not media.face:
        raise LegacyGrantError("legacy_face_missing")
    email = normalize_email(recipient_email)
    if owner.email and normalize_email(owner.email) == email:
        raise LegacyGrantError("recipient_is_owner", status=422)
    if await _open_grant_count(db, owner.id) >= settings.legacy_max_grants:
        raise LegacyGrantError("legacy_grant_limit")

    key = keys.generate_key()
    now = utcnow()
    grant = LegacyGrant(
        owner_id=owner.id,
        persona_id=persona.id,
        recipient_email=email,
        key_digest=keys.digest(pepper, key),
        status="pending",
        consent_text_version=consent_text_version,
        created_at=now,
        expires_at=now + timedelta(days=settings.legacy_key_ttl_days),
    )
    db.add(grant)
    await db.flush()
    # Kayıt hem rıza kanıtı hem iz: kim, ne zaman, hangi metin sürümü. Anahtar ve e-posta yok.
    audit.record(
        db,
        action="legacy.created",
        target_type="legacy_grant",
        target_id=grant.id,
        user_id=owner.id,
        actor_id=owner.id,
        meta={"consent_text_version": consent_text_version},
    )
    await db.commit()

    await password_auth_service.send_message(
        deps,
        email=email,
        locale=owner.locale,
        template="legacy_key_delivery",
        params={
            "owner_name": owner.display_name,
            "key": key,
            "link": f"{settings.web_url.rstrip('/')}/miras/anahtar",
            "expires_on": grant.expires_at.date().isoformat(),
        },
        limited=False,
    )
    audit.record(
        db,
        action="legacy.sent",
        target_type="legacy_grant",
        target_id=grant.id,
        user_id=owner.id,
        actor_id=owner.id,
        meta={"channel": "email"},
    )
    await db.commit()
    return CreatedGrant(grant=grant, key=key)


# --- alıcı tarafı ----------------------------------------------------------------------


async def _locked(db: AsyncSession, settings: Settings, user: User) -> bool:
    since = utcnow() - timedelta(seconds=settings.legacy_redeem_lockout_s)
    failures = await db.scalar(
        select(func.count())
        .select_from(LegacyRedeemFailure)
        .where(LegacyRedeemFailure.user_id == user.id, LegacyRedeemFailure.created_at > since)
    )
    return int(failures or 0) >= settings.legacy_redeem_max_failures


async def _fail(
    db: AsyncSession, user: User, reason: str, grant_id: uuid.UUID | None = None
) -> RedeemFailedError:
    db.add(LegacyRedeemFailure(user_id=user.id))
    audit.record(
        db,
        action="legacy.redeem_failed",
        target_type="legacy_grant",
        target_id=grant_id,
        user_id=user.id,
        actor_id=user.id,
        meta={"reason": reason},
    )
    await db.commit()
    return RedeemFailedError(reason)


async def _usable_grant(db: AsyncSession, digest: str, user: User) -> LegacyGrant | None:
    grant = await db.scalar(select(LegacyGrant).where(LegacyGrant.key_digest == digest))
    if grant is None or not hmac.compare_digest(grant.key_digest, digest):
        return None
    if effective_status(grant) != "pending" or grant.owner_id == user.id:
        return None
    return grant


async def start_redeem(
    db: AsyncSession,
    settings: Settings,
    deps: password_auth_service.Deps,
    pepper: bytes,
    user: User,
    raw_key: str,
) -> RedeemStarted:
    if await _locked(db, settings, user):
        raise RedeemLockedError
    try:
        digest = keys.digest(pepper, raw_key)
    except keys.InvalidKeyFormatError as exc:
        raise await _fail(db, user, "format") from exc
    grant = await _usable_grant(db, digest, user)
    if grant is None:
        raise await _fail(db, user, "unknown_or_unusable")
    flow_id = await password_auth_service.issue_code(
        db,
        deps,
        purpose="legacy",
        email=grant.recipient_email,
        locale=user.locale,
        user_id=user.id,
        payload={"grant_id": str(grant.id)},
        template="legacy_redeem_code",
    )
    return RedeemStarted(flow_id=flow_id, email_hint=mask_email(grant.recipient_email))


async def finish_redeem(
    db: AsyncSession,
    settings: Settings,
    deps: password_auth_service.Deps,
    user: User,
    flow_id: uuid.UUID,
    code: str,
) -> LegacyAccess:
    if await _locked(db, settings, user):
        raise RedeemLockedError
    try:
        row = await password_auth_service.check_code(db, flow_id, "legacy", code)
    except AuthFailedError as exc:
        raise await _fail(db, user, "code") from exc
    if row.user_id != user.id:
        # Kod başka bir hesabın akışına ait: o hesap adına anahtar kullanılamaz.
        raise await _fail(db, user, "flow_owner")
    grant = await db.get(LegacyGrant, uuid.UUID(str(row.payload.get("grant_id"))))
    if grant is None or effective_status(grant) != "pending" or grant.owner_id == user.id:
        raise await _fail(db, user, "grant_gone", grant.id if grant else None)

    # Anahtarı tek adımda tüket: aynı anda iki kullanım olamaz.
    now = utcnow()
    consumed = await db.execute(
        update(LegacyGrant)
        .where(LegacyGrant.id == grant.id, LegacyGrant.status == "pending")
        .values(status="redeemed", redeemed_at=now, redeemed_by=user.id)
        .execution_options(synchronize_session=False)
    )
    if consumed.rowcount != 1:  # type: ignore[attr-defined]
        await db.rollback()
        raise await _fail(db, user, "consumed_concurrently", grant.id)
    access = LegacyAccess(
        grant_id=grant.id, recipient_id=user.id, persona_id=grant.persona_id, status="active"
    )
    db.add(access)
    audit.record(
        db,
        action="legacy.redeemed",
        target_type="legacy_grant",
        target_id=grant.id,
        user_id=grant.owner_id,
        actor_id=user.id,
    )
    await db.commit()

    owner = await db.get(User, grant.owner_id)
    if owner is not None and owner.email:
        await password_auth_service.send_message(
            deps,
            email=owner.email,
            locale=owner.locale,
            template="legacy_key_used",
            params={"recipient_email": grant.recipient_email},
            limited=False,
        )
    return access


async def active_access(db: AsyncSession, user: User, persona: Persona) -> LegacyAccess | None:
    return await db.scalar(
        select(LegacyAccess).where(
            LegacyAccess.recipient_id == user.id,
            LegacyAccess.persona_id == persona.id,
            LegacyAccess.status == "active",
        )
    )
