"""Miras uçları (Faz 5, ADR 0010): sahibin kişilik taslağı, önizleme durumu ve yayın. Anahtar
ve alıcı uçları sonraki adımlarda eklenir."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import CurrentUser, SteppedUpUser
from app.database import get_db
from app.models.legacy import LegacyGrant
from app.models.persona import Persona
from app.models.user import User
from app.schemas.legacy import (
    LegacyConsentTextOut,
    LegacyDraftIn,
    LegacyGrantCreate,
    LegacyGrantCreatedOut,
    LegacyGrantOut,
    LegacyPersonaOut,
    LegacyPublishOut,
    LegacyRedeemedOut,
    LegacyRedeemIn,
    LegacyRedeemStartedOut,
    LegacyRedeemVerifyIn,
)
from app.services import legacy_grant_service, legacy_service, password_auth_service

router = APIRouter(prefix="/legacy", tags=["legacy"])

DB = Annotated[AsyncSession, Depends(get_db)]
default_limit = Depends(rate_limited("default", "rate_limit_default_per_minute"))
# Taslak arka planda pahalı bir model çağrısı yapar: sıkı sınır.
synthesis_limit = Depends(rate_limited("legacy_synthesis", "rate_limit_call_per_minute"))
# Anahtar uçları sıkı: tahmin denemelerine karşı (hesap başına ayrıca 24 saat kilit var).
grant_limit = Depends(rate_limited("legacy_grant", "rate_limit_call_per_minute"))
redeem_limit = Depends(rate_limited("legacy_redeem", "rate_limit_call_per_minute"))


async def _out(db: AsyncSession, persona: Persona, user: User) -> LegacyPersonaOut:
    v = legacy_service.view(persona)
    d = v.definition
    media = await legacy_service.media_readiness(db, user.id)
    published = (persona.policy or {}).get("published_version")
    return LegacyPersonaOut(
        id=persona.id,
        name=persona.name,
        status=v.status,
        has_draft=v.has_draft,
        identity=d.identity if v.has_draft else "",
        personality=d.personality if v.has_draft else "",
        speaking_style=d.speaking_style if v.has_draft else "",
        example_dialogs=d.example_dialogs if v.has_draft else [],
        included_memories=len(await legacy_service.scope_memories(db, user.id)),
        voice_ready=media.voice,
        face_ready=media.face,
        published_version=published if isinstance(published, int) else None,
    )


@router.get("/persona", response_model=LegacyPersonaOut, dependencies=[default_limit])
async def get_persona(user: CurrentUser, db: DB) -> LegacyPersonaOut:
    persona = await legacy_service.get_or_create_persona(db, user)
    return await _out(db, persona, user)


@router.post(
    "/persona/synthesize",
    response_model=LegacyPersonaOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[synthesis_limit],
)
async def synthesize(user: CurrentUser, db: DB) -> LegacyPersonaOut:
    """Taslağı (yeniden) yazdırır. Sonuç işçide hazırlanır; durum ``GET /legacy/persona``'da."""
    persona = await legacy_service.request_synthesis(db, user)
    return await _out(db, persona, user)


@router.put("/persona", response_model=LegacyPersonaOut, dependencies=[default_limit])
async def update_persona(body: LegacyDraftIn, user: CurrentUser, db: DB) -> LegacyPersonaOut:
    persona = await legacy_service.get_or_create_persona(db, user)
    persona = await legacy_service.update_draft(
        db,
        persona,
        identity=body.identity,
        personality=body.personality,
        speaking_style=body.speaking_style,
        example_dialogs=body.example_dialogs,
    )
    return await _out(db, persona, user)


@router.post(
    "/persona/publish",
    response_model=LegacyPublishOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[default_limit],
    responses={403: {"description": "step_up_required"}, 409: {"description": "not ready"}},
)
async def publish(user: SteppedUpUser, db: DB) -> LegacyPublishOut:
    """Alıcıların konuşacağı sürümü dondurur. Adım-yukarı doğrulama, taslak, onaylı ses ve yüz
    gerekir."""
    persona = await legacy_service.get_or_create_persona(db, user)
    try:
        version = await legacy_service.publish(db, persona, user)
    except legacy_service.LegacyNotReadyError as exc:
        raise HTTPException(exc.status, exc.code) from exc
    return LegacyPublishOut(
        version=version.version,
        memories=len(version.definition.get("canon_memories", [])),
    )


# --- anahtar: sahip tarafı (adım 6) ------------------------------------------------------


def _deps(request: Request) -> password_auth_service.Deps:
    return password_auth_service.Deps(
        messaging=request.app.state.registry.messaging(),
        limiter=request.app.state.rate_limiter,
    )


def _grant_out(grant: LegacyGrant) -> LegacyGrantOut:
    return LegacyGrantOut(
        id=grant.id,
        recipient_email=grant.recipient_email,
        status=legacy_grant_service.effective_status(grant),
        created_at=grant.created_at,
        expires_at=grant.expires_at,
        redeemed_at=grant.redeemed_at,
    )


@router.get("/consent-text", response_model=LegacyConsentTextOut, dependencies=[default_limit])
async def consent_text(user: CurrentUser) -> LegacyConsentTextOut:
    texts = legacy_grant_service.CONSENT_TEXT
    return LegacyConsentTextOut(
        version=legacy_grant_service.CONSENT_VERSION,
        text=texts.get(user.locale, texts["tr"]),
    )


@router.get("/grants", response_model=list[LegacyGrantOut], dependencies=[default_limit])
async def list_grants(user: CurrentUser, db: DB) -> list[LegacyGrantOut]:
    return [_grant_out(g) for g in await legacy_grant_service.list_grants(db, user)]


@router.post(
    "/grants",
    response_model=LegacyGrantCreatedOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[grant_limit],
    responses={403: {"description": "step_up_required"}, 409: {"description": "not ready"}},
)
async def create_grant(
    request: Request, body: LegacyGrantCreate, user: SteppedUpUser, db: DB
) -> LegacyGrantCreatedOut:
    """Anahtarı üretir ve alıcıya e-postayla gönderir. Anahtar bu cevapta bir kez görünür."""
    try:
        created = await legacy_grant_service.create_grant(
            db,
            request.app.state.settings,
            _deps(request),
            request.app.state.legacy_pepper,
            user,
            recipient_email=str(body.recipient_email),
            consent_text_version=body.consent_text_version,
        )
    except legacy_grant_service.LegacyGrantError as exc:
        raise HTTPException(exc.status, exc.code) from exc
    return LegacyGrantCreatedOut(**_grant_out(created.grant).model_dump(), key=created.key)


# --- anahtar: alıcı tarafı (adım 7) ------------------------------------------------------

_INVALID = "invalid_or_expired"


@router.post(
    "/redeem",
    response_model=LegacyRedeemStartedOut,
    dependencies=[redeem_limit],
    responses={400: {"description": _INVALID}, 429: {"description": "too_many_attempts"}},
)
async def redeem(
    request: Request, body: LegacyRedeemIn, user: CurrentUser, db: DB
) -> LegacyRedeemStartedOut:
    """Anahtar doğruysa anahtarın gönderildiği e-postaya kod gider. Her hata aynı görünür."""
    try:
        started = await legacy_grant_service.start_redeem(
            db,
            request.app.state.settings,
            _deps(request),
            request.app.state.legacy_pepper,
            user,
            body.key,
        )
    except legacy_grant_service.RedeemLockedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too_many_attempts") from exc
    except legacy_grant_service.RedeemFailedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _INVALID) from exc
    return LegacyRedeemStartedOut(flow_id=started.flow_id, email_hint=started.email_hint)


@router.post(
    "/redeem/verify",
    response_model=LegacyRedeemedOut,
    dependencies=[redeem_limit],
    responses={400: {"description": _INVALID}, 429: {"description": "too_many_attempts"}},
)
async def redeem_verify(
    request: Request, body: LegacyRedeemVerifyIn, user: CurrentUser, db: DB
) -> LegacyRedeemedOut:
    try:
        access = await legacy_grant_service.finish_redeem(
            db, request.app.state.settings, _deps(request), user, body.flow_id, body.code
        )
    except legacy_grant_service.RedeemLockedError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too_many_attempts") from exc
    except legacy_grant_service.RedeemFailedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _INVALID) from exc
    persona = await db.get(Persona, access.persona_id)
    return LegacyRedeemedOut(
        persona_id=access.persona_id, owner_name=persona.name if persona else ""
    )
