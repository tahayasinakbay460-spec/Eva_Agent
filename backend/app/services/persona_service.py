"""Persona lookup and seeding. Authorization lives here: a user sees system personas
(owner NULL) and their own."""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.persona import Persona
from app.models.user import User
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


async def get_default_eva(db: AsyncSession) -> Persona:
    result = await db.execute(select(Persona).where(Persona.slug == EVA_SLUG))
    persona = result.scalar_one_or_none()
    if persona is None:
        raise PersonaNotFoundError("default EVA persona is not seeded")
    return persona


def _visible_to(user: User):  # type: ignore[no-untyped-def]  # SQLAlchemy expression
    return or_(Persona.owner_id.is_(None), Persona.owner_id == user.id)


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
