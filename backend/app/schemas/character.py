import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.persona.types import ExampleDialog, TimeAwareness

Visibility = Literal["private", "public"]
_VOICE_KEY = r"^[a-z0-9][a-z0-9_-]{0,31}$"


class CharacterIn(BaseModel):
    """Kullanıcının yazdığı karakter tanımı. Prompt'a güvenilmez veri olarak girer (§9.3)."""

    name: str = Field(min_length=1, max_length=80)
    identity: str = Field(min_length=1, max_length=2000)
    personality: str = Field(min_length=1, max_length=4000)
    speaking_style: str = Field(default="", max_length=4000)
    example_dialogs: list[ExampleDialog] = Field(default_factory=list, max_length=10)
    time_awareness: TimeAwareness = "aware_of_present"
    visibility: Visibility = "public"
    # Hazır seslerden biri (``GET /media/options``); boş = EVA'nın varsayılan sesi.
    voice_key: str | None = Field(default=None, pattern=_VOICE_KEY)


class CharacterOut(BaseModel):
    id: uuid.UUID
    name: str
    identity: str
    personality: str
    speaking_style: str
    example_dialogs: list[ExampleDialog]
    time_awareness: TimeAwareness
    visibility: Visibility
    voice_key: str | None
    has_face: bool
    is_mine: bool
