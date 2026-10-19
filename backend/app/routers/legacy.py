"""Miras uçları (Faz 5, ADR 0010). Şimdilik sahibin kişilik taslağı; anahtar ve alıcı uçları
sonraki adımlarda eklenir."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import CurrentUser
from app.database import get_db
from app.schemas.legacy import LegacyDraftIn, LegacyPersonaOut
from app.services import legacy_service

router = APIRouter(prefix="/legacy", tags=["legacy"])

DB = Annotated[AsyncSession, Depends(get_db)]
default_limit = Depends(rate_limited("default", "rate_limit_default_per_minute"))
# Taslak arka planda pahalı bir model çağrısı yapar: sıkı sınır.
synthesis_limit = Depends(rate_limited("legacy_synthesis", "rate_limit_call_per_minute"))


def _out(v: legacy_service.LegacyPersonaView) -> LegacyPersonaOut:
    d = v.definition
    return LegacyPersonaOut(
        id=v.persona.id,
        name=v.persona.name,
        status=v.status,
        has_draft=v.has_draft,
        identity=d.identity if v.has_draft else "",
        personality=d.personality if v.has_draft else "",
        speaking_style=d.speaking_style if v.has_draft else "",
        example_dialogs=d.example_dialogs if v.has_draft else [],
    )


@router.get("/persona", response_model=LegacyPersonaOut, dependencies=[default_limit])
async def get_persona(user: CurrentUser, db: DB) -> LegacyPersonaOut:
    persona = await legacy_service.get_or_create_persona(db, user)
    return _out(legacy_service.view(persona))


@router.post(
    "/persona/synthesize",
    response_model=LegacyPersonaOut,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[synthesis_limit],
)
async def synthesize(user: CurrentUser, db: DB) -> LegacyPersonaOut:
    """Taslağı (yeniden) yazdırır. Sonuç işçide hazırlanır; durum ``GET /legacy/persona``'da."""
    persona = await legacy_service.request_synthesis(db, user)
    return _out(legacy_service.view(persona))


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
    return _out(legacy_service.view(persona))
