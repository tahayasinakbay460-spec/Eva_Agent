import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.persona.types import ExampleDialog

SynthesisStatus = Literal["none", "pending", "ready", "failed", "not_enough_data"]


class LegacyPersonaOut(BaseModel):
    """Sahibin Miras personası. ``has_draft=False`` iken metin alanları henüz boştur."""

    id: uuid.UUID
    name: str
    status: SynthesisStatus
    has_draft: bool
    identity: str
    personality: str
    speaking_style: str
    example_dialogs: list[ExampleDialog]
    # Miras'a şu an dahil anı sayısı (kapsam ekranı /memories'te, ``legacy_scope`` ile).
    included_memories: int
    # Paylaşım için ikisi de zorunlu (sahibin kararı, ADR 0010).
    voice_ready: bool
    face_ready: bool
    # Alıcıların konuştuğu sürüm; hiç yayınlanmadıysa null.
    published_version: int | None


class LegacyPublishOut(BaseModel):
    version: int
    memories: int


class LegacyDraftIn(BaseModel):
    identity: str = Field(min_length=1, max_length=2000)
    personality: str = Field(min_length=1, max_length=4000)
    speaking_style: str = Field(min_length=1, max_length=4000)
    example_dialogs: list[ExampleDialog] = Field(default_factory=list, max_length=10)
