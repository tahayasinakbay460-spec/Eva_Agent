"""Miras (CLAUDE.md §8, ADR 0010): sahibin Miras personası ve kişilik taslağı.

Her kullanıcının en fazla bir Miras personası vardır (``type="legacy"``, gizli). Taslağın durumu
``policy["synthesis"]`` alanında: ``none`` (hiç istenmedi) | ``pending`` (işçide) | ``ready`` |
``failed`` | ``not_enough_data`` (EVA henüz sahibini yeterince tanımıyor).
"""

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import utcnow
from app.legacy import synthesis
from app.models.legacy import LegacyAccess, PersonaVersion
from app.models.memory import Memory
from app.models.persona import Persona
from app.models.user import User
from app.persona.types import ExampleDialog, PersonaDefinition
from app.providers.registry import ProviderRegistry
from app.services import audit, biometric_service, persona_service
from app.worker import queue
from app.worker.jobs import LEGACY_SYNTHESIZE

SynthesisStatus = Literal["none", "pending", "ready", "failed", "not_enough_data"]

# Taslak çıkarmak için en az bu kadar malzeme olmalı (anı + sahibin mesajı).
MIN_SOURCE_ITEMS = 5

_PLACEHOLDER = "(henüz yazılmadı)"


@dataclass(frozen=True, slots=True)
class LegacyPersonaView:
    persona: Persona
    status: SynthesisStatus
    definition: PersonaDefinition
    has_draft: bool


def _status(persona: Persona) -> SynthesisStatus:
    value = (persona.policy or {}).get("synthesis", "none")
    allowed: tuple[SynthesisStatus, ...] = ("none", "pending", "ready", "failed", "not_enough_data")
    return value if value in allowed else "none"


def _set_status(persona: Persona, status: SynthesisStatus) -> None:
    # JSON sütununda değişikliğin görülmesi için sözlüğü yeniden ata.
    persona.policy = {**(persona.policy or {}), "synthesis": status}


async def get_persona(db: AsyncSession, user: User) -> Persona | None:
    return await db.scalar(
        select(Persona).where(Persona.owner_id == user.id, Persona.type == "legacy")
    )


async def get_or_create_persona(db: AsyncSession, user: User) -> Persona:
    persona = await get_persona(db, user)
    if persona is not None:
        return persona
    definition = PersonaDefinition(
        name=user.display_name,
        kind="legacy",
        source="user",
        identity=_PLACEHOLDER,
        personality=_PLACEHOLDER,
        speaking_style=_PLACEHOLDER,
        language=user.locale,
    )
    persona = Persona(
        type="legacy",
        owner_id=user.id,
        name=user.display_name,
        definition=definition.model_dump(),
        policy={"synthesis": "none", "has_draft": False},
        visibility="private",
    )
    db.add(persona)
    await db.commit()
    return persona


def view(persona: Persona) -> LegacyPersonaView:
    return LegacyPersonaView(
        persona=persona,
        status=_status(persona),
        definition=PersonaDefinition.model_validate(persona.definition),
        has_draft=bool((persona.policy or {}).get("has_draft")),
    )


async def request_synthesis(db: AsyncSession, user: User) -> Persona:
    """Taslağı işçiden ister. Aynı anda birden fazla istek tek işe iner."""
    persona = await get_or_create_persona(db, user)
    _set_status(persona, "pending")
    await queue.enqueue(
        db,
        LEGACY_SYNTHESIZE,
        {"persona_id": str(persona.id)},
        dedupe_key=f"legacy_synthesize:{persona.id}",
        max_attempts=3,
    )
    await db.commit()
    return persona


async def update_draft(
    db: AsyncSession,
    persona: Persona,
    *,
    identity: str,
    personality: str,
    speaking_style: str,
    example_dialogs: list[ExampleDialog],
) -> Persona:
    """Sahibin elle düzenlemesi; taslağın son hâli budur."""
    current = PersonaDefinition.model_validate(persona.definition)
    persona.definition = current.model_copy(
        update={
            "identity": identity,
            "personality": personality,
            "speaking_style": speaking_style,
            "example_dialogs": example_dialogs,
        }
    ).model_dump()
    persona.policy = {
        **(persona.policy or {}),
        "has_draft": True,
        "edited_at": utcnow().isoformat(),
    }
    await db.commit()
    return persona


async def run_synthesis(
    db: AsyncSession, registry: ProviderRegistry, persona_id: uuid.UUID
) -> SynthesisStatus:
    """İşçi tarafı: malzemeyi topla, taslağı yaz. Tekrar çalıştırılabilir."""
    persona = await db.get(Persona, persona_id)
    if persona is None or persona.type != "legacy" or persona.owner_id is None:
        return "failed"
    owner = await db.get(User, persona.owner_id)
    if owner is None:
        return "failed"
    eva = await persona_service.get_default_eva(db)
    memories = await synthesis.source_memories(db, owner.id, eva.id)
    messages = await synthesis.source_messages(db, owner.id, eva.id)
    if len(memories) + len(messages) < MIN_SOURCE_ITEMS:
        _set_status(persona, "not_enough_data")
        await db.commit()
        return "not_enough_data"

    draft = await synthesis.synthesize(
        registry, owner_name=owner.display_name, memories=memories, messages=messages
    )
    if draft is None:
        _set_status(persona, "failed")
        await db.commit()
        return "failed"

    current = PersonaDefinition.model_validate(persona.definition)
    persona.definition = current.model_copy(
        update={
            "identity": draft.identity,
            "personality": draft.personality,
            "speaking_style": draft.speaking_style,
            "example_dialogs": draft.example_dialogs,
        }
    ).model_dump()
    persona.policy = {**(persona.policy or {}), "synthesis": "ready", "has_draft": True}
    audit.record(
        db,
        action="legacy.draft_synthesized",
        target_type="persona",
        target_id=persona.id,
        user_id=owner.id,
        actor_id=None,
        meta={"memories": len(memories), "messages": len(messages)},
    )
    await db.commit()
    return "ready"


# --- önizleme ve yayın (Faz 5, adım 5) -------------------------------------------------


class LegacyNotReadyError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


# PersonaDefinition.canon_memories üst sınırı.
MAX_CANON_MEMORIES = 200


async def scope_memories(db: AsyncSession, owner_id: uuid.UUID) -> list[Memory]:
    eva = await persona_service.get_default_eva(db)
    return (await synthesis.source_memories(db, owner_id, eva.id))[:MAX_CANON_MEMORIES]


async def preview_definition(db: AsyncSession, persona: Persona) -> PersonaDefinition:
    """Sahibin şu anki taslağı + şu an Miras'a dahil anıları (kanon anılar olarak)."""
    if persona.owner_id is None:
        raise LegacyNotReadyError("legacy_not_found", status=404)
    canon = [m.content for m in await scope_memories(db, persona.owner_id)]
    current = PersonaDefinition.model_validate(persona.definition)
    return current.model_copy(update={"canon_memories": canon})


async def latest_version(db: AsyncSession, persona_id: uuid.UUID) -> PersonaVersion | None:
    return await db.scalar(
        select(PersonaVersion)
        .where(PersonaVersion.persona_id == persona_id)
        .order_by(PersonaVersion.version.desc())
        .limit(1)
    )


async def active_access(db: AsyncSession, user: User, persona: Persona) -> LegacyAccess | None:
    return await db.scalar(
        select(LegacyAccess).where(
            LegacyAccess.recipient_id == user.id,
            LegacyAccess.persona_id == persona.id,
            LegacyAccess.status == "active",
        )
    )


async def ensure_can_talk(db: AsyncSession, persona: Persona, user: User) -> None:
    """Miras personasıyla her konuşmadan (ve her turdan) önce.

    Sahip: taslak hazır olmalı (önizleme). Alıcı: aktif erişimi, yayınlanmış bir sürüm ve
    sahibin hâlâ onaylı ses ve yüzü olmalı; sahip erişimi kapatır ya da ses/yüz rızasını geri
    alırsa konuşma o an durur (ADR 0010)."""
    if persona.type != "legacy":
        return
    if persona.owner_id == user.id:
        if not view(persona).has_draft:
            raise LegacyNotReadyError("legacy_draft_missing")
        return
    if persona.owner_id is None or await active_access(db, user, persona) is None:
        raise LegacyNotReadyError("legacy_not_found", status=404)
    if await latest_version(db, persona.id) is None:
        raise LegacyNotReadyError("legacy_not_published")
    media = await media_readiness(db, persona.owner_id)
    if not (media.voice and media.face):
        raise LegacyNotReadyError("legacy_media_unavailable")


async def prompt_definition(db: AsyncSession, persona: Persona, user: User) -> PersonaDefinition:
    """Prompt'a girecek tanım. Sahip canlı taslakla (önizleme), alıcı yayınlanmış son sürümle
    konuşur; alıcının konuşmaları bu sürümü hiçbir zaman değiştirmez."""
    if persona.type != "legacy":
        return persona_service.definition_of(persona)
    await ensure_can_talk(db, persona, user)
    if persona.owner_id == user.id:
        return await preview_definition(db, persona)
    version = await latest_version(db, persona.id)
    if version is None:  # pragma: no cover - ensure_can_talk bunu yakalar
        raise LegacyNotReadyError("legacy_not_published")
    return PersonaDefinition.model_validate(version.definition)


def media_owner_id(persona: Persona, user: User) -> uuid.UUID:
    """ "Kendi sesi/yüzü" kimin? Miras'ta her zaman personanın sahibinin (ADR 0010)."""
    if persona.type == "legacy" and persona.owner_id is not None:
        return persona.owner_id
    return user.id


@dataclass(frozen=True, slots=True)
class MediaReadiness:
    voice: bool
    face: bool


async def media_readiness(db: AsyncSession, owner_id: uuid.UUID) -> MediaReadiness:
    """Sahibin onaylı, aktif klon sesi ve yüzü var mı? Miras paylaşımı için ikisi de zorunlu."""
    return MediaReadiness(
        voice=await biometric_service.active_asset(db, owner_id, "voice") is not None,
        face=await biometric_service.active_asset(db, owner_id, "face") is not None,
    )


async def publish(db: AsyncSession, persona: Persona, owner: User) -> PersonaVersion:
    """Alıcıların konuşacağı dondurulmuş sürümü yayınlar. Ses ve yüz zorunlu (sahibin kararı)."""
    if not view(persona).has_draft:
        raise LegacyNotReadyError("legacy_draft_missing")
    media = await media_readiness(db, owner.id)
    if not media.voice:
        raise LegacyNotReadyError("legacy_voice_missing")
    if not media.face:
        raise LegacyNotReadyError("legacy_face_missing")
    definition = await preview_definition(db, persona)
    previous = await latest_version(db, persona.id)
    version = PersonaVersion(
        persona_id=persona.id,
        version=(previous.version + 1) if previous else 1,
        definition=definition.model_dump(),
    )
    db.add(version)
    persona.policy = {**(persona.policy or {}), "published_version": version.version}
    audit.record(
        db,
        action="legacy.published",
        target_type="persona",
        target_id=persona.id,
        user_id=owner.id,
        actor_id=owner.id,
        meta={"version": version.version, "memories": len(definition.canon_memories)},
    )
    await db.commit()
    return version
