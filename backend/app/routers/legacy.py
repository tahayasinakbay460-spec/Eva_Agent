"""Miras uçları (Faz 5, ADR 0010): sahibin kişilik taslağı, önizleme durumu ve yayın. Anahtar
ve alıcı uçları sonraki adımlarda eklenir."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import CurrentUser, SteppedUpUser
from app.database import get_db
from app.models.persona import Persona
from app.models.user import User
from app.schemas.legacy import LegacyDraftIn, LegacyPersonaOut, LegacyPublishOut
from app.services import legacy_service

router = APIRouter(prefix="/legacy", tags=["legacy"])

DB = Annotated[AsyncSession, Depends(get_db)]
default_limit = Depends(rate_limited("default", "rate_limit_default_per_minute"))
# Taslak arka planda pahalı bir model çağrısı yapar: sıkı sınır.
synthesis_limit = Depends(rate_limited("legacy_synthesis", "rate_limit_call_per_minute"))


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
