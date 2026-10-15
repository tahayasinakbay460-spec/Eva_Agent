from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import CurrentUser
from app.database import get_db
from app.schemas.persona import PersonaOut
from app.services import persona_service

router = APIRouter(
    prefix="/personas",
    tags=["personas"],
    dependencies=[Depends(rate_limited("default", "rate_limit_default_per_minute"))],
)

DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[PersonaOut])
async def list_personas(user: CurrentUser, db: DB) -> list[PersonaOut]:
    personas = await persona_service.list_personas_for_user(db, user)
    return [PersonaOut.model_validate(p) for p in personas]
