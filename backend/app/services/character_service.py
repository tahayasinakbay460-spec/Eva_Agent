"""Karakter Stüdyosu (Faz 4, ADR 0009): kullanıcının oluşturduğu karakterler.

Karakter, ``type="character"`` olan bir personadır; sohbet, görüşme ve hafıza onu EVA gibi
``persona_id`` ile kullanır. Herkese açık karakterleri herkes görür ve kullanır; yalnızca
sahibi düzenler ve siler. Yüz görseli sahibinin veri anahtarıyla şifreli saklanır ve fotoğraftan
çalışan avatar sağlayıcısına yalnızca görüşme sırasında verilir.
"""

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.persona import Persona
from app.models.user import User
from app.persona.types import PersonaDefinition
from app.providers.registry import ProviderRegistry
from app.schemas.character import CharacterIn, CharacterOut, Visibility
from app.services import audit, media_service
from app.services.biometric_service import (
    IMAGE_SIZE_LIMIT,
    IMAGE_TYPES,
    BiometricError,
    normalize_face_image,
    sniff_container,
)
from app.storage.encrypted import EncryptedStore

MAX_CHARACTERS_PER_USER = 50
FACE_SIZE_LIMIT = IMAGE_SIZE_LIMIT


class CharacterNotFoundError(LookupError):
    pass


class CharacterError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True, slots=True)
class CharacterFace:
    data: bytes
    media_type: str


def _definition(data: CharacterIn) -> PersonaDefinition:
    return PersonaDefinition(
        name=data.name,
        kind="character",
        source="user",
        identity=data.identity,
        personality=data.personality,
        speaking_style=data.speaking_style,
        example_dialogs=data.example_dialogs,
        time_awareness=data.time_awareness,
    )


def to_out(persona: Persona, user: User) -> CharacterOut:
    d = PersonaDefinition.model_validate(persona.definition)
    visibility: Visibility = "public" if persona.visibility == "public" else "private"
    return CharacterOut(
        id=persona.id,
        name=persona.name,
        identity=d.identity,
        personality=d.personality,
        speaking_style=d.speaking_style,
        example_dialogs=d.example_dialogs,
        time_awareness=d.time_awareness,
        visibility=visibility,
        voice_key=persona.voice_key,
        has_face=persona.face_blob_key is not None,
        is_mine=persona.owner_id == user.id,
    )


def _check_voice(settings: Settings, registry: ProviderRegistry, key: str | None) -> None:
    if key is not None and not media_service.voice_key_valid(settings, registry, key):
        raise CharacterError("unknown_voice", status=422)


async def create(
    db: AsyncSession,
    settings: Settings,
    registry: ProviderRegistry,
    user: User,
    data: CharacterIn,
) -> Persona:
    _check_voice(settings, registry, data.voice_key)
    count = await db.scalar(
        select(func.count())
        .select_from(Persona)
        .where(Persona.owner_id == user.id, Persona.type == "character")
    )
    if (count or 0) >= MAX_CHARACTERS_PER_USER:
        raise CharacterError("too_many_characters")
    persona = Persona(
        type="character",
        owner_id=user.id,
        name=data.name,
        definition=_definition(data).model_dump(),
        policy={},
        visibility=data.visibility,
        voice_key=data.voice_key,
    )
    db.add(persona)
    await db.commit()
    return persona


async def update(
    db: AsyncSession,
    settings: Settings,
    registry: ProviderRegistry,
    persona: Persona,
    data: CharacterIn,
) -> Persona:
    _check_voice(settings, registry, data.voice_key)
    persona.name = data.name
    persona.definition = _definition(data).model_dump()
    persona.visibility = data.visibility
    persona.voice_key = data.voice_key
    await db.commit()
    return persona


async def list_mine(db: AsyncSession, user: User) -> list[Persona]:
    result = await db.execute(
        select(Persona)
        .where(Persona.owner_id == user.id, Persona.type == "character")
        .order_by(Persona.created_at.desc())
    )
    return list(result.scalars().all())


async def list_public(db: AsyncSession, *, limit: int, offset: int) -> list[Persona]:
    result = await db.execute(
        select(Persona)
        .where(Persona.type == "character", Persona.visibility == "public")
        .order_by(Persona.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_visible(db: AsyncSession, user: User, character_id: uuid.UUID) -> Persona:
    """Sahibi ya da herkese açıksa herkes. Başkasının gizli karakteri "yok" sayılır (IDOR)."""
    persona = await db.get(Persona, character_id)
    if (
        persona is None
        or persona.type != "character"
        or (persona.owner_id != user.id and persona.visibility != "public")
    ):
        raise CharacterNotFoundError(str(character_id))
    return persona


async def get_owned(db: AsyncSession, user: User, character_id: uuid.UUID) -> Persona:
    persona = await db.get(Persona, character_id)
    if persona is None or persona.type != "character" or persona.owner_id != user.id:
        raise CharacterNotFoundError(str(character_id))
    return persona


async def delete(db: AsyncSession, store: EncryptedStore, persona: Persona) -> None:
    """Karakteri, yüz görselini ve (veritabanında zincirleme) ona ait sohbetleri siler."""
    if persona.face_blob_key:
        await store.delete("media", persona.face_blob_key)
    audit.record(
        db,
        action="character.deleted",
        target_type="persona",
        target_id=persona.id,
        user_id=persona.owner_id,
        actor_id=persona.owner_id,
    )
    await db.delete(persona)
    await db.commit()


async def set_face(
    db: AsyncSession,
    store: EncryptedStore,
    user: User,
    persona: Persona,
    *,
    media_type: str,
    data: bytes,
) -> None:
    """Yüz görselini doğrular, temizler (EXIF/konum silinir, PNG'ye çevrilir) ve şifreli kaydeder.
    Yenisi eskisinin yerine geçer."""
    if not data:
        raise CharacterError("file_empty", status=422)
    if len(data) > FACE_SIZE_LIMIT:
        raise CharacterError("file_too_large", status=413)
    if media_type not in IMAGE_TYPES:
        raise CharacterError("unsupported_media_type", status=415)
    if sniff_container(data) != media_type.split("/", 1)[1]:
        raise CharacterError("media_type_mismatch", status=415)
    try:
        png = await asyncio.to_thread(normalize_face_image, data)
    except BiometricError as exc:
        raise CharacterError(exc.code, status=exc.status) from exc

    old_key = persona.face_blob_key
    new_key = f"{user.id}/characters/{persona.id}/{uuid.uuid4()}"
    await store.put(db, user.id, "media", new_key, png)
    persona.face_blob_key = new_key
    persona.face_media_type = "image/png"
    audit.record(
        db,
        action="character.face_set",
        target_type="persona",
        target_id=persona.id,
        user_id=user.id,
        actor_id=user.id,
        meta={"rights_confirmed": True},
    )
    await db.commit()
    if old_key:
        await store.delete("media", old_key)


async def remove_face(db: AsyncSession, store: EncryptedStore, persona: Persona) -> None:
    old_key = persona.face_blob_key
    persona.face_blob_key = None
    persona.face_media_type = None
    audit.record(
        db,
        action="character.face_removed",
        target_type="persona",
        target_id=persona.id,
        user_id=persona.owner_id,
        actor_id=persona.owner_id,
    )
    await db.commit()
    if old_key:
        await store.delete("media", old_key)


async def face(db: AsyncSession, store: EncryptedStore, persona: Persona) -> CharacterFace | None:
    """Karakterin yüz görseli (sahibinin anahtarıyla çözülür)."""
    if persona.face_blob_key is None or persona.owner_id is None:
        return None
    data = await store.get(db, persona.owner_id, "media", persona.face_blob_key)
    return CharacterFace(data, persona.face_media_type or "image/png")
