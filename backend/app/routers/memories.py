"""Anı uç noktaları: "EVA benim hakkımda ne biliyor?" ekranının arkası (CLAUDE.md §6.4).

Her uç nokta: giriş zorunlu + sahiplik kontrolü + girdi doğrulama + istek sınırı (§2.5).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limited
from app.core.security import CurrentUser
from app.database import get_db
from app.models.persona import Persona
from app.models.user import User
from app.schemas.memory import MemoryCreate, MemoryKind, MemoryOut, MemoryUpdate
from app.services import memory_service
from app.services.persona_service import PersonaNotFoundError

router = APIRouter(
    prefix="/memories",
    tags=["memories"],
    dependencies=[Depends(rate_limited("default", "rate_limit_default_per_minute"))],
)

DB = Annotated[AsyncSession, Depends(get_db)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")


async def _persona(db: AsyncSession, user: User, persona_id: uuid.UUID | None) -> Persona:
    try:
        return await memory_service.resolve_persona(db, user, persona_id)
    except PersonaNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Persona not found") from exc


@router.get("", response_model=list[MemoryOut])
async def list_memories(
    user: CurrentUser,
    db: DB,
    persona_id: uuid.UUID | None = None,
    kind: MemoryKind | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> list[MemoryOut]:
    persona = await _persona(db, user, persona_id)
    memories = await memory_service.list_memories(
        db, user, persona, kind=kind, limit=limit, offset=offset
    )
    return [MemoryOut.model_validate(m) for m in memories]


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
async def add_memory(body: MemoryCreate, user: CurrentUser, db: DB) -> MemoryOut:
    persona = await _persona(db, user, body.persona_id)
    data = memory_service.MemoryInput(
        kind=body.kind,
        content=body.content,
        occurred_on=body.occurred_on,
        people=body.people,
        emotion=body.emotion,
        sensitivity=body.sensitivity,
    )
    try:
        memory = await memory_service.add_memory(
            db, user, persona, data, source=memory_service.source_for(persona, user)
        )
    except memory_service.MemoryLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Memory limit reached"
        ) from exc
    return MemoryOut.model_validate(memory)


@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: uuid.UUID, body: MemoryUpdate, user: CurrentUser, db: DB
) -> MemoryOut:
    sent = body.model_fields_set
    patch = memory_service.MemoryPatch(
        kind=body.kind,
        content=body.content,
        occurred_on=body.occurred_on,
        clear_occurred_on="occurred_on" in sent and body.occurred_on is None,
        people=body.people,
        emotion=body.emotion,
        clear_emotion="emotion" in sent and body.emotion is None,
        sensitivity=body.sensitivity,
        legacy_scope=body.legacy_scope,
    )
    try:
        memory = await memory_service.update_memory(db, user, memory_id, patch)
    except memory_service.MemoryNotFoundError as exc:
        raise _not_found() from exc
    return MemoryOut.model_validate(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget_memory(memory_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    try:
        await memory_service.forget_memory(db, user, memory_id)
    except memory_service.MemoryNotFoundError as exc:
        raise _not_found() from exc
