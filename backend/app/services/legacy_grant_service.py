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

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.database import utcnow
from app.legacy import keys
from app.models.call import CallSession
from app.models.conversation import Conversation
from app.models.legacy import LegacyAccess, LegacyGrant, LegacyRedeemFailure
from app.models.memory import Memory
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
                (
                    (LegacyGrant.status == "redeemed")
                    & LegacyGrant.id.in_(
                        select(LegacyAccess.grant_id).where(LegacyAccess.status == "active")
                    )
                )
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
    if not (await legacy_service.familiarity(db, settings, owner.id)).ready:
        raise LegacyGrantError("legacy_not_enough_data")
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
    # Aynı kişi aynı Miras'ı daha önce açıp kapatmışsa (ya da hâlâ açıksa) eskisi yerini yeniye
    # bırakır: alıcının listesinde tek kayıt görünür.
    await db.execute(
        update(LegacyAccess)
        .where(
            LegacyAccess.recipient_id == user.id,
            LegacyAccess.persona_id == grant.persona_id,
            LegacyAccess.status != "deleted",
        )
        .values(status="replaced", ended_at=now)
        .execution_options(synchronize_session=False)
    )
    access = LegacyAccess(
        grant_id=grant.id,
        recipient_id=user.id,
        persona_id=grant.persona_id,
        status="active",
        mode=grant.mode,
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


# --- iptal (adım 9) ve alıcının kendi listesi (adım 8) ---------------------------------


class GrantNotFoundError(LookupError):
    pass


async def _end_calls(
    db: AsyncSession, user_id: uuid.UUID, persona_id: uuid.UUID, reason: str
) -> None:
    conversations = select(Conversation.id).where(
        Conversation.user_id == user_id, Conversation.persona_id == persona_id
    )
    await db.execute(
        update(CallSession)
        .where(
            CallSession.user_id == user_id,
            CallSession.conversation_id.in_(conversations),
            CallSession.status != "ended",
        )
        .values(status="ended", ended_at=utcnow(), end_reason=reason)
        .execution_options(synchronize_session=False)
    )


async def revoke_grant(db: AsyncSession, owner: User, grant_id: uuid.UUID) -> LegacyGrant:
    """Sahip anahtarı ya da açılmış erişimi kapatır. Etkisi anında: anahtar artık kullanılamaz,
    alıcının sohbeti ve görüşmesi bir sonraki turda durur, açık görüşmeleri burada biter."""
    grant = await db.get(LegacyGrant, grant_id)
    if grant is None or grant.owner_id != owner.id:
        raise GrantNotFoundError(str(grant_id))
    if grant.status == "revoked":
        return grant
    now = utcnow()
    grant.status = "revoked"
    grant.revoked_at = now
    access = await db.scalar(select(LegacyAccess).where(LegacyAccess.grant_id == grant.id))
    if access is not None and access.status == "active":
        access.status = "revoked"
        access.ended_at = now
        await _end_calls(db, access.recipient_id, access.persona_id, "legacy_revoked")
    audit.record(
        db,
        action="legacy.revoked",
        target_type="legacy_grant",
        target_id=grant.id,
        user_id=owner.id,
        actor_id=owner.id,
        meta={"had_access": access is not None},
    )
    await db.commit()
    return grant


@dataclass(frozen=True, slots=True)
class SharedLegacy:
    access: LegacyAccess
    owner_name: str


async def shared_with_me(db: AsyncSession, user: User) -> list[SharedLegacy]:
    rows = await db.execute(
        select(LegacyAccess, Persona.name)
        .join(Persona, Persona.id == LegacyAccess.persona_id)
        .where(
            LegacyAccess.recipient_id == user.id,
            LegacyAccess.status.not_in(("deleted", "replaced")),
        )
        .order_by(LegacyAccess.created_at.desc())
    )
    return [SharedLegacy(access=a, owner_name=name) for a, name in rows.all()]


async def _own_access(db: AsyncSession, user: User, access_id: uuid.UUID) -> LegacyAccess:
    access = await db.get(LegacyAccess, access_id)
    if access is None or access.recipient_id != user.id or access.status == "deleted":
        raise GrantNotFoundError(str(access_id))
    return access


async def archive_access(db: AsyncSession, user: User, access_id: uuid.UUID) -> LegacyAccess:
    """Alıcı Miras'ı arşivler (veda): konuşma kapanır, geçmişi silinmez."""
    access = await _own_access(db, user, access_id)
    if access.status == "active":
        access.status = "archived"
        access.ended_at = utcnow()
        await _end_calls(db, user.id, access.persona_id, "legacy_archived")
        audit.record(
            db,
            action="legacy.archived",
            target_type="legacy_access",
            target_id=access.id,
            user_id=user.id,
            actor_id=user.id,
        )
        await db.commit()
    return access


async def delete_access(db: AsyncSession, user: User, access_id: uuid.UUID) -> None:
    """Alıcı (yaşarken paylaşılan) Miras'ı kendi tarafından siler: kendi konuşmaları ve kendi
    anıları da gider. Sahibin personası ve diğer alıcılar etkilenmez. Vefat sonrası Miras bu yoldan
    silinemez; e-posta onaylı akış gerekir (``start_posthumous_delete``)."""
    access = await _own_access(db, user, access_id)
    if access.mode == "posthumous":
        raise LegacyGrantError("confirmation_required")
    await _end_calls(db, user.id, access.persona_id, "legacy_deleted")
    await db.execute(
        delete(Memory).where(Memory.user_id == user.id, Memory.persona_id == access.persona_id)
    )
    await db.execute(
        delete(Conversation).where(
            Conversation.user_id == user.id, Conversation.persona_id == access.persona_id
        )
    )
    access.status = "deleted"
    access.ended_at = access.ended_at or utcnow()
    audit.record(
        db,
        action="legacy.deleted_by_recipient",
        target_type="legacy_access",
        target_id=access.id,
        user_id=user.id,
        actor_id=user.id,
    )
    await db.commit()


# --- vefat sonrası Miras'ın silinmesi (ADR 0011) ---------------------------------------


async def start_posthumous_delete(
    db: AsyncSession, deps: password_auth_service.Deps, user: User, access_id: uuid.UUID
) -> RedeemStarted:
    """Arayüzdeki üç onaydan sonra: anahtarın geldiği e-postaya silme kodu gider."""
    access = await _own_access(db, user, access_id)
    if access.mode != "posthumous" or access.status != "active":
        raise GrantNotFoundError(str(access_id))
    grant = await db.get(LegacyGrant, access.grant_id)
    if grant is None:  # pragma: no cover - yabancı anahtar bunu garanti eder
        raise GrantNotFoundError(str(access_id))
    flow_id = await password_auth_service.issue_code(
        db,
        deps,
        purpose="legacy_delete",
        email=grant.recipient_email,
        locale=user.locale,
        user_id=user.id,
        payload={"access_id": str(access.id)},
        template="legacy_delete_code",
    )
    return RedeemStarted(flow_id=flow_id, email_hint=mask_email(grant.recipient_email))


async def finish_posthumous_delete(
    db: AsyncSession, user: User, access_id: uuid.UUID, flow_id: uuid.UUID, code: str
) -> LegacyAccess:
    """Kod doğruysa yalnızca bu alıcının erişimi kapanır. Persona, yayınlanmış sürüm ve alıcının
    geçmişi silinmez: karakter sistemde yaşamaya devam eder; geri getirmek için destek ekibi
    (admin) ``restore_access`` kullanır."""
    try:
        row = await password_auth_service.check_code(db, flow_id, "legacy_delete", code)
    except AuthFailedError as exc:
        raise RedeemFailedError("code") from exc
    if row.user_id != user.id or row.payload.get("access_id") != str(access_id):
        raise RedeemFailedError("flow_mismatch")
    access = await _own_access(db, user, access_id)
    if access.mode != "posthumous" or access.status != "active":
        raise GrantNotFoundError(str(access_id))
    access.status = "deleted"
    access.ended_at = utcnow()
    await _end_calls(db, user.id, access.persona_id, "legacy_deleted")
    audit.record(
        db,
        action="legacy.deleted_by_recipient",
        target_type="legacy_access",
        target_id=access.id,
        user_id=user.id,
        actor_id=user.id,
        meta={"mode": "posthumous", "kept": True},
    )
    await db.commit()
    return access


async def restore_access(db: AsyncSession, admin: User, access_id: uuid.UUID) -> LegacyAccess:
    """Destek: alıcının sildiği vefat sonrası Miras'ı geri getirir (alıcı bizimle iletişime
    geçtiğinde)."""
    access = await db.get(LegacyAccess, access_id)
    if access is None or access.mode != "posthumous" or access.status != "deleted":
        raise GrantNotFoundError(str(access_id))
    access.status = "active"
    access.ended_at = None
    audit.record(
        db,
        action="legacy.access_restored",
        target_type="legacy_access",
        target_id=access.id,
        user_id=access.recipient_id,
        actor_id=admin.id,
    )
    await db.commit()
    return access
