"""Persona bulma ve varsayılan personayı oluşturma. Yetki kontrolü burada: kullanıcı
sistem personalarını (sahibi NULL), kendi personalarını, herkese açık karakterleri ve anahtarla
erişimi açılmış Miras personalarını görür."""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legacy import LegacyAccess
from app.models.persona import Persona
from app.models.user import User
from app.persona.builtin import BUILTIN_CHARACTERS
from app.persona.eva import EVA_DEFINITION, EVA_SLUG
from app.persona.types import PersonaDefinition


class PersonaNotFoundError(LookupError):
    pass


async def ensure_default_eva(db: AsyncSession) -> Persona:
    result = await db.execute(select(Persona).where(Persona.slug == EVA_SLUG))
    persona = result.scalar_one_or_none()
    if persona is None:
        persona = Persona(
            type="eva",
            owner_id=None,
            slug=EVA_SLUG,
            name=EVA_DEFINITION.name,
            definition=EVA_DEFINITION.model_dump(),
            policy={},
        )
        db.add(persona)
        await db.commit()
    return persona


async def ensure_builtin_characters(db: AsyncSession) -> None:
    """Hazır karakterleri yazar ya da günceller (tanım kodda değiştiyse). Kimsenin malı değiller,
    herkese açıklar (§9.1)."""
    existing = {
        p.slug: p
        for p in (
            await db.scalars(select(Persona).where(Persona.slug.in_(list(BUILTIN_CHARACTERS))))
        ).all()
    }
    for slug, definition in BUILTIN_CHARACTERS.items():
        persona = existing.get(slug)
        if persona is None:
            db.add(
                Persona(
                    type="character",
                    owner_id=None,
                    slug=slug,
                    name=definition.name,
                    definition=definition.model_dump(),
                    policy={},
                    visibility="public",
                )
            )
        elif persona.definition != definition.model_dump() or persona.name != definition.name:
            persona.name = definition.name
            persona.definition = definition.model_dump()
    await db.commit()


async def get_default_eva(db: AsyncSession) -> Persona:
    result = await db.execute(select(Persona).where(Persona.slug == EVA_SLUG))
    persona = result.scalar_one_or_none()
    if persona is None:
        raise PersonaNotFoundError("default EVA persona is not seeded")
    return persona


def _visible_to(user: User):  # type: ignore[no-untyped-def]  # SQLAlchemy ifadesi
    return or_(
        Persona.owner_id.is_(None),
        Persona.owner_id == user.id,
        Persona.visibility == "public",
        Persona.id.in_(
            select(LegacyAccess.persona_id).where(
                LegacyAccess.recipient_id == user.id, LegacyAccess.status == "active"
            )
        ),
    )


async def get_persona_for_user(db: AsyncSession, user: User, persona_id: uuid.UUID) -> Persona:
    result = await db.execute(select(Persona).where(Persona.id == persona_id, _visible_to(user)))
    persona = result.scalar_one_or_none()
    if persona is None:
        raise PersonaNotFoundError(str(persona_id))
    return persona


async def list_personas_for_user(db: AsyncSession, user: User) -> list[Persona]:
    result = await db.execute(select(Persona).where(_visible_to(user)).order_by(Persona.created_at))
    return list(result.scalars().all())


def definition_of(persona: Persona) -> PersonaDefinition:
    return PersonaDefinition.model_validate(persona.definition)
