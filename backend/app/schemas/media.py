import uuid

from pydantic import BaseModel, Field

# Katalog anahtarı ya da "own" (kullanıcının kendi rızalı klonu / fotoğrafı).
MediaKey = str


class MediaOptionOut(BaseModel):
    key: str
    name: str
    has_image: bool = False


class MediaChoiceOut(BaseModel):
    voice: MediaKey
    avatar: MediaKey


class MediaOptionsOut(BaseModel):
    """EVA'nın hangi sesle ve hangi yüzle konuşabileceği. ``own_*`` = kullanıcının onaylanmış
    kendi sesi / fotoğrafı seçilebilir mi."""

    voices: list[MediaOptionOut]
    avatars: list[MediaOptionOut]
    own_voice: bool
    own_avatar: bool
    # "persona" seçilebilir mi: karakterin kendi yüz görseli (ADR 0009).
    persona_avatar: bool = False
    selected: MediaChoiceOut
    defaults: MediaChoiceOut


class MediaPreferenceIn(BaseModel):
    persona_id: uuid.UUID | None = None
    # Boş = personanın varsayılanı.
    voice: MediaKey | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")
    avatar: MediaKey | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")
