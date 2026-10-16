"""Anılar: ekleme, listeleme, düzenleme, silme (CLAUDE.md §6).

Güvenlik kuralı (§6.5): her sorgu hem ``user_id`` hem ``persona_id`` ile yapılır.
Başkasının anısının ID'sini bilsen bile ona ulaşamazsın; sistem "böyle bir anı yok" der.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.models.persona import Persona
from app.models.user import User
from app.services import persona_service

# Bir kullanıcının bir persona için tutabileceği en fazla anı sayısı (kötüye kullanıma karşı).
MAX_MEMORIES_PER_PERSONA = 5000
# Kullanıcının kendi eklediği anı, otomatik çıkarılandan biraz daha önemli sayılır:
# madem uğraşıp eklemiş, onun için değerli.
USER_ADDED_IMPORTANCE = 0.7


class MemoryNotFoundError(LookupError):
    pass


class MemoryLimitError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class MemoryInput:
    kind: str
    content: str
    occurred_on: date | None
    people: list[str]
    emotion: str | None
    sensitivity: str


@dataclass(frozen=True, slots=True)
class MemoryPatch:
    """Sadece doldurulan alanlar değişir; ``None`` olan alanlara dokunulmaz."""

    kind: str | None = None
    content: str | None = None
    occurred_on: date | None = None
    clear_occurred_on: bool = False
    people: list[str] | None = None
    emotion: str | None = None
    clear_emotion: bool = False
    sensitivity: str | None = None


def _legacy_scope_for(sensitivity: str) -> str:
    # Hassas anılar Miras'a varsayılan olarak girmez; sahibi isterse tek tek ekler (§8.1).
    return "excluded" if sensitivity == "sensitive" else "included"


async def resolve_persona(db: AsyncSession, user: User, persona_id: uuid.UUID | None) -> Persona:
    """Persona verilmediyse EVA. Verildiyse kullanıcının görebileceği bir persona olmalı."""
    if persona_id is None:
        return await persona_service.get_default_eva(db)
    return await persona_service.get_persona_for_user(db, user, persona_id)


async def list_memories(
    db: AsyncSession,
    user: User,
    persona: Persona,
    *,
    kind: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Memory]:
    query = select(Memory).where(Memory.user_id == user.id, Memory.persona_id == persona.id)
    if kind is not None:
        query = query.where(Memory.kind == kind)
    query = query.order_by(Memory.created_at.desc(), Memory.id).limit(limit).offset(offset)
    return list((await db.execute(query)).scalars().all())


async def add_memory(
    db: AsyncSession, user: User, persona: Persona, data: MemoryInput, *, source: str
) -> Memory:
    count = await db.scalar(
        select(func.count())
        .select_from(Memory)
        .where(Memory.user_id == user.id, Memory.persona_id == persona.id)
    )
    if (count or 0) >= MAX_MEMORIES_PER_PERSONA:
        raise MemoryLimitError()
    memory = Memory(
        user_id=user.id,
        persona_id=persona.id,
        kind=data.kind,
        content=data.content,
        occurred_on=data.occurred_on,
        people=data.people,
        emotion=data.emotion,
        importance=USER_ADDED_IMPORTANCE if source == "user_added" else 0.5,
        source=source,
        sensitivity=data.sensitivity,
        legacy_scope=_legacy_scope_for(data.sensitivity),
    )
    db.add(memory)
    await db.commit()
    return memory


async def get_memory(db: AsyncSession, user: User, memory_id: uuid.UUID) -> Memory:
    """Sahiplik kontrolü sorgunun içinde: başkasının anısı "yok" sayılır (IDOR koruması)."""
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id)
    )
    memory = result.scalar_one_or_none()
    if memory is None:
        raise MemoryNotFoundError(str(memory_id))
    return memory


async def update_memory(
    db: AsyncSession, user: User, memory_id: uuid.UUID, patch: MemoryPatch
) -> Memory:
    memory = await get_memory(db, user, memory_id)
    if patch.kind is not None:
        memory.kind = patch.kind
    if patch.content is not None:
        memory.content = patch.content
    if patch.clear_occurred_on:
        memory.occurred_on = None
    elif patch.occurred_on is not None:
        memory.occurred_on = patch.occurred_on
    if patch.people is not None:
        memory.people = patch.people
    if patch.clear_emotion:
        memory.emotion = None
    elif patch.emotion is not None:
        memory.emotion = patch.emotion
    if patch.sensitivity is not None:
        memory.sensitivity = patch.sensitivity
        memory.legacy_scope = _legacy_scope_for(patch.sensitivity)
    await db.commit()
    return memory


async def forget_memory(db: AsyncSession, user: User, memory_id: uuid.UUID) -> None:
    """ "Bunu unut": anıyı gerçekten siler, çöp kutusu yok (§6.4).

    Sonraki adımlarda vektörü, önbelleği ve özetleri de buradan silinecek.
    """
    memory = await get_memory(db, user, memory_id)
    await db.execute(delete(Memory).where(Memory.id == memory.id, Memory.user_id == user.id))
    await db.commit()
