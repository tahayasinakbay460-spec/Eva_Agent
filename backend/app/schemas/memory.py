"""Anı uç noktalarının istek/cevap şekilleri. Kurallar burada kontrol edilir (girdi doğrulama)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

MemoryKind = Literal["episode", "fact"]
Sensitivity = Literal["normal", "sensitive"]
# Duygu etiketleri sabit bir listeden seçilir; ekranda Türkçe karşılıkları gösterilir.
Emotion = Literal[
    "happy", "sad", "excited", "calm", "angry", "anxious", "nostalgic", "proud", "grateful"
]


def _strip(value: str) -> str:
    return value.strip()


Content = Annotated[str, Field(min_length=1, max_length=2000), AfterValidator(_strip)]
Person = Annotated[str, Field(min_length=1, max_length=60), AfterValidator(_strip)]


class MemoryCreate(BaseModel):
    # Boş bırakılırsa anı EVA'ya kaydedilir.
    persona_id: uuid.UUID | None = None
    kind: MemoryKind = "episode"
    content: Content
    occurred_on: date | None = None
    people: list[Person] = Field(default_factory=list, max_length=20)
    emotion: Emotion | None = None
    sensitivity: Sensitivity = "normal"

    @field_validator("content")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("content is blank")
        return value

    @field_validator("occurred_on")
    @classmethod
    def _not_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("occurred_on is in the future")
        return value


class MemoryUpdate(BaseModel):
    """Gönderilmeyen alan değişmez. ``occurred_on`` / ``emotion`` için ``null`` göndermek siler."""

    kind: MemoryKind | None = None
    content: Content | None = None
    occurred_on: date | None = None
    people: list[Person] | None = Field(default=None, max_length=20)
    emotion: Emotion | None = None
    sensitivity: Sensitivity | None = None

    @field_validator("occurred_on")
    @classmethod
    def _not_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("occurred_on is in the future")
        return value


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    persona_id: uuid.UUID
    kind: MemoryKind
    content: str
    occurred_on: date | None
    people: list[str]
    emotion: Emotion | None
    importance: float
    source: Literal["auto", "user_added", "owner_legacy", "recipient_added"]
    sensitivity: Sensitivity
    created_at: datetime
    updated_at: datetime
